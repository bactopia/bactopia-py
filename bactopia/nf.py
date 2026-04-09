"""Nextflow repo introspection utilities for Bactopia."""

import json
import logging
import re
import sys
from pathlib import Path


def find_main_nf(directory: Path) -> list:
    """Find all main.nf files under a directory, sorted.

    Args:
        directory: Directory to search recursively.

    Returns:
        Sorted list of Path objects for each main.nf found.
    """
    if not directory.exists():
        return []
    return sorted(directory.rglob("main.nf"))


def parse_groovydoc(main_nf: Path) -> dict:
    """Parse a GroovyDoc block from the top of a main.nf file.

    Extracts the opening /** ... */ block and returns the tags found within it.
    A valid GroovyDoc must start with /** on line 1 or 2.

    Args:
        main_nf: Path to a main.nf file.

    Returns:
        A dict with:
            - has_doc: True if a GroovyDoc block was found
            - tags: set of tag names found (e.g. {"status", "keywords", "citation"})
    """
    result = {"has_doc": False, "tags": set()}
    try:
        with open(main_nf) as f:
            lines = f.readlines()
    except OSError:
        return result

    # Find /** on line 1 or 2
    doc_start = None
    for i in range(min(2, len(lines))):
        if lines[i].strip().startswith("/**"):
            doc_start = i
            break

    if doc_start is None:
        return result

    # Read until */ closing
    doc_lines = []
    for line in lines[doc_start:]:
        doc_lines.append(line)
        if "*/" in line:
            break

    if not any("*/" in line for line in doc_lines):
        return result

    result["has_doc"] = True

    # Also require @status to confirm it's a real GroovyDoc
    tag_pattern = re.compile(r"@(\w+)")
    for line in doc_lines:
        for match in tag_pattern.finditer(line):
            result["tags"].add(match.group(1))

    if "status" not in result["tags"]:
        result["has_doc"] = False

    return result


def has_groovydoc(main_nf: Path) -> bool:
    """Check if a main.nf file has a valid GroovyDoc (/** block with @status tag).

    Args:
        main_nf: Path to a main.nf file.

    Returns:
        True if the file has a valid GroovyDoc block.
    """
    return parse_groovydoc(main_nf)["has_doc"]


def check_tier(
    bactopia_path: Path,
    tier_name: str,
    directory: Path,
    required_files: list,
    check_nftest: bool = True,
):
    """Check a component tier for GroovyDoc, required files, and nf-test coverage.

    Args:
        bactopia_path: Root path of the Bactopia repo.
        tier_name: Display name for the tier (e.g. "Modules").
        directory: Directory to scan for main.nf files.
        required_files: List of required filenames (besides main.nf).
        check_nftest: Whether to check for nf-test files.

    Returns:
        A dict with total, doc_count, tag_coverage, and a list of issue strings.
    """
    main_nf_files = find_main_nf(directory)
    total = len(main_nf_files)
    no_doc = 0
    issues = []
    all_tags = {}

    for main_nf in main_nf_files:
        component_dir = main_nf.parent
        rel_path = component_dir.relative_to(bactopia_path)

        # GroovyDoc check
        doc = parse_groovydoc(main_nf)
        all_tags[str(rel_path)] = sorted(doc["tags"])
        if not doc["has_doc"]:
            no_doc += 1
            issues.append(f"[no groovydoc] {rel_path}")

        # Required file checks
        for req in required_files:
            if not (component_dir / req).exists():
                issues.append(f"[missing {req}] {rel_path}")

        # nf-test check
        if check_nftest:
            tests_dir = component_dir / "tests"
            has_tests = tests_dir.is_dir() and any(tests_dir.glob("*.nf.test"))
            if not has_tests:
                issues.append(f"[no nf-test] {rel_path}")

    # Build tag coverage summary
    tag_counts = {}
    for tags in all_tags.values():
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return {
        "total": total,
        "doc_count": total - no_doc,
        "issues": sorted(set(issues)),
        "tag_coverage": {k: tag_counts[k] for k in sorted(tag_counts)},
    }


def get_nftest_coverage(bactopia_path: Path, directory: Path = None) -> dict:
    """Calculate nf-test coverage for components.

    Args:
        bactopia_path: Root path of the Bactopia repo.
        directory: Directory to scope the search to. Defaults to workflows/.

    Returns:
        A dict with total component count, tested count, and root_test flag.
    """
    if directory is None:
        directory = bactopia_path / "workflows"

    total = len(find_main_nf(directory))

    # Find directories that have tests/*.nf.test
    tested_dirs = set()
    for test_file in directory.rglob("*.nf.test"):
        if test_file.parent.name == "tests":
            tested_dirs.add(test_file.parent.parent)

    root_test = (bactopia_path / "tests" / "main.nf.test").exists()

    return {
        "total": total,
        "tested": len(tested_dirs),
        "root_test": root_test,
    }


def cleanup_value(value, is_conda=False):
    """Remove some characters Nextflow param values"""
    if is_conda:
        return value.lstrip('"').split('".replace')[0]
    else:
        return value.rstrip(",").strip('"')


def parse_module_config(module_config: str, registry: str) -> dict:
    """
    Pull out the Conda, Docker and singularity info from a module.config

    Example:
        process {
            withName: 'CSVTK_CONCAT' {
                // Environment information
                ext.toolName = "bioconda::csvtk=0.31.0".replace("=", "-").replace(":", "-").replace(" ", "-")
                ext.docker = "biocontainers/csvtk:0.31.0--h9ee0642_0"
                ext.image = "https://depot.galaxyproject.org/singularity/csvtk:0.31.0--h9ee0642_0"
                ext.condaDir = "${params.condadir}"

                ext.wf = params.wf
                ext.scope = "run"
            }
        }
    """
    envs = {}
    if not Path(module_config).exists():
        logging.debug(f"No module.config found: {module_config}")
        return envs
    with open(module_config, "rt") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("ext.toolName"):
                # Conda
                # ext.toolName = "bioconda::csvtk=0.31.0".replace(...) -> bioconda::csvtk=0.31.0
                value = line.split("=", 1)[1].strip()
                envs["conda"] = cleanup_value(value, is_conda=True)
            elif line.startswith("ext.docker"):
                # Docker
                value = line.split("=", 1)[1].strip()
                envs["docker"] = f"{registry}/{cleanup_value(value)}"
            elif line.startswith("ext.image"):
                # Singularity
                value = line.split("=", 1)[1].strip()
                envs["singularity"] = cleanup_value(value)

            # Stop once we have all three
            if len(envs) == 3:
                break
    logging.debug(f"Parsed envs from: {module_config}")
    logging.debug(f"{envs}")
    return envs


def parse_workflows(bactopia_path, input_wf, include_merlin=False, build_all=False):
    """Parse Bactopia's catalog.json to get modules per-workflow."""
    import json

    from bactopia.parsers.workflows import get_modules_by_workflow

    # Load catalog.json
    catalog_path = f"{bactopia_path}/data/catalog.json"
    logging.debug(f"Loading catalog from {catalog_path}")
    with open(catalog_path) as fh:
        catalog = json.load(fh)

    workflows = catalog["workflows"]

    if input_wf not in workflows and not build_all:
        # Let nextflow handle unknown workflows
        logging.error(f"{input_wf} is not a known workflow, skipping")
        sys.exit(0)

    # Build the final workflows structure
    final_workflows = {}
    for wf, wf_info in workflows.items():
        if input_wf == wf or build_all:
            logging.debug(f"Processing workflow: {wf}")
            final_workflows[wf] = {}

            # Optionally skip merlin subworkflow
            if not include_merlin and "merlin" in wf_info.get("subworkflows", []):
                logging.debug("Skipping merlin modules since --include_merlin not set")
                # Temporarily remove merlin to exclude its modules
                orig_subs = wf_info["subworkflows"]
                wf_info["subworkflows"] = [s for s in orig_subs if s != "merlin"]
                modules = get_modules_by_workflow(wf, catalog)
                wf_info["subworkflows"] = orig_subs
            else:
                modules = get_modules_by_workflow(wf, catalog)

            # Map each module key to its module.config path
            for module in modules:
                module_meta = catalog["modules"].get(module)
                if module_meta:
                    config_path = f"{bactopia_path}/{module_meta['path']}module.config"
                else:
                    # Fallback: derive path from key
                    module_path = f"modules/{module.replace('_', '/')}"
                    config_path = f"{bactopia_path}/{module_path}/module.config"
                if not Path(config_path).exists():
                    logging.warning(
                        f"module.config not found at {config_path} for module '{module}', skipping"
                    )
                    continue
                logging.debug(f"Adding module {module}: {config_path}")
                final_workflows[wf][module] = config_path

    return final_workflows


def parse_conda_tools(module_config: str) -> list:
    """
    Extract bioconda tool names, versions, and builds from a module.config file.

    Uses parse_module_config to get the conda and docker fields. The build string
    is extracted from the docker tag (e.g. "bakta:1.11.4--pyhdfd78af_0" -> "pyhdfd78af_0").

    Args:
        module_config: Path to a module.config file.

    Returns:
        List of dicts with 'name', 'version', and 'build' keys for each bioconda tool.
    """
    envs = parse_module_config(module_config, registry="")
    tools = []
    if "conda" in envs:
        # Extract build from docker tag: "tool:version--build" -> "build"
        build = None
        docker = envs.get("docker", "")
        if "--" in docker:
            build = docker.rsplit("--", 1)[1]

        for tool in envs["conda"].split():
            if "::" in tool:
                _, pkg = tool.split("::", 1)
                if "=" in pkg:
                    parts = pkg.split("=")
                    name = parts[0]
                    version = parts[1]
                    # A third segment means the build is pinned in the conda
                    # string (e.g. bioconda::tool=1.0=h123_0)
                    pinned = len(parts) > 2
                    tools.append(
                        {
                            "name": name,
                            "version": version,
                            "build": build,
                            "pinned": pinned,
                        }
                    )
    return tools


def parse_all_conda_tools(bactopia_path: str, module_filter: str | None = None) -> dict:
    """
    Find all module.config files under modules and extract conda tools.

    Args:
        bactopia_path: The path to a Bactopia repository.
        module_filter: Optional name to filter modules. Matches exact name
            or prefix (e.g. "bakta" matches "bakta_run", "bakta_download").

    Returns:
        Dict mapping module names to dicts with 'tools' and 'config' keys.
    """
    modules = {}
    modules_dir = Path(f"{bactopia_path}/modules")
    if not modules_dir.exists():
        return modules
    prefix = f"{module_filter}_" if module_filter else None
    for config in sorted(modules_dir.rglob("module.config")):
        module_name = str(config.parent.relative_to(modules_dir)).replace("/", "_")
        if (
            module_filter
            and module_name != module_filter
            and not module_name.startswith(prefix)
        ):
            continue
        tools = parse_conda_tools(str(config))
        if tools:
            config_rel = str(config.relative_to(bactopia_path))
            modules[module_name] = {"tools": tools, "config": config_rel}
    return modules


def get_bactopia_version(bactopia_path: Path) -> str:
    """Extract the Bactopia version from nextflow.config.

    Args:
        bactopia_path: Root path of the Bactopia repo.

    Returns:
        Version string, or "unknown" if not found.
    """
    nf_config = Path(bactopia_path) / "nextflow.config"
    if nf_config.exists():
        for line in nf_config.read_text().splitlines():
            m = re.match(r"\s*params\.bactopia_version\s*=\s*['\"]([^'\"]+)['\"]", line)
            if m:
                return m.group(1)
    return "unknown"


def parse_dataset_urls(bactopia_path, datasets_path):
    """Parse Bactopia's params.config to extract dataset download URLs.

    Args:
        bactopia_path: Path to the Bactopia repository.
        datasets_path: Base path where datasets will be saved.

    Returns:
        List of dicts with 'dataset', 'url', and 'save_path' keys.
    """
    bactopia_path = Path(bactopia_path)
    version = get_bactopia_version(bactopia_path)
    params_config = bactopia_path / "conf" / "params.config"
    if not params_config.exists():
        logging.error(f"params.config not found: {params_config}")
        return []

    urls = []
    for line in params_config.read_text().splitlines():
        if "_url" not in line or "=" not in line:
            continue
        line = line.strip()
        if line.startswith("//"):
            continue
        param, val = line.split("=", 1)
        param = param.strip()
        val = val.strip().strip("'\"")
        if not val.startswith("http"):
            continue
        val = val.replace("${params.bactopia_version}", version)
        dataset = param.replace("_url", "")
        urls.append(
            {
                "dataset": dataset,
                "url": val,
                "save_path": val.replace(
                    "https://datasets.bactopia.com/datasets/", f"{datasets_path}/"
                ),
            }
        )

    return urls


def get_empty_placeholders(bactopia_path: Path) -> list:
    """List files in the data/empty/ directory.

    Args:
        bactopia_path: Root path of the Bactopia repo.

    Returns:
        Sorted list of filenames relative to data/empty/.
    """
    empty_dir = bactopia_path / "data" / "empty"
    if not empty_dir.exists():
        return []
    return sorted(
        str(f.relative_to(empty_dir)) for f in empty_dir.iterdir() if f.is_file()
    )


# ---------------------------------------------------------------------------
# Enhanced parsing functions for the linter
# ---------------------------------------------------------------------------


def _read_lines(path: Path) -> list[str]:
    """Read file lines, returning empty list on error."""
    try:
        return path.read_text().splitlines(keepends=True)
    except OSError:
        return []


def _extract_doc_block(lines: list[str]) -> list[str] | None:
    """Extract the /** ... */ block from the first two lines of a file."""
    doc_start = None
    for i in range(min(2, len(lines))):
        if lines[i].strip().startswith("/**"):
            doc_start = i
            break
    if doc_start is None:
        return None

    doc_lines = []
    for line in lines[doc_start:]:
        doc_lines.append(line)
        if "*/" in line:
            break

    if not any("*/" in line for line in doc_lines):
        return None
    return doc_lines


def parse_groovydoc_full(main_nf: Path) -> dict:
    """Parse a GroovyDoc block, returning tag names and their values.

    Args:
        main_nf: Path to a main.nf file.

    Returns:
        A dict with:
            - has_doc: True if a GroovyDoc block was found
            - tags: dict mapping tag names to their values
            - raw_lines: the raw doc block lines
            - links: list of URLs found in the doc block
    """
    result = {
        "has_doc": False,
        "tags": {},
        "raw_lines": [],
        "links": [],
        # Parsed GroovyDoc fields for lint rules M031-M037
        "doc_output_fields": [],  # field names from @output record(...), ? stripped
        "doc_input_records": [],  # list of {fields: [...]} per @input record(...), ? stripped
        "doc_input_params": [],  # non-record @input names, ? stripped
        "doc_output_described_fields": [],  # fields with description lines, ? stripped
        "doc_tag_order": [],  # ordered list of tag names as they appear
        # Optionality tracking (base names of fields that had ? suffix in GroovyDoc)
        "doc_optional_output_fields": set(),
        "doc_optional_input_fields": set(),
        "doc_optional_input_params": set(),
    }
    lines = _read_lines(main_nf)
    if not lines:
        return result

    doc_lines = _extract_doc_block(lines)
    if doc_lines is None:
        return result

    result["raw_lines"] = doc_lines

    # Extract tags with their values
    # Multi-value tags are stored as lists; single-value tags as strings.
    # Continuation lines (lines with * but no @tag) are appended to the
    # previous single-value tag (e.g., multi-line @modules or @subworkflows).
    multi_value_tags = {"input", "output", "note", "publish", "section", "results"}
    tag_pattern = re.compile(r"\*\s*@(\w+)\s*(.*)")
    continuation_pattern = re.compile(r"\*\s+([^@\s].+)")
    last_single_tag = None
    for line in doc_lines:
        m = tag_pattern.search(line)
        if m:
            tag_name = m.group(1)
            tag_value = m.group(2).strip()
            if tag_name in multi_value_tags:
                result["tags"].setdefault(tag_name, [])
                result["tags"][tag_name].append(tag_value)
                last_single_tag = None
            else:
                result["tags"][tag_name] = tag_value
                last_single_tag = tag_name
        elif last_single_tag:
            # Continuation line for a single-value tag
            cm = continuation_pattern.search(line)
            if cm:
                result["tags"][last_single_tag] += " " + cm.group(1).strip()

    # Extract URLs
    url_pattern = re.compile(r"https?://[^\s\)>]+")
    for line in doc_lines:
        for url_match in url_pattern.finditer(line):
            result["links"].append(url_match.group(0))

    result["has_doc"] = "status" in result["tags"]

    # --- Parse GroovyDoc fields for lint rules M031-M037 ---

    # Track tag ordering from raw lines
    seen_tags = []
    tag_order_pattern = re.compile(r"\*\s*@(\w+)")
    for line in doc_lines:
        m = tag_order_pattern.search(line)
        if m:
            tag_name = m.group(1)
            if tag_name not in seen_tags:
                seen_tags.append(tag_name)
    result["doc_tag_order"] = seen_tags

    # Parse @output record(...) fields (strip ? suffix, track optionality)
    output_tags = result["tags"].get("output", [])
    for oval in output_tags:
        record_match = re.match(r"record\(([^)]+)\)", oval)
        if record_match:
            fields = []
            for raw in record_match.group(1).split(","):
                raw = raw.strip()
                if raw.endswith("?"):
                    base = raw[:-1]
                    result["doc_optional_output_fields"].add(base)
                    fields.append(base)
                else:
                    fields.append(raw)
            result["doc_output_fields"] = fields

    # Parse @input blocks (strip ? suffix, track optionality)
    input_tags = result["tags"].get("input", [])
    for ival in input_tags:
        # Check for record(meta, ...) syntax
        record_match = re.match(r"record\(([^)]+)\)", ival)
        if record_match:
            fields = []
            for raw in record_match.group(1).split(","):
                raw = raw.strip()
                if raw.endswith("?"):
                    base = raw[:-1]
                    result["doc_optional_input_fields"].add(base)
                    fields.append(base)
                else:
                    fields.append(raw)
            result["doc_input_records"].append({"fields": fields})
        else:
            # Non-record input (e.g., "db", "proteins", "proteins?")
            param_name = ival.split()[0] if ival.strip() else ""
            if param_name:
                if param_name.endswith("?"):
                    base = param_name[:-1]
                    result["doc_optional_input_params"].add(base)
                    result["doc_input_params"].append(base)
                else:
                    result["doc_input_params"].append(param_name)

    # Parse @output description lines to find which fields are described
    # Pattern: * - `field`: description  (field may have ? suffix)
    desc_pattern = re.compile(r"\*\s*-\s*`(\w+\??)`\s*:")
    in_output_section = False
    for line in doc_lines:
        if re.search(r"\*\s*@output", line):
            in_output_section = True
            continue
        if re.search(r"\*\s*@\w+", line) and not re.search(r"\*\s*@output", line):
            in_output_section = False
            continue
        if in_output_section:
            dm = desc_pattern.search(line)
            if dm:
                field_name = dm.group(1).rstrip("?")
                result["doc_output_described_fields"].append(field_name)

    return result


def parse_main_nf_structure(main_nf: Path) -> dict:
    """Extract structural information from a main.nf file.

    Args:
        main_nf: Path to a main.nf file.

    Returns:
        A dict with structural info about the file.
    """
    result = {
        "has_types_preview": False,
        "process_name": None,
        "output_record_fields": [],
        "has_versions_yml": False,
        "links": [],
        "emit_channels": [],
        "has_comment_markers": False,
        "has_tuple_references": False,
        "has_blank_before_main": None,
        "has_blank_before_emit": None,
        "emit_has_published_comment": False,
        "emit_has_sample_outputs": False,
        "emit_has_run_outputs": False,
        # prefix/meta (M017, M018)
        "has_prefix_definition": False,
        "has_meta_init": False,
        "meta_fields_set": set(),
        # process directives (M019, M020)
        "has_conda_directive": False,
        "has_container_directive": False,
        # meta.name interpolation (M021)
        "has_meta_name_interpolation": False,
        # script block (M022)
        "has_cleanup_comment": False,
        # output record details (M023-M030)
        "output_has_named_comment": False,
        "output_has_generic_comment": False,
        "output_has_meta_field": False,
        "output_has_results": False,
        "output_results_is_list": False,
        "output_results_fields": [],
        "output_named_fields": [],
        "output_named_field_patterns": {},
        "output_has_logs": False,
        "output_has_nf_logs": False,
        "output_versions_uses_files": False,
        "output_generic_using_file": [],
        # Input parsing for M031/M032/M033
        "input_record_fields": [],  # fields from (meta: Map, field: Type): Record
        "input_params": [],  # non-record input names (db, proteins, etc.)
        # Optionality tracking for M033
        "code_optional_input_fields": set(),  # input record fields with Type?
        "code_optional_input_params": set(),  # non-record input params with Type?
        "code_optional_output_fields": set(),  # output fields with optional: true
        # Workflow-specific fields (W011-W020)
        "first_line": "",
        "todos": [],  # list of {"line_num": int, "text": str}
        "channel_operators": [],  # list of {"operator": str, "line_num": int, "line_text": str}
        "has_collect_nf_logs_import": False,
        "wf_output_block_text": "",  # top-level output {} block (not process output:)
        "publish_block_lines": [],  # lines from publish: section
        "wf_params_block": {  # top-level params {} block in workflows
            "exists": False,
            "first_param": None,
            "first_param_line": "",
            "params": [],  # list of {"name": str, "colon_col": int, "line_num": int}
        },
        "includes": [],  # list of {"name": str, "source": str, "line_num": int, "brace_col": int}
        "mix_sources": {"sample": [], "run": []},
        # Subworkflow-specific fields (S011-S016)
        "workflow_name": None,
        "workflow_declaration_line_num": None,
        "gather_csvtk_calls": [],  # list of {"name": str, "is_dynamic": bool, "line_num": int, "receiver": str}
        "csvtk_concat_aliases": set(),  # include names resolving to CSVTK_CONCAT
        "emit_mix_sources": {"sample": [], "run": []},
    }

    lines = _read_lines(main_nf)
    if not lines:
        return result

    full_text = "".join(lines)

    # Check for nextflow.preview.types = true
    types_pattern = re.compile(r"nextflow\.preview\.types\s*=\s*true")
    result["has_types_preview"] = bool(types_pattern.search(full_text))

    # Extract process name (process UPPER_CASE {)
    process_pattern = re.compile(r"^\s*process\s+([A-Z_0-9]+)\s*\{", re.MULTILINE)
    pm = process_pattern.search(full_text)
    if pm:
        result["process_name"] = pm.group(1)

    # Check for any process definition (including non-uppercase)
    any_process_pattern = re.compile(r"^\s*process\s+(\w+)\s*\{", re.MULTILINE)
    apm = any_process_pattern.search(full_text)
    if apm and not pm:
        # There's a process but it's not UPPER_CASE
        result["process_name"] = apm.group(1)

    # Extract output record fields from record(...) in output block
    # The record() block contains nested parens (file(), files()), so we
    # can't use a simple regex. Instead, find "record(" after "output:" and
    # use balanced parenthesis counting to extract the full block.
    output_block = re.search(
        r"\boutput:\s*\n(.*?)(?=\n\s*(?:script:|exec:|shell:|stub:|\Z))",
        full_text,
        re.DOTALL,
    )
    if output_block:
        output_text = output_block.group(1)
        record_start = output_text.find("record(")
        if record_start != -1:
            # Find matching closing paren using balanced counting
            depth = 0
            start_idx = record_start + len("record(")
            end_idx = start_idx
            for i in range(record_start, len(output_text)):
                if output_text[i] == "(":
                    depth += 1
                elif output_text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            record_text = output_text[start_idx:end_idx]
            # Extract field names -- look for "word:" at start of line
            # (after optional whitespace and comment lines)
            field_pattern = re.compile(r"^\s*(\w+)\s*:", re.MULTILINE)
            for fm in field_pattern.finditer(record_text):
                field_name = fm.group(1)
                # Skip comments that happen to match (e.g., "// Named fields")
                line_start = record_text.rfind("\n", 0, fm.start()) + 1
                prefix_text = record_text[line_start : fm.start()].strip()
                if not prefix_text.startswith("//"):
                    result["output_record_fields"].append(field_name)
                    # Check for optional: true on the same line (M033)
                    line_end = record_text.find("\n", fm.end())
                    if line_end == -1:
                        line_end = len(record_text)
                    rest_of_line = record_text[fm.end() : line_end]
                    if re.search(r"optional\s*:\s*true", rest_of_line):
                        result["code_optional_output_fields"].add(field_name)

            # --- Output record detail parsing (M023-M030) ---

            # Check for section comments
            result["output_has_named_comment"] = (
                "// Named fields (used downstream)" in record_text
            )
            result["output_has_generic_comment"] = (
                "// Generic fields (used for publishing)" in record_text
            )

            # Check for meta: meta field
            result["output_has_meta_field"] = bool(
                re.search(r"^\s*meta\s*:\s*meta\s*,?\s*$", record_text, re.MULTILINE)
            )

            # Split record into named and generic sections
            generic_marker = "// Generic fields (used for publishing)"
            named_marker = "// Named fields (used downstream)"
            named_section = ""
            generic_section = ""
            if generic_marker in record_text:
                parts = record_text.split(generic_marker, 1)
                named_section = parts[0]
                generic_section = parts[1]
            elif named_marker in record_text:
                named_section = record_text

            # Extract named fields (between Named and Generic comments, excl meta)
            if named_section:
                # Find fields after the Named comment
                after_named = named_section
                if named_marker in named_section:
                    after_named = named_section.split(named_marker, 1)[1]
                named_field_pat = re.compile(
                    r"^\s*(\w+)\s*:\s*(files?)\((.+?)\)", re.MULTILINE
                )
                for nfm in named_field_pat.finditer(after_named):
                    fname = nfm.group(1)
                    if fname != "meta":
                        result["output_named_fields"].append(fname)
                        result["output_named_field_patterns"][fname] = nfm.group(
                            3
                        ).strip()

            # Parse results block
            results_match = re.search(r"results\s*:\s*\[", record_text, re.MULTILINE)
            if results_match:
                result["output_has_results"] = True
                # Extract the results list content using balanced brackets
                bracket_start = results_match.end() - 1
                depth = 0
                bracket_end = bracket_start
                for i in range(bracket_start, len(record_text)):
                    if record_text[i] == "[":
                        depth += 1
                    elif record_text[i] == "]":
                        depth -= 1
                        if depth == 0:
                            bracket_end = i
                            break
                results_content = record_text[bracket_start + 1 : bracket_end]
                # Check if multi-line
                result["output_results_is_list"] = "\n" in results_content
                # Extract files() patterns from results block
                results_files_pat = re.compile(r"files\((.+?)\)")
                for rfm in results_files_pat.finditer(results_content):
                    result["output_results_fields"].append(rfm.group(1).strip())

            # Check logs, nf_logs, versions in generic section
            check_text = generic_section if generic_section else record_text
            result["output_has_logs"] = bool(
                re.search(r"^\s*logs\s*:", check_text, re.MULTILINE)
            )
            result["output_has_nf_logs"] = bool(
                re.search(r"^\s*nf_logs\s*:", check_text, re.MULTILINE)
            )

            # Check if versions uses files() vs file()
            versions_match = re.search(
                r"^\s*versions\s*:\s*(files?)\(", check_text, re.MULTILINE
            )
            if versions_match:
                result["output_versions_uses_files"] = (
                    versions_match.group(1) == "files"
                )

            # Check all generic fields use files() not file()
            if generic_section:
                generic_field_pat = re.compile(
                    r"^\s*(\w+)\s*:\s*(file)\(", re.MULTILINE
                )
                for gfm in generic_field_pat.finditer(generic_section):
                    result["output_generic_using_file"].append(gfm.group(1))

    # Extract input block fields
    input_block = re.search(
        r"\binput:\s*\n(.*?)(?=\n\s*(?:output:|script:|exec:|shell:|stub:|\Z))",
        full_text,
        re.DOTALL,
    )
    if input_block:
        input_text = input_block.group(1)
        # Match Record input: (meta: Map, field1: Type, field2: Type?): Record
        record_input_match = re.search(r"\(([^)]+)\)\s*:\s*Record", input_text)
        if record_input_match:
            for part in record_input_match.group(1).split(","):
                part = part.strip()
                pieces = part.split(":")
                name = pieces[0].strip()
                result["input_record_fields"].append(name)
                if len(pieces) > 1 and pieces[1].strip().endswith("?"):
                    result["code_optional_input_fields"].add(name)
        # Match non-record inputs: name: Type (one per line, not inside parens)
        for line in input_text.split("\n"):
            stripped = line.strip()
            # Skip empty lines, comments, and the Record line
            if not stripped or stripped.startswith("//") or "Record" in stripped:
                continue
            if stripped.startswith("("):
                continue
            # Match "name: Type" or "name: Type?" (optional)
            param_match = re.match(r"(\w+)\s*:\s*(\w+\??)", stripped)
            if param_match:
                param_name = param_match.group(1)
                result["input_params"].append(param_name)
                if param_match.group(2).endswith("?"):
                    result["code_optional_input_params"].add(param_name)

    # Check for versions.yml in script block
    result["has_versions_yml"] = "versions.yml" in full_text

    # Extract emit channels (for subworkflows/workflows)
    emit_block = re.search(r"\bemit:\s*\n(.*?)(?=\n\s*\}|\Z)", full_text, re.DOTALL)
    if emit_block:
        channel_pattern = re.compile(r"^\s*(\w+)\s*=", re.MULTILINE)
        for cm in channel_pattern.finditer(emit_block.group(1)):
            result["emit_channels"].append(cm.group(1))

    # Check for comment markers like // ---
    result["has_comment_markers"] = bool(re.search(r"//\s*-{3,}", full_text))

    # Check for tuple references (should be record instead)
    result["has_tuple_references"] = bool(
        re.search(r"\btuple\b", full_text, re.IGNORECASE)
    )

    # Check for prefix = task.ext.prefix ?: "${_meta.name}" (M017)
    result["has_prefix_definition"] = bool(
        re.search(
            r'prefix\s*=\s*task\.ext\.prefix\s*\?:\s*"\$\{_meta\.name\}"', full_text
        )
    )

    # Check for meta = [:] initialization and meta.X field assignments (M018)
    result["has_meta_init"] = bool(re.search(r"meta\s*=\s*\[:\]", full_text))
    meta_field_pattern = re.compile(r"meta\.(\w+)\s*=")
    result["meta_fields_set"] = {
        m.group(1) for m in meta_field_pattern.finditer(full_text)
    }

    # Check for conda/container directives (M019, M020)
    result["has_conda_directive"] = bool(
        re.search(
            r'conda\s+"\$\{task\.ext\.condaDir\}/\$\{task\.ext\.toolName\}"', full_text
        )
    )
    result["has_container_directive"] = bool(
        re.search(r'container\s+"\$\{task\.ext\.container\}"', full_text)
    )

    # Check for ${meta.name} interpolation (M021)
    # Exclude assignment lines like "meta.name = prefix"
    has_interpolation = False
    for line in lines:
        stripped = line.strip()
        if re.search(r"meta\.name\s*=", stripped):
            continue  # skip assignment lines (meta.name = prefix)
        if re.search(r"task\.ext\.prefix", stripped):
            continue  # skip prefix definition line
        if re.search(r"\$\{meta\.name\}", stripped):
            has_interpolation = True
            break
    result["has_meta_name_interpolation"] = has_interpolation

    # Check for # Cleanup comment (M022)
    # Search full text -- the comment is unambiguous and scoping to the script
    # block is fragile due to nested braces in Groovy maps/closures.
    result["has_cleanup_comment"] = bool(re.search(r"#\s*Cleanup", full_text))

    # Check for blank lines before main: and emit: blocks
    stripped_lines = [ln.rstrip() for ln in lines]
    for i, line in enumerate(stripped_lines):
        stripped = line.strip()
        if stripped == "main:":
            result["has_blank_before_main"] = (
                i > 0 and stripped_lines[i - 1].strip() == ""
            )
        elif stripped == "emit:":
            result["has_blank_before_emit"] = (
                i > 0 and stripped_lines[i - 1].strip() == ""
            )

    # Check emit block structure (sample_outputs, run_outputs, comments)
    if emit_block:
        emit_text = emit_block.group(1)
        result["emit_has_sample_outputs"] = bool(
            re.search(r"^\s*sample_outputs\s*=", emit_text, re.MULTILINE)
        )
        result["emit_has_run_outputs"] = bool(
            re.search(r"^\s*run_outputs\s*=", emit_text, re.MULTILINE)
        )
        result["emit_has_published_comment"] = bool(
            re.search(r"//\s*Published outputs", emit_text)
        )

    # --- Workflow-specific parsing (W011-W020) ---

    # W011: First line
    result["first_line"] = lines[0].rstrip() if lines else ""

    # Determine GroovyDoc line range to skip for TODOs/channel ops
    doc_block = _extract_doc_block(lines)
    doc_end_line = 0
    if doc_block:
        doc_end_line = len(doc_block)  # 0-indexed end (exclusive)

    # W012: TODOs (skip GroovyDoc block)
    todo_pattern = re.compile(r"(//\s*TODO|#\s*TODO)(.*)", re.IGNORECASE)
    for i, line in enumerate(lines):
        if i < doc_end_line:
            continue
        m = todo_pattern.search(line)
        if m:
            result["todos"].append({"line_num": i + 1, "text": m.group(0).strip()})

    # W013: Disallowed channel operators (skip GroovyDoc and comment-only lines)
    disallowed_ops = re.compile(
        r"\.(join|map|combine|collect|filter|flatMap|groupTuple|"
        r"branch|multiMap|toList|toSortedList|unique|distinct|first|last|"
        r"take|until|cross|spread|tap|set|merge|transpose)\s*[\({]"
    )
    for i, line in enumerate(lines):
        if i < doc_end_line:
            continue
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        m = disallowed_ops.search(line)
        if m:
            result["channel_operators"].append(
                {"operator": m.group(1), "line_num": i + 1, "line_text": line.rstrip()}
            )

    # W014: collectNextflowLogs import
    result["has_collect_nf_logs_import"] = bool(
        re.search(
            r"include\s*\{\s*collectNextflowLogs\s*\}\s*from\s*['\"]plugin/nf-bactopia['\"]",
            full_text,
        )
    )

    # W018: Parse include statements (handles both plain and "as" aliases)
    include_re = re.compile(
        r"include\s*\{\s*(\w+(?:\s+as\s+\w+)?)\s*\}\s*from\s*['\"]([^'\"]+)['\"]"
    )
    for i, line in enumerate(lines):
        m = include_re.match(line)
        if m:
            # Content is the full text between braces (e.g. "CSVTK_CONCAT as GENES_CONCAT")
            content = m.group(1)
            name = content.split()[-1]  # effective name (alias or original)
            brace_col = line.index("}")
            result["includes"].append(
                {
                    "name": name,
                    "source": m.group(2),
                    "line_num": i + 1,
                    "brace_col": brace_col,
                    "content_len": len(content),
                }
            )

    # S014: Track CSVTK_CONCAT aliases (including "as" aliases)
    # The includes list only captures simple includes, not "as" aliases, so
    # scan the raw lines for all CSVTK_CONCAT imports.
    csvtk_alias_re = re.compile(
        r"include\s*\{\s*CSVTK_CONCAT(?:\s+as\s+(\w+))?\s*\}\s*from"
    )
    for line in lines:
        am = csvtk_alias_re.search(line)
        if am:
            result["csvtk_concat_aliases"].add(am.group(1) or "CSVTK_CONCAT")

    # S012: Parse workflow declaration line
    for i, line in enumerate(lines):
        wf_m = re.match(r"workflow\s+(\w+)\s*\{", line)
        if wf_m:
            result["workflow_declaration_line_num"] = i + 1  # 1-indexed
            result["workflow_name"] = wf_m.group(1)
            break

    # S013/S014: Parse gatherCsvtk calls
    gather_recv_re = re.compile(r"(\w+)\s*\(\s*gatherCsvtk\s*\(")
    name_re_single = re.compile(r"\[name:\s*'([^']+)'\]")
    name_re_double = re.compile(r'\[name:\s*"([^"]+)"\]')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "gatherCsvtk(" not in stripped:
            continue
        recv_m = gather_recv_re.search(stripped)
        receiver = recv_m.group(1) if recv_m else "unknown"
        name_m = name_re_single.search(stripped)
        is_dynamic = False
        name_val = None
        if name_m:
            name_val = name_m.group(1)
        else:
            name_m = name_re_double.search(stripped)
            if name_m:
                name_val = name_m.group(1)
                is_dynamic = "${" in name_val
        if name_val is not None:
            result["gather_csvtk_calls"].append(
                {
                    "name": name_val,
                    "is_dynamic": is_dynamic,
                    "line_num": i + 1,
                    "receiver": receiver,
                }
            )

    # S015/S016: Parse emit-block mix sources for subworkflows
    if emit_block:
        emit_text = emit_block.group(1)

        def _collect_emit_assignment(text: str, var_name: str) -> str:
            """Collect a possibly multi-line assignment from emit text."""
            emit_lines = text.split("\n")
            collecting = False
            paren_depth = 0
            full_rhs = ""
            for eline in emit_lines:
                stripped_e = eline.strip()
                if not collecting:
                    em = re.match(rf"{var_name}\s*=\s*(.+)", stripped_e)
                    if em:
                        collecting = True
                        rhs_start = em.group(1)
                        full_rhs = rhs_start
                        paren_depth += rhs_start.count("(") - rhs_start.count(")")
                        if paren_depth <= 0:
                            break
                else:
                    full_rhs += " " + stripped_e
                    paren_depth += stripped_e.count("(") - stripped_e.count(")")
                    if paren_depth <= 0:
                        break
            return full_rhs

        sample_rhs = _collect_emit_assignment(emit_text, "sample_outputs")
        run_rhs = _collect_emit_assignment(emit_text, "run_outputs")

        def _extract_emit_processes(rhs: str) -> list[str]:
            """Extract process names from .out references, preserving order."""
            return [m.group(1) for m in re.finditer(r"(\w+)\.out", rhs)]

        result["emit_mix_sources"]["sample"] = _extract_emit_processes(sample_rhs)
        result["emit_mix_sources"]["run"] = _extract_emit_processes(run_rhs)

    # W017/W019: Parse top-level params block
    params_start = None
    for i, line in enumerate(lines):
        if re.match(r"^params\s*\{", line):
            params_start = i
            break
    if params_start is not None:
        # Find closing brace using balanced counting
        depth = 0
        params_end = params_start
        for i in range(params_start, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth == 0:
                params_end = i
                break
        params_lines = lines[params_start + 1 : params_end]
        result["wf_params_block"]["exists"] = True
        param_decl_pattern = re.compile(r"^(\s*)(\w+)(\s*):(\s*)")
        first_found = False
        for j, pline in enumerate(params_lines):
            pm = param_decl_pattern.match(pline)
            if pm:
                name = pm.group(2)
                colon_col = len(pm.group(1)) + len(name) + len(pm.group(3))
                actual_line_num = params_start + 1 + j + 1  # 1-indexed
                if not first_found:
                    result["wf_params_block"]["first_param"] = name
                    result["wf_params_block"]["first_param_line"] = pline.rstrip()
                    first_found = True
                result["wf_params_block"]["params"].append(
                    {"name": name, "colon_col": colon_col, "line_num": actual_line_num}
                )

    # W015: Top-level output block
    for i, line in enumerate(lines):
        if re.match(r"^output\s*\{", line):
            depth = 0
            output_lines = []
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                output_lines.append(lines[j].rstrip())
                if depth == 0:
                    break
            result["wf_output_block_text"] = "\n".join(output_lines)
            break

    # W016: Publish block lines
    in_workflow = False
    workflow_depth = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^workflow\s*\{", line):
            in_workflow = True
            workflow_depth = 1
            continue
        if in_workflow:
            workflow_depth += line.count("{") - line.count("}")
            if stripped == "publish:":
                # Collect lines after publish: until closing brace
                for k in range(i + 1, len(lines)):
                    pline = lines[k].strip()
                    if pline == "}":
                        break
                    result["publish_block_lines"].append(pline)
                break
            if workflow_depth <= 0:
                break

    # W020: Mix source parsing -- state-based to handle chained .mix() lines
    mix_arg_re = re.compile(r"\.mix\(([^)]+)\)")
    current_mix_key = None  # "sample" or "run"
    for line in lines:
        stripped = line.strip()
        # Check for assignment start
        sample_m = re.match(r"ch_sample_outputs\s*=\s*(.+)", stripped)
        run_m = re.match(r"ch_run_outputs\s*=\s*(.+)", stripped)
        if sample_m:
            current_mix_key = "sample"
            rhs = sample_m.group(1)
            first_source = rhs.split(".mix(")[0].strip()
            # Skip self-references (reassignment patterns)
            if first_source != "ch_sample_outputs":
                result["mix_sources"]["sample"].append(first_source)
            for mix_m in mix_arg_re.finditer(rhs):
                result["mix_sources"]["sample"].append(mix_m.group(1).strip())
        elif run_m:
            current_mix_key = "run"
            rhs = run_m.group(1)
            first_source = rhs.split(".mix(")[0].strip()
            if first_source != "ch_run_outputs":
                result["mix_sources"]["run"].append(first_source)
            for mix_m in mix_arg_re.finditer(rhs):
                result["mix_sources"]["run"].append(mix_m.group(1).strip())
        elif stripped.startswith(".mix(") and current_mix_key:
            # Continuation line for the current chain
            mix_m = mix_arg_re.search(stripped)
            if mix_m:
                result["mix_sources"][current_mix_key].append(mix_m.group(1).strip())
        elif current_mix_key and stripped and not stripped.startswith(".mix("):
            # Non-continuation line ends the chain
            current_mix_key = None

    return result


def parse_module_config_full(config_path: Path) -> dict:
    """Parse a module.config file for all ext.* properties and params.

    Args:
        config_path: Path to a module.config file.

    Returns:
        A dict with:
            - ext: dict of ext.* property names to their raw values
            - params: list of parameter names defined in params {} block
            - exists: whether the file exists
    """
    result = {
        "ext": {},
        "params": [],
        "exists": False,
        # New fields (MC010-MC015)
        "has_tool_arguments_comment": False,
        "has_environment_comment": False,
        "section_order_correct": False,
        "has_ext_args": False,
        "params_comment": None,
        "params_alphabetical": True,
    }
    if not config_path.exists():
        return result
    result["exists"] = True

    text = config_path.read_text()
    text_lines = text.splitlines()

    # Extract ext.* properties
    ext_pattern = re.compile(r"ext\.(\w+)\s*=\s*(.*)")
    for m in ext_pattern.finditer(text):
        result["ext"][m.group(1)] = m.group(2).strip()

    # Check for ext.args (any variant: args, args2, args3, ...)
    result["has_ext_args"] = any(
        k == "args" or (k.startswith("args") and k[4:].isdigit()) for k in result["ext"]
    )

    # Check for section comments and ordering (MC012-MC014)
    tool_args_line = None
    env_info_line = None
    first_identity_line = None
    for i, line in enumerate(text_lines):
        stripped = line.strip()
        if stripped == "// Tool arguments":
            result["has_tool_arguments_comment"] = True
            tool_args_line = i
        elif stripped == "// Environment information":
            result["has_environment_comment"] = True
            env_info_line = i
        elif first_identity_line is None and re.match(r"ext\.(wf|scope)\s*=", stripped):
            first_identity_line = i

    # Section ordering: identity < tool args < environment
    if (
        first_identity_line is not None
        and tool_args_line is not None
        and env_info_line is not None
    ):
        result["section_order_correct"] = (
            first_identity_line < tool_args_line < env_info_line
        )

    # Extract params from the params {} block, tracking per-line ignores
    ignore_pattern = re.compile(r"//\s*bactopia-lint:\s*ignore\s+([\w, ]+)")
    params_block = re.search(r"params\s*\{([^}]*)\}", text, re.DOTALL)
    if params_block:
        params_content = params_block.group(1)
        param_names_ordered = []

        # Extract params comment (first // comment line in block)
        for line in params_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                result["params_comment"] = stripped
                break

        for line in params_content.splitlines():
            param_match = re.match(r"^\s*(\w+)\s*=", line)
            if not param_match:
                continue
            name = param_match.group(1)
            if name.startswith("//"):
                continue
            param_names_ordered.append(name)
            # Check for inline ignore on same line
            inline_ignores = set()
            ig = ignore_pattern.search(line)
            if ig:
                for rule_id in ig.group(1).split(","):
                    rule_id = rule_id.strip()
                    if rule_id:
                        inline_ignores.add(rule_id)
            result["params"].append({"name": name, "ignores": inline_ignores})

        # Check alphabetical order
        if param_names_ordered:
            result["params_alphabetical"] = param_names_ordered == sorted(
                param_names_ordered
            )

    return result


def parse_schema_json(schema_path: Path) -> dict:
    """Parse a schema.json file and validate its structure.

    Args:
        schema_path: Path to a schema.json file.

    Returns:
        A dict with structural validation results.
    """
    result = {
        "exists": False,
        "valid_json": False,
        "required_keys": {},
        "defs_keys": [],
        "param_names": [],
        "type_default_mismatches": [],
    }

    if not schema_path.exists():
        return result
    result["exists"] = True

    try:
        data = json.loads(schema_path.read_text())
        result["valid_json"] = True
    except (json.JSONDecodeError, OSError):
        return result

    # Check for required top-level keys
    for key in ("$schema", "$id", "title", "description", "type", "$defs", "allOf"):
        result["required_keys"][key] = key in data

    # Extract $defs keys and parameter names
    if "$defs" in data and isinstance(data["$defs"], dict):
        result["defs_keys"] = list(data["$defs"].keys())
        for def_key, def_val in data["$defs"].items():
            if isinstance(def_val, dict) and "properties" in def_val:
                result["param_names"].extend(def_val["properties"].keys())
                # Check type/default consistency (JS005)
                for param_name, param_val in def_val["properties"].items():
                    if not isinstance(param_val, dict):
                        continue
                    param_type = param_val.get("type")
                    if "default" not in param_val or param_type is None:
                        continue
                    default = param_val["default"]
                    mismatch = False
                    if param_type == "integer":
                        # Must be int, not float or bool
                        mismatch = not (
                            isinstance(default, int) and not isinstance(default, bool)
                        )
                    elif param_type == "number":
                        # Must be float
                        mismatch = not isinstance(default, float)
                    elif param_type == "string":
                        mismatch = not isinstance(default, str)
                    elif param_type == "boolean":
                        mismatch = not isinstance(default, bool)
                    if mismatch:
                        result["type_default_mismatches"].append(
                            {
                                "param": param_name,
                                "type": param_type,
                                "default": default,
                            }
                        )

    return result


def check_file_whitespace(path: Path) -> dict:
    """Check a file for whitespace-only lines and trailing whitespace.

    Args:
        path: Path to the file to check.

    Returns:
        A dict with lists of 1-based line numbers for each issue type.
    """
    result = {"whitespace_only_lines": [], "trailing_whitespace_lines": []}
    if not path.exists():
        return result
    try:
        lines = path.read_text().splitlines(keepends=True)
    except OSError:
        return result
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\n\r")
        if stripped and stripped.isspace():
            result["whitespace_only_lines"].append(i)
        elif stripped != stripped.rstrip():
            result["trailing_whitespace_lines"].append(i)
    return result


def parse_workflow_config(config_path: Path) -> dict:
    """Parse a workflow nextflow.config for params.workflow fields.

    Extracts the ext value from params.workflow block. The ext should be a
    Groovy list literal (e.g., ["fna", "faa", "gff"]).

    Args:
        config_path: Path to the nextflow.config file.

    Returns:
        A dict with:
            - exists: bool
            - ext: list[str] | None (parsed ext values, or None if not found)
            - ext_raw: str | None (raw ext value string)
    """
    result = {"exists": False, "ext": None, "ext_raw": None}
    if not config_path.exists():
        return result
    result["exists"] = True

    try:
        text = config_path.read_text()
    except OSError:
        return result

    # Match ext = ["fna", "faa", "gff"] or ext = ["fna"]
    ext_match = re.search(r"ext\s*=\s*\[([^\]]*)\]", text)
    if ext_match:
        raw = ext_match.group(1)
        result["ext_raw"] = raw
        # Parse quoted strings from the list
        result["ext"] = re.findall(r'"([^"]*)"', raw)
        return result

    # Check for old string format: ext = "fna"
    ext_str_match = re.search(r'ext\s*=\s*"([^"]*)"', text)
    if ext_str_match:
        result["ext_raw"] = ext_str_match.group(1)
        result["ext"] = None  # String format is invalid -- rule will flag this
    return result


def parse_includes(main_nf: Path, bactopia_path: Path) -> dict:
    """Parse include statements from a main.nf file.

    Resolves source paths against the file's directory and the repo root
    to derive normalized component keys (lowercase, underscore-separated).

    Args:
        main_nf: Path to a main.nf file.
        bactopia_path: Root path of the Bactopia repo.

    Returns:
        A dict with:
            modules: list of module keys (e.g., "abricate_run")
            subworkflows: list of subworkflow keys (e.g., "bactopia_gather")
            plugins: list of plugin function names
    """
    result: dict[str, list[str]] = {"modules": [], "subworkflows": [], "plugins": []}
    if not main_nf.exists():
        return result

    try:
        text = main_nf.read_text()
    except OSError:
        return result

    seen_modules: set[str] = set()
    seen_subworkflows: set[str] = set()

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
            # e.g., "modules/abricate/run/main" -> "abricate_run"
            component = rel_str.removeprefix("modules/")
            if component.endswith("/main"):
                component = component[:-5]
            key = component.replace("/", "_")
            if key not in seen_modules:
                seen_modules.add(key)
                result["modules"].append(key)
        elif rel_str.startswith("subworkflows/"):
            # e.g., "subworkflows/bactopia/gather/main" -> "bactopia_gather"
            component = rel_str.removeprefix("subworkflows/")
            if component.endswith("/main"):
                component = component[:-5]
            key = component.replace("/", "_")
            if key not in seen_subworkflows:
                seen_subworkflows.add(key)
                result["subworkflows"].append(key)

    return result
