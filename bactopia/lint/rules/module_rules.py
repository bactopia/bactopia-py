"""Lint rules for Bactopia modules (M001-M030, MC001-MC015, JS001-JS005, FMT001-FMT002)."""

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


REQUIRED_META_FIELDS = {"id", "name", "scope", "output_dir", "logs_dir", "process_name"}
GENERIC_OUTPUT_FIELDS = {"results", "logs", "nf_logs", "versions"}
PASSTHROUGH_OUTPUT_FIELDS = {"r1", "r2", "se", "lr"}


def rule_m017(component: str, ctx: dict) -> list[LintResult]:
    """prefix = task.ext.prefix ?: "${meta.name}" present."""
    rid = "M017"
    if ctx["structure"]["has_prefix_definition"]:
        return [_pass(rid, component, "prefix definition present")]
    return [
        _fail(
            rid,
            component,
            'Missing: prefix = task.ext.prefix ?: "${meta.name}"',
        )
    ]


def rule_m018(component: str, ctx: dict) -> list[LintResult]:
    """meta = [:] initialized with all 6 required fields."""
    rid = "M018"
    if not ctx["structure"]["has_meta_init"]:
        return [_fail(rid, component, "Missing meta initialization: meta = [:]")]
    missing = sorted(REQUIRED_META_FIELDS - ctx["structure"]["meta_fields_set"])
    if missing:
        return [
            _fail(
                rid,
                component,
                f"Missing meta fields: meta.{', meta.'.join(missing)}",
            )
        ]
    return [_pass(rid, component, "meta initialized with all required fields")]


def rule_m019(component: str, ctx: dict) -> list[LintResult]:
    """conda directive uses standard pattern."""
    rid = "M019"
    if ctx["structure"]["has_conda_directive"]:
        return [_pass(rid, component, "conda directive present")]
    return [
        _fail(
            rid,
            component,
            'Missing: conda "${task.ext.condaDir}/${task.ext.toolName}"',
        )
    ]


def rule_m020(component: str, ctx: dict) -> list[LintResult]:
    """container directive uses standard pattern."""
    rid = "M020"
    if ctx["structure"]["has_container_directive"]:
        return [_pass(rid, component, "container directive present")]
    return [
        _fail(
            rid,
            component,
            'Missing: container "${task.ext.container}"',
        )
    ]


def rule_m021(component: str, ctx: dict) -> list[LintResult]:
    """No ${meta.name} interpolation -- use ${prefix}."""
    rid = "M021"
    if ctx["structure"]["has_meta_name_interpolation"]:
        return [
            _fail(
                rid,
                component,
                "Found ${meta.name} interpolation -- use ${prefix}",
            )
        ]
    return [_pass(rid, component, "No meta.name interpolation found")]


def rule_m022(component: str, ctx: dict) -> list[LintResult]:
    """# Cleanup comment in script block."""
    rid = "M022"
    if ctx["structure"]["has_cleanup_comment"]:
        return [_pass(rid, component, "# Cleanup comment found in script block")]
    return [_warn(rid, component, "Missing '# Cleanup' comment in script block")]


def rule_m023(component: str, ctx: dict) -> list[LintResult]:
    """Output record has '// Named fields (used downstream)' comment."""
    rid = "M023"
    if ctx["structure"]["output_has_named_comment"]:
        return [_pass(rid, component, "Named fields comment present in output record")]
    return [
        _fail(
            rid,
            component,
            "Missing '// Named fields (used downstream)' comment in output record",
        )
    ]


def rule_m024(component: str, ctx: dict) -> list[LintResult]:
    """Output record has meta: meta field."""
    rid = "M024"
    if ctx["structure"]["output_has_meta_field"]:
        return [_pass(rid, component, "meta: meta field present in output record")]
    return [_fail(rid, component, "Missing 'meta: meta' field in output record")]


def rule_m025(component: str, ctx: dict) -> list[LintResult]:
    """Output record has '// Generic fields (used for publishing)' comment."""
    rid = "M025"
    if ctx["structure"]["output_has_generic_comment"]:
        return [
            _pass(rid, component, "Generic fields comment present in output record")
        ]
    return [
        _fail(
            rid,
            component,
            "Missing '// Generic fields (used for publishing)' comment in output record",
        )
    ]


def rule_m026(component: str, ctx: dict) -> list[LintResult]:
    """Output results is a multi-line list containing files() for every named field."""
    rid = "M026"
    struct = ctx["structure"]
    if not struct["output_has_results"]:
        return [_fail(rid, component, "Missing 'results' field in output record")]
    if not struct["output_results_is_list"]:
        return [_fail(rid, component, "results must be a multi-line list [...]")]
    # Check that every named field pattern is represented in results
    named_patterns = struct["output_named_field_patterns"]
    results_fields = struct["output_results_fields"]
    missing = []
    for field_name, pattern in named_patterns.items():
        if field_name in PASSTHROUGH_OUTPUT_FIELDS:
            continue
        if pattern not in results_fields:
            missing.append(field_name)
    if missing:
        return [
            _fail(
                rid,
                component,
                f"results block missing entries for named fields: {', '.join(missing)}",
            )
        ]
    return [_pass(rid, component, "results block contains all named field outputs")]


def rule_m027(component: str, ctx: dict) -> list[LintResult]:
    """Output record has logs field."""
    rid = "M027"
    if ctx["structure"]["output_has_logs"]:
        return [_pass(rid, component, "logs field present in output record")]
    return [
        _fail(
            rid,
            component,
            'Missing logs field: logs: files("*.{log,err}", optional: true)',
        )
    ]


def rule_m028(component: str, ctx: dict) -> list[LintResult]:
    """Output record has nf_logs field."""
    rid = "M028"
    if ctx["structure"]["output_has_nf_logs"]:
        return [_pass(rid, component, "nf_logs field present in output record")]
    return [
        _fail(
            rid,
            component,
            'Missing nf_logs field: nf_logs: files(".command.*")',
        )
    ]


def rule_m029(component: str, ctx: dict) -> list[LintResult]:
    """Output record versions uses files() not file()."""
    rid = "M029"
    if "versions" not in ctx["structure"]["output_record_fields"]:
        return []  # M012 covers missing versions
    if ctx["structure"]["output_versions_uses_files"]:
        return [_pass(rid, component, "versions uses files()")]
    return [_fail(rid, component, "versions must use files() not file()")]


def rule_m030(component: str, ctx: dict) -> list[LintResult]:
    """All generic fields use files() not file()."""
    rid = "M030"
    bad_fields = ctx["structure"]["output_generic_using_file"]
    if bad_fields:
        return [
            _fail(
                rid,
                component,
                f"Generic fields using file() instead of files(): {', '.join(bad_fields)}",
            )
        ]
    return [_pass(rid, component, "All generic fields use files()")]


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


def _module_name_from_component(component: str) -> str:
    """Derive the expected params block module name from a component path.

    modules/abricate/run -> abricate_run
    modules/mlst -> mlst
    """
    return component.replace("modules/", "").replace("/", "_")


def rule_mc010(component: str, ctx: dict) -> list[LintResult]:
    """params block first line is // module_name or // No parameters."""
    rid = "MC010"
    if not ctx["config"]["exists"]:
        return []
    comment = ctx["config"]["params_comment"]
    if comment is None:
        return [_fail(rid, component, "No comment found in params block")]
    expected_name = _module_name_from_component(component)
    if comment == f"// {expected_name}" or comment == "// No parameters":
        return [_pass(rid, component, f"params comment matches: {comment}")]
    return [
        _fail(
            rid,
            component,
            f"params comment '{comment}' should be '// {expected_name}' or '// No parameters'",
        )
    ]


def rule_mc011(component: str, ctx: dict) -> list[LintResult]:
    """ext.args present (empty string or list+join pattern)."""
    rid = "MC011"
    if not ctx["config"]["exists"]:
        return []
    if ctx["config"]["has_ext_args"]:
        return [_pass(rid, component, "ext.args is defined")]
    return [_fail(rid, component, "module.config missing ext.args")]


def rule_mc012(component: str, ctx: dict) -> list[LintResult]:
    """// Tool arguments section comment present."""
    rid = "MC012"
    if not ctx["config"]["exists"]:
        return []
    if ctx["config"]["has_tool_arguments_comment"]:
        return [_pass(rid, component, "'// Tool arguments' comment present")]
    return [_fail(rid, component, "module.config missing '// Tool arguments' comment")]


def rule_mc013(component: str, ctx: dict) -> list[LintResult]:
    """// Environment information section comment present."""
    rid = "MC013"
    if not ctx["config"]["exists"]:
        return []
    if ctx["config"]["has_environment_comment"]:
        return [_pass(rid, component, "'// Environment information' comment present")]
    return [
        _fail(
            rid, component, "module.config missing '// Environment information' comment"
        )
    ]


def rule_mc014(component: str, ctx: dict) -> list[LintResult]:
    """Section ordering: identity -> tool args -> environment."""
    rid = "MC014"
    if not ctx["config"]["exists"]:
        return []
    # Only check if all three sections are present
    cfg = ctx["config"]
    if not (cfg["has_tool_arguments_comment"] and cfg["has_environment_comment"]):
        return []  # MC012/MC013 cover missing sections
    if cfg["section_order_correct"]:
        return [_pass(rid, component, "Section ordering is correct")]
    return [
        _fail(
            rid,
            component,
            "Sections out of order: expected identity -> tool args -> environment",
        )
    ]


def rule_mc015(component: str, ctx: dict) -> list[LintResult]:
    """params block entries in alphabetical order."""
    rid = "MC015"
    if not ctx["config"]["exists"]:
        return []
    params = ctx["config"]["params"]
    if not params:
        return []  # No params to check
    if ctx["config"]["params_alphabetical"]:
        return [_pass(rid, component, "params are in alphabetical order")]
    names = [p["name"] for p in params]
    return [
        _fail(
            rid,
            component,
            f"params not in alphabetical order: {', '.join(names)}",
        )
    ]


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


def rule_js005(component: str, ctx: dict) -> list[LintResult]:
    """type/default strict match: integer->int, number->float, string->str, boolean->bool."""
    rid = "JS005"
    if not ctx["schema"]["valid_json"]:
        return []
    mismatches = ctx["schema"]["type_default_mismatches"]
    if not mismatches:
        return [_pass(rid, component, "All type/default pairs are consistent")]
    msgs = [
        f"{m['param']}: type={m['type']} but default={m['default']!r}"
        for m in mismatches
    ]
    return [_fail(rid, component, f"Type/default mismatches: {'; '.join(msgs)}")]


# ---------------------------------------------------------------------------
# File formatting rules (FMT001-FMT002)
# ---------------------------------------------------------------------------


def rule_fmt001(component: str, ctx: dict) -> list[LintResult]:
    """No whitespace-only lines in component files."""
    rid = "FMT001"
    whitespace = ctx.get("whitespace", {})
    issues = []
    for filename, ws_data in whitespace.items():
        lines = ws_data.get("whitespace_only_lines", [])
        if lines:
            issues.append(f"{filename} lines {', '.join(str(ln) for ln in lines)}")
    if issues:
        return [_warn(rid, component, f"Whitespace-only lines: {'; '.join(issues)}")]
    return [_pass(rid, component, "No whitespace-only lines")]


def rule_fmt002(component: str, ctx: dict) -> list[LintResult]:
    """No trailing whitespace in component files."""
    rid = "FMT002"
    whitespace = ctx.get("whitespace", {})
    issues = []
    for filename, ws_data in whitespace.items():
        lines = ws_data.get("trailing_whitespace_lines", [])
        if lines:
            issues.append(f"{filename} lines {', '.join(str(ln) for ln in lines)}")
    if issues:
        return [_warn(rid, component, f"Trailing whitespace: {'; '.join(issues)}")]
    return [_pass(rid, component, "No trailing whitespace")]


# ---------------------------------------------------------------------------
# GroovyDoc accuracy rules (M031-M037)
# ---------------------------------------------------------------------------

STANDARD_OUTPUT_FIELDS = {"meta", "results", "logs", "nf_logs", "versions"}

# Expected tag ordering in GroovyDoc
TAG_ORDER = [
    "status",
    "keywords",
    "tags",
    "citation",
    "note",
    "input",
    "output",
    "results",
]


def rule_m031(component: str, ctx: dict) -> list[LintResult]:
    """@output record(...) fields match actual record() output fields."""
    rid = "M031"
    doc = ctx["groovydoc"]
    struct = ctx["structure"]
    if not doc["has_doc"]:
        return []  # M006 covers this
    doc_fields = doc.get("doc_output_fields", [])
    actual_fields = struct.get("output_record_fields", [])
    if not doc_fields and not actual_fields:
        return []  # No output to check (e.g., download modules without @output)
    if not doc_fields:
        return []  # No @output record() in doc -- could be intentional
    if not actual_fields:
        return [
            _fail(
                rid,
                component,
                "@output documents fields but no record() found in output block",
            )
        ]
    if doc_fields == actual_fields:
        return [_pass(rid, component, "@output fields match actual record() output")]
    # Show the difference
    doc_set = set(doc_fields)
    actual_set = set(actual_fields)
    extra_in_doc = sorted(doc_set - actual_set)
    missing_in_doc = sorted(actual_set - doc_set)
    if extra_in_doc or missing_in_doc:
        msgs = []
        if extra_in_doc:
            msgs.append(f"in @output but not in code: {', '.join(extra_in_doc)}")
        if missing_in_doc:
            msgs.append(f"in code but not in @output: {', '.join(missing_in_doc)}")
        return [_fail(rid, component, f"@output field mismatch: {'; '.join(msgs)}")]
    # Same fields but different order -- style issue, not correctness
    return [_warn(rid, component, "@output fields match but order differs from code")]


def rule_m032(component: str, ctx: dict) -> list[LintResult]:
    """@input record(...) fields match actual input Record fields."""
    rid = "M032"
    doc = ctx["groovydoc"]
    struct = ctx["structure"]
    if not doc["has_doc"]:
        return []
    doc_records = doc.get("doc_input_records", [])
    actual_fields = struct.get("input_record_fields", [])
    if not doc_records and not actual_fields:
        return []  # No record inputs
    if not doc_records:
        return []  # No @input record() in doc -- might use different syntax
    if not actual_fields:
        return []  # No Record input in code -- might be a download module
    # Compare the first @input record against actual input record
    doc_fields = doc_records[0]["fields"]
    if doc_fields == actual_fields:
        return [_pass(rid, component, "@input record fields match actual input")]
    doc_set = set(doc_fields)
    actual_set = set(actual_fields)
    extra_in_doc = sorted(doc_set - actual_set)
    missing_in_doc = sorted(actual_set - doc_set)
    msgs = []
    if extra_in_doc:
        msgs.append(f"in @input but not in code: {', '.join(extra_in_doc)}")
    if missing_in_doc:
        msgs.append(f"in code but not in @input: {', '.join(missing_in_doc)}")
    if not msgs:
        msgs.append(
            f"field order differs: doc=[{', '.join(doc_fields)}] vs code=[{', '.join(actual_fields)}]"
        )
    return [_fail(rid, component, f"@input record field mismatch: {'; '.join(msgs)}")]


def rule_m034(component: str, ctx: dict) -> list[LintResult]:
    """@output does not describe standard fields (meta, results, logs, nf_logs, versions)."""
    rid = "M034"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    described = doc.get("doc_output_described_fields", [])
    if not described:
        return []  # No field descriptions at all
    bad_fields = sorted(set(described) & STANDARD_OUTPUT_FIELDS)
    if bad_fields:
        return [
            _warn(
                rid,
                component,
                f"@output describes standard fields that should be skipped: {', '.join(bad_fields)}",
            )
        ]
    return [_pass(rid, component, "@output only describes tool-specific fields")]


def rule_m035(component: str, ctx: dict) -> list[LintResult]:
    """@citation keys exist in data/citations.yml."""
    rid = "M035"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    citation_value = doc["tags"].get("citation", "")
    if not citation_value:
        return []  # M007 covers missing @citation
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


def rule_m036(component: str, ctx: dict) -> list[LintResult]:
    """GroovyDoc tag ordering: @status -> @keywords -> @tags -> @citation -> @note -> @input -> @output."""
    rid = "M036"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    actual_order = doc.get("doc_tag_order", [])
    if not actual_order:
        return []
    # Filter to only known ordered tags
    known_order = [t for t in actual_order if t in TAG_ORDER]
    expected_positions = {t: i for i, t in enumerate(TAG_ORDER)}
    # Check that known tags appear in the correct relative order
    for i in range(len(known_order) - 1):
        curr = known_order[i]
        nxt = known_order[i + 1]
        if expected_positions[curr] > expected_positions[nxt]:
            return [
                _warn(
                    rid,
                    component,
                    f"Tag ordering incorrect: @{curr} appears before @{nxt} "
                    f"(expected: {' -> '.join('@' + t for t in TAG_ORDER if t in known_order)})",
                )
            ]
    return [_pass(rid, component, "GroovyDoc tag ordering is correct")]


def rule_m037(component: str, ctx: dict) -> list[LintResult]:
    """Blank lines between GroovyDoc sections."""
    rid = "M037"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    raw_lines = doc.get("raw_lines", [])
    if not raw_lines:
        return []

    # Check for blank line (just " *" or " * ") before first tag
    # and between tag groups (tags/note, note/input, input/output)
    tag_line_pattern = re.compile(r"\*\s*@(\w+)")
    blank_line_pattern = re.compile(r"^\s*\*\s*$")

    issues = []
    prev_tag = None
    # Track transitions that need blank lines between them
    needs_blank = {
        ("citation", "note"),
        ("citation", "input"),
        ("note", "input"),
        ("input", "output"),
    }

    for i, line in enumerate(raw_lines):
        m = tag_line_pattern.search(line)
        if m:
            curr_tag = m.group(1)
            if prev_tag and (prev_tag, curr_tag) in needs_blank:
                # Check that the previous line is blank
                if i > 0 and not blank_line_pattern.match(raw_lines[i - 1]):
                    issues.append(f"missing blank line before @{curr_tag}")
            # For multi-valued tags (input appearing twice), skip check
            if curr_tag != prev_tag:
                prev_tag = curr_tag

    if issues:
        return [_warn(rid, component, f"GroovyDoc formatting: {'; '.join(issues)}")]
    return [_pass(rid, component, "GroovyDoc section spacing is correct")]


def rule_m038(component: str, ctx: dict) -> list[LintResult]:
    """GroovyDoc does not contain '*/' inside the comment block (e.g., glob patterns with */)."""
    rid = "M038"
    doc = ctx["groovydoc"]
    if not doc["has_doc"]:
        return []
    raw_lines = doc.get("raw_lines", [])
    if not raw_lines:
        return []
    # Check all lines except the last (which legitimately ends with */)
    for i, line in enumerate(raw_lines[:-1]):
        if "*/" in line:
            return [
                _fail(
                    rid,
                    component,
                    f"GroovyDoc line {i + 1} contains '*/' which prematurely closes the comment block "
                    "(likely a glob pattern like 'dir/*/file' -- use directory names instead)",
                )
            ]
    return [_pass(rid, component, "No premature */ in GroovyDoc block")]


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
    rule_m017,
    rule_m018,
    rule_m019,
    rule_m020,
    rule_m021,
    rule_m022,
    rule_m023,
    rule_m024,
    rule_m025,
    rule_m026,
    rule_m027,
    rule_m028,
    rule_m029,
    rule_m030,
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
    rule_mc010,
    rule_mc011,
    rule_mc012,
    rule_mc013,
    rule_mc014,
    rule_mc015,
    # schema.json
    rule_js001,
    rule_js002,
    rule_js003,
    rule_js004,
    rule_js005,
    # GroovyDoc accuracy
    rule_m031,
    rule_m032,
    rule_m034,
    rule_m035,
    rule_m036,
    rule_m037,
    rule_m038,
    # file formatting
    rule_fmt001,
    rule_fmt002,
]
