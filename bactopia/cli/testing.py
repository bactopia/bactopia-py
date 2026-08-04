"""Run nf-test suites for Bactopia components across all runtimes.

Every component is tested against a 4-cell matrix of container/environment
profiles:

    docker | conda | singularity_galaxy | singularity_pull

Docker owns the snapshot: it validates the committed ``main.nf.test.snap`` (or
generates one when none exists / ``--generate``). The remaining profiles then
validate their output against that same snapshot, so a mismatch surfaces
runtime drift (e.g. Conda resolving a newer tool version than the pinned
container). This tool only *executes* and *classifies* -- it never rewrites
tests.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import rich
import rich.console
import rich.table
import rich.traceback
import rich_click as click

import bactopia
from bactopia.cli.common import common_options, setup_logging
from bactopia.cli.download import build_env, needs_docker_pull
from bactopia.nf import parse_module_config
from bactopia.parsers.workflows import get_modules_by_workflow

BACTOPIA_CACHEDIR = os.getenv("BACTOPIA_CACHEDIR", f"{Path.home()}/.bactopia")

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-test": [
        {
            "name": "Required Options",
            "options": ["--bactopia-path", "--test-data"],
        },
        {
            "name": "Cleanup",
            "options": ["--cleanup", "--dry-run"],
        },
        {
            "name": "Test Selection",
            "options": [
                "--tier",
                "--include",
                "--exclude",
            ],
        },
        {
            "name": "Execution Options",
            "options": [
                "--cachedir",
                "--generate",
                "--force-rebuild",
                "--max-retry",
                "--jobs",
                "--fail-fast",
                "--timeout",
                "--times",
                "--timeout-multiplier",
            ],
        },
        {
            "name": "Output Options",
            "options": [
                "--outdir",
                "--json",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}

TIERS = ["modules", "subworkflows", "workflows"]

# The profile matrix, in display/execution order. Docker is always first
# because it establishes the snapshot the others validate against.
PROFILES = ["docker", "conda", "singularity_galaxy", "singularity_pull"]

# profile -> (nf-test --profile, extra environment variables)
PROFILE_NF = {
    "docker": ("docker", {}),
    "conda": ("conda", {}),
    "singularity_galaxy": ("singularity", {"NFT_SINGULARITY_PULL_DOCKER": "false"}),
    "singularity_pull": ("singularity", {"NFT_SINGULARITY_PULL_DOCKER": "true"}),
}

# Short column headers for the matrix table
PROFILE_HEADERS = {
    "docker": "docker",
    "conda": "conda",
    "singularity_galaxy": "singularity_galaxy",
    "singularity_pull": "singularity_pull",
}

# Status constants
PASSED = "passed"
NO_SNAPSHOT = "no_snapshot"
SNAPSHOT_MISMATCH = "snapshot_mismatch"
VERSION_DRIFT = "version_drift"
OUTPUT_DRIFT = "output_drift"
VERSION_OUTPUT_DRIFT = "version+output_drift"
SNAPSHOT_STALE = "snapshot_stale"
NON_REPRODUCIBLE = "non_reproducible"
SYNTAX_ERROR = "syntax_error"
TOOL_ERROR = "tool_error"
ASSERTION_FAILED = "assertion_failed"
SKIPPED = "skipped"
TIMEOUT = "timeout"
UNDECLARED_OUTPUTS = "undeclared_outputs"
BUILD_FAILED = "build_failed"
NO_GROUND_TRUTH = "no_ground_truth"
NA = "n/a"

# Statuses that do NOT count as a failure for the process exit code.
NON_FAILURE = {PASSED, NA, SKIPPED, NO_GROUND_TRUTH}

STATUS_STYLES = {
    PASSED: "green",
    NO_SNAPSHOT: "yellow",
    SNAPSHOT_MISMATCH: "red",
    VERSION_DRIFT: "yellow",
    OUTPUT_DRIFT: "red",
    VERSION_OUTPUT_DRIFT: "red",
    SNAPSHOT_STALE: "yellow bold",
    NON_REPRODUCIBLE: "red",
    SYNTAX_ERROR: "red",
    TOOL_ERROR: "red",
    ASSERTION_FAILED: "yellow",
    SKIPPED: "dim",
    TIMEOUT: "red bold",
    UNDECLARED_OUTPUTS: "yellow bold",
    BUILD_FAILED: "magenta bold",
    NO_GROUND_TRUTH: "dim yellow",
    NA: "dim",
}

# Order statuses are summarised in the per-profile summary line.
SUMMARY_ORDER = [
    PASSED,
    UNDECLARED_OUTPUTS,
    VERSION_DRIFT,
    OUTPUT_DRIFT,
    VERSION_OUTPUT_DRIFT,
    SNAPSHOT_MISMATCH,
    SNAPSHOT_STALE,
    TOOL_ERROR,
    ASSERTION_FAILED,
    NON_REPRODUCIBLE,
    TIMEOUT,
    SYNTAX_ERROR,
    NO_SNAPSHOT,
    BUILD_FAILED,
    NO_GROUND_TRUTH,
    NA,
    SKIPPED,
]

# Extract "<file>:md5,<hash>" tokens from a snapshot for drift classification.
_MD5_TOKEN = re.compile(r'([^\s"]+):md5,([0-9a-f]+)')


def preflight_checks(bactopia_path: Path, test_data: Path) -> tuple:
    """Verify prerequisites before running tests.

    Requires nf-test, Nextflow, and all three runtimes (Docker, Conda/Mamba,
    Singularity/Apptainer) since this tool exercises every profile in one run.

    Args:
        bactopia_path: Path to the Bactopia repository.
        test_data: Path to the bactopia-tests data directory.

    Returns:
        Tuple of (conda_method, singularity_exe) detected on PATH.
    """
    if not bactopia_path.exists():
        logging.error(f"Bactopia path does not exist: {bactopia_path}")
        sys.exit(1)
    if not (bactopia_path / "main.nf").exists():
        logging.error(
            f"No main.nf found in {bactopia_path}, is this a valid Bactopia repository?"
        )
        sys.exit(1)
    if not test_data.exists():
        logging.error(f"Test data path does not exist: {test_data}")
        sys.exit(1)

    # Test harness
    if shutil.which("nf-test") is None:
        logging.error("nf-test is not available on PATH")
        sys.exit(1)
    if shutil.which("nextflow") is None:
        logging.error("nextflow is not available on PATH")
        sys.exit(1)

    # Docker (daemon must be reachable)
    if shutil.which("docker") is None:
        logging.error("docker is not available on PATH")
        sys.exit(1)
    try:
        info = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=30
        )
        if info.returncode != 0:
            logging.error("docker is installed but the daemon is not responding")
            sys.exit(1)
    except Exception as e:
        logging.error(f"Could not query the Docker daemon: {e}")
        sys.exit(1)

    # Conda / Mamba
    conda_method = None
    for candidate in ("mamba", "conda"):
        if shutil.which(candidate):
            conda_method = candidate
            break
    if conda_method is None:
        logging.error("neither mamba nor conda is available on PATH")
        sys.exit(1)

    # Singularity / Apptainer
    singularity_exe = None
    for candidate in ("singularity", "apptainer"):
        if shutil.which(candidate):
            singularity_exe = candidate
            break
    if singularity_exe is None:
        logging.error("neither singularity nor apptainer is available on PATH")
        sys.exit(1)

    try:
        result = subprocess.run(
            ["nextflow", "-version"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if "version" in line.lower():
                logging.debug(f"Nextflow: {line.strip()}")
                break
    except Exception as e:
        logging.warning(f"Could not check Nextflow version: {e}")

    logging.debug(f"Runtimes: docker, {conda_method}, {singularity_exe}")
    return conda_method, singularity_exe


def discover_tests(
    bactopia_path: Path,
    tier: str,
    include: list | None = None,
    exclude: list | None = None,
) -> list:
    """Discover nf-test files in the Bactopia repository.

    Args:
        bactopia_path: Path to the Bactopia repository.
        tier: Which tier to scan (modules/subworkflows/workflows/all).
        include: Optional list of component names to include.
        exclude: Optional list of component names to exclude.

    Returns:
        List of dicts with component, tier, and test_dir keys.
    """
    tiers = TIERS if tier == "all" else [tier]
    tests = []

    for tier_name in tiers:
        # The root main.nf (bactopia workflow) lives at repo root with tests/
        if tier_name == "workflows":
            root_test = bactopia_path / "tests" / "main.nf.test"
            if root_test.exists():
                component_name = "bactopia"
                segments = [component_name]
                if (
                    not include
                    or any(inc == component_name or inc in segments for inc in include)
                ) and not (
                    exclude
                    and any(exc == component_name or exc in segments for exc in exclude)
                ):
                    tests.append(
                        {
                            "component": component_name,
                            "tier": tier_name,
                            "test_dir": root_test.parent,
                        }
                    )

        tier_dir = bactopia_path / tier_name
        if not tier_dir.exists():
            logging.warning(f"Tier directory not found: {tier_dir}")
            continue

        for test_file in sorted(tier_dir.rglob("main.nf.test")):
            if test_file.parent.name != "tests":
                continue

            # Extract component name: path between tier dir and tests/
            # e.g., modules/abricate/run/tests/main.nf.test -> abricate_run
            # Strip "bactopia-tools/" prefix for workflow tools
            component_dir = test_file.parent.parent
            rel_path = str(component_dir.relative_to(tier_dir))
            if rel_path.startswith("bactopia-tools/"):
                rel_path = rel_path[len("bactopia-tools/") :]
            component_name = rel_path.replace("/", "_")

            # Apply include/exclude filters
            # Match against full name or any underscore-separated segment
            # e.g., "sccmec" matches "sccmec" and "bactopia-tools_sccmec"
            #        but not "staphopiasccmec"
            segments = component_name.split("_")
            if include and not any(
                inc == component_name or inc in segments for inc in include
            ):
                continue
            if exclude and any(
                exc == component_name or exc in segments for exc in exclude
            ):
                continue

            tests.append(
                {
                    "component": component_name,
                    "tier": tier_name,
                    "test_dir": test_file.parent,
                }
            )

    return tests


def classify_result(stdout: str, stderr: str, exit_code: int) -> str:
    """Classify nf-test output into a status category.

    Args:
        stdout: Captured standard output from nf-test.
        stderr: Captured standard error from nf-test.
        exit_code: Process exit code.

    Returns:
        One of the status constants (PASSED, SNAPSHOT_MISMATCH, etc.).
    """
    if exit_code == 0:
        return PASSED

    combined = stdout + "\n" + stderr

    # Check for snapshot issues
    if "Snapshot" in combined and (
        "does not match" in combined or "Different Snapshot" in combined
    ):
        return SNAPSHOT_MISMATCH

    # Check for missing snapshot
    if (
        "no such snapshot" in combined.lower()
        or "snapshot not found" in combined.lower()
    ):
        return NO_SNAPSHOT

    # Check for syntax/compilation errors
    syntax_patterns = [
        "Compilation failed",
        "unable to resolve class",
        "Unexpected input",
        "BUG: parsing",
    ]
    for pattern in syntax_patterns:
        if pattern in combined:
            return SYNTAX_ERROR

    # Check for assertion failures (workflow completed, assertions didn't match)
    # Only classify as assertion failure when there's no Nextflow ERROR marker --
    # process failures also trigger nf-test assertion messages
    if (
        "assertion" in combined.lower()
        and "failed" in combined.lower()
        and "ERROR ~" not in combined
    ):
        return ASSERTION_FAILED

    # Default: tool error (process exited non-zero)
    return TOOL_ERROR


def _cleanup_test_dir(test_dir: Path):
    """Remove .nf-test/ directory and .nf-test.log from a test directory."""
    nf_test_dir = test_dir / ".nf-test"
    nf_test_log = test_dir / ".nf-test.log"
    if nf_test_dir.exists():
        shutil.rmtree(nf_test_dir, ignore_errors=True)
    if nf_test_log.exists():
        nf_test_log.unlink(missing_ok=True)


def cleanup_all(bactopia_path: Path, dry_run: bool = False):
    """Find and remove .nf-test/ directories and .nf-test.log files.

    Only scans the component tier roots (modules, subworkflows, workflows) and
    the root pipeline test dir (tests/). Artifacts elsewhere -- notably the
    relocated work dirs under logs/ -- are left untouched.

    Args:
        bactopia_path: Path to the Bactopia repository.
        dry_run: If True, only list what would be removed.
    """
    action = "Would remove" if dry_run else "Removing"
    count = 0
    roots = [bactopia_path / name for name in (*TIERS, "tests")]
    for root in roots:
        if not root.exists():
            continue
        for nf_test_dir in sorted(root.rglob(".nf-test")):
            if nf_test_dir.is_dir():
                logging.info(f"{action} {nf_test_dir}")
                if not dry_run:
                    shutil.rmtree(nf_test_dir, ignore_errors=True)
                count += 1
        for nf_test_log in sorted(root.rglob(".nf-test.log")):
            if nf_test_log.is_file():
                logging.info(f"{action} {nf_test_log}")
                if not dry_run:
                    nf_test_log.unlink(missing_ok=True)
                count += 1
    if dry_run:
        logging.info(f"Found {count} nf-test artifact(s) to clean up")
    else:
        logging.info(f"Cleaned up {count} nf-test artifact(s)")


def _run_with_timeout(cmd, cwd, env, timeout):
    """Run a command with timeout, killing the entire process group on timeout.

    Uses start_new_session so the child becomes its own process group leader.
    On timeout, sends SIGTERM to the group (nf-test + Nextflow + Java children),
    waits briefly, then SIGKILL if still alive.

    Args:
        cmd: Command list to execute.
        cwd: Working directory.
        env: Environment variables.
        timeout: Timeout in seconds, or None for no timeout.

    Returns:
        Tuple of (stdout, stderr, returncode, timed_out).
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return stdout, stderr, proc.returncode, False
    except subprocess.TimeoutExpired:
        # Kill the entire process group (nf-test + nextflow + java children)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        # Give processes a moment to clean up, then force kill
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        # Drain any remaining output
        stdout, stderr = proc.communicate()
        return stdout or "", stderr or "", proc.returncode or -1, True


# ---------------------------------------------------------------------------
# Build phase: resolve each test's environment closure and pre-build them
# serially so Nextflow never builds (and never hammers Galaxy) mid-run.
# ---------------------------------------------------------------------------


def _load_catalog(bactopia_path: Path) -> dict | None:
    """Load catalog.json from the Bactopia repository, or None if missing."""
    catalog_path = bactopia_path / "catalog.json"
    if not catalog_path.exists():
        return None
    try:
        with open(catalog_path) as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        logging.warning(f"Could not read {catalog_path}: {e}")
        return None


def _load_test_times(path: Path) -> dict:
    """Load per-component test-time baselines, or {} if unavailable.

    Returns the "components" sub-dict mapping "<tier>/<component>" to
    {"expected_seconds": float, ...}. Missing file or parse error -> {}.
    """
    try:
        with open(path) as fh:
            return json.load(fh).get("components", {})
    except (json.JSONDecodeError, OSError):
        return {}


LONG_JOB_SECONDS = 600


def _component_timeout(tier, component, baselines, multiplier, ceiling):
    """Per-component timeout in seconds, or None if disabled.

    ceiling is None when --timeout 0 (disabled) -> no timeout at all.
    No baseline entry / expected<=0 / empty baselines -> ceiling.
    Otherwise min(int(expected_seconds * multiplier), ceiling). No floor.
    """
    if ceiling is None:
        return None
    entry = baselines.get(f"{tier}/{component}")
    if not entry or entry.get("expected_seconds", 0) <= 0:
        return ceiling
    return min(int(entry["expected_seconds"] * multiplier), ceiling)


def _ordered_tests(tests, baselines):
    """Longest-first by baseline expected_seconds. Unknown (no entry) sorts
    first (inf). Empty baselines -> original order preserved (stable sort)."""
    if not baselines:
        return tests
    return sorted(
        tests,
        key=lambda t: baselines.get(f"{t['tier']}/{t['component']}", {}).get(
            "expected_seconds", float("inf")
        ),
        reverse=True,
    )


def _long_jobs(tests, baselines):
    """(expected_seconds, component) for tests whose baseline exceeds
    LONG_JOB_SECONDS, longest first."""
    out = [
        (baselines[f"{t['tier']}/{t['component']}"]["expected_seconds"], t["component"])
        for t in tests
        if baselines.get(f"{t['tier']}/{t['component']}", {}).get("expected_seconds", 0)
        > LONG_JOB_SECONDS
    ]
    return sorted(out, reverse=True)


def _modules_for(name: str, catalog: dict) -> list | None:
    """Resolve a component name to its module keys across all three tiers.

    A module resolves to itself; a workflow/subworkflow resolves to the full
    (recursive) set of modules it calls.
    """
    modules = catalog.get("modules", {})
    subworkflows = catalog.get("subworkflows", {})
    workflows = catalog.get("workflows", {})

    if name in modules:
        return [name]

    def walk(sw_name, collected, seen, visited):
        if sw_name in visited:
            return
        visited.add(sw_name)
        entry = subworkflows.get(sw_name)
        if entry is None:
            return
        calls = entry.get("calls", {})
        for mod in calls.get("modules", []):
            if mod not in seen:
                seen.add(mod)
                collected.append(mod)
        for nested in calls.get("subworkflows", []):
            walk(nested, collected, seen, visited)

    if name in workflows:
        return get_modules_by_workflow(name, catalog)

    if name in subworkflows:
        collected, seen, visited = [], set(), set()
        walk(name, collected, seen, visited)
        return collected

    return None


def _module_config_path(module_key: str, catalog: dict, bactopia_path: Path) -> Path:
    """Map a module key to its module.config path via the catalog."""
    meta = catalog.get("modules", {}).get(module_key)
    if meta and meta.get("path"):
        return bactopia_path / meta["path"] / "module.config"
    # Fallback: derive from the key (e.g. blast_tblastn -> modules/blast/tblastn)
    return bactopia_path / "modules" / module_key.replace("_", "/") / "module.config"


def _configs_for_test(test: dict, catalog: dict | None, bactopia_path: Path) -> list:
    """Return the deduplicated module.config paths a test depends on."""
    configs = []
    seen = set()

    def add(path: Path):
        if path.exists() and str(path) not in seen:
            seen.add(str(path))
            configs.append(path)

    if catalog:
        module_keys = _modules_for(test["component"], catalog)
        if module_keys is not None:
            for key in module_keys:
                add(_module_config_path(key, catalog, bactopia_path))
            if configs:
                return configs

    # Fallback for module-tier tests (or unknown components): the component's
    # own module.config sits beside its main.nf.
    add(Path(test["test_dir"]).parent / "module.config")
    return configs


def _env_artifacts(info: dict, conda_path: str, singularity_path: str) -> dict:
    """Expected on-disk artifact paths for a module's envs.

    Mirrors the exact naming used by ``bactopia.cli.download.build_env`` so we
    can verify a build succeeded without reimplementing it.
    """
    conda_env = (
        info.get("conda", "").replace("=", "-").replace(":", "-").replace(" ", "-")
    )
    conda_marker = Path(conda_path) / conda_env / "env-built.txt"

    galaxy_img = None
    if info.get("singularity"):
        gname = (
            info["singularity"]
            .replace("https://", "")
            .replace(":", "-")
            .replace("/", "-")
        )
        galaxy_img = Path(singularity_path) / f"{gname}.img"

    dname = info.get("docker", "").replace(":", "-").replace("/", "-")
    pull_img = Path(singularity_path) / f"{dname}.img"

    return {
        "conda_marker": conda_marker,
        "galaxy_img": galaxy_img,
        "pull_img": pull_img,
    }


def _image_ok(path: Path | None) -> bool:
    """A Singularity image counts as built only if it exists and is non-empty."""
    return bool(path) and path.exists() and path.stat().st_size > 0


def _needs_build(info: dict, art: dict, force: bool) -> bool:
    """True if any of a module's expected env artifacts is missing (or force)."""
    if force:
        return True
    if not art["conda_marker"].exists():
        return True
    if needs_docker_pull(info["docker"]):
        return True
    if not _image_ok(art["pull_img"]):
        return True
    if info.get("singularity") and not _image_ok(art["galaxy_img"]):
        return True
    return False


def run_build_phase(
    configs: list,
    conda_path: str,
    singularity_path: str,
    conda_method: str,
    singularity_exe: str,
    force: bool,
    max_retry: int,
) -> dict:
    """Serially build every environment/image the selected tests need.

    Args:
        configs: Ordered, deduplicated list of module.config paths.
        conda_path: Directory for Conda environments.
        singularity_path: Directory for Singularity images.
        conda_method: "mamba" or "conda".
        singularity_exe: "singularity" or "apptainer".
        force: Force a rebuild of existing environments/images.
        max_retry: Maximum build retries.

    Returns:
        Dict keyed by str(config) -> per-profile build success booleans.
    """
    Path(conda_path).mkdir(parents=True, exist_ok=True)
    Path(singularity_path).mkdir(parents=True, exist_ok=True)

    status = {}
    total = len(configs)
    built = 0
    for config in configs:
        info = parse_module_config(str(config), registry="quay.io")
        if not info or "docker" not in info:
            logging.warning(f"Could not parse envs from {config}, skipping build")
            status[str(config)] = {p: False for p in PROFILES}
            continue

        name = config.parent.name
        art = _env_artifacts(info, conda_path, singularity_path)
        if _needs_build(info, art, force):
            built += 1
            logging.info(f"Building environments for {name}")
        else:
            logging.debug(f"Environments for {name} already present")

        # Conda + Docker + Galaxy singularity (or docker-converted fallback
        # when no Galaxy URL exists).
        try:
            build_env(
                name,
                info,
                conda_path,
                conda_method,
                singularity_exe,
                singularity_path,
                "all",
                force=force,
                max_retry=max_retry,
                use_build=False,
            )
        except Exception as e:  # pragma: no cover - defensive
            logging.error(f"build_env(all) failed for {name}: {e}")

        # Docker-converted Singularity image for the singularity_pull cell.
        # Only needed when a Galaxy URL exists; otherwise the call above
        # already produced the docker-derived image.
        if info.get("singularity"):
            try:
                build_env(
                    name,
                    info,
                    conda_path,
                    conda_method,
                    singularity_exe,
                    singularity_path,
                    "singularity",
                    force=force,
                    max_retry=max_retry,
                    use_build=True,
                )
            except Exception as e:  # pragma: no cover - defensive
                logging.error(f"build_env(singularity_pull) failed for {name}: {e}")

        status[str(config)] = {
            "docker": not needs_docker_pull(info["docker"]),
            "conda": art["conda_marker"].exists(),
            "singularity_galaxy": _image_ok(art["galaxy_img"]),
            "singularity_pull": _image_ok(art["pull_img"]),
        }

    if built:
        logging.info(
            f"Build phase complete: built {built} of {total} environment set(s)"
        )
    else:
        logging.info(f"All {total} environment set(s) already present")
    return status


def _aggregate_build(test: dict, build_status: dict) -> dict:
    """Roll a test's per-config build results into per-profile booleans.

    A profile is buildable only if every module in the closure built for it.
    """
    configs = [str(c) for c in test.get("build_configs", [])]
    result = {}
    for profile in PROFILES:
        if not configs:
            result[profile] = False
            continue
        result[profile] = all(
            build_status.get(c, {}).get(profile, False) for c in configs
        )
    return result


# ---------------------------------------------------------------------------
# Test phase: run the profile matrix for a single component.
# ---------------------------------------------------------------------------


def _md5_buckets(snapshot_text: str) -> tuple:
    """Split a snapshot's md5 tokens into (versions, outputs) name->hash maps."""
    versions = {}
    outputs = {}
    for name, digest in _MD5_TOKEN.findall(snapshot_text):
        if "versions" in name.lower():
            versions[name] = digest
        else:
            outputs[name] = digest
    return versions, outputs


def _run_nf_test(test_dir: Path, nf_profile: str, env: dict, timeout, workdir: Path):
    """Run ``nf-test`` for one profile with a relocated work directory."""
    workdir.parent.mkdir(parents=True, exist_ok=True)
    run_env = env.copy()
    run_env["NFT_WORKDIR"] = str(workdir)
    cmd = ["nf-test", "test", "main.nf.test", "--profile", nf_profile]
    stdout, stderr, rc, timed_out = _run_with_timeout(cmd, test_dir, run_env, timeout)
    return " ".join(cmd), stdout, stderr, rc, timed_out


def _classify_drift(
    snap_file: Path,
    test_dir: Path,
    nf_profile: str,
    env: dict,
    timeout,
    workdir: Path,
) -> str:
    """Subclassify a snapshot mismatch as version and/or output drift.

    Regenerates the failing profile's snapshot to compare which md5 tokens
    moved, then restores the ground-truth snapshot. One extra nf-test run.
    """
    try:
        ground = snap_file.read_text()
    except OSError:
        return SNAPSHOT_MISMATCH

    try:
        snap_file.unlink()
        _run_nf_test(test_dir, nf_profile, env, timeout, workdir)
        if not snap_file.exists():
            return SNAPSHOT_MISMATCH
        actual = snap_file.read_text()
    except OSError:
        return SNAPSHOT_MISMATCH
    finally:
        # Always restore the docker-established ground truth.
        try:
            snap_file.write_text(ground)
        except OSError:
            logging.error(f"Failed to restore snapshot {snap_file}")

    v_exp, o_exp = _md5_buckets(ground)
    v_act, o_act = _md5_buckets(actual)
    v_diff = v_exp != v_act
    o_diff = o_exp != o_act
    if v_diff and o_diff:
        return VERSION_OUTPUT_DRIFT
    if v_diff:
        return VERSION_DRIFT
    if o_diff:
        return OUTPUT_DRIFT
    return SNAPSHOT_MISMATCH


def _file_md5(path: Path) -> str | None:
    """Raw-bytes md5 of a file; None if unreadable.

    Files are hashed verbatim -- never decompressed. Intrinsically
    non-deterministic types (see ``_INTRINSIC_NONCOMPARABLE``) are excluded from
    the byte comparison upstream rather than normalised here.
    """
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _as_paths(value) -> list:
    """Flatten an output_N.json field value into a list of path strings."""
    if isinstance(value, str):
        return [value] if "/" in value else []
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_as_paths(v))
        return out
    return []


def _output_records(cell_dir: Path) -> list:
    """Parse a cell's numeric nf-test ``output_<int>.json`` records.

    Returns a list of (process_name, scope, {field: [paths]}). Skips the meta
    map, the logs/nf_logs channels, and the ``results`` publishing aggregate
    (which duplicates the named field files). Named aggregate output files
    (output_*_outputs.json) are ignored to avoid double-counting.
    """
    records = []
    for meta in sorted(cell_dir.glob(".nf-test/tests/*/meta")):
        for jf in sorted(meta.glob("output_*.json")):
            if not jf.stem[len("output_") :].isdigit():
                continue
            try:
                data = json.loads(jf.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            for recs in data.values():
                if not isinstance(recs, list):
                    continue
                for rec in recs:
                    if not isinstance(rec, dict):
                        continue
                    meta_map = (
                        rec.get("meta") if isinstance(rec.get("meta"), dict) else {}
                    )
                    pname = meta_map.get("process_name") or "?"
                    scope = meta_map.get("scope") or ""
                    fields = {}
                    for field, val in rec.items():
                        if field in ("meta", "logs", "nf_logs", "results"):
                            continue
                        paths = _as_paths(val)
                        if paths:
                            fields[field] = paths
                    records.append((pname, scope, fields))
    return records


# File suffixes whose bytes vary run-to-run regardless of content (gzip embeds
# an mtime/OS byte), so a cross-profile md5 comparison is never meaningful.
_INTRINSIC_NONCOMPARABLE = (".gz",)


def _build_files_matrix(comp_dir: Path, ran: list, reference: str = "docker") -> list:
    """Cross-profile md5 matrix of declared outputs, keyed by process+field+name.

    Files are hashed verbatim and compared only across ``ran`` profiles (those
    that executed). Two distinct non-comparisons are kept separate:

    - ``comparable: false`` + ``verdict: "skip"`` -- intrinsically
      non-byte-comparable (e.g. ``.gz``); existence-check it, never md5.
    - ``comparable: true`` + ``verdict: "indeterminate"`` + ``incomplete: [...]``
      -- a ran profile didn't produce the file this run (transient; re-check
      after fixing that profile). A broken profile never reads as ``stable``.
    """
    per_profile = {}
    scopes = {}
    for profile in PROFILES:
        pmap = {}
        for pname, scope, fields in _output_records(comp_dir / profile):
            for field, paths in fields.items():
                for p in paths:
                    pth = Path(p)
                    key = (pname, field, pth.name)
                    pmap[key] = _file_md5(pth)
                    scopes.setdefault(key, scope)
        per_profile[profile] = pmap

    keys = set()
    for pmap in per_profile.values():
        keys.update(pmap.keys())

    ref_ran = reference in ran
    files = []
    for key in sorted(keys):
        pname, field, name = key
        md5s = {p: per_profile.get(p, {}).get(key) for p in PROFILES}
        incomplete = []
        divergent = []
        if name.endswith(_INTRINSIC_NONCOMPARABLE):
            comparable = False
            verdict = "skip"
        else:
            comparable = True
            ref = md5s.get(reference) if ref_ran else None
            incomplete = [p for p in ran if md5s.get(p) is None]
            present = [p for p in ran if md5s.get(p) is not None]
            divergent = [p for p in present if ref is not None and md5s[p] != ref]
            if ref is None or incomplete:
                verdict = "indeterminate"
            elif divergent:
                verdict = "divergent"
            else:
                verdict = "stable"
        entry = {
            "process": pname,
            "scope": scopes.get(key, ""),
            "field": field,
            "name": name,
            "comparable": comparable,
            "md5": md5s,
            "verdict": verdict,
            "divergent_profiles": divergent,
        }
        if incomplete:
            entry["incomplete"] = incomplete
        if "version" in field.lower() or name == "versions.yml":
            entry["kind"] = "versions"
            entry["tool_key"] = pname
        files.append(entry)
    return files


_CMD_BLOCK_END = re.compile(
    r"^\s{0,4}(Work dir:|Command exit status:|Command output:|Tip:|Nextflow stderr:|-- Check)"
)


def _command_error_block(text: str) -> str:
    """Extract the verbatim ``Command error:`` block (the tool's own stderr).

    This layer carries the real cause; the trailing nf-test/groovy exception is
    only the cascade symptom, identical for every crashed-before-output tool.
    """
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.strip().startswith("Command error:")),
        None,
    )
    if start is None:
        return ""
    out = []
    for ln in lines[start + 1 :]:
        if _CMD_BLOCK_END.match(ln):
            break
        out.append(ln)
    return "\n".join(out).strip()


def _reason_from_block(block: str) -> str | None:
    """Best one-line cause from a Command error block (Python or R)."""
    stripped = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not stripped:
        return None
    for ln in reversed(stripped):
        if re.match(r"^[A-Za-z_][\w.]*(Error|Exception):", ln) and not ln.startswith(
            "java."
        ):
            return ln[:200]
    for i, ln in enumerate(stripped):
        if ln.startswith("Error in "):
            return ln[:200]
        if ln.startswith("Error:"):
            for nxt in stripped[i + 1 :]:
                if nxt.startswith("!"):
                    return nxt.lstrip("! ").strip()[:200]
    for ln in stripped:
        if "defunct" in ln or "deprecated" in ln:
            return ln[:200]
    return stripped[-1][:200]


def _error_class(block: str) -> str:
    """Bucket a tool_error by signatures in its Command error block.

    ``env_dependency`` spans any language (Python or R): conda resolved a
    too-new dependency. Falls back to ``unknown`` so a consumer reads the block.
    """
    t = block.lower()
    if (
        "modulenotfounderror" in t
        or "no module named" in t
        or "pkg_resources" in t
        or "importerror" in t
        or "deprecate_stop" in t
        or "is now defunct" in t
        or "was deprecated" in t
        or "newshape" in t
        or re.search(r"attributeerror:[^\n]*has no attribute", t)
    ):
        return "env_dependency"
    if "are the same file" in t:
        return "staging_bug"
    if "permission denied" in t or "accessdenied" in t:
        return "fs_permission"
    if "traceback (most recent call last)" in t or re.search(
        r"^[a-z_][\w.]*(error|exception):", t, re.MULTILINE
    ):
        return "tool_crash"
    return "unknown"


def _suggested_edit(files: list, tier: str) -> dict:
    """Derive a test-edit hint from per-field verdicts (module/subworkflow).

    Subworkflow fields are scope-prefixed (``sample.``/``run.``) from the
    record's ``meta.scope``. Each ``versions.yml`` is handled independently: a
    stable one belongs in the snapshot, a divergent one becomes a ``contains``
    entry keyed by its own tool. A field is divergent if *any* of its files
    diverge, so it never lands in both ``snapshot`` and ``existence``.
    """
    subwf = tier == "subworkflows"

    def disp(f):
        return f"{f['scope']}.{f['field']}" if subwf and f.get("scope") else f["field"]

    field_verdict = {}
    is_versions = {}
    tool_of = {}
    scopes_seen = set()
    for f in files:
        df = disp(f)
        if subwf and f.get("scope"):
            scopes_seen.add(f["scope"])
        if f.get("kind") == "versions":
            is_versions[df] = True
            tool_of[df] = f.get("tool_key")
        # Precedence when a field has several files: divergent > skip > stable.
        rank = {"divergent": 3, "skip": 2, "stable": 1}
        v = f["verdict"]
        if rank.get(v, 0) > rank.get(field_verdict.get(df), 0):
            field_verdict[df] = v

    snapshot, existence, contains = [], [], []
    if subwf and scopes_seen:
        snapshot.extend(f"{sc}.meta" for sc in sorted(scopes_seen))
    else:
        snapshot.append("meta")

    for field, verdict in field_verdict.items():
        if is_versions.get(field):
            if verdict == "divergent":
                contains.append({"field": field, "value": tool_of.get(field)})
            else:
                snapshot.append(field)
        elif verdict in ("divergent", "skip"):
            existence.append(field)
        else:
            snapshot.append(field)

    edit = {
        "tier": "subworkflow" if subwf else "module",
        "snapshot": snapshot,
    }
    if existence:
        edit["existence"] = existence
    if contains:
        edit["contains"] = contains
    return edit


def _cell_reason(cell: dict, status: str, divergent_fields: list) -> str | None:
    """One-line triage string for a cell's status."""
    if status in (VERSION_DRIFT, OUTPUT_DRIFT, VERSION_OUTPUT_DRIFT):
        flds = sorted(set(divergent_fields))
        return f"{len(flds)} divergent field(s): {', '.join(flds) or '?'}"
    if status == SNAPSHOT_STALE:
        return "committed snapshot no longer matches the reference runtime -- run --generate"
    if status == SNAPSHOT_MISMATCH:
        return "snapshot did not match (no output divergence detected)"
    if status == ASSERTION_FAILED:
        return "assertions failed (no output divergence detected)"
    if status == TOOL_ERROR:
        blob = cell.get("_stdout", "") + "\n" + cell.get("_stderr", "")
        block = _command_error_block(blob)
        return _reason_from_block(block or blob)
    if status == UNDECLARED_OUTPUTS:
        return f"{len(cell.get('undeclared_outputs', []))} undeclared output(s)"
    if status == BUILD_FAILED:
        return "environment build failed during the build phase"
    if status == NO_GROUND_TRUTH:
        return "no docker snapshot to validate against"
    if status == NON_REPRODUCIBLE:
        return "docker snapshot not reproducible across two runs"
    if status == TIMEOUT:
        return "exceeded the per-run timeout"
    return None


def _finalize_component(
    comp_dir: Path, tier: str, cells: dict, generate: bool
) -> tuple:
    """Post-process a component's cells with the cross-profile files matrix.

    For module/subworkflow tiers the matrix is the primary drift signal:
    mismatch-like validation failures are reclassified to version/output drift
    by which fields actually diverged. When docker (the reference) itself fails
    to match on a ``generate=false`` run, the committed snapshot is stale.

    Returns (files, undeclared_union, suggested_edit, notes).
    """
    files, notes = [], []
    ran = [
        p
        for p in PROFILES
        if cells.get(p, {}).get("status")
        not in (NA, BUILD_FAILED, NO_GROUND_TRUTH, SKIPPED, TIMEOUT)
    ]
    if tier in ("modules", "subworkflows"):
        try:
            files = _build_files_matrix(comp_dir, ran)
        except Exception as e:  # pragma: no cover - defensive
            notes.append(f"files matrix failed: {e}")

    divergent_fields = {p: [] for p in PROFILES}
    versions_div = {p: False for p in PROFILES}
    output_div = {p: False for p in PROFILES}
    for f in files:
        if f["verdict"] != "divergent":
            continue
        for p in f["divergent_profiles"]:
            divergent_fields[p].append(f["field"])
            if f.get("kind") == "versions":
                versions_div[p] = True
            else:
                output_div[p] = True

    docker_status = cells.get("docker", {}).get("status")
    docker_stale = (not generate) and docker_status in (
        SNAPSHOT_MISMATCH,
        ASSERTION_FAILED,
    )
    if docker_stale and "docker" in cells:
        cells["docker"]["status"] = SNAPSHOT_STALE

    for profile, cell in cells.items():
        status = cell["status"]
        if profile != "docker" and status in (
            SNAPSHOT_MISMATCH,
            ASSERTION_FAILED,
            VERSION_DRIFT,
            OUTPUT_DRIFT,
            VERSION_OUTPUT_DRIFT,
        ):
            if docker_stale:
                status = SNAPSHOT_STALE
            elif versions_div[profile] and output_div[profile]:
                status = VERSION_OUTPUT_DRIFT
            elif versions_div[profile]:
                status = VERSION_DRIFT
            elif output_div[profile]:
                status = OUTPUT_DRIFT
        cell["status"] = status
        if status == TOOL_ERROR:
            blob = cell.get("_stdout", "") + "\n" + cell.get("_stderr", "")
            block = _command_error_block(blob)
            cell["error_class"] = _error_class(block or blob)
            cell["reason"] = _reason_from_block(block or blob) or "tool error"
        else:
            cell["reason"] = _cell_reason(
                cell, status, divergent_fields.get(profile, [])
            )

    union = sorted({o for c in cells.values() for o in c.get("undeclared_outputs", [])})
    actionable = any(f["verdict"] in ("stable", "divergent", "skip") for f in files)
    suggested = _suggested_edit(files, tier) if actionable else None
    return files, union, suggested, notes


def _scan_undeclared(test_dir: Path) -> list:
    """Return undeclared output files for a passing test (best effort)."""
    try:
        from bactopia.outputs import scan_test_outputs

        return scan_test_outputs(test_dir).get("undeclared_outputs", [])
    except Exception as e:  # pragma: no cover - defensive
        logging.debug(f"Output scan failed for {test_dir}: {e}")
        return []


def _write_cell_logs(cell_dir: Path, cell: dict):
    """Persist stdout/stderr/outputs for a single matrix cell."""
    cell_dir.mkdir(parents=True, exist_ok=True)
    (cell_dir / "stdout.txt").write_text(cell.pop("_stdout", ""))
    (cell_dir / "stderr.txt").write_text(cell.pop("_stderr", ""))
    undeclared = cell.get("undeclared_outputs", [])
    lines = ["# Undeclared outputs:"] + undeclared if undeclared else ["# OK"]
    (cell_dir / "outputs.txt").write_text("\n".join(lines) + "\n")


def run_component(
    test: dict,
    run_dir: str,
    conda_path: str,
    singularity_path: str,
    generate: bool,
    timeout: int,
    build_status: dict,
) -> dict:
    """Execute the full profile matrix for one component.

    Docker runs first and owns ``main.nf.test.snap``: it validates the
    committed snapshot, or generates one when none exists / ``--generate``.
    Conda and both Singularity variants then validate against that snapshot.
    A non-docker run that would *create* a missing snapshot is reverted and
    reported as ``no_ground_truth`` so it never pollutes the ground truth.

    Args:
        test: Discovered test dict (component, tier, test_dir, galaxy).
        run_dir: Timestamped run output directory.
        conda_path: Conda cache directory.
        singularity_path: Singularity cache directory.
        generate: Force docker snapshot regeneration.
        timeout: Per-run timeout in seconds (None = none).
        build_status: Per-config build results.

    Returns:
        Dict with component, tier, galaxy, and a cells map keyed by profile.
    """
    test_dir = Path(test["test_dir"])
    component = test["component"]
    tier = test["tier"]
    galaxy_available = test.get("galaxy", False)
    snap_file = test_dir / "main.nf.test.snap"
    effective_timeout = timeout if timeout else None
    build_ok = _aggregate_build(test, build_status)

    base_env = os.environ.copy()
    base_env["BACTOPIA_TESTS"] = str(test["test_data"])
    base_env["NXF_CONDA_CACHEDIR"] = conda_path
    base_env["NXF_SINGULARITY_CACHEDIR"] = singularity_path

    comp_dir = Path(run_dir) / tier / component

    def workdir(profile, suffix=".nf-test"):
        return comp_dir / profile / suffix

    def timeout_cell(profile, stdout, stderr):
        return {
            "status": TIMEOUT,
            "duration": 0.0,
            "cmd": f"nf-test ... --profile {PROFILE_NF[profile][0]}",
            "cwd": str(test_dir),
            "_stdout": stdout,
            "_stderr": stderr + f"\n[timed out after {timeout}s]",
        }

    cells = {}

    # --- docker (ground truth) ------------------------------------------
    nf_profile, extra_env = PROFILE_NF["docker"]
    env = {**base_env, **extra_env}
    if not build_ok["docker"]:
        cells["docker"] = {
            "status": BUILD_FAILED,
            "duration": 0.0,
            "_stdout": "",
            "_stderr": "environment build failed during the build phase",
        }
    else:
        regen = generate or not snap_file.exists()
        if generate and snap_file.exists():
            snap_file.unlink()
        start = time.monotonic()
        cmd, stdout, stderr, rc, timed_out = _run_nf_test(
            test_dir, nf_profile, env, effective_timeout, workdir("docker")
        )
        if timed_out:
            cells["docker"] = timeout_cell("docker", stdout, stderr)
        else:
            status = classify_result(stdout, stderr, rc)
            # Reproducibility check when we (re)generated the snapshot.
            if regen and status == PASSED:
                cmd2, stdout2, stderr2, rc2, timed_out2 = _run_nf_test(
                    test_dir, nf_profile, env, effective_timeout, workdir("docker")
                )
                if timed_out2:
                    cells["docker"] = timeout_cell("docker", stdout2, stderr2)
                    status = None
                elif rc2 != 0:
                    status = NON_REPRODUCIBLE
                    stdout, stderr = stdout2, stderr2
            if status is not None:
                undeclared = []
                if status == PASSED:
                    undeclared = _scan_undeclared(test_dir)
                    if undeclared:
                        status = UNDECLARED_OUTPUTS
                elif status == SNAPSHOT_MISMATCH and tier == "workflows":
                    status = _classify_drift(
                        snap_file,
                        test_dir,
                        nf_profile,
                        env,
                        effective_timeout,
                        workdir("docker", ".nf-test-drift"),
                    )
                cells["docker"] = {
                    "status": status,
                    "duration": round(time.monotonic() - start, 1),
                    "cmd": cmd,
                    "cwd": str(test_dir),
                    "undeclared_outputs": undeclared,
                    "_stdout": stdout,
                    "_stderr": stderr,
                }

    ground_truth = snap_file.exists()

    # --- validation profiles --------------------------------------------
    for profile in ("conda", "singularity_galaxy", "singularity_pull"):
        nf_profile, extra_env = PROFILE_NF[profile]
        env = {**base_env, **extra_env}

        if profile == "singularity_galaxy" and not galaxy_available:
            cells[profile] = {
                "status": NA,
                "duration": 0.0,
                "_stdout": "",
                "_stderr": "no Galaxy image available (module ships docker only)",
            }
            continue
        if not build_ok[profile]:
            cells[profile] = {
                "status": BUILD_FAILED,
                "duration": 0.0,
                "_stdout": "",
                "_stderr": "environment build failed during the build phase",
            }
            continue

        existed = snap_file.exists()
        start = time.monotonic()
        cmd, stdout, stderr, rc, timed_out = _run_nf_test(
            test_dir, nf_profile, env, effective_timeout, workdir(profile)
        )
        if timed_out:
            cells[profile] = timeout_cell(profile, stdout, stderr)
            continue

        status = classify_result(stdout, stderr, rc)

        # Guard: a non-docker profile must never establish ground truth. If it
        # created a previously-absent snapshot, revert it and report why.
        if not existed and snap_file.exists():
            snap_file.unlink(missing_ok=True)
            status = NO_GROUND_TRUTH
        elif status == SNAPSHOT_MISMATCH and ground_truth and tier == "workflows":
            status = _classify_drift(
                snap_file,
                test_dir,
                nf_profile,
                env,
                effective_timeout,
                workdir(profile, ".nf-test-drift"),
            )

        undeclared = []
        if status == PASSED:
            undeclared = _scan_undeclared(test_dir)
            if undeclared:
                status = UNDECLARED_OUTPUTS

        cells[profile] = {
            "status": status,
            "duration": round(time.monotonic() - start, 1),
            "cmd": cmd,
            "cwd": str(test_dir),
            "undeclared_outputs": undeclared,
            "_stdout": stdout,
            "_stderr": stderr,
        }

    # Cross-profile analysis: reclassify drift, compute reasons, undeclared union.
    files, undeclared_union, suggested_edit, notes = _finalize_component(
        comp_dir, tier, cells, generate
    )

    # Persist per-cell logs and strip heavy fields from the returned dict.
    for profile, cell in cells.items():
        _write_cell_logs(comp_dir / profile, cell)

    result = {
        "component": component,
        "tier": tier,
        "galaxy": galaxy_available,
        "cells": cells,
        "files": files,
        "undeclared_outputs_union": undeclared_union,
        "notes": notes,
    }
    if suggested_edit:
        result["suggested_edit"] = suggested_edit
    return result


def create_log_dir(logs_dir: Path) -> Path:
    """Create a timestamped log directory for the current run.

    Args:
        logs_dir: Base logs directory.

    Returns:
        Path to the created run directory.
    """
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = logs_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _profile_counts(results: list) -> dict:
    """Per-profile status counts across all components."""
    counts = {p: {} for p in PROFILES}
    for r in results:
        for profile, cell in r["cells"].items():
            status = cell["status"]
            counts[profile][status] = counts[profile].get(status, 0) + 1
    return counts


def _summary_rows(results: list) -> list:
    """Build the serializable per-component rows for summary/JSON output."""
    rows = []
    for r in results:
        row = {
            "component": r["component"],
            "tier": r["tier"],
            "galaxy": r["galaxy"],
            "cells": {
                profile: {
                    "status": cell["status"],
                    "duration": cell["duration"],
                    "reason": cell.get("reason"),
                    "undeclared_outputs": cell.get("undeclared_outputs", []),
                    **(
                        {"error_class": cell["error_class"]}
                        if cell.get("error_class")
                        else {}
                    ),
                }
                for profile, cell in r["cells"].items()
            },
            "undeclared_outputs_union": r.get("undeclared_outputs_union", []),
            "files": r.get("files", []),
        }
        if r.get("suggested_edit"):
            row["suggested_edit"] = r["suggested_edit"]
        if r.get("notes"):
            row["notes"] = r["notes"]
        rows.append(row)
    return rows


def save_summary(run_dir: Path, results: list, params: dict):
    """Write summary JSON and TSV (the matrix) to the log directory."""
    counts = _profile_counts(results)
    summary_rows = _summary_rows(results)

    summary_json = {
        "profiles": PROFILES,
        "reference_profile": "docker",
        "summary": counts,
        "params": params,
        "results": summary_rows,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary_json, indent=2))

    header = ["component", "tier"] + PROFILES
    tsv_lines = [f"# generate={params.get('generate', False)}", "\t".join(header)]
    for row in summary_rows:
        cols = [row["component"], row["tier"]]
        cols += [row["cells"].get(p, {}).get("status", NA) for p in PROFILES]
        tsv_lines.append("\t".join(cols))
    (run_dir / "summary.tsv").write_text("\n".join(tsv_lines) + "\n")

    logging.info(f"Logs saved to {run_dir}")


def print_results(
    console: rich.console.Console, results: list, use_json: bool, tier: str = "all"
):
    """Display the profile matrix as a Rich table or JSON."""
    counts = _profile_counts(results)

    if use_json:
        output = {
            "profiles": PROFILES,
            "reference_profile": "docker",
            "summary": counts,
            "results": _summary_rows(results),
        }
        print(json.dumps(output, indent=2))
        return

    table = rich.table.Table(title="Bactopia Test Matrix")
    table.add_column("Component", style="bold")
    table.add_column("Tier")
    for profile in PROFILES:
        table.add_column(PROFILE_HEADERS[profile])

    for r in results:
        cols = [r["component"], r["tier"]]
        for profile in PROFILES:
            cell = r["cells"].get(profile, {})
            status = cell.get("status", NA)
            style = STATUS_STYLES.get(status, "")
            cols.append(f"[{style}]{status}[/{style}]")
        table.add_row(*cols)

    console.print(table)
    console.print()

    # Per-profile summary lines
    label_w = max(len(h) for h in PROFILE_HEADERS.values())
    for profile in PROFILES:
        parts = []
        for status_key in SUMMARY_ORDER:
            count = counts[profile].get(status_key, 0)
            if count > 0:
                style = STATUS_STYLES.get(status_key, "")
                parts.append(f"[{style}]{count} {status_key}[/{style}]")
        if parts:
            console.print(f"{PROFILE_HEADERS[profile]:>{label_w}}: {', '.join(parts)}")

    # Celebrate only when every cell across every profile is green (or N/A).
    all_passed = all(
        cell["status"] in (PASSED, NA) for r in results for cell in r["cells"].values()
    )
    if all_passed and len(results) > 0:
        console.print()
        console.print(
            f"[bold green]🎉🎉🎉 All {len(results)} components passed across every profile! 🎉🎉🎉[/bold green]"
        )


def _run_failed(results: list) -> bool:
    """True if any matrix cell holds a failure status."""
    return any(
        cell["status"] not in NON_FAILURE
        for r in results
        for cell in r["cells"].values()
    )


@click.command()
@common_options
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where the Bactopia repository is stored",
)
@click.option(
    "--test-data",
    default=None,
    help="Directory containing bactopia-tests data (sets BACTOPIA_TESTS env). Required unless --cleanup",
)
@click.option(
    "--tier",
    default="all",
    type=click.Choice(["modules", "subworkflows", "workflows", "all"]),
    help="Which component tier to test",
)
@click.option(
    "--include",
    default=None,
    help="Comma-separated list of component names to include",
)
@click.option(
    "--exclude",
    default=None,
    help="Comma-separated list of component names to exclude",
)
@click.option(
    "--cachedir",
    default=BACTOPIA_CACHEDIR,
    show_default=True,
    help="Cache directory holding conda/ and singularity/ subdirectories for pre-built environments",
)
@click.option(
    "--generate",
    is_flag=True,
    help="Force regeneration of the docker snapshot (otherwise the committed snapshot is validated; a missing snapshot is always generated)",
)
@click.option(
    "--force-rebuild",
    is_flag=True,
    help="Force a rebuild of existing Conda environments and Singularity images",
)
@click.option(
    "--max-retry",
    default=3,
    type=int,
    show_default=True,
    help="Maximum build retries per environment during the build phase",
)
@click.option(
    "--jobs",
    default=32,
    type=int,
    show_default=True,
    help="Number of components tested in parallel (profiles within a component run sequentially). Tune to the test host; the default 32 suits a large box",
)
@click.option(
    "--fail-fast",
    is_flag=True,
    help="Stop on the first component with any failing profile instead of continuing",
)
@click.option(
    "--timeout",
    default=90,
    type=int,
    show_default=True,
    help="Per-run timeout in minutes. Each nf-test subprocess is killed after this duration. Set to 0 to disable",
)
@click.option(
    "--times",
    "times",
    default=None,
    help="Path to test-times baseline JSON (expected_seconds per component). "
    "Default: {bactopia-path}/conf/test-times.json. Enables per-component "
    "timeouts and longest-first ordering.",
)
@click.option(
    "-tm",
    "--timeout-multiplier",
    "timeout_multiplier",
    default=4,
    type=click.IntRange(min=1),
    show_default=True,
    help="Per-component timeout = min(expected_seconds * this, --timeout). "
    "Only applied when a test-times file is available.",
)
@click.option(
    "--cleanup",
    is_flag=True,
    help="Remove .nf-test/ temp files under modules/subworkflows/workflows/tests, then exit (no tests run)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="With --cleanup, list what would be removed without deleting",
)
@click.option(
    "--outdir",
    default=".",
    show_default=True,
    help="Directory to write the logs/ folder into",
)
@click.option("--json", "use_json", is_flag=True, help="Output results as JSON")
def testing(
    bactopia_path,
    test_data,
    tier,
    include,
    exclude,
    cachedir,
    generate,
    force_rebuild,
    max_retry,
    jobs,
    fail_fast,
    timeout,
    times,
    timeout_multiplier,
    cleanup,
    dry_run,
    outdir,
    use_json,
    verbose,
    silent,
):
    """Run the nf-test profile matrix for Bactopia components.

    Each component is tested against docker, conda, singularity_galaxy, and
    singularity_pull. Docker validates (or generates) the snapshot; the other
    profiles validate against it so runtime drift is surfaced without rewriting
    any tests. Environments are pre-built serially before the parallel test
    phase. Per-profile logs and work directories are kept under logs/.
    """
    setup_logging(verbose, silent)

    bp = Path(bactopia_path).absolute().resolve()

    # Cleanup mode: remove .nf-test artifacts under tier roots + tests/, then exit
    if cleanup:
        if not bp.exists():
            logging.error(f"Bactopia path does not exist: {bp}")
            sys.exit(1)
        cleanup_all(bp, dry_run=dry_run)
        return

    if not test_data:
        logging.error("--test-data is required when running tests.")
        sys.exit(1)
    td = Path(test_data).absolute().resolve()

    conda_method, singularity_exe = preflight_checks(bp, td)

    conda_path = str((Path(cachedir).absolute() / "conda").resolve())
    singularity_path = str((Path(cachedir).absolute() / "singularity").resolve())

    include_list = [x.strip() for x in include.split(",")] if include else None
    exclude_list = [x.strip() for x in exclude.split(",")] if exclude else None

    tests = discover_tests(bp, tier, include_list, exclude_list)
    if not tests:
        logging.error("No tests found matching the given criteria.")
        sys.exit(1)
    logging.info(f"Discovered {len(tests)} component(s) to test")

    # Annotate each test with its environment closure + Galaxy availability.
    catalog = _load_catalog(bp)
    if catalog is None:
        logging.warning(
            "catalog.json not found; falling back to per-module.config resolution"
        )

    times_path = Path(times).absolute() if times else bp / "conf" / "test-times.json"
    baselines = _load_test_times(times_path)
    if baselines:
        logging.info(
            f"Found test-times ({len(baselines)} baselines) at {times_path}; "
            f"running jobs longest-to-shortest with per-component timeouts"
        )
    else:
        logging.warning(
            f"test-times not found at {times_path}; "
            f"using flat --timeout and discovery order"
        )
    all_configs = []
    seen_configs = set()
    for t in tests:
        t["test_data"] = str(td)
        configs = _configs_for_test(t, catalog, bp)
        t["build_configs"] = configs
        galaxy = True
        for c in configs:
            info = parse_module_config(str(c), registry="quay.io")
            if not info.get("singularity"):
                galaxy = False
                break
        t["galaxy"] = bool(configs) and galaxy
        for c in configs:
            if str(c) not in seen_configs:
                seen_configs.add(str(c))
                all_configs.append(c)

    # Dispatch longest/unknown-first and warn when long jobs starve --jobs.
    tests = _ordered_tests(tests, baselines)
    if baselines:
        long = _long_jobs(tests, baselines)
        if long and len(long) > jobs:
            logging.warning(
                f"{len(long)} component(s) exceed {LONG_JOB_SECONDS // 60} min "
                f"(longest {long[0][1]} ~{long[0][0] / 60:.0f} min); --jobs={jobs} "
                f"is below that, so long jobs run back-to-back and dominate wall "
                f"time. Raise --jobs to overlap them."
            )

    # Build phase (serial): pre-build every environment/image the tests need.
    logging.info(
        f"Checking {len(all_configs)} environment set(s) "
        f"[conda={conda_method}, singularity={singularity_exe}]"
    )
    build_status = run_build_phase(
        all_configs,
        conda_path,
        singularity_path,
        conda_method,
        singularity_exe,
        force_rebuild,
        max_retry,
    )

    # Log directory
    logs_dir = Path(outdir).absolute().resolve() / "logs" / "run-tests"
    run_dir = create_log_dir(logs_dir)

    # Test phase (parallel across components)
    results = []
    failed = False
    ceiling_seconds = timeout * 60 if timeout > 0 else None

    with ProcessPoolExecutor(max_workers=jobs) as executor:
        future_to_test = {}
        for t in tests:
            comp_timeout = _component_timeout(
                t["tier"],
                t["component"],
                baselines,
                timeout_multiplier,
                ceiling_seconds,
            )
            future = executor.submit(
                run_component,
                t,
                str(run_dir),
                conda_path,
                singularity_path,
                generate,
                comp_timeout,
                build_status,
            )
            future_to_test[future] = t

        total = len(future_to_test)
        completed = 0
        for future in as_completed(future_to_test):
            t = future_to_test[future]
            try:
                result = future.result()
            except Exception as e:
                logging.error(f"Component {t['component']} raised an exception: {e}")
                result = {
                    "component": t["component"],
                    "tier": t["tier"],
                    "galaxy": t.get("galaxy", False),
                    "cells": {
                        p: {"status": TOOL_ERROR, "duration": 0.0} for p in PROFILES
                    },
                }
            results.append(result)
            completed += 1

            statuses = " ".join(
                f"{PROFILE_HEADERS[p]}={result['cells'].get(p, {}).get('status', NA)}"
                for p in PROFILES
            )
            logging.info(
                f"({completed} of {total}) {result['component']} ({result['tier']}): {statuses}"
            )

            if fail_fast and any(
                c["status"] not in NON_FAILURE for c in result["cells"].values()
            ):
                failed = True
                executor.shutdown(wait=False, cancel_futures=True)
                break

    results.sort(key=lambda r: (r["tier"], r["component"]))

    params = {
        "bactopia_path": str(bp),
        "test_data": str(td),
        "tier": tier,
        "include": include,
        "exclude": exclude,
        "cachedir": str(Path(cachedir).absolute()),
        "conda_path": conda_path,
        "singularity_path": singularity_path,
        "generate": generate,
        "force_rebuild": force_rebuild,
        "max_retry": max_retry,
        "jobs": jobs,
        "fail_fast": fail_fast,
        "timeout": timeout,
        "times": str(times_path),
        "timeout_multiplier": timeout_multiplier,
        "cleanup": cleanup,
        "dry_run": dry_run,
        "outdir": str(Path(outdir).absolute()),
        "json": use_json,
        "verbose": verbose,
        "silent": silent,
    }
    save_summary(run_dir, results, params)

    console = rich.console.Console()
    print_results(console, results, use_json, tier=tier)

    if failed or _run_failed(results):
        sys.exit(1)


def main():
    if len(sys.argv) == 1:
        testing.main(["--help"])
    else:
        testing()


if __name__ == "__main__":
    main()
