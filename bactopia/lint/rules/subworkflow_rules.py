"""Lint rules for Bactopia subworkflows (S001-S006)."""

import re

from bactopia.lint.models import LintResult


def _pass(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "PASS", component, msg)


def _warn(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "WARN", component, msg)


def _fail(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "FAIL", component, msg)


def _is_tool_subworkflow(component: str) -> bool:
    """Tool subworkflows live under subworkflows/bactopia/ (not utils/)."""
    return "/bactopia/" in component and "/utils/" not in component


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
    """Emits sample_outputs and run_outputs (tool subworkflows only)."""
    rid = "S005"
    if not _is_tool_subworkflow(component):
        return []  # Skip for utils/ subworkflows
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
    if not _is_tool_subworkflow(component):
        return []
    if ctx["structure"]["emit_has_published_comment"]:
        return [_pass(rid, component, "'// Published outputs' comment present")]
    return [_fail(rid, component, "Emit block missing '// Published outputs' comment")]


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
]
