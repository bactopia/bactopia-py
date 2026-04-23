"""CLI command for generating the Bactopia component catalog (catalog.json)."""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.nf import (
    find_main_nf,
    get_bactopia_version,
    parse_groovydoc_full,
    parse_includes,
    parse_main_nf_structure,
    parse_module_config_full,
    parse_workflow_config,
)

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


def _extract_description(groovydoc: dict) -> str:
    """Extract the first line description from GroovyDoc raw lines."""
    if not groovydoc.get("has_doc") or not groovydoc.get("raw_lines"):
        return ""
    for line in groovydoc["raw_lines"]:
        stripped = line.strip().lstrip("* ").strip()
        # Skip empty lines and tag lines
        if not stripped or stripped.startswith("@") or stripped.startswith("/**"):
            continue
        return stripped
    return ""


def _parse_output_fields(raw_lines: list[str]) -> dict[str, list[str]]:
    """Group GroovyDoc @output field names by their parent channel.

    Walks the raw GroovyDoc lines looking for @output headers and their
    associated field description lines (``* - `field`: ...``).

    Returns:
        Dict mapping channel names to lists of field names, e.g.,
        {"sample_outputs": ["gff", "gbk", ...], "run_outputs": []}.
    """
    field_pattern = re.compile(r"\*\s*-\s*`(\w+\??)`\s*:")
    output_pattern = re.compile(r"\*\s*@output\s+(\S+)")
    tag_pattern = re.compile(r"\*\s*@(?!output)\w+")

    channels: dict[str, list[str]] = {}
    current_channel = None

    for line in raw_lines:
        # New @output channel
        m = output_pattern.search(line)
        if m:
            current_channel = m.group(1)
            channels[current_channel] = []
            continue

        # Another tag ends the current @output section
        if tag_pattern.search(line):
            current_channel = None
            continue

        # Field description under current channel
        if current_channel is not None:
            fm = field_pattern.search(line)
            if fm:
                channels[current_channel].append(fm.group(1).rstrip("?"))

    return channels


def _infer_scope(emits: dict[str, list[str]]) -> str:
    """Infer subworkflow scope from emit channels and their documented fields."""
    if emits.get("sample_outputs"):
        return "sample"
    if "run_outputs" in emits:
        return "run"
    return "custom"


def _parse_tags(groovydoc: dict) -> dict | None:
    """Parse GroovyDoc @tags into a structured dict.

    Splits 'complexity:simple input-type:single features:a,b' into
    {"complexity": "simple", "input_type": "single", "features": ["a", "b"]}.
    Returns None if no @tags present.
    """
    raw = groovydoc.get("tags", {}).get("tags", "")
    if not raw:
        return None
    result = {}
    for part in raw.split():
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        # Normalize key: hyphens to underscores for consistency
        key = key.replace("-", "_")
        if key == "features":
            result[key] = [f for f in value.split(",") if f]
        else:
            result[key] = value
    return result or None


def _extract_tool_info(ext: dict) -> dict | None:
    """Extract tool name and version from ext.toolName."""
    raw = ext.get("toolName", "")
    if not raw:
        return None
    # toolName format: "bioconda::abricate=1.2.0".replace(...)
    # Extract just the quoted part
    m = re.match(r'"([^"]+)"', raw)
    if not m:
        return None
    spec = m.group(1)
    # Parse "bioconda::abricate=1.2.0" or multi-package specs
    parts = spec.split()
    if not parts:
        return None
    # Use first package
    pkg = parts[0]
    if "::" in pkg:
        pkg = pkg.split("::", 1)[1]
    if "=" in pkg:
        parts = pkg.split("=")
        return {"name": parts[0], "version": parts[1]}
    return {"name": pkg, "version": "unknown"}


def _clean_scope(raw: str) -> str:
    """Clean ext.scope value (remove quotes)."""
    return raw.strip().strip('"').strip("'")


def _build_module_entry(
    component_name: str, main_nf: Path, bactopia_path: Path
) -> dict:
    """Build a catalog entry for a module."""
    groovydoc = parse_groovydoc_full(main_nf)
    config = parse_module_config_full(main_nf.parent / "module.config")

    entry = {
        "description": _extract_description(groovydoc),
        "path": str(main_nf.parent.relative_to(bactopia_path)) + "/",
    }

    # Scope and process_name from config
    if config["exists"]:
        if "scope" in config["ext"]:
            entry["scope"] = _clean_scope(config["ext"]["scope"])
        if "process_name" in config["ext"]:
            entry["process_name"] = config["ext"]["process_name"].strip('"').strip("'")
        tool = _extract_tool_info(config["ext"])
        if tool:
            entry["tool"] = tool

    # Takes from GroovyDoc @input
    if groovydoc.get("doc_input_records"):
        fields = groovydoc["doc_input_records"][0].get("fields", [])
        if fields:
            entry["takes"] = [f for f in fields if f != "meta"]
            optional_input = groovydoc.get("doc_optional_input_fields", set())
            if optional_input:
                takes_opt = [f for f in entry["takes"] if f in optional_input]
                if takes_opt:
                    entry["takes_optional"] = takes_opt

    # Emits from GroovyDoc @output (named fields only)
    if groovydoc.get("doc_output_fields"):
        standard = {"meta", "results", "logs", "nf_logs", "versions"}
        named = [f for f in groovydoc["doc_output_fields"] if f not in standard]
        if named:
            entry["emits"] = named
            optional_output = groovydoc.get("doc_optional_output_fields", set())
            if optional_output:
                emits_opt = [f for f in named if f in optional_output]
                if emits_opt:
                    entry["emits_optional"] = emits_opt

    # Tags from GroovyDoc @tags
    parsed_tags = _parse_tags(groovydoc)
    if parsed_tags:
        entry["tags"] = parsed_tags

    return entry


def _build_subworkflow_entry(
    component_name: str, main_nf: Path, bactopia_path: Path
) -> dict:
    """Build a catalog entry for a subworkflow."""
    groovydoc = parse_groovydoc_full(main_nf)
    includes = parse_includes(main_nf, bactopia_path)

    entry = {
        "description": _extract_description(groovydoc),
        "path": str(main_nf.parent.relative_to(bactopia_path)) + "/",
    }

    # Takes from GroovyDoc @input
    if groovydoc.get("doc_input_records"):
        fields = groovydoc["doc_input_records"][0].get("fields", [])
        if fields:
            entry["takes"] = [f for f in fields if f != "meta"]
            optional_input = groovydoc.get("doc_optional_input_fields", set())
            if optional_input:
                takes_opt = [f for f in entry["takes"] if f in optional_input]
                if takes_opt:
                    entry["takes_optional"] = takes_opt
    if groovydoc.get("doc_input_params"):
        entry["takes_params"] = groovydoc["doc_input_params"]
        optional_params = groovydoc.get("doc_optional_input_params", set())
        if optional_params:
            params_opt = [p for p in entry["takes_params"] if p in optional_params]
            if params_opt:
                entry["takes_params_optional"] = params_opt

    # Emits from GroovyDoc @output -- structured as channel -> fields dict
    tags = groovydoc.get("tags", {})
    raw_outputs = tags.get("output", [])
    if isinstance(raw_outputs, list) and raw_outputs:
        # Extract channel names (first word only -- some @output lines include descriptions)
        channel_names = [o.split()[0] for o in raw_outputs if o.strip()]
        # Parse field-level detail from raw GroovyDoc lines
        channel_fields = _parse_output_fields(groovydoc.get("raw_lines", []))
        # Build dict: every declared channel gets an entry, even if no fields documented
        entry["emits"] = {ch: channel_fields.get(ch, []) for ch in channel_names}
        entry["scope"] = _infer_scope(entry["emits"])

    # Merlin dynamically dispatches to species-specific subworkflows so its
    # sample_outputs has no fixed field names to document, but it is sample scope.
    if component_name == "merlin":
        entry["scope"] = "sample"

    # Calls
    calls = {}
    if includes["modules"]:
        calls["modules"] = includes["modules"]
    if includes["subworkflows"]:
        calls["subworkflows"] = includes["subworkflows"]
    if calls:
        entry["calls"] = calls

    # Tags from GroovyDoc @tags
    parsed_tags = _parse_tags(groovydoc)
    if parsed_tags:
        entry["tags"] = parsed_tags

    return entry


def _build_workflow_entry(
    component_name: str, main_nf: Path, bactopia_path: Path
) -> dict:
    """Build a catalog entry for a workflow."""
    groovydoc = parse_groovydoc_full(main_nf)
    includes = parse_includes(main_nf, bactopia_path)

    # Determine type
    is_tool = "bactopia-tools/" in str(main_nf)
    wf_path = str(main_nf.parent.relative_to(bactopia_path))
    # Add trailing slash for tool/named workflow directories, but not for the
    # root bactopia workflow which uses a Nextflow convention path
    if is_tool or wf_path != ".":
        wf_path += "/"
    entry = {
        "description": _extract_description(groovydoc),
        "type": "tool" if is_tool else "named",
        "path": wf_path,
    }

    # ext from nextflow.config (bactopia-tools only)
    if is_tool:
        wc = parse_workflow_config(main_nf.parent / "nextflow.config")
        if wc["ext"] is not None:
            entry["ext"] = wc["ext"]

    # Subworkflows called (filter out utils init subworkflows)
    utils_keys = {"utils_bactopia", "utils_bactopia-tools"}
    subworkflows = [s for s in includes["subworkflows"] if s not in utils_keys]
    if subworkflows:
        entry["subworkflows"] = subworkflows

    return entry


def generate_catalog(bactopia_path: Path) -> dict:
    """Generate the complete catalog.json structure.

    Args:
        bactopia_path: Root path of the Bactopia repo.

    Returns:
        The catalog dict ready for JSON serialization.
    """
    # Extract versions from nextflow.config
    bactopia_version = get_bactopia_version(bactopia_path)
    plugin_version = "unknown"
    nf_config = bactopia_path / "nextflow.config"
    if nf_config.exists():
        for line in nf_config.read_text().splitlines():
            m = re.match(r"\s*id\s+['\"]nf-bactopia@([^'\"]+)['\"]", line)
            if m:
                plugin_version = m.group(1)

    catalog = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bactopia_version": bactopia_version,
        "bactopia_py_version": bactopia.__version__,
        "nf_bactopia_version": plugin_version,
        "modules": {},
        "subworkflows": {},
        "workflows": {},
    }

    # Modules
    modules_dir = bactopia_path / "modules"
    for main_nf in find_main_nf(modules_dir):
        rel = main_nf.parent.relative_to(bactopia_path)
        # Skip non-local modules (e.g., modules/nf-core)
        if "local" in str(rel) or "bactopia" in str(rel):
            component_name = (
                str(rel).replace("modules/local/bactopia/", "").replace("modules/", "")
            )
        else:
            component_name = str(rel).replace("modules/", "")
        # Normalize key: slash to underscore (e.g., "abricate/run" -> "abricate_run")
        key = component_name.replace("/", "_")
        catalog["modules"][key] = _build_module_entry(
            component_name, main_nf, bactopia_path
        )

    # Subworkflows
    subworkflows_dir = bactopia_path / "subworkflows"
    for main_nf in find_main_nf(subworkflows_dir):
        rel = main_nf.parent.relative_to(bactopia_path)
        component_name = (
            str(rel).replace("subworkflows/local/", "").replace("subworkflows/", "")
        )
        # Skip test directories and utils (init plumbing)
        if "/tests/" in str(rel) or component_name.startswith("utils/"):
            continue
        key = component_name.replace("/", "_")
        catalog["subworkflows"][key] = _build_subworkflow_entry(
            component_name, main_nf, bactopia_path
        )

    # Workflows
    workflows_dir = bactopia_path / "workflows"
    for main_nf in find_main_nf(workflows_dir):
        rel = main_nf.parent.relative_to(bactopia_path)
        component_name = (
            str(rel).replace("workflows/bactopia-tools/", "").replace("workflows/", "")
        )
        # Skip test directories
        if "/tests/" in str(rel):
            continue
        catalog["workflows"][component_name] = _build_workflow_entry(
            component_name, main_nf, bactopia_path
        )

    # Also include root main.nf as the "bactopia" workflow
    root_main = bactopia_path / "main.nf"
    if root_main.exists():
        catalog["workflows"]["bactopia"] = _build_workflow_entry(
            "bactopia", root_main, bactopia_path
        )

    return catalog


def render_llms_txt(catalog: dict, template_path: Path) -> str:
    """Render llms.txt from a Jinja2 template using catalog data.

    Args:
        catalog: Catalog dict as returned by generate_catalog().
        template_path: Path to the Jinja2 template file.

    Returns:
        Rendered llms.txt content as a string.
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_path.name)
    return template.render(catalog=catalog)


@click.command()
@click.version_option(bactopia.__version__, "--version")
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    default=None,
    help="Output path for catalog.json (default: stdout)",
)
@click.option("--pretty", is_flag=True, help="Pretty-print JSON output.")
@click.option(
    "--llms-output",
    "llms_output_path",
    type=click.Path(),
    default=None,
    help="Also render llms.txt to this path. Uses the bundled template at bactopia/templates/bactopia/llms.txt.j2 unless --llms-template is provided.",
)
@click.option(
    "--llms-template",
    "llms_template_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Jinja2 template for llms.txt. Defaults to the template bundled inside bactopia-py.",
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
def catalog(
    bactopia_path,
    output_path,
    pretty,
    llms_output_path,
    llms_template_path,
    verbose,
):
    """Generate machine-readable catalog of all Bactopia components.

    Produces catalog.json containing workflows, subworkflows, and modules
    with their contracts (takes/emits), dependencies, and metadata.
    Replaces data/workflows.yml as the authoritative component index.

    Optionally also renders llms.txt from a Jinja2 template when
    --llms-output is provided.
    """
    # Setup logs
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.WARNING)

    # Validate path
    bp = Path(bactopia_path).absolute().resolve()
    if not bp.exists():
        logging.error(f"Bactopia path {bactopia_path} does not exist.")
        sys.exit(1)
    if not (bp / "main.nf").exists():
        logging.error(f"No main.nf found in {bp}, is this a valid Bactopia repository?")
        sys.exit(1)

    # Generate catalog
    console = rich.console.Console(stderr=True)
    console.print(f"[bold]bactopia-catalog[/bold] v{bactopia.__version__}")
    console.print(f"Scanning {bp}...")

    data = generate_catalog(bp)

    console.print(
        f"Found {len(data['modules'])} modules, "
        f"{len(data['subworkflows'])} subworkflows, "
        f"{len(data['workflows'])} workflows"
    )

    # Output
    indent = 2 if pretty else None
    output_json = json.dumps(data, indent=indent)

    if output_path:
        Path(output_path).write_text(output_json + "\n")
        console.print(f"Catalog written to {output_path}")
    else:
        print(output_json)

    # Optionally render llms.txt
    if llms_output_path:
        if llms_template_path:
            tpl = Path(llms_template_path)
        else:
            # Bundled template ships inside bactopia-py
            tpl = (
                Path(__file__).parent.parent / "templates" / "bactopia" / "llms.txt.j2"
            )
        tpl = tpl.resolve()
        if not tpl.exists():
            logging.error(f"llms.txt template not found: {tpl}")
            sys.exit(1)
        rendered = render_llms_txt(data, tpl)
        Path(llms_output_path).write_text(rendered)
        console.print(f"llms.txt written to {llms_output_path}")


def main():
    if len(sys.argv) == 1:
        catalog.main(["--help"])
    else:
        catalog()


if __name__ == "__main__":
    main()
