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
from rich.logging import RichHandler

import bactopia

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


def analyze_run(run_dir: Path, baselines_path: Path | None, tolerance: float) -> dict:
    """Analyze a test run and produce a structured report.

    Args:
        run_dir: Path to the test run directory.
        baselines_path: Path to baselines JSON file (or None to skip timing).
        tolerance: Default tolerance factor for timing anomaly detection.

    Returns:
        Complete analysis dict suitable for JSON output.
    """
    summary = parse_summary(run_dir)
    results = summary["results"]
    status_counts = summary["summary"]
    params = summary.get("params", {})

    # Format timestamp from directory name
    dirname = run_dir.name  # e.g. "20260325_084014"
    try:
        ts = datetime.strptime(dirname, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        timestamp = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        timestamp = dirname

    # Tiers present
    tiers_tested = sorted(set(r["tier"] for r in results))

    # Duration stats
    duration = compute_duration_stats(results)

    # Passed stats
    passed_count = status_counts.get("passed", 0)
    total = len(results)
    passed_pct = round(passed_count / total * 100, 1) if total > 0 else 0

    # Classify failures and fix status for assertion failures from older runs
    # that were incorrectly labeled as tool_error
    failed_results = [r for r in results if r["status"] != "passed"]
    failure_details = []

    for r in failed_results:
        stdout_path = run_dir / r["tier"] / f"{r['component']}.stdout.txt"
        if stdout_path.exists():
            raw = stdout_path.read_text(errors="replace")
            clean = strip_ansi(raw)
            classification = classify_failure(clean)
        else:
            classification = {
                "pattern": "unclassified",
                "message": f"stdout file not found: {stdout_path.name}",
            }

        # Reconcile status with pattern analysis -- the pattern classification
        # from stdout is more accurate than the original status from testing.py
        status = r["status"]
        pattern = classification["pattern"]
        if pattern == "assertion_failure" and status != "assertion_failed":
            status_counts[status] = status_counts.get(status, 1) - 1
            status_counts["assertion_failed"] = (
                status_counts.get("assertion_failed", 0) + 1
            )
            status = "assertion_failed"
        elif pattern != "assertion_failure" and status == "assertion_failed":
            status_counts["assertion_failed"] = (
                status_counts.get("assertion_failed", 1) - 1
            )
            status_counts["tool_error"] = status_counts.get("tool_error", 0) + 1
            status = "tool_error"

        failure_details.append(
            {
                "component": r["component"],
                "tier": r["tier"],
                "status": status,
                "duration": r["duration"],
                **classification,
            }
        )

    # Group by pattern
    groups = defaultdict(list)
    for fd in failure_details:
        groups[fd["pattern"]].append(fd)

    # Labels for each pattern
    labels = {
        "null_container": "Null container errors",
        "missing_config": "Missing config/include errors",
        "syntax_error": "Compilation/syntax errors",
        "undeclared_parameter": "Undeclared parameter errors",
        "process_failure": "Process execution failures",
        "abort_error": "Execution aborted unexpectedly",
        "assertion_failure": "Test assertion failures (workflow completed)",
        "unclassified": "Unclassified failures",
    }

    details = {
        "null_container": "Container image is quay.io/null (missing or unconfigured module.config)",
        "missing_config": "Config file referenced by includeConfig does not exist",
        "syntax_error": "Nextflow script failed to compile",
        "undeclared_parameter": "Parameter specified but not declared in script or config",
        "process_failure": "A Nextflow process terminated with a non-zero exit status",
        "abort_error": "Nextflow execution aborted due to an unexpected error",
        "assertion_failure": "Workflow ran successfully but test assertions did not match",
        "unclassified": "Failures that did not match any known error pattern",
    }

    # Build ordered failure groups
    pattern_order = [
        "undeclared_parameter",
        "missing_config",
        "process_failure",
        "null_container",
        "abort_error",
        "assertion_failure",
        "syntax_error",
        "unclassified",
    ]

    failure_groups = []
    for pattern in pattern_order:
        components = groups.get(pattern, [])
        group = {
            "pattern": pattern,
            "label": labels[pattern],
            "count": len(components),
            "detail": details[pattern],
            "components": components,
        }
        # Add parameter summary for undeclared_parameter group
        if pattern == "undeclared_parameter" and components:
            param_counts = defaultdict(int)
            for c in components:
                for p in c.get("parameters", []):
                    param_counts[p] += 1
            group["parameters"] = dict(
                sorted(param_counts.items(), key=lambda x: -x[1])
            )
        failure_groups.append(group)

    # Timing anomalies
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
        anomalies = check_timing_anomalies(results, baselines, tolerance)
        timing["slow_tests"] = anomalies["slow_tests"]
        timing["fast_tests"] = anomalies["fast_tests"]

    return {
        "timestamp": timestamp,
        "run_dir": str(run_dir),
        "total_tests": total,
        "tiers_tested": tiers_tested,
        "params": params,
        "duration": duration,
        "status_counts": {k: v for k, v in status_counts.items() if v > 0},
        "passed": {"count": passed_count, "percentage": passed_pct},
        "failure_groups": failure_groups,
        "timing_anomalies": timing,
    }


def print_rich(console: rich.console.Console, data: dict):
    """Render test review data as Rich tables.

    Args:
        console: Rich console for output.
        data: Analysis dict from analyze_run().
    """
    console.print(f"[bold]Test Run Review[/bold]  ({data['timestamp']})")
    console.print(f"Run: {data['run_dir']}\n")

    # Header stats
    header = rich.table.Table(title="Overview", show_header=False, box=None)
    header.add_row("Total tests:", str(data["total_tests"]))
    header.add_row("Tiers:", ", ".join(data["tiers_tested"]))
    dur = data["duration"]
    header.add_row("Total duration:", f"{dur['total_seconds']:.0f}s")
    header.add_row("Average:", f"{dur['average_seconds']:.1f}s")
    header.add_row("Median:", f"{dur['median_seconds']:.1f}s")
    if dur["longest"]:
        header.add_row(
            "Longest:",
            f"{dur['longest']['component']} ({dur['longest']['duration']:.1f}s)",
        )
    if dur["shortest"]:
        header.add_row(
            "Shortest:",
            f"{dur['shortest']['component']} ({dur['shortest']['duration']:.1f}s)",
        )
    console.print(header)
    console.print()

    # Run parameters
    params = data.get("params", {})
    if params:
        params_table = rich.table.Table(
            title="Run Parameters", show_header=False, box=None
        )
        params_table.add_row("Generate:", str(params.get("generate", False)))
        params_table.add_row("Profile:", str(params.get("profile", "unknown")))
        params_table.add_row("Tier:", str(params.get("tier", "all")))
        params_table.add_row("Jobs:", str(params.get("jobs", "unknown")))
        params_table.add_row("Fail fast:", str(params.get("fail_fast", False)))
        params_table.add_row("Cleanup:", str(params.get("cleanup", False)))
        if params.get("include"):
            params_table.add_row("Include:", str(params["include"]))
        if params.get("exclude"):
            params_table.add_row("Exclude:", str(params["exclude"]))
        console.print(params_table)
        console.print()

    # Status counts
    status_table = rich.table.Table(title="Status Breakdown", box=None)
    status_table.add_column("Status", style="bold")
    status_table.add_column("Count", justify="right")
    for status, count in data["status_counts"].items():
        style = "green" if status == "passed" else "red"
        status_table.add_row(f"[{style}]{status}[/{style}]", str(count))
    console.print(status_table)

    passed = data["passed"]
    console.print(
        f"\n[green]{passed['count']} passed[/green] ({passed['percentage']}% of {data['total_tests']} total)\n"
    )

    # Failure groups
    for group in data["failure_groups"]:
        if group["count"] == 0:
            continue

        console.print(f"[bold red]{group['label']}[/bold red] ({group['count']})")
        console.print(f"  {group['detail']}")

        # Show parameter summary for undeclared_parameter
        if group["pattern"] == "undeclared_parameter" and "parameters" in group:
            for param, cnt in group["parameters"].items():
                console.print(f"  - [yellow]{param}[/yellow]: {cnt} tests")

        # List affected components
        comp_table = rich.table.Table(box=None, show_header=True, padding=(0, 1))
        comp_table.add_column("Component", style="bold")
        comp_table.add_column("Tier")
        comp_table.add_column("Duration", justify="right")
        comp_table.add_column("Detail")

        for c in sorted(group["components"], key=lambda x: x["component"]):
            detail = c.get("message", "")
            # Truncate long details
            if len(detail) > 80:
                detail = detail[:77] + "..."
            comp_table.add_row(
                c["component"], c["tier"], f"{c['duration']:.1f}s", detail
            )

        console.print(comp_table)
        console.print()

    # Timing anomalies
    timing = data["timing_anomalies"]
    if not timing["baselines_available"]:
        console.print(
            "[dim]No timing baselines available. Use --update-baselines to create them.[/dim]\n"
        )
    else:
        if timing["slow_tests"]:
            console.print(
                f"[bold yellow]Slow Tests[/bold yellow] ({len(timing['slow_tests'])})"
            )
            slow_table = rich.table.Table(box=None, show_header=True, padding=(0, 1))
            slow_table.add_column("Component", style="bold")
            slow_table.add_column("Tier")
            slow_table.add_column("Actual", justify="right")
            slow_table.add_column("Expected", justify="right")
            slow_table.add_column("Ratio", justify="right")
            for t in timing["slow_tests"]:
                slow_table.add_row(
                    t["component"],
                    t["tier"],
                    f"{t['actual_seconds']:.1f}s",
                    f"{t['expected_seconds']:.1f}s",
                    f"{t['ratio']:.1f}x",
                )
            console.print(slow_table)
            console.print()

        if timing["fast_tests"]:
            console.print(
                f"[bold cyan]Suspiciously Fast Tests[/bold cyan] ({len(timing['fast_tests'])})"
            )
            fast_table = rich.table.Table(box=None, show_header=True, padding=(0, 1))
            fast_table.add_column("Component", style="bold")
            fast_table.add_column("Tier")
            fast_table.add_column("Actual", justify="right")
            fast_table.add_column("Expected", justify="right")
            fast_table.add_column("Ratio", justify="right")
            for t in timing["fast_tests"]:
                fast_table.add_row(
                    t["component"],
                    t["tier"],
                    f"{t['actual_seconds']:.1f}s",
                    f"{t['expected_seconds']:.1f}s",
                    f"{t['ratio']:.1f}x",
                )
            console.print(fast_table)
            console.print()

        if not timing["slow_tests"] and not timing["fast_tests"]:
            console.print("[green]All test durations within expected range.[/green]\n")


@click.command()
@click.version_option(bactopia.__version__, "--version")
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored.",
)
@click.option(
    "--run",
    "run_timestamp",
    default=None,
    help="Specific test run timestamp (YYYYMMDD_HHMMSS). Default: latest.",
)
@click.option(
    "--logs-dir",
    default=None,
    help="Directory containing test run logs. Default: {bactopia-path}/logs.",
)
@click.option(
    "--baselines",
    default=None,
    help="Path to test-times baseline JSON file. Default: {bactopia-path}/conf/test-times.json.",
)
@click.option(
    "--tolerance",
    default=2.0,
    type=float,
    show_default=True,
    help="Tolerance factor for timing anomaly detection.",
)
@click.option(
    "--update-baselines",
    "do_update_baselines",
    is_flag=True,
    help="Write/update the baselines file from current run results.",
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.option(
    "--pretty", is_flag=True, help="Pretty-print JSON output (implies --json)."
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
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
    # Setup logs
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )

    # Validate path
    bp = Path(bactopia_path).absolute().resolve()
    if not bp.exists():
        logging.error(f"Bactopia path {bactopia_path} does not exist.")
        sys.exit(1)

    # Resolve logs directory
    logs = Path(logs_dir).absolute().resolve() if logs_dir else bp / "logs"
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
        update_baselines(summary["results"], baselines_path)

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
