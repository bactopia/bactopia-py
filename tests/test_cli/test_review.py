"""Unit tests for bactopia-review-tests matrix consumption.

Builds a fake run directory with a matrix ``summary.json`` (the schema
``bactopia-test`` writes) plus per-cell logs, then exercises the failure
grouping, per-profile stats, and stdout-based failure classifier.
"""

import json

from bactopia.cli import review as rv

PROFILES = ["docker", "conda", "singularity_galaxy", "singularity_pull"]


def _cell(status, reason=None, undeclared=None, error_class=None):
    c = {
        "status": status,
        "duration": 5.0,
        "reason": reason,
        "undeclared_outputs": undeclared or [],
    }
    if error_class:
        c["error_class"] = error_class
    return c


def _counts(results):
    counts = {p: {} for p in PROFILES}
    for r in results:
        for p, c in r["cells"].items():
            counts[p][c["status"]] = counts[p].get(c["status"], 0) + 1
    return counts


def _write_run(tmp_path, results, cell_logs=None):
    """Write summary.json + per-cell stdout/outputs for a run dir."""
    run = tmp_path / "20260101_000000"
    run.mkdir()
    summary = {
        "profiles": PROFILES,
        "reference_profile": "docker",
        "summary": _counts(results),
        "params": {"tier": "modules", "generate": False, "jobs": 4},
        "results": results,
    }
    (run / "summary.json").write_text(json.dumps(summary))
    for (tier, comp, profile), text in (cell_logs or {}).items():
        d = run / tier / comp / profile
        d.mkdir(parents=True, exist_ok=True)
        (d / "stdout.txt").write_text(text)
    return run


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------


def test_classify_failure_process_failure():
    out = "ERROR ~ Error executing process > 'SISTR (1)'"
    result = rv.classify_failure(out)
    assert result["pattern"] == "process_failure"
    assert result["process"] == "SISTR (1)"


def test_classify_failure_null_container():
    assert rv.classify_failure("Container: quay.io/null")["pattern"] == "null_container"


def test_classify_failure_assertion():
    result = rv.classify_failure("2 of 3 assertions failed")
    assert result["pattern"] == "assertion_failure"
    assert result["assertions_failed"] == 2


def test_classify_failure_unclassified():
    assert rv.classify_failure("something odd")["pattern"] == "unclassified"


# ---------------------------------------------------------------------------
# analyze_run over a matrix summary.json
# ---------------------------------------------------------------------------


def test_analyze_run_groups_drift_with_reason(tmp_path):
    results = [
        {
            "component": "pasty",
            "tier": "modules",
            "galaxy": True,
            "cells": {
                "docker": _cell("passed"),
                "conda": _cell(
                    "version+output_drift",
                    reason="3 divergent field(s): details, tsv, versions",
                ),
                "singularity_galaxy": _cell("passed"),
                "singularity_pull": _cell("passed"),
            },
        }
    ]
    run = _write_run(tmp_path, results)
    data = rv.analyze_run(run, None, 2.0)

    groups = {g["pattern"]: g for g in data["failure_groups"] if g["count"]}
    assert "version+output_drift" in groups
    entry = groups["version+output_drift"]["components"][0]
    assert entry["profile"] == "conda"
    # the cell's own reason is surfaced as the detail message
    assert "divergent field" in entry["message"]
    # docker is 100% passed, conda 0%
    assert data["passed"]["docker"]["percentage"] == 100.0
    assert data["passed"]["conda"]["count"] == 0


def test_analyze_run_snapshot_stale_group(tmp_path):
    results = [
        {
            "component": "pasty",
            "tier": "modules",
            "galaxy": True,
            "cells": {
                p: _cell(
                    "snapshot_stale", reason="committed snapshot ... run --generate"
                )
                for p in PROFILES
            },
        }
    ]
    run = _write_run(tmp_path, results)
    data = rv.analyze_run(run, None, 2.0)
    groups = {g["pattern"]: g for g in data["failure_groups"] if g["count"]}
    assert groups["snapshot_stale"]["count"] == 4


def test_analyze_run_tool_error_uses_reason_over_stdout(tmp_path):
    results = [
        {
            "component": "sistr",
            "tier": "modules",
            "galaxy": True,
            "cells": {
                "docker": _cell("passed"),
                "conda": _cell(
                    "tool_error",
                    reason="ModuleNotFoundError: No module named 'pkg_resources'",
                    error_class="env_dependency",
                ),
                "singularity_galaxy": _cell("passed"),
                "singularity_pull": _cell("passed"),
            },
        }
    ]
    logs = {("modules", "sistr", "conda"): "ERROR ~ Error executing process > 'SISTR'"}
    run = _write_run(tmp_path, results, logs)
    data = rv.analyze_run(run, None, 2.0)

    # stdout classifies the pattern (process_failure) but the concise cell
    # reason wins as the displayed message.
    hits = [
        c
        for g in data["failure_groups"]
        for c in g["components"]
        if c["component"] == "sistr"
    ]
    assert hits and "pkg_resources" in hits[0]["message"]


def test_analyze_run_ignores_na_and_passed(tmp_path):
    results = [
        {
            "component": "foo",
            "tier": "modules",
            "galaxy": False,
            "cells": {
                "docker": _cell("passed"),
                "conda": _cell("passed"),
                "singularity_galaxy": _cell("n/a"),
                "singularity_pull": _cell("passed"),
            },
        }
    ]
    run = _write_run(tmp_path, results)
    data = rv.analyze_run(run, None, 2.0)
    assert all(g["count"] == 0 for g in data["failure_groups"])
    assert data["total_components"] == 1


def test_analyze_run_timing_keyed_on_docker(tmp_path):
    results = [
        {
            "component": "foo",
            "tier": "modules",
            "galaxy": True,
            "cells": {
                "docker": {
                    "status": "passed",
                    "duration": 40.0,
                    "reason": None,
                    "undeclared_outputs": [],
                },
                "conda": {
                    "status": "passed",
                    "duration": 5.0,
                    "reason": None,
                    "undeclared_outputs": [],
                },
                "singularity_galaxy": {
                    "status": "passed",
                    "duration": 6.0,
                    "reason": None,
                    "undeclared_outputs": [],
                },
                "singularity_pull": {
                    "status": "passed",
                    "duration": 7.0,
                    "reason": None,
                    "undeclared_outputs": [],
                },
            },
        }
    ]
    run = _write_run(tmp_path, results)
    data = rv.analyze_run(run, None, 2.0)
    # duration stats derive from the docker cell (40s), not the others
    assert data["duration"]["total_seconds"] == 40.0
