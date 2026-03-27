"""Run nf-test suites for Bactopia components."""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from pathlib import Path

import rich
import rich.console
import rich.table
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia

BACTOPIA_CACHEDIR = os.getenv("BACTOPIA_CACHEDIR", f"{Path.home()}/.bactopia")
CONDA_CACHEDIR = os.getenv("NXF_CONDA_CACHEDIR", f"{BACTOPIA_CACHEDIR}/conda")
SINGULARITY_CACHEDIR = os.getenv(
    "NXF_SINGULARITY_CACHEDIR", f"{BACTOPIA_CACHEDIR}/singularity"
)

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
                "--profile",
                "--condadir",
                "--singularity_cache",
                "--generate",
                "--jobs",
                "--fail-fast",
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

# Status constants
PASSED = "passed"
NO_SNAPSHOT = "no_snapshot"
SNAPSHOT_MISMATCH = "snapshot_mismatch"
NON_REPRODUCIBLE = "non_reproducible"
SYNTAX_ERROR = "syntax_error"
TOOL_ERROR = "tool_error"
ASSERTION_FAILED = "assertion_failed"
SKIPPED = "skipped"

STATUS_STYLES = {
    PASSED: "green",
    NO_SNAPSHOT: "yellow",
    SNAPSHOT_MISMATCH: "red",
    NON_REPRODUCIBLE: "red",
    SYNTAX_ERROR: "red",
    TOOL_ERROR: "red",
    ASSERTION_FAILED: "yellow",
    SKIPPED: "dim",
}


def preflight_checks(bactopia_path: Path, test_data: Path):
    """Verify prerequisites before running tests.

    Args:
        bactopia_path: Path to the Bactopia repository.
        test_data: Path to the bactopia-tests data directory.
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

    # Check nf-test is available
    if shutil.which("nf-test") is None:
        logging.error("nf-test is not available on PATH")
        sys.exit(1)

    # Check minimum Nextflow version
    if shutil.which("nextflow") is None:
        logging.error("nextflow is not available on PATH")
        sys.exit(1)
    try:
        result = subprocess.run(
            ["nextflow", "-version"],
            capture_output=True,
            text=True,
        )
        version_line = ""
        for line in result.stdout.splitlines():
            if "version" in line.lower():
                version_line = line
                break
        if version_line:
            logging.debug(f"Nextflow: {version_line.strip()}")
    except Exception as e:
        logging.warning(f"Could not check Nextflow version: {e}")


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
    if "Snapshot" in combined and "does not match" in combined:
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
    """Find and remove all .nf-test/ directories and .nf-test.log files.

    Args:
        bactopia_path: Path to the Bactopia repository.
        dry_run: If True, only list what would be removed.
    """
    action = "Would remove" if dry_run else "Removing"
    count = 0
    for nf_test_dir in sorted(bactopia_path.rglob(".nf-test")):
        if nf_test_dir.is_dir():
            logging.info(f"{action} {nf_test_dir}")
            if not dry_run:
                shutil.rmtree(nf_test_dir, ignore_errors=True)
            count += 1
    for nf_test_log in sorted(bactopia_path.rglob(".nf-test.log")):
        if nf_test_log.is_file():
            logging.info(f"{action} {nf_test_log}")
            if not dry_run:
                nf_test_log.unlink(missing_ok=True)
            count += 1
    if dry_run:
        logging.info(f"Found {count} nf-test artifact(s) to clean up")
    else:
        logging.info(f"Cleaned up {count} nf-test artifact(s)")


def run_single_test(
    test_dir: Path,
    test_data: Path,
    profile: str,
    condadir: str,
    singularity_cache: str,
    generate: bool,
) -> dict:
    """Execute nf-test for a single component.

    Args:
        test_dir: Path to the tests/ directory containing main.nf.test.
        test_data: Path to bactopia-tests data directory.
        profile: Nextflow profile to use (docker/singularity/conda).
        condadir: Path to Conda environment cache directory.
        singularity_cache: Path to Singularity image cache directory.
        generate: If True, delete snapshot and run twice for reproducibility.

    Returns:
        Dict with status, duration, stdout, and stderr.
    """
    snap_file = test_dir / "main.nf.test.snap"
    env = os.environ.copy()
    env["BACTOPIA_TESTS"] = str(test_data)
    env["NXF_CONDA_CACHEDIR"] = condadir
    env["NXF_SINGULARITY_CACHEDIR"] = singularity_cache

    cmd = ["nf-test", "test", "main.nf.test", "--profile", profile]

    if generate:
        # Delete existing snapshot for fresh generation
        if snap_file.exists():
            snap_file.unlink()

    start = time.monotonic()

    # First run (generate mode: create snapshot; normal mode: verify test passes)
    result = subprocess.run(
        cmd,
        cwd=test_dir,
        capture_output=True,
        text=True,
        env=env,
    )

    status = classify_result(result.stdout, result.stderr, result.returncode)

    # Generate mode: if first run passed, run again to verify reproducibility
    if generate and status == PASSED:
        result2 = subprocess.run(
            cmd,
            cwd=test_dir,
            capture_output=True,
            text=True,
            env=env,
        )
        if result2.returncode != 0:
            status = NON_REPRODUCIBLE
            result = result2

    duration = time.monotonic() - start

    # Always clean up on pass; keep on failure for debugging
    if status == PASSED:
        _cleanup_test_dir(test_dir)

    return {
        "status": status,
        "duration": round(duration, 1),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "cmd": " ".join(cmd),
        "cwd": str(test_dir),
    }


def save_logs(results: list, logs_dir: Path, params: dict):
    """Write per-component log files and summary to the logs directory.

    Creates a timestamped subdirectory with tier-based organization:
        logs/{timestamp}/{tier}/{component}.stdout.txt
        logs/{timestamp}/{tier}/{component}.stderr.txt
        logs/{timestamp}/summary.json
        logs/{timestamp}/summary.tsv

    Args:
        results: List of result dicts from test execution.
        logs_dir: Base logs directory.
    """
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = logs_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write per-component logs organized by tier
    for r in results:
        tier_dir = run_dir / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        name = r["component"]
        (tier_dir / f"{name}.stdout.txt").write_text(r.get("stdout", ""))
        (tier_dir / f"{name}.stderr.txt").write_text(r.get("stderr", ""))

    # Build summary data
    summary_counts = {}
    for r in results:
        summary_counts[r["status"]] = summary_counts.get(r["status"], 0) + 1

    summary_rows = [
        {
            "component": r["component"],
            "tier": r["tier"],
            "status": r["status"],
            "duration": r["duration"],
        }
        for r in results
    ]

    # Write summary.json
    summary_json = {
        "summary": summary_counts,
        "params": params,
        "results": summary_rows,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary_json, indent=2))

    # Write summary.tsv
    tsv_lines = ["component\ttier\tstatus\tduration"]
    for row in summary_rows:
        tsv_lines.append(
            f"{row['component']}\t{row['tier']}\t{row['status']}\t{row['duration']}"
        )
    (run_dir / "summary.tsv").write_text("\n".join(tsv_lines) + "\n")

    logging.info(f"Logs saved to {run_dir}")


def print_results(console: rich.console.Console, results: list, use_json: bool):
    """Display test results as a Rich table or JSON.

    Args:
        console: Rich console for output.
        results: List of result dicts.
        use_json: If True, output JSON instead of a table.
    """
    # Build summary counts
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    if use_json:
        output = {
            "summary": summary,
            "results": [
                {
                    "component": r["component"],
                    "tier": r["tier"],
                    "status": r["status"],
                    "duration": r["duration"],
                }
                for r in results
            ],
        }
        print(json.dumps(output, indent=2))
        return

    # Rich table
    table = rich.table.Table(title="Bactopia Test Results")
    table.add_column("Component", style="bold")
    table.add_column("Tier")
    table.add_column("Status")
    table.add_column("Duration", justify="right")

    for r in results:
        style = STATUS_STYLES.get(r["status"], "")
        table.add_row(
            r["component"],
            r["tier"],
            f"[{style}]{r['status']}[/{style}]",
            f"{r['duration']}s",
        )

    console.print(table)
    console.print()

    # Summary line
    parts = []
    for status_key in [
        PASSED,
        TOOL_ERROR,
        SYNTAX_ERROR,
        SNAPSHOT_MISMATCH,
        NON_REPRODUCIBLE,
        NO_SNAPSHOT,
        SKIPPED,
    ]:
        count = summary.get(status_key, 0)
        if count > 0:
            style = STATUS_STYLES.get(status_key, "")
            parts.append(f"[{style}]{count} {status_key}[/{style}]")

    console.print(f"Summary: {', '.join(parts)}")


@click.command()
@click.version_option(bactopia.__version__, "--version")
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where the Bactopia repository is stored.",
)
@click.option(
    "--test-data",
    default=None,
    help="Directory containing bactopia-tests data (sets BACTOPIA_TESTS env). Required unless --cleanup.",
)
@click.option(
    "--tier",
    default="all",
    type=click.Choice(["modules", "subworkflows", "workflows", "all"]),
    help="Which component tier to test.",
)
@click.option(
    "--include",
    default=None,
    help="Comma-separated list of component names to include.",
)
@click.option(
    "--exclude",
    default=None,
    help="Comma-separated list of component names to exclude.",
)
@click.option(
    "--profile",
    default="docker",
    type=click.Choice(["docker", "singularity", "conda"]),
    help="Nextflow profile to use for tests.",
)
@click.option(
    "--condadir",
    default=CONDA_CACHEDIR,
    show_default=True,
    help="Directory where Conda environments are stored (NXF_CONDA_CACHEDIR env variable takes precedence).",
)
@click.option(
    "--singularity_cache",
    default=SINGULARITY_CACHEDIR,
    show_default=True,
    help="Directory where Singularity images are stored (NXF_SINGULARITY_CACHEDIR env variable takes precedence).",
)
@click.option(
    "--generate",
    is_flag=True,
    help="Generate mode: delete snapshots and run twice to verify reproducibility.",
)
@click.option(
    "--jobs",
    default=max(1, cpu_count() // 4),
    type=int,
    show_default=True,
    help="Number of parallel test workers.",
)
@click.option(
    "--fail-fast",
    is_flag=True,
    help="Stop on the first test failure instead of continuing.",
)
@click.option(
    "--cleanup",
    is_flag=True,
    help="Find and remove all .nf-test/ temp files, then exit (no tests run).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="With --cleanup, list what would be removed without deleting.",
)
@click.option(
    "--outdir",
    default=".",
    show_default=True,
    help="Directory to write the logs/ folder into.",
)
@click.option("--json", "use_json", is_flag=True, help="Output results as JSON.")
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
def testing(
    bactopia_path,
    test_data,
    tier,
    include,
    exclude,
    profile,
    condadir,
    singularity_cache,
    generate,
    jobs,
    fail_fast,
    cleanup,
    dry_run,
    outdir,
    use_json,
    verbose,
    silent,
):
    """Run nf-test suites for Bactopia components.

    Discovers and executes nf-test files across modules, subworkflows, and
    workflows. Results are classified by status and displayed as a summary
    table. Per-test logs are saved to a logs/ directory.
    """
    # Setup logging
    logging.basicConfig(
        format="%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )

    # Resolve paths
    bp = Path(bactopia_path).absolute().resolve()

    # Cleanup mode: remove all .nf-test artifacts and exit
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

    # Pre-flight checks
    preflight_checks(bp, td)

    # Parse include/exclude
    include_list = [x.strip() for x in include.split(",")] if include else None
    exclude_list = [x.strip() for x in exclude.split(",")] if exclude else None

    # Discover tests
    tests = discover_tests(bp, tier, include_list, exclude_list)
    if not tests:
        logging.error("No tests found matching the given criteria.")
        sys.exit(1)

    logging.info(f"Discovered {len(tests)} test(s) to run")

    # Execute tests in parallel
    results = []
    failed = False

    with ProcessPoolExecutor(max_workers=jobs) as executor:
        future_to_test = {}
        for t in tests:
            future = executor.submit(
                run_single_test,
                t["test_dir"],
                td,
                profile,
                str(Path(condadir).absolute()),
                str(Path(singularity_cache).absolute()),
                generate,
            )
            future_to_test[future] = t

        for future in as_completed(future_to_test):
            t = future_to_test[future]
            try:
                result = future.result()
            except Exception as e:
                logging.error(f"Test {t['component']} raised an exception: {e}")
                result = {
                    "status": TOOL_ERROR,
                    "duration": 0.0,
                    "stdout": "",
                    "stderr": str(e),
                }

            result["component"] = t["component"]
            result["tier"] = t["tier"]
            results.append(result)

            logging.debug(f"    cwd: {result.get('cwd', 'N/A')}")
            logging.debug(f"Command: {result.get('cmd', 'N/A')}")
            logging.info(
                f"{t['component']} ({t['tier']}): {result['status']} [{result['duration']}s]"
            )

            if fail_fast and result["status"] != PASSED:
                failed = True
                executor.shutdown(wait=False, cancel_futures=True)
                break

    # Sort results by tier then component name
    results.sort(key=lambda r: (r["tier"], r["component"]))

    # Save logs
    logs_dir = Path(outdir).absolute().resolve() / "logs"
    params = {
        "bactopia_path": str(bp),
        "test_data": str(td),
        "tier": tier,
        "include": include,
        "exclude": exclude,
        "profile": profile,
        "condadir": str(Path(condadir).absolute()),
        "singularity_cache": str(Path(singularity_cache).absolute()),
        "generate": generate,
        "jobs": jobs,
        "fail_fast": fail_fast,
        "cleanup": cleanup,
        "dry_run": dry_run,
        "outdir": str(Path(outdir).absolute()),
        "json": use_json,
        "verbose": verbose,
        "silent": silent,
    }
    save_logs(results, logs_dir, params)

    # Display results
    console = rich.console.Console()
    print_results(console, results, use_json)

    # Exit with non-zero if any test failed
    if failed or any(r["status"] != PASSED for r in results):
        sys.exit(1)


def main():
    if len(sys.argv) == 1:
        testing.main(["--help"])
    else:
        testing()


if __name__ == "__main__":
    main()
