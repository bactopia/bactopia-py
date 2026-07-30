"""CLI command for analyzing nf-test timing and results."""

import json
import logging
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import rich
import rich.console
import rich.table
import rich.traceback
import rich_click as click

import bactopia
from bactopia.cli.common import common_options, setup_logging

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-review-tests": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Run Selection",
            "options": [
                "--run",
                "--logs-dir",
            ],
        },
        {
            "name": "Timing Options",
            "options": [
                "--baselines",
                "--tolerance",
                "--update-baselines",
            ],
        },
        {
            "name": "Output Options",
            "options": [
                "--json",
                "--pretty",
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

# Regex to strip ANSI escape codes from nf-test stdout
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\(B")

# Timestamp directory pattern (YYYYMMDD_HHMMSS)
TIMESTAMP_PATTERN = re.compile(r"^\d{8}_\d{6}$")

# Error classification patterns (checked in priority order)
RE_NULL_CONTAINER = re.compile(
    r"Container:\s*quay\.io/null|Unable to find image '.*null.*'"
)
RE_MISSING_CONFIG = re.compile(r"Invalid include source:\s*'(.+?)'")
RE_SYNTAX_ERROR = re.compile(
    r"Compilation failed|unable to resolve class|Unexpected input|BUG: parsing"
)
RE_UNDECLARED_PARAM = re.compile(
    r"Parameter [`'](.+?)[`'] was specified .* but is not declared"
)
RE_PROCESS_FAILURE = re.compile(r"ERROR ~ Error executing process > '(.+?)'")
RE_CAUSED_BY = re.compile(r"Caused by:\s*\n\s*(.+)")
RE_EXIT_STATUS = re.compile(r"Command exit status:\s*(\d+)")
RE_COMMAND_ERROR = re.compile(r"Command error:\s*\n((?:\s+.+\n)*)")
RE_ABORT_ERROR = re.compile(r"ERROR ~ Execution aborted due to an unexpected error")
RE_NF_LOG_PATH = re.compile(r"Check '(.+?)' file for details")
RE_ASSERTION_FAILED = re.compile(r"(\d+) of (\d+) assertions? failed")
RE_HAS_NF_ERROR = re.compile(r"ERROR ~")

# Matrix profiles (fallback if summary.json omits the list)
PROFILES_DEFAULT = ["docker", "conda", "singularity_galaxy", "singularity_pull"]

# Cell statuses that are not failures worth grouping.
PASS_LIKE = {"passed", "n/a", "skipped"}

# Statuses assigned directly by bactopia-test (not inferred from stdout).
DIRECT_PATTERNS = {
    "version_drift": "Runtime resolved a different tool version than the docker-pinned container -- update the version pin",
    "output_drift": "Output content differs from the docker snapshot (non-reproducible file or a genuine change to review)",
    "version+output_drift": "Both tool version and output differ from the docker snapshot",
    "snapshot_mismatch": "Snapshot did not match the docker ground truth (drift not subclassified)",
    "snapshot_stale": "Committed snapshot is stale (docker itself no longer matches) -- run --generate",
    "non_reproducible": "Docker snapshot generation was not reproducible across two runs",
    "build_failed": "Environment/image failed to build during the build phase",
    "no_ground_truth": "No docker snapshot was available to validate against",
    "no_snapshot": "nf-test reported a missing snapshot",
    "timeout": "Test exceeded the per-run timeout",
}

PATTERN_LABELS = {
    "version_drift": "Version drift (update pin)",
    "output_drift": "Output drift",
    "version+output_drift": "Version + output drift",
    "snapshot_mismatch": "Snapshot mismatch",
    "snapshot_stale": "Stale snapshot (run --generate)",
    "non_reproducible": "Non-reproducible snapshot",
    "build_failed": "Environment build failures",
    "no_ground_truth": "No ground-truth snapshot",
    "no_snapshot": "Missing snapshot",
    "timeout": "Timed out",
    "undeclared_outputs": "Undeclared output files",
    "undeclared_parameter": "Undeclared parameter errors",
    "missing_config": "Missing config/include errors",
    "process_failure": "Process execution failures",
    "null_container": "Null container errors",
    "abort_error": "Execution aborted unexpectedly",
    "assertion_failure": "Test assertion failures (workflow completed)",
    "syntax_error": "Compilation/syntax errors",
    "unclassified": "Unclassified failures",
}

PATTERN_DETAILS = {
    "version_drift": "The tool version resolved by Conda/Singularity differs from the container pin",
    "output_drift": "Output files differ from the docker-generated snapshot",
    "version+output_drift": "Both the tool version and its output differ from docker",
    "snapshot_mismatch": "Snapshot did not match and could not be subclassified",
    "snapshot_stale": "The reference runtime (docker) no longer matches the committed snapshot; regenerate it",
    "non_reproducible": "Two docker runs produced different snapshots",
    "build_failed": "Could not build the Conda env or Singularity image before testing",
    "no_ground_truth": "Docker did not establish a snapshot for the non-docker profiles to validate",
    "no_snapshot": "No snapshot file was found for the test",
    "timeout": "The nf-test subprocess was killed after the timeout",
    "undeclared_outputs": "Files produced but not in results/logs/versions/nf_logs (add to results or .outputs-ignore)",
    "undeclared_parameter": "Parameter specified but not declared in script or config",
    "missing_config": "Config file referenced by includeConfig does not exist",
    "process_failure": "A Nextflow process terminated with a non-zero exit status",
    "null_container": "Container image is quay.io/null (missing or unconfigured module.config)",
    "abort_error": "Nextflow execution aborted due to an unexpected error",
    "assertion_failure": "Workflow ran successfully but test assertions did not match",
    "syntax_error": "Nextflow script failed to compile",
    "unclassified": "Failures that did not match any known error pattern",
}

PATTERN_ORDER = [
    "version_drift",
    "output_drift",
    "version+output_drift",
    "snapshot_mismatch",
    "snapshot_stale",
    "non_reproducible",
    "build_failed",
    "no_ground_truth",
    "no_snapshot",
    "timeout",
    "undeclared_outputs",
    "undeclared_parameter",
    "missing_config",
    "process_failure",
    "null_container",
    "abort_error",
    "assertion_failure",
    "syntax_error",
    "unclassified",
]


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return ANSI_ESCAPE.sub("", text)


def find_latest_run(logs_dir: Path) -> Path | None:
    """Find the most recent test run directory.

    Args:
        logs_dir: Directory containing timestamped test run directories.

    Returns:
        Path to the latest run directory, or None if no runs found.
    """
    runs = sorted(
        d for d in logs_dir.iterdir() if d.is_dir() and TIMESTAMP_PATTERN.match(d.name)
    )
    return runs[-1] if runs else None


def parse_summary(run_dir: Path) -> dict:
    """Read and parse summary.json from a test run.

    Args:
        run_dir: Path to the test run directory.

    Returns:
        Parsed summary dict with 'summary' and 'results' keys.
    """
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        logging.error(f"No summary.json found in {run_dir}")
        sys.exit(1)
    with open(summary_path) as f:
        return json.load(f)


def classify_failure(stdout_text: str) -> dict:
    """Classify a test failure by analyzing its stdout content.

    Patterns are checked in priority order (most specific first).

    Args:
        stdout_text: Raw stdout content (ANSI codes already stripped).

    Returns:
        Dict with 'pattern' key and pattern-specific detail fields.
    """
    # 1. Null container
    if RE_NULL_CONTAINER.search(stdout_text):
        return {
            "pattern": "null_container",
            "message": "Container image is null/missing",
        }

    # 2. Missing config file
    m = RE_MISSING_CONFIG.search(stdout_text)
    if m:
        return {
            "pattern": "missing_config",
            "missing_path": m.group(1),
            "message": f"Invalid include source: '{m.group(1)}'",
        }

    # 3. Syntax/compilation error
    if RE_SYNTAX_ERROR.search(stdout_text):
        return {"pattern": "syntax_error", "message": "Script compilation failed"}

    # 4. Undeclared parameter
    params = RE_UNDECLARED_PARAM.findall(stdout_text)
    if params:
        unique_params = sorted(set(params))
        return {
            "pattern": "undeclared_parameter",
            "parameters": unique_params,
            "message": f"Undeclared parameter(s): {', '.join(unique_params)}",
        }

    # 5. Process execution failure
    m = RE_PROCESS_FAILURE.search(stdout_text)
    if m:
        result = {
            "pattern": "process_failure",
            "process": m.group(1),
            "message": f"Error executing process > '{m.group(1)}'",
        }
        caused = RE_CAUSED_BY.search(stdout_text)
        if caused:
            result["caused_by"] = caused.group(1).strip()
        exit_m = RE_EXIT_STATUS.search(stdout_text)
        if exit_m:
            result["exit_status"] = int(exit_m.group(1))
        cmd_err = RE_COMMAND_ERROR.search(stdout_text)
        if cmd_err:
            lines = cmd_err.group(1).strip().splitlines()
            result["command_error"] = "\n".join(lines[:5])
        return result

    # 6. Execution aborted
    if RE_ABORT_ERROR.search(stdout_text):
        result = {
            "pattern": "abort_error",
            "message": "Execution aborted due to an unexpected error",
        }
        log_m = RE_NF_LOG_PATH.search(stdout_text)
        if log_m:
            result["nextflow_log"] = log_m.group(1)
        return result

    # 7. Assertion failure (no Nextflow ERROR)
    assertion_m = RE_ASSERTION_FAILED.search(stdout_text)
    if assertion_m and not RE_HAS_NF_ERROR.search(stdout_text):
        return {
            "pattern": "assertion_failure",
            "assertions_failed": int(assertion_m.group(1)),
            "assertions_total": int(assertion_m.group(2)),
            "message": f"{assertion_m.group(1)} of {assertion_m.group(2)} assertions failed",
        }

    # 8. Unclassified
    # Grab some meaningful content for debugging
    content = stdout_text.strip()
    snippet = content[:500] if content else "(empty stdout)"
    return {
        "pattern": "unclassified",
        "message": "Could not classify failure",
        "snippet": snippet,
    }


def compute_duration_stats(results: list) -> dict:
    """Compute duration statistics from test results.

    Args:
        results: List of result dicts from summary.json.

    Returns:
        Dict with total, average, median, longest, and shortest duration info.
    """
    durations = [r["duration"] for r in results]
    if not durations:
        return {
            "total_seconds": 0,
            "average_seconds": 0,
            "median_seconds": 0,
            "longest": None,
            "shortest": None,
        }

    longest = max(results, key=lambda r: r["duration"])
    shortest = min(results, key=lambda r: r["duration"])

    return {
        "total_seconds": round(sum(durations), 1),
        "average_seconds": round(statistics.mean(durations), 1),
        "median_seconds": round(statistics.median(durations), 1),
        "longest": {
            "component": longest["component"],
            "tier": longest["tier"],
            "duration": longest["duration"],
        },
        "shortest": {
            "component": shortest["component"],
            "tier": shortest["tier"],
            "duration": shortest["duration"],
        },
    }


def check_timing_anomalies(results: list, baselines: dict, tolerance: float) -> dict:
    """Check test durations against expected baselines.

    Args:
        results: List of result dicts from summary.json.
        baselines: Baselines dict with 'components' key.
        tolerance: Default tolerance factor for anomaly detection.

    Returns:
        Dict with slow_tests and fast_tests lists.
    """
    components = baselines.get("components", {})
    slow = []
    fast = []

    for r in results:
        key = f"{r['tier']}/{r['component']}"
        if key not in components:
            continue
        baseline = components[key]
        expected = baseline["expected_seconds"]
        tol = baseline.get("tolerance_factor", tolerance)
        actual = r["duration"]

        if expected <= 0:
            continue

        ratio = round(actual / expected, 2)
        entry = {
            "component": r["component"],
            "tier": r["tier"],
            "actual_seconds": actual,
            "expected_seconds": expected,
            "ratio": ratio,
        }

        if actual > expected * tol:
            slow.append(entry)
        elif actual < expected / tol:
            fast.append(entry)

    slow.sort(key=lambda x: x["ratio"], reverse=True)
    fast.sort(key=lambda x: x["ratio"])

    return {"slow_tests": slow, "fast_tests": fast}


def update_baselines(results: list, baselines_path: Path):
    """Write or update test time baselines from current run results.

    Preserves custom tolerance_factor values and entries for components
    not in the current run (supports partial runs).

    Args:
        results: List of result dicts from summary.json.
        baselines_path: Path to write the baselines JSON file.
    """
    existing = {}
    if baselines_path.exists():
        with open(baselines_path) as f:
            existing = json.load(f)

    components = existing.get("components", {})

    for r in results:
        key = f"{r['tier']}/{r['component']}"
        if key in components:
            # Preserve custom tolerance if it was changed from default
            old_tol = components[key].get("tolerance_factor", 2.0)
            components[key] = {
                "expected_seconds": r["duration"],
                "tolerance_factor": old_tol,
            }
        else:
            components[key] = {
                "expected_seconds": r["duration"],
                "tolerance_factor": 2.0,
            }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    data = {
        "_meta": {
            "updated": now,
            "source_run": baselines_path.parent.name
            if baselines_path.parent.name != "conf"
            else "manual",
            "total_components": len(components),
        },
        "components": dict(sorted(components.items())),
    }

    baselines_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baselines_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    logging.info(f"Baselines updated: {baselines_path} ({len(components)} components)")


def _docker_results(results: list) -> list:
    """Flatten matrix results to docker-cell pseudo-results.

    Timing stats and baselines key on the docker profile since it is the
    canonical, container-pinned runtime.
    """
    flat = []
    for r in results:
        cell = r.get("cells", {}).get("docker")
        if cell is None:
            continue
        flat.append(
            {
                "component": r["component"],
                "tier": r["tier"],
                "duration": cell.get("duration", 0),
            }
        )
    return flat


def analyze_run(run_dir: Path, baselines_path: Path | None, tolerance: float) -> dict:
    """Analyze a matrix test run and produce a structured report.

    Args:
        run_dir: Path to the test run directory.
        baselines_path: Path to baselines JSON file (or None to skip timing).
        tolerance: Default tolerance factor for timing anomaly detection.

    Returns:
        Complete analysis dict suitable for JSON output.
    """
    summary = parse_summary(run_dir)
    results = summary.get("results", [])
    profiles = summary.get("profiles", PROFILES_DEFAULT)
    per_profile_counts = summary.get("summary", {})
    params = summary.get("params", {})

    dirname = run_dir.name
    try:
        ts = datetime.strptime(dirname, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        timestamp = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        timestamp = dirname

    tiers_tested = sorted(set(r["tier"] for r in results))
    docker_res = _docker_results(results)
    duration = compute_duration_stats(docker_res)
    total = len(results)

    # Per-profile passed stats
    passed = {}
    for p in profiles:
        counts = per_profile_counts.get(p, {})
        pc = counts.get("passed", 0)
        tot = sum(counts.values())
        passed[p] = {
            "count": pc,
            "percentage": round(pc / tot * 100, 1) if tot else 0,
        }

    # Collect every non-passing cell across all profiles.
    failure_details = []
    for r in results:
        for profile in profiles:
            cell = r.get("cells", {}).get(profile)
            if cell is None:
                continue
            status = cell["status"]
            if status in PASS_LIKE:
                continue
            base = {
                "component": r["component"],
                "tier": r["tier"],
                "profile": profile,
                "status": status,
                "duration": cell.get("duration", 0),
            }
            if status == "undeclared_outputs":
                outputs_path = (
                    run_dir / r["tier"] / r["component"] / profile / "outputs.txt"
                )
                undeclared = cell.get("undeclared_outputs", [])
                if not undeclared and outputs_path.exists():
                    undeclared = [
                        line
                        for line in outputs_path.read_text().splitlines()
                        if line and not line.startswith("#")
                    ]
                message = ", ".join(undeclared) if undeclared else "see outputs.txt"
                failure_details.append(
                    {**base, "pattern": "undeclared_outputs", "message": message}
                )
            elif status in DIRECT_PATTERNS:
                failure_details.append(
                    {
                        **base,
                        "pattern": status,
                        "message": cell.get("reason") or DIRECT_PATTERNS[status],
                    }
                )
            else:
                stdout_path = (
                    run_dir / r["tier"] / r["component"] / profile / "stdout.txt"
                )
                if stdout_path.exists():
                    classification = classify_failure(
                        strip_ansi(stdout_path.read_text(errors="replace"))
                    )
                else:
                    classification = {
                        "pattern": "unclassified",
                        "message": f"stdout not found: {stdout_path}",
                    }
                if cell.get("reason"):
                    classification = {**classification, "message": cell["reason"]}
                failure_details.append({**base, **classification})

    groups = defaultdict(list)
    for fd in failure_details:
        groups[fd["pattern"]].append(fd)

    failure_groups = []
    for pattern in PATTERN_ORDER:
        comps = groups.get(pattern, [])
        group = {
            "pattern": pattern,
            "label": PATTERN_LABELS.get(pattern, pattern),
            "count": len(comps),
            "detail": PATTERN_DETAILS.get(pattern, ""),
            "components": comps,
        }
        if pattern == "undeclared_parameter" and comps:
            param_counts = defaultdict(int)
            for c in comps:
                for p in c.get("parameters", []):
                    param_counts[p] += 1
            group["parameters"] = dict(
                sorted(param_counts.items(), key=lambda x: -x[1])
            )
        failure_groups.append(group)

    timing = {
        "baselines_file": str(baselines_path) if baselines_path else None,
        "baselines_available": False,
        "slow_tests": [],
        "fast_tests": [],
    }
    if baselines_path and baselines_path.exists():
        with open(baselines_path) as f:
            baselines = json.load(f)
        timing["baselines_available"] = True
        anomalies = check_timing_anomalies(docker_res, baselines, tolerance)
        timing["slow_tests"] = anomalies["slow_tests"]
        timing["fast_tests"] = anomalies["fast_tests"]

    return {
        "timestamp": timestamp,
        "run_dir": str(run_dir),
        "total_components": total,
        "tiers_tested": tiers_tested,
        "profiles": profiles,
        "params": params,
        "duration": duration,
        "status_counts": per_profile_counts,
        "passed": passed,
        "failure_groups": failure_groups,
        "timing_anomalies": timing,
    }


def print_rich(console: rich.console.Console, data: dict):
    """Render matrix test-review data as Rich tables."""
    console.print(f"[bold]Test Run Review[/bold]  ({data['timestamp']})")
    console.print(f"Run: {data['run_dir']}\n")

    profiles = data.get("profiles", PROFILES_DEFAULT)

    header = rich.table.Table(title="Overview", show_header=False, box=None)
    header.add_row("Components:", str(data["total_components"]))
    header.add_row("Tiers:", ", ".join(data["tiers_tested"]))
    dur = data["duration"]
    header.add_row(
        "Docker duration:",
        f"{dur['total_seconds']:.0f}s total, {dur['average_seconds']:.1f}s avg",
    )
    if dur["longest"]:
        header.add_row(
            "Longest:",
            f"{dur['longest']['component']} ({dur['longest']['duration']:.1f}s)",
        )
    console.print(header)
    console.print()

    params = data.get("params", {})
    if params:
        pt = rich.table.Table(title="Run Parameters", show_header=False, box=None)
        pt.add_row("Generate:", str(params.get("generate", False)))
        pt.add_row("Tier:", str(params.get("tier", "all")))
        pt.add_row("Jobs:", str(params.get("jobs", "unknown")))
        pt.add_row("Fail fast:", str(params.get("fail_fast", False)))
        pt.add_row("Cache dir:", str(params.get("cachedir", "unknown")))
        if params.get("include"):
            pt.add_row("Include:", str(params["include"]))
        if params.get("exclude"):
            pt.add_row("Exclude:", str(params["exclude"]))
        console.print(pt)
        console.print()

    # Status breakdown: one column per profile.
    counts = data.get("status_counts", {})
    seen = []
    for p in profiles:
        for s in counts.get(p, {}):
            if s not in seen:
                seen.append(s)
    order = [
        "passed",
        "n/a",
        "version_drift",
        "output_drift",
        "version+output_drift",
        "snapshot_mismatch",
        "snapshot_stale",
        "non_reproducible",
        "build_failed",
        "no_ground_truth",
        "no_snapshot",
        "timeout",
        "tool_error",
        "assertion_failed",
        "syntax_error",
        "undeclared_outputs",
    ]
    ordered = [s for s in order if s in seen] + [s for s in seen if s not in order]
    st = rich.table.Table(title="Status Breakdown by Profile", box=None)
    st.add_column("Status", style="bold")
    for p in profiles:
        st.add_column(p, justify="right")
    for s in ordered:
        style = (
            "green" if s == "passed" else ("dim" if s in ("n/a", "skipped") else "red")
        )
        row = [f"[{style}]{s}[/{style}]"]
        for p in profiles:
            row.append(str(counts.get(p, {}).get(s, 0)))
        st.add_row(*row)
    console.print(st)

    passed = data.get("passed", {})
    parts = [
        f"{p}: {passed.get(p, {}).get('count', 0)} ({passed.get(p, {}).get('percentage', 0)}%)"
        for p in profiles
    ]
    console.print("\n[green]Passed[/green] -> " + " | ".join(parts) + "\n")

    for group in data["failure_groups"]:
        if group["count"] == 0:
            continue
        console.print(f"[bold red]{group['label']}[/bold red] ({group['count']})")
        console.print(f"  {group['detail']}")
        if group["pattern"] == "undeclared_parameter" and "parameters" in group:
            for param, cnt in group["parameters"].items():
                console.print(f"  - [yellow]{param}[/yellow]: {cnt} tests")
        ct = rich.table.Table(box=None, show_header=True, padding=(0, 1))
        ct.add_column("Component", style="bold")
        ct.add_column("Tier")
        ct.add_column("Profile")
        ct.add_column("Duration", justify="right")
        ct.add_column("Detail")
        for c in sorted(
            group["components"], key=lambda x: (x["component"], x.get("profile", ""))
        ):
            detail = c.get("message", "")
            if len(detail) > 80:
                detail = detail[:77] + "..."
            ct.add_row(
                c["component"],
                c["tier"],
                c.get("profile", ""),
                f"{c['duration']:.1f}s",
                detail,
            )
        console.print(ct)
        console.print()

    timing = data["timing_anomalies"]
    if not timing["baselines_available"]:
        console.print(
            "[dim]No timing baselines available. Use --update-baselines to create them.[/dim]\n"
        )
        return
    for label, key, color in (
        ("Slow Tests", "slow_tests", "bold yellow"),
        ("Suspiciously Fast Tests", "fast_tests", "bold cyan"),
    ):
        rows = timing[key]
        if not rows:
            continue
        console.print(f"[{color}]{label}[/{color}] ({len(rows)})")
        tbl = rich.table.Table(box=None, show_header=True, padding=(0, 1))
        tbl.add_column("Component", style="bold")
        tbl.add_column("Tier")
        tbl.add_column("Actual", justify="right")
        tbl.add_column("Expected", justify="right")
        tbl.add_column("Ratio", justify="right")
        for tt in rows:
            tbl.add_row(
                tt["component"],
                tt["tier"],
                f"{tt['actual_seconds']:.1f}s",
                f"{tt['expected_seconds']:.1f}s",
                f"{tt['ratio']:.1f}x",
            )
        console.print(tbl)
        console.print()
    if not timing["slow_tests"] and not timing["fast_tests"]:
        console.print("[green]All test durations within expected range.[/green]\n")


@click.command()
@common_options
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--run",
    "run_timestamp",
    default=None,
    help="Specific test run timestamp (YYYYMMDD_HHMMSS). Default: latest",
)
@click.option(
    "--logs-dir",
    default=None,
    help="Directory containing test run logs. Default: {bactopia-path}/logs/run-tests",
)
@click.option(
    "--baselines",
    default=None,
    help="Path to test-times baseline JSON file. Default: {bactopia-path}/conf/test-times.json",
)
@click.option(
    "--tolerance",
    default=2.0,
    type=float,
    show_default=True,
    help="Tolerance factor for timing anomaly detection",
)
@click.option(
    "--update-baselines",
    "do_update_baselines",
    is_flag=True,
    help="Write/update the baselines file from current run results",
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.option(
    "--pretty", is_flag=True, help="Pretty-print JSON output (implies --json)"
)
def review(
    bactopia_path,
    run_timestamp,
    logs_dir,
    baselines,
    tolerance,
    do_update_baselines,
    use_json,
    pretty,
    verbose,
    silent,
):
    """Review nf-test results with grouped error analysis and timing checks.

    Analyzes test run logs, classifies failures by error pattern,
    and optionally checks durations against expected baselines.
    """
    setup_logging(verbose, silent)

    # Validate path
    bp = Path(bactopia_path).absolute().resolve()
    if not bp.exists():
        logging.error(f"Bactopia path {bactopia_path} does not exist.")
        sys.exit(1)

    # Resolve logs directory
    logs = (
        Path(logs_dir).absolute().resolve() if logs_dir else bp / "logs" / "run-tests"
    )
    if not logs.exists():
        logging.error(f"Logs directory {logs} does not exist.")
        sys.exit(1)

    # Find run directory
    if run_timestamp:
        run_dir = logs / run_timestamp
        if not run_dir.exists():
            logging.error(f"Test run {run_timestamp} not found in {logs}")
            available = sorted(
                d.name
                for d in logs.iterdir()
                if d.is_dir() and TIMESTAMP_PATTERN.match(d.name)
            )
            if available:
                logging.info(f"Available runs: {', '.join(available[-5:])}")
            sys.exit(1)
    else:
        run_dir = find_latest_run(logs)
        if run_dir is None:
            logging.error(f"No test runs found in {logs}")
            sys.exit(1)

    logging.info(f"Reviewing test run: {run_dir.name}")

    # Resolve baselines path
    baselines_path = (
        Path(baselines).absolute().resolve()
        if baselines
        else bp / "conf" / "test-times.json"
    )

    # Analyze
    data = analyze_run(run_dir, baselines_path, tolerance)

    # Update baselines if requested
    if do_update_baselines:
        summary = parse_summary(run_dir)
        update_baselines(_docker_results(summary["results"]), baselines_path)

    # Output
    if use_json or pretty:
        indent = 2 if pretty else None
        print(json.dumps(data, indent=indent))
    else:
        print_rich(rich.console.Console(), data)


def main():
    if len(sys.argv) == 1:
        review.main(["--help"])
    else:
        review()


if __name__ == "__main__":
    main()
