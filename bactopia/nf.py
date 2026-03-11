"""Nextflow repo introspection utilities for Bactopia."""

import logging
import re
import sys
from pathlib import Path

from bactopia.utils import execute


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
    """Parse Bactopia's workflows.yaml to get modules per-workflow"""
    from bactopia.parsers.generic import parse_yaml

    # Load the workflows.yml file
    logging.debug(f"Loading workflows from {bactopia_path}/data/workflows.yml")
    workflows_yaml = parse_yaml(f"{bactopia_path}/data/workflows.yml")
    workflows = workflows_yaml["workflows"]

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
            modules = {}

            # Get modules from includes
            if "includes" in wf_info:
                for include in wf_info["includes"]:
                    if include in workflows and "modules" in workflows[include]:
                        if include == "merlin" and not include_merlin:
                            logging.debug(
                                "Skipping merlin modules since --include_merlin not set"
                            )
                            continue
                        else:
                            for module in workflows[include]["modules"]:
                                logging.debug(
                                    f"Adding module {module} from include {include}"
                                )
                                modules[module] = True

            # Get direct modules
            if "modules" in wf_info:
                for module in wf_info["modules"]:
                    logging.debug(f"Adding module {module}")
                    modules[module] = True

            # Parse each module
            for module in modules:
                # Convert module name to path (underscore to slash)
                module_path = f"modules/{module.replace('_', '/')}"
                final_workflows[wf][module] = (
                    f"{bactopia_path}/{module_path}/module.config"
                )

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


def parse_dataset_urls(bactopia_path, datasets_path):
    """Parse Bactopia's Nextflow config to extract dataset download URLs.

    Args:
        bactopia_path: Path to the Bactopia repository.
        datasets_path: Base path where datasets will be saved.

    Returns:
        List of dicts with 'dataset', 'url', and 'save_path' keys.
    """
    urls = []
    nf_config, stderr = execute(
        f"nextflow config -flat {bactopia_path}/main.nf", capture=True
    )
    for line in nf_config.split("\n"):
        if "_url =" in line:
            param, val = line.split(" = ")
            param = param.replace("params.", "")
            val = val.replace("'", "")
            urls.append(
                {
                    "dataset": param.split("_")[0],
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
