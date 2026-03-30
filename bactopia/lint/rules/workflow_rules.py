"""Lint rules for Bactopia workflows (W001-W020)."""

import re

from bactopia.lint.models import LintResult


def _pass(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "PASS", component, msg)


def _warn(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "WARN", component, msg)


def _fail(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "FAIL", component, msg)


def rule_w001(component: str, ctx: dict) -> list[LintResult]:
    """main.nf exists."""
    rid = "W001"
    if ctx["main_nf_path"].exists():
        return [_pass(rid, component, "main.nf exists")]
    return [_fail(rid, component, "main.nf is missing")]


def rule_w002(component: str, ctx: dict) -> list[LintResult]:
    """nextflow.preview.types = true present."""
    rid = "W002"
    if ctx["structure"]["has_types_preview"]:
        return [_pass(rid, component, "nextflow.preview.types = true present")]
    return [_fail(rid, component, "Missing 'nextflow.preview.types = true'")]


def rule_w003(component: str, ctx: dict) -> list[LintResult]:
    """GroovyDoc present."""
    rid = "W003"
    if ctx["groovydoc"]["has_doc"]:
        return [_pass(rid, component, "GroovyDoc block present")]
    return [_fail(rid, component, "Missing GroovyDoc block (/** ... */ with @status)")]


def rule_w004(component: str, ctx: dict) -> list[LintResult]:
    """Has @status and @keywords."""
    rid = "W004"
    if not ctx["groovydoc"]["has_doc"]:
        return []  # W003 covers this
    tags = ctx["groovydoc"]["tags"]
    required = ["status", "keywords"]
    missing = [t for t in required if t not in tags]
    if not missing:
        return [_pass(rid, component, "@status and @keywords present")]
    return [_fail(rid, component, f"Missing required tags: @{', @'.join(missing)}")]


def rule_w005(component: str, ctx: dict) -> list[LintResult]:
    """Has @section and @publish tags (entry workflows)."""
    rid = "W005"
    if not ctx["groovydoc"]["has_doc"]:
        return []
    tags = ctx["groovydoc"]["tags"]
    missing = []
    if "section" not in tags:
        missing.append("@section")
    if "publish" not in tags:
        missing.append("@publish")
    if not missing:
        return [_pass(rid, component, "@section and @publish tags present")]
    return [_warn(rid, component, f"Entry workflow missing tags: {', '.join(missing)}")]


def rule_w006(component: str, ctx: dict) -> list[LintResult]:
    """Links use HTTPS."""
    rid = "W006"
    links = ctx["groovydoc"].get("links", [])
    http_links = [u for u in links if u.startswith("http://")]
    if not http_links:
        return [_pass(rid, component, "All links use HTTPS")]
    return [_warn(rid, component, f"Links should use HTTPS: {', '.join(http_links)}")]


def rule_w007(component: str, ctx: dict) -> list[LintResult]:
    """No tuple references -- only .collect { ... tuple(...) } pattern allowed."""
    rid = "W007"

    try:
        lines = ctx["main_nf_path"].read_text().splitlines()
    except OSError:
        return []
    for line in lines:
        stripped = line.strip()
        if not re.search(r"\btuple\b", stripped, re.IGNORECASE):
            continue
        # Allow: .collect { f -> tuple(r.meta, f) }
        if re.search(r"\.collect\s*\{.*\btuple\s*\(", stripped):
            continue
        return [
            _fail(rid, component, "Found 'tuple' reference -- use 'record' instead")
        ]
    return [_pass(rid, component, "No tuple type references found")]


# Controlled vocabulary for params.workflow.ext values
VALID_EXT_KEYS = {
    "fna",  # assembled genome
    "fna_anno",  # annotator-formatted assembly
    "faa",  # protein sequences
    "gff",  # gene coordinates
    "gbk",  # GenBank file
    "tsv_meta",  # analysis metadata TSV
    "blastdb",  # BLAST database
    "r1",  # forward reads (Illumina PE)
    "r2",  # reverse reads (Illumina PE)
    "se",  # single-end reads (Illumina SE)
    "lr",  # long reads (ONT/PacBio)
    "fastq",  # alias: expands to r1, r2, se, lr
}


def _is_bactopia_tool(component: str) -> bool:
    """Check if a workflow component is a bactopia-tool (not a named workflow)."""
    return "bactopia-tools/" in component


def rule_w008(component: str, ctx: dict) -> list[LintResult]:
    """params.workflow.ext is a list (bactopia-tools only)."""
    rid = "W008"
    if not _is_bactopia_tool(component):
        return []  # Named workflows don't use ext
    wc = ctx.get("workflow_config")
    if not wc or not wc["exists"]:
        return [_fail(rid, component, "nextflow.config is missing")]
    if wc["ext"] is not None:
        return [_pass(rid, component, "params.workflow.ext is a list")]
    if wc["ext_raw"] is not None:
        return [
            _fail(
                rid,
                component,
                f"params.workflow.ext is a string ('{wc['ext_raw']}'), must be a list",
            )
        ]
    return [_fail(rid, component, "params.workflow.ext is missing")]


def rule_w009(component: str, ctx: dict) -> list[LintResult]:
    """params.workflow.ext values are from controlled vocabulary."""
    rid = "W009"
    if not _is_bactopia_tool(component):
        return []
    wc = ctx.get("workflow_config")
    if not wc or not wc["exists"] or wc["ext"] is None:
        return []  # W008 covers missing/invalid ext
    invalid = [v for v in wc["ext"] if v not in VALID_EXT_KEYS]
    if not invalid:
        return [_pass(rid, component, "All ext values are valid")]
    return [_fail(rid, component, f"Invalid ext values: {', '.join(invalid)}")]


def rule_w010(component: str, ctx: dict) -> list[LintResult]:
    """params.workflow.ext is not empty."""
    rid = "W010"
    if not _is_bactopia_tool(component):
        return []
    wc = ctx.get("workflow_config")
    if not wc or not wc["exists"] or wc["ext"] is None:
        return []  # W008 covers missing/invalid ext
    if len(wc["ext"]) > 0:
        return [
            _pass(rid, component, f"params.workflow.ext has {len(wc['ext'])} value(s)")
        ]
    return [_fail(rid, component, "params.workflow.ext is an empty list")]


CANONICAL_OUTPUT_BLOCK = """\
output {
    // Sample-level outputs (stored in ${params.outdir}/<SAMPLE_NAME>/)
    sample_outputs {
        path { r ->
            r.results.flatten()  >> "${r.meta.output_dir}/"
            r.logs.flatten()     >> "${r.meta.logs_dir}/"
            r.versions.flatten() >> "${r.meta.logs_dir}/"
        }
    }
    sample_nf_logs {
        path { meta, f -> f >> "${meta.logs_dir}/nf${f.name}" }
    }

    // Run-level outputs (stored in ${params.outdir}/bactopia-runs/<RUN_NAME>/)
    run_outputs {
        path { r ->
            r.results.flatten()  >> "${params.rundir}/${r.meta.output_dir}/"
            r.logs.flatten()     >> "${params.rundir}/${r.meta.logs_dir}/"
            r.versions.flatten() >> "${params.rundir}/${r.meta.logs_dir}/"
        }
    }
    run_nf_logs {
        path { meta, f -> f >> "${params.rundir}/${meta.logs_dir}/nf${f.name}" }
    }
}"""


def rule_w011(component: str, ctx: dict) -> list[LintResult]:
    """First line must be shebang."""
    rid = "W011"
    first = ctx["structure"].get("first_line", "")
    if first == "#!/usr/bin/env nextflow":
        return [_pass(rid, component, "Shebang line present")]
    return [
        _fail(
            rid,
            component,
            f"First line must be '#!/usr/bin/env nextflow', got: '{first}'",
        )
    ]


def rule_w012(component: str, ctx: dict) -> list[LintResult]:
    """Flag TODO comments as warnings."""
    rid = "W012"
    todos = ctx["structure"].get("todos", [])
    if not todos:
        return [_pass(rid, component, "No TODO comments found")]
    results = []
    for t in todos:
        results.append(
            _warn(rid, component, f"TODO on line {t['line_num']}: {t['text']}")
        )
    return results


def rule_w013(component: str, ctx: dict) -> list[LintResult]:
    """Only .mix() channel operator allowed in workflows."""
    rid = "W013"
    ops = ctx["structure"].get("channel_operators", [])
    if not ops:
        return [_pass(rid, component, "No disallowed channel operators")]
    results = []
    for op in ops:
        results.append(
            _fail(
                rid,
                component,
                f"Line {op['line_num']}: .{op['operator']}() not allowed in workflows"
                f" -- move to nf-bactopia plugin",
            )
        )
    return results


def rule_w014(component: str, ctx: dict) -> list[LintResult]:
    """Must import collectNextflowLogs from plugin/nf-bactopia."""
    rid = "W014"
    if ctx["structure"].get("has_collect_nf_logs_import", False):
        return [_pass(rid, component, "collectNextflowLogs import present")]
    return [
        _fail(
            rid,
            component,
            "Missing: include { collectNextflowLogs } from 'plugin/nf-bactopia'",
        )
    ]


def rule_w015(component: str, ctx: dict) -> list[LintResult]:
    """Output block must match canonical structure."""
    rid = "W015"
    actual = ctx["structure"].get("wf_output_block_text", "")
    if not actual:
        return [_fail(rid, component, "No top-level output {} block found")]
    # Compare line-by-line after stripping trailing whitespace
    expected_lines = CANONICAL_OUTPUT_BLOCK.splitlines()
    actual_lines = actual.splitlines()
    for i, (exp, act) in enumerate(zip(expected_lines, actual_lines), 1):
        if exp.rstrip() != act.rstrip():
            return [
                _fail(
                    rid,
                    component,
                    f"Output block differs at line {i}: expected '{exp.strip()}',"
                    f" got '{act.strip()}'",
                )
            ]
    if len(expected_lines) != len(actual_lines):
        return [
            _fail(
                rid,
                component,
                f"Output block has {len(actual_lines)} lines,"
                f" expected {len(expected_lines)}",
            )
        ]
    return [_pass(rid, component, "Output block matches canonical structure")]


def rule_w016(component: str, ctx: dict) -> list[LintResult]:
    """Publish block structure with verbatim comments and scope consistency."""
    rid = "W016"
    pub_lines = ctx["structure"].get("publish_block_lines", [])
    if not pub_lines:
        return [_fail(rid, component, "No publish block found")]

    results = []
    # Check verbatim comments exist and are in order
    comment_lines = [line for line in pub_lines if line.startswith("//")]
    expected_comments = ["// Per-sample", "// Run-level"]
    if comment_lines != expected_comments:
        results.append(
            _fail(
                rid,
                component,
                f"Publish block comments must be {expected_comments},"
                f" got {comment_lines}",
            )
        )

    # Check scope consistency: sample lines reference .sample_outputs,
    # run lines reference .run_outputs
    in_sample = False
    in_run = False
    for line in pub_lines:
        if line == "// Per-sample":
            in_sample = True
            in_run = False
            continue
        if line == "// Run-level":
            in_run = True
            in_sample = False
            continue
        if "=" not in line:
            continue
        lhs, rhs = line.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()
        if in_sample and lhs in ("sample_outputs", "sample_nf_logs"):
            if "run_outputs" in rhs:
                results.append(
                    _fail(
                        rid,
                        component,
                        f"'{lhs}' references run_outputs instead of sample_outputs",
                    )
                )
        if in_run and lhs in ("run_outputs", "run_nf_logs"):
            if "sample_outputs" in rhs:
                results.append(
                    _fail(
                        rid,
                        component,
                        f"'{lhs}' references sample_outputs instead of run_outputs",
                    )
                )

    if not results:
        return [_pass(rid, component, "Publish block structure is correct")]
    return results


def rule_w017(component: str, ctx: dict) -> list[LintResult]:
    """Params block must exist with rundir : String as first param."""
    rid = "W017"
    pb = ctx["structure"].get("wf_params_block", {})
    if not pb.get("exists"):
        return [_fail(rid, component, "No params {} block found")]
    if pb["first_param"] != "rundir":
        return [
            _fail(
                rid,
                component,
                f"First param must be 'rundir', got '{pb['first_param']}'",
            )
        ]
    # Check single space format: "    rundir : String"
    first_line = pb.get("first_param_line", "")
    stripped = first_line.strip()
    if not stripped.startswith("rundir : "):
        return [
            _fail(
                rid,
                component,
                f"rundir must use single space format 'rundir : String',"
                f" got '{stripped}'",
            )
        ]
    return [_pass(rid, component, "Params block has 'rundir : String' as first param")]


def rule_w018(component: str, ctx: dict) -> list[LintResult]:
    """All include statement closing braces must be vertically aligned."""
    rid = "W018"
    includes = ctx["structure"].get("includes", [])
    if not includes:
        return []  # No includes to check
    # Expected brace column based on longest name
    max_name_len = max(len(inc["name"]) for inc in includes)
    # Format: "include { NAME<spaces>} from ..."
    # "include { " is 10 chars, then name, then space(s), then "}"
    expected_col = 10 + max_name_len + 1  # +1 for the space before }
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


def rule_w019(component: str, ctx: dict) -> list[LintResult]:
    """All params (except rundir) must have colons vertically aligned."""
    rid = "W019"
    pb = ctx["structure"].get("wf_params_block", {})
    if not pb.get("exists"):
        return []  # W017 covers missing params
    # Exclude rundir (first param) from alignment check
    other_params = [p for p in pb["params"] if p["name"] != "rundir"]
    if not other_params:
        return [_pass(rid, component, "No params to align (only rundir)")]
    # Expected colon column based on longest param name
    # Params are indented 4 spaces: "    name<spaces>: Type"
    max_name_len = max(len(p["name"]) for p in other_params)
    expected_col = 4 + max_name_len + 1  # indent + name + space before :
    misaligned = []
    for p in other_params:
        if p["colon_col"] != expected_col:
            misaligned.append(
                f"line {p['line_num']}: '{p['name']}' colon at col"
                f" {p['colon_col']}, expected {expected_col}"
            )
    if not misaligned:
        return [_pass(rid, component, "All param colons are aligned")]
    return [_fail(rid, component, f"Misaligned param colons: {'; '.join(misaligned)}")]


def rule_w020(component: str, ctx: dict) -> list[LintResult]:
    """sample_outputs and run_outputs mix sources must match."""
    rid = "W020"
    mix = ctx["structure"].get("mix_sources", {"sample": [], "run": []})
    sample_sources = mix["sample"]
    run_sources = mix["run"]
    if not sample_sources and not run_sources:
        return []  # No mix chains found -- skip

    # Normalize sources: extract prefix before .sample_outputs / .run_outputs
    def _normalize(sources: list[str]) -> set[str]:
        normalized = set()
        for s in sources:
            # Strip .sample_outputs or .run_outputs suffix to get the prefix
            s = re.sub(r"\.(sample_outputs|run_outputs)$", "", s)
            normalized.add(s)
        return normalized

    sample_set = _normalize(sample_sources)
    run_set = _normalize(run_sources)
    if sample_set == run_set:
        return [_pass(rid, component, "sample and run mix sources match")]

    only_sample = sample_set - run_set
    only_run = run_set - sample_set
    parts = []
    if only_sample:
        parts.append(f"in sample but not run: {', '.join(sorted(only_sample))}")
    if only_run:
        parts.append(f"in run but not sample: {', '.join(sorted(only_run))}")
    return [_warn(rid, component, f"Mix source mismatch -- {'; '.join(parts)}")]


WORKFLOW_RULES = [
    rule_w001,
    rule_w002,
    rule_w003,
    rule_w004,
    rule_w005,
    rule_w006,
    rule_w007,
    rule_w008,
    rule_w009,
    rule_w010,
    rule_w011,
    rule_w012,
    rule_w013,
    rule_w014,
    rule_w015,
    rule_w016,
    rule_w017,
    rule_w018,
    rule_w019,
    rule_w020,
]
