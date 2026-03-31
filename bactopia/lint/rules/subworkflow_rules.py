"""Lint rules for Bactopia subworkflows (S001-S016)."""

import re

from bactopia.lint.models import LintResult


def _pass(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "PASS", component, msg)


def _warn(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "WARN", component, msg)


def _fail(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "FAIL", component, msg)


def _parse_tags_field(tags_value: str) -> dict[str, str]:
    result = {}
    for part in tags_value.split():
        if ":" in part:
            key, value = part.split(":", 1)
            result[key] = value
    return result


def rule_s001(component: str, ctx: dict) -> list[LintResult]:
    """main.nf exists."""
    rid = "S001"
    if ctx["main_nf_path"].exists():
        return [_pass(rid, component, "main.nf exists")]
    return [_fail(rid, component, "main.nf is missing")]


def rule_s002(component: str, ctx: dict) -> list[LintResult]:
    """nextflow.preview.types = true present."""
    rid = "S002"
    if ctx["structure"]["has_types_preview"]:
        return [_pass(rid, component, "nextflow.preview.types = true present")]
    return [_fail(rid, component, "Missing 'nextflow.preview.types = true'")]


def rule_s003(component: str, ctx: dict) -> list[LintResult]:
    """GroovyDoc with required tags."""
    rid = "S003"
    if not ctx["groovydoc"]["has_doc"]:
        return [
            _fail(rid, component, "Missing GroovyDoc block (/** ... */ with @status)")
        ]
    tags = ctx["groovydoc"]["tags"]
    required = ["status", "keywords", "tags", "citation"]
    missing = [t for t in required if t not in tags]
    if not missing:
        return [_pass(rid, component, "GroovyDoc has all required tags")]
    return [
        _fail(
            rid, component, f"Missing required GroovyDoc tags: @{', @'.join(missing)}"
        )
    ]


def rule_s004(component: str, ctx: dict) -> list[LintResult]:
    """Features comma-separated without spaces."""
    rid = "S004"
    tags = ctx["groovydoc"]["tags"]
    tags_value = tags.get("tags", "")
    if not tags_value:
        return []
    parsed = _parse_tags_field(tags_value)
    features = parsed.get("features", "")
    if not features:
        return []
    if ", " in features:
        return [
            _warn(
                rid,
                component,
                f"Features should not have spaces after commas: features:{features}",
            )
        ]
    return [_pass(rid, component, "Features list formatting is correct")]


def rule_s005(component: str, ctx: dict) -> list[LintResult]:
    """Emits sample_outputs and run_outputs."""
    rid = "S005"
    missing = []
    if not ctx["structure"]["emit_has_sample_outputs"]:
        missing.append("sample_outputs")
    if not ctx["structure"]["emit_has_run_outputs"]:
        missing.append("run_outputs")
    if not missing:
        return [_pass(rid, component, "Emits sample_outputs and run_outputs")]
    return [_fail(rid, component, f"Emit block missing: {', '.join(missing)}")]


def rule_s006(component: str, ctx: dict) -> list[LintResult]:
    """Links use HTTPS."""
    rid = "S006"
    links = ctx["groovydoc"].get("links", [])
    http_links = [u for u in links if u.startswith("http://")]
    if not http_links:
        return [_pass(rid, component, "All links use HTTPS")]
    return [_warn(rid, component, f"Links should use HTTPS: {', '.join(http_links)}")]


def rule_s007(component: str, ctx: dict) -> list[LintResult]:
    """No tuple references -- should use record instead."""
    rid = "S007"
    if ctx["structure"]["has_tuple_references"]:
        return [
            _fail(rid, component, "Found 'tuple' reference -- use 'record' instead")
        ]
    return [_pass(rid, component, "No tuple references found")]


def rule_s008(component: str, ctx: dict) -> list[LintResult]:
    """Empty line before main: block."""
    rid = "S008"
    val = ctx["structure"]["has_blank_before_main"]
    if val is None:
        return []  # No main: block found
    if val:
        return [_pass(rid, component, "Blank line before main:")]
    return [_fail(rid, component, "Missing blank line before main:")]


def rule_s009(component: str, ctx: dict) -> list[LintResult]:
    """Empty line before emit: block."""
    rid = "S009"
    val = ctx["structure"]["has_blank_before_emit"]
    if val is None:
        return []  # No emit: block found
    if val:
        return [_pass(rid, component, "Blank line before emit:")]
    return [_fail(rid, component, "Missing blank line before emit:")]


def rule_s010(component: str, ctx: dict) -> list[LintResult]:
    """Emit block has '// Published outputs' comment."""
    rid = "S010"
    if ctx["structure"]["emit_has_published_comment"]:
        return [_pass(rid, component, "'// Published outputs' comment present")]
    return [_fail(rid, component, "Emit block missing '// Published outputs' comment")]


def rule_s011(component: str, ctx: dict) -> list[LintResult]:
    """All include statement closing braces must be vertically aligned."""
    rid = "S011"
    includes = ctx["structure"].get("includes", [])
    if not includes:
        return []
    # content_len accounts for "as" aliases (e.g. "CSVTK_CONCAT as GENES_CONCAT")
    max_content_len = max(inc.get("content_len", len(inc["name"])) for inc in includes)
    # "include { " is 10 chars, then content, then space(s), then "}"
    expected_col = 10 + max_content_len + 1
    misaligned = []
    for inc in includes:
        if inc["brace_col"] != expected_col:
            misaligned.append(
                f"line {inc['line_num']}: '{inc['name']}' brace at col"
                f" {inc['brace_col']}, expected {expected_col}"
            )
    if not misaligned:
        return [_pass(rid, component, "All include braces are aligned")]
    return [
        _fail(rid, component, f"Misaligned include braces: {'; '.join(misaligned)}")
    ]


def rule_s012(component: str, ctx: dict) -> list[LintResult]:
    """Single blank line between last include and workflow declaration."""
    rid = "S012"
    includes = ctx["structure"].get("includes", [])
    wf_line = ctx["structure"].get("workflow_declaration_line_num")
    if not includes or wf_line is None:
        return []
    last_include_line = max(inc["line_num"] for inc in includes)
    gap = wf_line - last_include_line - 1
    if gap == 1:
        return [
            _pass(rid, component, "Single blank line between includes and workflow")
        ]
    return [
        _fail(
            rid,
            component,
            f"Expected 1 blank line between includes (line {last_include_line})"
            f" and workflow (line {wf_line}), found {gap}",
        )
    ]


def rule_s013(component: str, ctx: dict) -> list[LintResult]:
    """gatherCsvtk name must start with lowercase workflow name."""
    rid = "S013"
    calls = ctx["structure"].get("gather_csvtk_calls", [])
    wf_name = ctx["structure"].get("workflow_name")
    if not calls or not wf_name:
        return []
    wf_lower = wf_name.lower()
    mismatched = []
    for call in calls:
        if call["is_dynamic"]:
            continue
        if not call["name"].startswith(wf_lower):
            mismatched.append(
                f"line {call['line_num']}: name '{call['name']}'"
                f" should start with '{wf_lower}'"
            )
    if not mismatched:
        return [_pass(rid, component, "All gatherCsvtk names match workflow name")]
    return [
        _warn(
            rid,
            component,
            f"gatherCsvtk name mismatch: {'; '.join(mismatched)}",
        )
    ]


def rule_s014(component: str, ctx: dict) -> list[LintResult]:
    """gatherCsvtk must only be used with CSVTK_CONCAT."""
    rid = "S014"
    calls = ctx["structure"].get("gather_csvtk_calls", [])
    if not calls:
        return []
    aliases = ctx["structure"].get("csvtk_concat_aliases", set())
    non_csvtk = []
    for call in calls:
        if call["receiver"] not in aliases:
            non_csvtk.append(
                f"line {call['line_num']}: gatherCsvtk output goes to"
                f" {call['receiver']}, not CSVTK_CONCAT"
            )
    if not non_csvtk:
        return [_pass(rid, component, "All gatherCsvtk calls feed into CSVTK_CONCAT")]
    return [_fail(rid, component, f"Invalid gatherCsvtk usage: {'; '.join(non_csvtk)}")]


def rule_s015(component: str, ctx: dict) -> list[LintResult]:
    """Emit mix sources must match between sample_outputs and run_outputs."""
    rid = "S015"
    mix = ctx["structure"].get("emit_mix_sources", {"sample": [], "run": []})
    sample_list = mix["sample"]
    run_list = mix["run"]
    # Only check when mix is used (more than 1 source on either side)
    if len(sample_list) <= 1 and len(run_list) <= 1:
        return []
    sample_set = set(sample_list)
    run_set = set(run_list)
    if sample_set == run_set:
        return [_pass(rid, component, "Emit mix sources match")]
    only_sample = sample_set - run_set
    only_run = run_set - sample_set
    parts = []
    if only_sample:
        parts.append(f"in sample but not run: {', '.join(sorted(only_sample))}")
    if only_run:
        parts.append(f"in run but not sample: {', '.join(sorted(only_run))}")
    return [_warn(rid, component, f"Emit mix source mismatch -- {'; '.join(parts)}")]


def rule_s016(component: str, ctx: dict) -> list[LintResult]:
    """Emit mix order must match between sample_outputs and run_outputs."""
    rid = "S016"
    mix = ctx["structure"].get("emit_mix_sources", {"sample": [], "run": []})
    sample_list = mix["sample"]
    run_list = mix["run"]
    if len(sample_list) <= 1 and len(run_list) <= 1:
        return []
    # Only check order if the sets match (S015 handles mismatches)
    if set(sample_list) != set(run_list):
        return []
    if sample_list == run_list:
        return [_pass(rid, component, "Emit mix order matches")]
    return [
        _warn(
            rid,
            component,
            f"Emit mix order differs: sample={sample_list}, run={run_list}",
        )
    ]


SUBWORKFLOW_RULES = [
    rule_s001,
    rule_s002,
    rule_s003,
    rule_s004,
    rule_s005,
    rule_s006,
    rule_s007,
    rule_s008,
    rule_s009,
    rule_s010,
    rule_s011,
    rule_s012,
    rule_s013,
    rule_s014,
    rule_s015,
    rule_s016,
]
