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
    parse_groovydoc_full,
    parse_main_nf_structure,
    parse_module_config_full,
    parse_workflow_config,
)

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


def _parse_includes(main_nf: Path, bactopia_path: Path) -> dict:
    """Parse include statements from a main.nf file.

    Resolves source paths against the file's directory and the repo root
    to derive normalized component keys (lowercase, underscore-separated).

    Returns dict with:
        modules: list of module keys (e.g., "abricate_run")
        subworkflows: list of subworkflow keys (e.g., "bactopia_gather")
        plugins: list of plugin function names
    """
    result = {"modules": [], "subworkflows": [], "plugins": []}
    if not main_nf.exists():
        return result

    try:
        text = main_nf.read_text()
    except OSError:
        return result

    seen_modules = set()
    seen_subworkflows = set()

    for m in re.finditer(
        r"include\s*\{\s*(\w+)(?:\s+as\s+\w+)?\s*\}\s*from\s*['\"]([^'\"]+)['\"]",
        text,
    ):
        source = m.group(2)

        if "plugin/" in source:
            result["plugins"].append(m.group(1))
            continue

        # Resolve the source path relative to the file's directory
        # Nextflow source paths omit .nf extension; parent of resolved path
        # is the component directory
        resolved = (main_nf.parent / source).resolve()

        try:
            rel_str = str(resolved.relative_to(bactopia_path))
        except ValueError:
            continue

        if rel_str.startswith("modules/"):
            # e.g., "modules/abricate/run/main" -> "abricate/run"
            component = rel_str.removeprefix("modules/")
            if component.endswith("/main"):
                component = component[:-5]
            key = component.replace("/", "_")
            if key not in seen_modules:
                seen_modules.add(key)
                result["modules"].append(key)
        elif rel_str.startswith("subworkflows/"):
            # e.g., "subworkflows/bactopia/gather/main" -> "bactopia/gather"
            component = rel_str.removeprefix("subworkflows/")
            if component.endswith("/main"):
                component = component[:-5]
            key = component.replace("/", "_")
            if key not in seen_subworkflows:
                seen_subworkflows.add(key)
                result["subworkflows"].append(key)

    return result


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
    field_pattern = re.compile(r"\*\s*-\s*`(\w+)`\s*:")
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
                channels[current_channel].append(fm.group(1))

    return channels


def _infer_scope(channels: list[str]) -> str:
    """Infer subworkflow scope from emit channel names."""
    has_sample = "sample_outputs" in channels
    has_run = "run_outputs" in channels
    if has_sample:
        return "sample"
    if has_run:
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
        name, version = pkg.rsplit("=", 1)
        return {"name": name, "version": version}
    return {"name": pkg, "version": "unknown"}


def _clean_scope(raw: str) -> str:
    """Clean ext.scope value (remove quotes)."""
    return raw.strip().strip('"').strip("'")


def _build_module_entry(component_name: str, main_nf: Path) -> dict:
    """Build a catalog entry for a module."""
    groovydoc = parse_groovydoc_full(main_nf)
    config = parse_module_config_full(main_nf.parent / "module.config")

    entry = {
        "description": _extract_description(groovydoc),
        "path": str(main_nf.parent.relative_to(main_nf.parents[3])) + "/",
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

    # Emits from GroovyDoc @output (named fields only)
    if groovydoc.get("doc_output_fields"):
        standard = {"meta", "results", "logs", "nf_logs", "versions"}
        named = [f for f in groovydoc["doc_output_fields"] if f not in standard]
        if named:
            entry["emits"] = named

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
    includes = _parse_includes(main_nf, bactopia_path)

    entry = {
        "description": _extract_description(groovydoc),
        "path": str(main_nf.parent.relative_to(main_nf.parents[3])) + "/",
    }

    # Takes from GroovyDoc @input
    if groovydoc.get("doc_input_records"):
        fields = groovydoc["doc_input_records"][0].get("fields", [])
        if fields:
            entry["takes"] = [f for f in fields if f != "meta"]
    if groovydoc.get("doc_input_params"):
        entry["takes_params"] = groovydoc["doc_input_params"]

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
        entry["scope"] = _infer_scope(channel_names)

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
    includes = _parse_includes(main_nf, bactopia_path)

    # Determine type
    is_tool = "bactopia-tools/" in str(main_nf)
    wf_path = str(main_nf.parent.relative_to(main_nf.parents[3 if is_tool else 2]))
    # Add trailing slash for tool/named workflow directories, but not for the
    # root bactopia workflow which uses a Nextflow convention path
    if is_tool or wf_path != "bactopia/bactopia":
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
    bactopia_version = "unknown"
    plugin_version = "unknown"
    nf_config = bactopia_path / "nextflow.config"
    if nf_config.exists():
        for line in nf_config.read_text().splitlines():
            m = re.match(r"\s*params\.bactopia_version\s*=\s*['\"]([^'\"]+)['\"]", line)
            if m:
                bactopia_version = m.group(1)
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
        catalog["modules"][key] = _build_module_entry(component_name, main_nf)

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
@click.option("--verbose", is_flag=True, help="Print debug related text.")
def catalog(bactopia_path, output_path, pretty, verbose):
    """Generate machine-readable catalog of all Bactopia components.

    Produces catalog.json containing workflows, subworkflows, and modules
    with their contracts (takes/emits), dependencies, and metadata.
    Replaces data/workflows.yml as the authoritative component index.
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


def main():
    if len(sys.argv) == 1:
        catalog.main(["--help"])
    else:
        catalog()


if __name__ == "__main__":
    main()
