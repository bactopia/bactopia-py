"""Lint rules for Bactopia modules (M001-M015, MC001-MC009, JS001-JS004)."""

import re
from pathlib import Path

from bactopia.lint.models import LintResult

VALID_STATUSES = {"stable", "beta", "deprecated"}
VALID_COMPLEXITIES = {"simple", "moderate", "complex"}
VALID_INPUT_TYPES = {"none", "single", "multiple"}
VALID_OUTPUT_TYPES = {"single", "multiple"}
VALID_FEATURES = {
    "database-dependent",
    "path-workarounds",
    "conditional-input",
    "conditional-logic",
    "compression",
    "archive-output",
    "resource-download",
    "internet-access",
    "alternative-execution",
    "filtering",
    "custom-outputs",
    "aggregation",
    "no-test",
}

TAG_KEYS = {"complexity", "input-type", "output-type", "features"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pass(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "PASS", component, msg)


def _warn(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "WARN", component, msg)


def _fail(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "FAIL", component, msg)


def _parse_tags_field(tags_value: str) -> dict[str, str]:
    """Parse @tags value like 'complexity:simple input-type:single ...' into a dict."""
    result = {}
    for part in tags_value.split():
        if ":" in part:
            key, value = part.split(":", 1)
            result[key] = value
    return result


# Global params that appear in many modules and don't need tool prefix
GLOBAL_PARAMS = {"run_name"}

# Param prefixes that are cross-cutting toggles (use_roary, skip_phylogeny, download_bakta, etc.)
GLOBAL_PARAM_PREFIXES = ("use_", "skip_", "download_")

# Standard subprocess names (the tool is the parent dir)
SUBPROCESS_NAMES = {"run", "summary", "download", "update", "build", "predict"}


def _tool_prefixes_from_component(component: str) -> list[str]:
    """Derive accepted param prefixes for a module.

    For modules/{tool} -> ["tool_"]
    For modules/{tool}/run -> ["tool_"]
    For modules/{tool}/{sub} -> ["tool_", "sub_", "tool_sub_"] (accept any)
    """
    parts = component.replace("modules/", "").split("/")
    if len(parts) == 1:
        return [f"{parts[0]}_"]
    prefixes = [f"{parts[0]}_"]
    if parts[-1] not in SUBPROCESS_NAMES:
        prefixes.append(f"{parts[-1]}_")
        prefixes.append(f"{parts[0]}_{parts[-1]}_")
    return prefixes


def _tool_name_from_component(component: str) -> str:
    """Derive the primary tool name from a component path."""
    parts = component.replace("modules/", "").split("/")
    return parts[0]


def _is_core_module(component: str) -> bool:
    """Check if this is a bactopia/ core module (skip param prefix checks)."""
    return component.startswith("modules/bactopia/")


# ---------------------------------------------------------------------------
# main.nf rules (M001-M015)
# ---------------------------------------------------------------------------


def rule_m001(component: str, ctx: dict) -> list[LintResult]:
    """main.nf exists."""
    rid = "M001"
    if ctx["main_nf_path"].exists():
        return [_pass(rid, component, "main.nf exists")]
    return [_fail(rid, component, "main.nf is missing")]


def rule_m002(component: str, ctx: dict) -> list[LintResult]:
    """module.config exists."""
    rid = "M002"
    if (ctx["component_dir"] / "module.config").exists():
        return [_pass(rid, component, "module.config exists")]
    return [_fail(rid, component, "module.config is missing")]


def rule_m003(component: str, ctx: dict) -> list[LintResult]:
    """schema.json exists."""
    rid = "M003"
    if (ctx["component_dir"] / "schema.json").exists():
        return [_pass(rid, component, "schema.json exists")]
    return [_fail(rid, component, "schema.json is missing")]


def rule_m004(component: str, ctx: dict) -> list[LintResult]:
    """tests/ directory with *.nf.test files."""
    rid = "M004"
    # Skip if the module has no-test in its features
    tags_value = ctx["groovydoc"]["tags"].get("tags", "")
    if tags_value:
        parsed = _parse_tags_field(tags_value)
        features = parsed.get("features", "")
        if "no-test" in features.split(","):
            return [_pass(rid, component, "Skipped (no-test feature)")]
    tests_dir = ctx["component_dir"] / "tests"
    if tests_dir.is_dir() and any(tests_dir.glob("*.nf.test")):
        return [_pass(rid, component, "nf-test files found")]
    return [_warn(rid, component, "No nf-test files found in tests/")]


def rule_m005(component: str, ctx: dict) -> list[LintResult]:
    """nextflow.preview.types = true present."""
    rid = "M005"
    if ctx["structure"]["has_types_preview"]:
        return [_pass(rid, component, "nextflow.preview.types = true present")]
    return [_fail(rid, component, "Missing 'nextflow.preview.types = true'")]


def rule_m006(component: str, ctx: dict) -> list[LintResult]:
    """GroovyDoc block present."""
    rid = "M006"
    if ctx["groovydoc"]["has_doc"]:
        return [_pass(rid, component, "GroovyDoc block present")]
    return [_fail(rid, component, "Missing GroovyDoc block (/** ... */ with @status)")]


def rule_m007(component: str, ctx: dict) -> list[LintResult]:
    """Required GroovyDoc tags: @status, @keywords, @tags, @citation."""
    rid = "M007"
    if not ctx["groovydoc"]["has_doc"]:
        return []  # M006 already covers this
    tags = ctx["groovydoc"]["tags"]
    required = ["status", "keywords", "tags", "citation"]
    missing = [t for t in required if t not in tags]
    if not missing:
        return [_pass(rid, component, "All required GroovyDoc tags present")]
    return [
        _fail(
            rid, component, f"Missing required GroovyDoc tags: @{', @'.join(missing)}"
        )
    ]


def rule_m008(component: str, ctx: dict) -> list[LintResult]:
    """@status value is stable/beta/deprecated."""
    rid = "M008"
    tags = ctx["groovydoc"]["tags"]
    status = tags.get("status", "")
    if not status:
        return []  # M007 covers missing @status
    if status in VALID_STATUSES:
        return [_pass(rid, component, f"@status is valid: {status}")]
    return [
        _fail(
            rid,
            component,
            f"@status '{status}' is not one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    ]


def rule_m009(component: str, ctx: dict) -> list[LintResult]:
    """@tags has complexity, input-type, output-type, features sub-keys."""
    rid = "M009"
    tags = ctx["groovydoc"]["tags"]
    tags_value = tags.get("tags", "")
    if not tags_value:
        return []  # M007 covers missing @tags
    parsed = _parse_tags_field(tags_value)
    missing = [k for k in TAG_KEYS if k not in parsed]
    if not missing:
        return [_pass(rid, component, "@tags has all required sub-keys")]
    return [_fail(rid, component, f"@tags missing sub-keys: {', '.join(missing)}")]


def rule_m010(component: str, ctx: dict) -> list[LintResult]:
    """Features list comma-separated without spaces."""
    rid = "M010"
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


def rule_m011(component: str, ctx: dict) -> list[LintResult]:
    """Process name is UPPER_CASE."""
    rid = "M011"
    name = ctx["structure"]["process_name"]
    if name is None:
        return [_fail(rid, component, "No process definition found")]
    if re.match(r"^[A-Z][A-Z0-9_]*$", name):
        return [_pass(rid, component, f"Process name {name} is UPPER_CASE")]
    return [_fail(rid, component, f"Process name '{name}' should be UPPER_CASE")]


def rule_m012(component: str, ctx: dict) -> list[LintResult]:
    """Output record includes 'versions' field."""
    rid = "M012"
    fields = ctx["structure"]["output_record_fields"]
    if not fields:
        return [_fail(rid, component, "No output record fields found")]
    if "versions" in fields:
        return [_pass(rid, component, "Output record includes 'versions' field")]
    return [_fail(rid, component, "Output record missing 'versions' field")]


def rule_m013(component: str, ctx: dict) -> list[LintResult]:
    """versions.yml created in script block."""
    rid = "M013"
    if ctx["structure"]["has_versions_yml"]:
        return [_pass(rid, component, "versions.yml is created in script block")]
    return [_fail(rid, component, "versions.yml not found in script block")]


def rule_m014(component: str, ctx: dict) -> list[LintResult]:
    """Links use HTTPS not HTTP."""
    rid = "M014"
    links = ctx["groovydoc"].get("links", [])
    http_links = [u for u in links if u.startswith("http://")]
    if not http_links:
        return [_pass(rid, component, "All links use HTTPS")]
    return [_warn(rid, component, f"Links should use HTTPS: {', '.join(http_links)}")]


def rule_m015(component: str, ctx: dict) -> list[LintResult]:
    """No // --- comment markers."""
    rid = "M015"
    if ctx["structure"]["has_comment_markers"]:
        return [
            _warn(rid, component, "Found '// ---' comment markers (should be removed)")
        ]
    return [_pass(rid, component, "No comment markers found")]


def rule_m016(component: str, ctx: dict) -> list[LintResult]:
    """No tuple references -- should use record instead."""
    rid = "M016"
    if ctx["structure"]["has_tuple_references"]:
        return [
            _fail(rid, component, "Found 'tuple' reference -- use 'record' instead")
        ]
    return [_pass(rid, component, "No tuple references found")]


# ---------------------------------------------------------------------------
# module.config rules (MC001-MC009)
# ---------------------------------------------------------------------------


def rule_mc001(component: str, ctx: dict) -> list[LintResult]:
    """Has ext.toolName."""
    rid = "MC001"
    if not ctx["config"]["exists"]:
        return []  # M002 covers this
    if "toolName" in ctx["config"]["ext"]:
        return [_pass(rid, component, "ext.toolName is defined")]
    return [_fail(rid, component, "module.config missing ext.toolName")]


def rule_mc002(component: str, ctx: dict) -> list[LintResult]:
    """Has ext.docker."""
    rid = "MC002"
    if not ctx["config"]["exists"]:
        return []
    if "docker" in ctx["config"]["ext"]:
        return [_pass(rid, component, "ext.docker is defined")]
    return [_fail(rid, component, "module.config missing ext.docker")]


def rule_mc003(component: str, ctx: dict) -> list[LintResult]:
    """Has ext.image."""
    rid = "MC003"
    if not ctx["config"]["exists"]:
        return []
    if "image" in ctx["config"]["ext"]:
        return [_pass(rid, component, "ext.image is defined")]
    return [_fail(rid, component, "module.config missing ext.image")]


def rule_mc004(component: str, ctx: dict) -> list[LintResult]:
    """Has ext.condaDir."""
    rid = "MC004"
    if not ctx["config"]["exists"]:
        return []
    if "condaDir" in ctx["config"]["ext"]:
        return [_pass(rid, component, "ext.condaDir is defined")]
    return [_fail(rid, component, "module.config missing ext.condaDir")]


def rule_mc005(component: str, ctx: dict) -> list[LintResult]:
    """Has ext.wf."""
    rid = "MC005"
    if not ctx["config"]["exists"]:
        return []
    if "wf" in ctx["config"]["ext"]:
        return [_pass(rid, component, "ext.wf is defined")]
    return [_fail(rid, component, "module.config missing ext.wf")]


def rule_mc006(component: str, ctx: dict) -> list[LintResult]:
    """Has ext.scope."""
    rid = "MC006"
    if not ctx["config"]["exists"]:
        return []
    if "scope" in ctx["config"]["ext"]:
        return [_pass(rid, component, "ext.scope is defined")]
    return [_fail(rid, component, "module.config missing ext.scope")]


def rule_mc007(component: str, ctx: dict) -> list[LintResult]:
    """Has ext.process_name."""
    rid = "MC007"
    if not ctx["config"]["exists"]:
        return []
    if "process_name" in ctx["config"]["ext"]:
        return [_pass(rid, component, "ext.process_name is defined")]
    return [_fail(rid, component, "module.config missing ext.process_name")]


def rule_mc008(component: str, ctx: dict) -> list[LintResult]:
    """Container URLs follow expected patterns."""
    rid = "MC008"
    if not ctx["config"]["exists"]:
        return []
    ext = ctx["config"]["ext"]
    issues = []
    docker_val = ext.get("docker", "")
    if docker_val and "biocontainers/" not in docker_val:
        issues.append(f"ext.docker should use biocontainers/ prefix, got: {docker_val}")
    image_val = ext.get("image", "")
    if image_val and "depot.galaxyproject.org/singularity/" not in image_val:
        issues.append(
            f"ext.image should use depot.galaxyproject.org URL, got: {image_val}"
        )
    if issues:
        return [_warn(rid, component, "; ".join(issues))]
    if docker_val or image_val:
        return [_pass(rid, component, "Container URLs follow expected patterns")]
    return []


def rule_mc009(component: str, ctx: dict) -> list[LintResult]:
    """Tool-specific params prefixed with tool name."""
    rid = "MC009"
    if not ctx["config"]["exists"]:
        return []
    if _is_core_module(component):
        return []  # Core modules (modules/bactopia/*) use their own conventions
    params = ctx["config"]["params"]
    if not params:
        return [_pass(rid, component, "No tool-specific params (or all prefixed)")]

    prefixes = _tool_prefixes_from_component(component)
    unprefixed = [
        p["name"]
        for p in params
        if rid not in p.get("ignores", set())
        and not any(p["name"].startswith(pfx) for pfx in prefixes)
        and p["name"] not in GLOBAL_PARAMS
        and not any(p["name"].startswith(gp) for gp in GLOBAL_PARAM_PREFIXES)
    ]
    if unprefixed:
        accepted = " or ".join(f"'{p}'" for p in prefixes)
        return [
            _fail(
                rid,
                component,
                f"Params not prefixed with {accepted}: {', '.join(unprefixed)}",
            )
        ]
    return [_pass(rid, component, "All params correctly prefixed")]


# ---------------------------------------------------------------------------
# schema.json rules (JS001-JS004)
# ---------------------------------------------------------------------------


def rule_js001(component: str, ctx: dict) -> list[LintResult]:
    """Valid JSON."""
    rid = "JS001"
    if not ctx["schema"]["exists"]:
        return []  # M003 covers this
    if ctx["schema"]["valid_json"]:
        return [_pass(rid, component, "schema.json is valid JSON")]
    return [_fail(rid, component, "schema.json is not valid JSON")]


def rule_js002(component: str, ctx: dict) -> list[LintResult]:
    """Has required keys: $schema, $id, title, description, type, $defs, allOf."""
    rid = "JS002"
    if not ctx["schema"]["valid_json"]:
        return []
    missing = [k for k, v in ctx["schema"]["required_keys"].items() if not v]
    if not missing:
        return [_pass(rid, component, "schema.json has all required keys")]
    return [_fail(rid, component, f"schema.json missing keys: {', '.join(missing)}")]


def rule_js003(component: str, ctx: dict) -> list[LintResult]:
    """$defs key follows {tool}_parameters pattern."""
    rid = "JS003"
    if not ctx["schema"]["valid_json"]:
        return []
    if _is_core_module(component):
        return []  # Core modules use their own $defs naming
    defs_keys = ctx["schema"]["defs_keys"]
    if not defs_keys:
        return []
    # Only check keys that end with _parameters (skip non-parameter defs)
    param_keys = [k for k in defs_keys if k.endswith("_parameters")]
    if not param_keys:
        return [_pass(rid, component, "No parameter $defs keys to check")]
    prefixes = _tool_prefixes_from_component(component)
    non_matching = [k for k in param_keys if not any(k.startswith(p) for p in prefixes)]
    if not non_matching:
        return [_pass(rid, component, "$defs key matches expected pattern")]
    return [
        _warn(
            rid,
            component,
            f"$defs keys {non_matching} not prefixed with {prefixes}",
        )
    ]


def _ignored_param_names(ctx: dict, rule_id: str) -> set[str]:
    """Get param names with inline ignores for a rule from module.config."""
    ignored = set()
    for p in ctx.get("config", {}).get("params", []):
        if isinstance(p, dict) and rule_id in p.get("ignores", set()):
            ignored.add(p["name"])
    return ignored


def rule_js004(component: str, ctx: dict) -> list[LintResult]:
    """Parameter names prefixed with tool name."""
    rid = "JS004"
    if not ctx["schema"]["valid_json"]:
        return []
    if _is_core_module(component):
        return []  # Core modules use their own param naming
    param_names = ctx["schema"]["param_names"]
    if not param_names:
        return [_pass(rid, component, "No parameters in schema")]
    # Respect inline ignores from module.config for matching param names
    config_ignored = _ignored_param_names(ctx, rid)
    prefixes = _tool_prefixes_from_component(component)
    unprefixed = [
        p
        for p in param_names
        if not any(p.startswith(pfx) for pfx in prefixes)
        and p not in GLOBAL_PARAMS
        and not any(p.startswith(gp) for gp in GLOBAL_PARAM_PREFIXES)
        and p not in config_ignored
    ]
    if unprefixed:
        accepted = " or ".join(f"'{p}'" for p in prefixes)
        return [
            _warn(
                rid,
                component,
                f"Schema params not prefixed with {accepted}: {', '.join(unprefixed)}",
            )
        ]
    return [_pass(rid, component, "All schema params correctly prefixed")]


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

MODULE_RULES = [
    # main.nf
    rule_m001,
    rule_m002,
    rule_m003,
    rule_m004,
    rule_m005,
    rule_m006,
    rule_m007,
    rule_m008,
    rule_m009,
    rule_m010,
    rule_m011,
    rule_m012,
    rule_m013,
    rule_m014,
    rule_m015,
    rule_m016,
    # module.config
    rule_mc001,
    rule_mc002,
    rule_mc003,
    rule_mc004,
    rule_mc005,
    rule_mc006,
    rule_mc007,
    rule_mc008,
    rule_mc009,
    # schema.json
    rule_js001,
    rule_js002,
    rule_js003,
    rule_js004,
]
