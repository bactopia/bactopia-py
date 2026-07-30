"""Unit tests for the bactopia-test matrix + classification logic.

These exercise the pure helpers in :mod:`bactopia.cli.testing` with tiny
on-disk fixtures (fake ``output_N.json`` records + byte files) so no docker,
nextflow, or conda is required. They codify the cross-profile drift matrix,
the Command-error classifier, and the derived suggested-edit behaviors.
"""

import json

from bactopia.cli import testing as bt

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------


def _write_cell(comp_dir, profile, records):
    """Create a profile's nf-test work tree from a list of record specs.

    Each record spec is a dict with optional ``process``/``scope`` and a
    ``fields`` map of ``{field: {basename: content}}``. Content may be str or
    bytes. Emits one ``output_<i>.json`` per record, mirroring nf-test.
    """
    meta_dir = comp_dir / profile / ".nf-test" / "tests" / "HASH" / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    for i, rec in enumerate(records):
        work = comp_dir / profile / ".nf-test" / "tests" / "HASH" / "work" / f"r{i}"
        work.mkdir(parents=True, exist_ok=True)
        obj = {
            "meta": {
                "process_name": rec.get("process", "TOOL"),
                "scope": rec.get("scope", "sample"),
            }
        }
        for field, files in rec.get("fields", {}).items():
            paths = []
            for name, content in files.items():
                fp = work / name
                if isinstance(content, bytes):
                    fp.write_bytes(content)
                else:
                    fp.write_text(content)
                paths.append(str(fp))
            obj[field] = paths[0] if len(paths) == 1 else paths
        (meta_dir / f"output_{i}.json").write_text(json.dumps({"0": [obj]}))


# ---------------------------------------------------------------------------
# classify_result
# ---------------------------------------------------------------------------


def test_classify_result_passed():
    assert bt.classify_result("ok", "", 0) == bt.PASSED


def test_classify_result_snapshot_mismatch_does_not_match():
    out = "Snapshot does not match the reference"
    assert bt.classify_result(out, "", 1) == bt.SNAPSHOT_MISMATCH


def test_classify_result_snapshot_mismatch_different_snapshot():
    # nf-test emits "Different Snapshot:" (stderr) -- must still be detected.
    assert (
        bt.classify_result("Snapshot", "Different Snapshot:", 1) == bt.SNAPSHOT_MISMATCH
    )


def test_classify_result_no_snapshot():
    assert bt.classify_result("no such snapshot", "", 1) == bt.NO_SNAPSHOT


def test_classify_result_syntax_error():
    assert bt.classify_result("Compilation failed", "", 1) == bt.SYNTAX_ERROR


def test_classify_result_assertion_failed():
    out = "1 of 2 assertions failed"
    assert bt.classify_result(out, "", 1) == bt.ASSERTION_FAILED


def test_classify_result_tool_error_default():
    assert bt.classify_result("boom", "", 1) == bt.TOOL_ERROR


def test_classify_result_process_failure_is_tool_error_not_assertion():
    # An nf-test assertion message with a Nextflow ERROR marker is a tool error.
    out = "assertion failed\nERROR ~ Error executing process"
    assert bt.classify_result(out, "", 1) == bt.TOOL_ERROR


# ---------------------------------------------------------------------------
# Command error block + reason + error_class
# ---------------------------------------------------------------------------

_PY_BLOCK = """\
  Command error:
    Traceback (most recent call last):
      File "x.py", line 1
    ModuleNotFoundError: No module named 'pkg_resources'
  Work dir:
    /tmp/xx
  Tip: change to the process work dir
"""

_R_BLOCK = """\
  Command error:
    Error:
    ! The `quoted_na` argument of `read_delim()` was deprecated in readr
      2.0.0 and is now defunct.
        2.   +-lifecycle::deprecate_stop(...)
    Execution halted
  Work dir:
    /tmp/yy
"""

_JAVA_CASCADE = _PY_BLOCK + "\nNextflow stdout:\njava.lang.NullPointerException: boom\n"


def test_command_error_block_stops_at_workdir():
    block = bt._command_error_block(_PY_BLOCK)
    assert "ModuleNotFoundError" in block
    assert "Work dir" not in block
    assert "Tip:" not in block


def test_command_error_block_absent():
    assert bt._command_error_block("no block here") == ""


def test_reason_python_exception():
    block = bt._command_error_block(_PY_BLOCK)
    assert (
        bt._reason_from_block(block)
        == "ModuleNotFoundError: No module named 'pkg_resources'"
    )


def test_reason_r_rlang_bang():
    block = bt._command_error_block(_R_BLOCK)
    reason = bt._reason_from_block(block)
    assert "quoted_na" in reason and "deprecated" in reason


def test_reason_skips_java_cascade():
    # The java NPE trails the real cause; reason must come from the block.
    block = bt._command_error_block(_JAVA_CASCADE)
    assert "java" not in bt._reason_from_block(block)


def test_error_class_env_dependency_python():
    assert bt._error_class(_PY_BLOCK.lower()) == "env_dependency"


def test_error_class_env_dependency_r():
    assert bt._error_class(_R_BLOCK) == "env_dependency"


def test_error_class_fs_permission():
    assert bt._error_class("cp: cannot open: Permission denied") == "fs_permission"


def test_error_class_staging_bug():
    assert bt._error_class("cp: 'a' and 'b' are the same file") == "staging_bug"


def test_error_class_tool_crash_on_generic_traceback():
    block = "Traceback (most recent call last):\nValueError: bad value"
    assert bt._error_class(block) == "tool_crash"


def test_error_class_unknown_when_no_signature():
    assert bt._error_class("segfault, no python here") == "unknown"


# ---------------------------------------------------------------------------
# _build_files_matrix
# ---------------------------------------------------------------------------

ALL = list(bt.PROFILES)


def test_matrix_stable_when_all_ran_equal(tmp_path):
    for p in ALL:
        _write_cell(tmp_path, p, [{"fields": {"tsv": {"out.tsv": "same"}}}])
    files = bt._build_files_matrix(tmp_path, ran=ALL)
    (f,) = files
    assert f["verdict"] == "stable"
    assert f["comparable"] is True
    assert f["divergent_profiles"] == []


def test_matrix_divergent_flags_only_the_outlier(tmp_path):
    for p in ALL:
        content = "different" if p == "conda" else "same"
        _write_cell(tmp_path, p, [{"fields": {"tsv": {"out.tsv": content}}}])
    files = bt._build_files_matrix(tmp_path, ran=ALL)
    (f,) = files
    assert f["verdict"] == "divergent"
    assert f["divergent_profiles"] == ["conda"]


def test_matrix_missing_profile_is_indeterminate_not_false_stable(tmp_path):
    # conda crashed and produced no file -> indeterminate, comparable True.
    for p in ("docker", "singularity_galaxy", "singularity_pull"):
        _write_cell(tmp_path, p, [{"fields": {"tsv": {"out.tsv": "same"}}}])
    files = bt._build_files_matrix(tmp_path, ran=ALL)
    (f,) = files
    assert f["verdict"] == "indeterminate"
    assert f["comparable"] is True
    assert f["incomplete"] == ["conda"]


def test_matrix_gz_is_skip_and_noncomparable(tmp_path):
    # gz bytes vary run-to-run; never byte-comparable regardless of content.
    for p in ALL:
        _write_cell(tmp_path, p, [{"fields": {"reads": {"x.fastq.gz": p}}}])
    files = bt._build_files_matrix(tmp_path, ran=ALL)
    (f,) = files
    assert f["verdict"] == "skip"
    assert f["comparable"] is False
    assert "incomplete" not in f


def test_matrix_excludes_non_ran_profile(tmp_path):
    # singularity_galaxy is N/A (not in ran); its absence must not force
    # indeterminate when the ran profiles all agree.
    ran = ["docker", "conda", "singularity_pull"]
    for p in ran:
        _write_cell(tmp_path, p, [{"fields": {"tsv": {"out.tsv": "same"}}}])
    files = bt._build_files_matrix(tmp_path, ran=ran)
    (f,) = files
    assert f["verdict"] == "stable"


def test_matrix_versions_kind_and_tool_key(tmp_path):
    for p in ALL:
        _write_cell(
            tmp_path,
            p,
            [{"process": "PASTY", "fields": {"versions": {"versions.yml": "v"}}}],
        )
    files = bt._build_files_matrix(tmp_path, ran=ALL)
    (f,) = files
    assert f.get("kind") == "versions"
    assert f["tool_key"] == "PASTY"


# ---------------------------------------------------------------------------
# _suggested_edit
# ---------------------------------------------------------------------------


def _fe(field, verdict, **kw):
    entry = {
        "process": kw.get("process", "TOOL"),
        "scope": kw.get("scope", ""),
        "field": field,
        "name": kw.get("name", field),
        "verdict": verdict,
        "divergent_profiles": kw.get("div", []),
    }
    if kw.get("versions"):
        entry["kind"] = "versions"
        entry["tool_key"] = kw.get("tool_key", "TOOL")
    return entry


def test_suggested_edit_module_partitions_fields():
    files = [
        _fe("blast", "stable"),
        _fe("tsv", "divergent", div=["conda"]),
        _fe("versions", "divergent", versions=True, tool_key="pasty", div=["conda"]),
    ]
    edit = bt._suggested_edit(files, "modules")
    assert edit["tier"] == "module"
    assert edit["snapshot"] == ["meta", "blast"]
    assert edit["existence"] == ["tsv"]
    assert edit["contains"] == [{"field": "versions", "value": "pasty"}]


def test_suggested_edit_gz_skip_goes_to_existence():
    files = [_fe("reads", "skip", name="x.fastq.gz")]
    edit = bt._suggested_edit(files, "modules")
    assert edit["existence"] == ["reads"]


def test_suggested_edit_subworkflow_scope_and_per_tool_versions():
    files = [
        _fe("blast", "stable", scope="sample"),
        _fe("tsv", "divergent", scope="sample", div=["conda"]),
        _fe(
            "versions",
            "divergent",
            scope="sample",
            versions=True,
            tool_key="pbptyper",
            div=["conda"],
        ),
        _fe("versions", "stable", scope="run", versions=True, tool_key="csvtk"),
    ]
    edit = bt._suggested_edit(files, "subworkflows")
    assert edit["tier"] == "subworkflow"
    # per-scope meta seeded, stable run.versions kept in snapshot
    assert "sample.meta" in edit["snapshot"] and "run.meta" in edit["snapshot"]
    assert "run.versions" in edit["snapshot"]
    assert edit["existence"] == ["sample.tsv"]
    # only the divergent sample.versions becomes a contains check
    assert edit["contains"] == [{"field": "sample.versions", "value": "pbptyper"}]


# ---------------------------------------------------------------------------
# _finalize_component
# ---------------------------------------------------------------------------


def _cells(**status_by_profile):
    return {
        p: {
            "status": status_by_profile[p],
            "duration": 1.0,
            "undeclared_outputs": [],
            "_stdout": "",
            "_stderr": "",
        }
        for p in bt.PROFILES
    }


def test_finalize_snapshot_stale_cascades(tmp_path):
    # Docker itself fails the committed snapshot on a validate run -> stale.
    cells = _cells(
        docker=bt.ASSERTION_FAILED,
        conda=bt.ASSERTION_FAILED,
        singularity_galaxy=bt.ASSERTION_FAILED,
        singularity_pull=bt.ASSERTION_FAILED,
    )
    bt._finalize_component(tmp_path, "modules", cells, generate=False)
    assert all(c["status"] == bt.SNAPSHOT_STALE for c in cells.values())
    assert "generate" in cells["conda"]["reason"]


def test_finalize_content_drift_reclassifies_from_matrix(tmp_path):
    # Docker passes; conda output + versions diverge -> version+output_drift.
    for p in bt.PROFILES:
        v = "new" if p == "conda" else "old"
        _write_cell(
            tmp_path,
            p,
            [
                {
                    "process": "T",
                    "fields": {"tsv": {"o.tsv": v}, "versions": {"versions.yml": v}},
                }
            ],
        )
    cells = _cells(
        docker=bt.PASSED,
        conda=bt.ASSERTION_FAILED,
        singularity_galaxy=bt.PASSED,
        singularity_pull=bt.PASSED,
    )
    bt._finalize_component(tmp_path, "modules", cells, generate=False)
    assert cells["docker"]["status"] == bt.PASSED
    assert cells["conda"]["status"] == bt.VERSION_OUTPUT_DRIFT
    assert "divergent field" in cells["conda"]["reason"]


def test_finalize_tool_error_sets_class_and_reason(tmp_path):
    cells = _cells(
        docker=bt.PASSED,
        conda=bt.TOOL_ERROR,
        singularity_galaxy=bt.PASSED,
        singularity_pull=bt.PASSED,
    )
    cells["conda"]["_stdout"] = _PY_BLOCK
    bt._finalize_component(tmp_path, "modules", cells, generate=False)
    assert cells["conda"]["error_class"] == "env_dependency"
    assert "pkg_resources" in cells["conda"]["reason"]


def test_finalize_undeclared_union(tmp_path):
    cells = _cells(
        docker=bt.UNDECLARED_OUTPUTS,
        conda=bt.TOOL_ERROR,
        singularity_galaxy=bt.UNDECLARED_OUTPUTS,
        singularity_pull=bt.UNDECLARED_OUTPUTS,
    )
    cells["docker"]["undeclared_outputs"] = ["a.fna"]
    cells["singularity_galaxy"]["undeclared_outputs"] = ["a.fna", "b.txt"]
    _, union, _, _ = bt._finalize_component(tmp_path, "modules", cells, generate=True)
    assert union == ["a.fna", "b.txt"]


def test_finalize_suggested_none_when_all_indeterminate(tmp_path):
    # Only docker produced files; conda/sing crashed -> every file indeterminate.
    _write_cell(tmp_path, "docker", [{"fields": {"tsv": {"o.tsv": "x"}}}])
    cells = _cells(
        docker=bt.UNDECLARED_OUTPUTS,
        conda=bt.TOOL_ERROR,
        singularity_galaxy=bt.TOOL_ERROR,
        singularity_pull=bt.TOOL_ERROR,
    )
    _, _, suggested, _ = bt._finalize_component(
        tmp_path, "modules", cells, generate=True
    )
    assert suggested is None


def test_finalize_passed_cell_keeps_status_despite_residual_divergence(tmp_path):
    # A passing test that only existence-checks still shows conda diverging in
    # files[], but the cell stays 'passed' (matrix is informational there).
    for p in bt.PROFILES:
        v = "new" if p == "conda" else "old"
        _write_cell(tmp_path, p, [{"process": "T", "fields": {"tsv": {"o.tsv": v}}}])
    cells = _cells(
        docker=bt.PASSED,
        conda=bt.PASSED,
        singularity_galaxy=bt.PASSED,
        singularity_pull=bt.PASSED,
    )
    files, _, _, _ = bt._finalize_component(tmp_path, "modules", cells, generate=False)
    assert cells["conda"]["status"] == bt.PASSED
    assert any(
        f["verdict"] == "divergent" and "conda" in f["divergent_profiles"]
        for f in files
    )


# ---------------------------------------------------------------------------
# Closure resolution
# ---------------------------------------------------------------------------

_CATALOG = {
    "modules": {"abricate_run": {"path": "modules/abricate/run/"}, "csvtk_concat": {}},
    "subworkflows": {
        "abricate": {"calls": {"modules": ["abricate_run", "csvtk_concat"]}},
        "nested": {"calls": {"subworkflows": ["abricate"], "modules": []}},
    },
    "workflows": {"btools": {"subworkflows": ["nested"]}},
}


def test_modules_for_module_is_self():
    assert bt._modules_for("abricate_run", _CATALOG) == ["abricate_run"]


def test_modules_for_subworkflow_expands():
    assert bt._modules_for("abricate", _CATALOG) == ["abricate_run", "csvtk_concat"]


def test_modules_for_workflow_walks_nested():
    assert bt._modules_for("btools", _CATALOG) == ["abricate_run", "csvtk_concat"]


def test_modules_for_unknown_returns_none():
    assert bt._modules_for("nope", _CATALOG) is None
