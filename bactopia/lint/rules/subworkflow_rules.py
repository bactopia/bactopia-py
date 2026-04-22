"""Lint rules for Bactopia subworkflows (S001-S025)."""

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


def _parse_doc_component_list(tag_value: str) -> set[str]:
    """Parse a @modules or @subworkflows tag value into a set of normalized names.

    Handles comma-separated names with optional 'as alias' notation.
    E.g., "prokka as prokka_module, csvtk_concat" -> {"prokka", "csvtk_concat"}
    """
    names = set()
    if not tag_value:
        return names
    for entry in tag_value.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # Handle "name as alias" notation -- extract base name
        parts = entry.split()
        if len(parts) >= 3 and parts[1] == "as":
            names.add(parts[0])
        else:
            names.add(parts[0])
    return names


def rule_s017(component: str, ctx: dict) -> list[LintResult]:
    """@modules match actual module includes."""
    rid = "S017"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    includes = ctx.get("includes", {})
    actual_modules = set(includes.get("modules", []))
    doc_value = doc["tags"].get("modules", "")
    doc_modules = _parse_doc_component_list(doc_value)
    # Skip if neither GroovyDoc nor includes mention modules
    if not actual_modules and not doc_modules:
        return []
    if doc_modules == actual_modules:
        return [_pass(rid, component, "@modules match actual includes")]
    missing = actual_modules - doc_modules
    extra = doc_modules - actual_modules
    parts = []
    if missing:
        parts.append(f"missing from @modules: {', '.join(sorted(missing))}")
    if extra:
        parts.append(f"extra in @modules: {', '.join(sorted(extra))}")
    return [_fail(rid, component, f"@modules mismatch: {'; '.join(parts)}")]


def rule_s018(component: str, ctx: dict) -> list[LintResult]:
    """@subworkflows match actual subworkflow includes."""
    rid = "S018"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    includes = ctx.get("includes", {})
    actual_subs = set(includes.get("subworkflows", []))
    doc_value = doc["tags"].get("subworkflows", "")
    doc_subs = _parse_doc_component_list(doc_value)
    # Skip if neither GroovyDoc nor includes mention subworkflows
    if not actual_subs and not doc_subs:
        return []
    if doc_subs == actual_subs:
        return [_pass(rid, component, "@subworkflows match actual includes")]
    missing = actual_subs - doc_subs
    extra = doc_subs - actual_subs
    parts = []
    if missing:
        parts.append(f"missing from @subworkflows: {', '.join(sorted(missing))}")
    if extra:
        parts.append(f"extra in @subworkflows: {', '.join(sorted(extra))}")
    return [_fail(rid, component, f"@subworkflows mismatch: {'; '.join(parts)}")]


def rule_s019(component: str, ctx: dict) -> list[LintResult]:
    """@citation keys exist in data/citations.yml."""
    rid = "S019"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    citation_value = doc["tags"].get("citation", "")
    if not citation_value:
        return []  # S003 covers missing @citation
    citation_keys = ctx.get("citation_keys", set())
    if not citation_keys:
        return []  # citations.yml not available -- skip check
    keys = [k.strip() for k in citation_value.split(",")]
    invalid = [k for k in keys if k and k not in citation_keys]
    if invalid:
        return [
            _fail(
                rid,
                component,
                f"@citation keys not in citations.yml: {', '.join(invalid)}",
            )
        ]
    return [_pass(rid, component, "All @citation keys are valid")]


def rule_s020(component: str, ctx: dict) -> list[LintResult]:
    """@tags complexity value is valid."""
    rid = "S020"
    tags = ctx["groovydoc"]["tags"]
    tags_value = tags.get("tags", "")
    if not tags_value:
        return []
    parsed = _parse_tags_field(tags_value)
    complexity = parsed.get("complexity", "")
    if not complexity:
        return []
    valid = {"simple", "moderate", "complex"}
    if complexity in valid:
        return [_pass(rid, component, f"complexity:{complexity} is valid")]
    return [
        _warn(
            rid,
            component,
            f"Invalid complexity value '{complexity}', expected one of: {', '.join(sorted(valid))}",
        )
    ]


def rule_s021(component: str, ctx: dict) -> list[LintResult]:
    """@tags input-type value is valid."""
    rid = "S021"
    tags = ctx["groovydoc"]["tags"]
    tags_value = tags.get("tags", "")
    if not tags_value:
        return []
    parsed = _parse_tags_field(tags_value)
    input_type = parsed.get("input-type", "")
    if not input_type:
        return []
    valid = {"none", "single", "multiple", "parameter"}
    if input_type in valid:
        return [_pass(rid, component, f"input-type:{input_type} is valid")]
    return [
        _warn(
            rid,
            component,
            f"Invalid input-type value '{input_type}', expected one of: {', '.join(sorted(valid))}",
        )
    ]


def rule_s022(component: str, ctx: dict) -> list[LintResult]:
    """@tags output-type value is valid."""
    rid = "S022"
    tags = ctx["groovydoc"]["tags"]
    tags_value = tags.get("tags", "")
    if not tags_value:
        return []
    parsed = _parse_tags_field(tags_value)
    output_type = parsed.get("output-type", "")
    if not output_type:
        return []
    valid = {"single", "multiple"}
    if output_type in valid:
        return [_pass(rid, component, f"output-type:{output_type} is valid")]
    return [
        _warn(
            rid,
            component,
            f"Invalid output-type value '{output_type}', expected one of: {', '.join(sorted(valid))}",
        )
    ]


VALID_FEATURES = {
    "aggregation",
    "alternative-execution",
    "archive-output",
    "components",
    "compression",
    "conditional-input",
    "conditional-logic",
    "database-dependent",
    "internet-access",
    "no-test",
    "resource-download",
}


def rule_s023(component: str, ctx: dict) -> list[LintResult]:
    """@tags features values are valid."""
    rid = "S023"
    tags = ctx["groovydoc"]["tags"]
    tags_value = tags.get("tags", "")
    if not tags_value:
        return []
    parsed = _parse_tags_field(tags_value)
    features = parsed.get("features", "")
    if not features:
        return []
    feature_list = [f.strip() for f in features.split(",")]
    invalid = [f for f in feature_list if f and f not in VALID_FEATURES]
    if invalid:
        return [
            _fail(
                rid,
                component,
                f"Invalid feature values: {', '.join(invalid)} "
                f"(valid: {', '.join(sorted(VALID_FEATURES))})",
            )
        ]
    return [_pass(rid, component, "All feature values are valid")]


# Canonical tag order for subworkflows
SUBWORKFLOW_TAG_ORDER = [
    "status",
    "keywords",
    "tags",
    "citation",
    "modules",
    "subworkflows",
    "note",
    "input",
    "output",
]


def rule_s024(component: str, ctx: dict) -> list[LintResult]:
    """GroovyDoc tag ordering."""
    rid = "S024"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    actual_order = doc.get("doc_tag_order", [])
    if not actual_order:
        return []
    known_order = [t for t in actual_order if t in SUBWORKFLOW_TAG_ORDER]
    expected_positions = {t: i for i, t in enumerate(SUBWORKFLOW_TAG_ORDER)}
    for i in range(len(known_order) - 1):
        curr = known_order[i]
        nxt = known_order[i + 1]
        if expected_positions[curr] > expected_positions[nxt]:
            return [
                _warn(
                    rid,
                    component,
                    f"Tag ordering incorrect: @{curr} appears before @{nxt} "
                    f"(expected: {' -> '.join('@' + t for t in SUBWORKFLOW_TAG_ORDER if t in known_order)})",
                )
            ]
    return [_pass(rid, component, "GroovyDoc tag ordering is correct")]


WRAPPED_PATH_TYPES = {"Value<Path>", "Value<Path?>"}


def rule_s025(component: str, ctx: dict) -> list[LintResult]:
    """Take-block Path inputs must not use Value<Path> wrapper (use bare Path or Path?)."""
    rid = "S025"
    take_inputs = ctx["structure"].get("sw_take_inputs", [])
    if not take_inputs:
        return []
    violations = []
    for inp in take_inputs:
        itype = inp.get("type", "")
        if itype in WRAPPED_PATH_TYPES:
            suggested = "Path?" if itype == "Value<Path?>" else "Path"
            violations.append(
                _fail(
                    rid,
                    component,
                    f"Take input '{inp['name']}' uses {itype} -- use {suggested} instead (line {inp['line_num']})",
                )
            )
    if not violations:
        return [_pass(rid, component, "No take-inputs use Value<Path> wrapper")]
    return violations


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
    rule_s017,
    rule_s018,
    rule_s019,
    rule_s020,
    rule_s021,
    rule_s022,
    rule_s023,
    rule_s024,
    rule_s025,
]
