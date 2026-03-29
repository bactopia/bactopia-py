"""Lint rules for Bactopia workflows (W001-W006)."""

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
    import re

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
]
