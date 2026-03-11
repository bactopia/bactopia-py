import logging
import os
import shutil
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.nf import parse_module_config, parse_workflows
from bactopia.utils import execute

BACTOPIA_CACHEDIR = os.getenv("BACTOPIA_CACHEDIR", f"{Path.home()}/.bactopia")
CONDA_CACHEDIR = os.getenv("NXF_CONDA_CACHEDIR", f"{BACTOPIA_CACHEDIR}/conda")
SINGULARITY_CACHEDIR = os.getenv(
    "NXF_SINGULARITY_CACHEDIR", f"{BACTOPIA_CACHEDIR}/singularity"
)

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-prune": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Prune Options",
            "options": [
                "--envtype",
                "--wf",
                "--condadir",
                "--registry",
                "--singularity_cache",
                "--singularity_pull_docker_container",
                "--execute",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}


def get_directory_size(path: Path) -> int:
    """Recursively sum file sizes within a directory.

    Args:
        path: Directory path.

    Returns:
        Total size in bytes.
    """
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string (e.g. "142.3 MB").
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_current_env_names(
    bactopia_path: str,
    wf: str,
    build_all: bool,
    registry: str,
    use_build: bool,
) -> dict:
    """Build sets of current environment names from module configs.

    Args:
        bactopia_path: Path to the Bactopia repository.
        wf: Workflow name to check.
        build_all: Whether to include all workflows.
        registry: Docker registry prefix.
        use_build: Whether singularity names derive from docker images.

    Returns:
        Dict with 'conda', 'singularity', and 'docker' sets of current env names,
        plus 'tools' dict mapping conda base names to full tool info for
        grouped output.
    """
    current = {
        "conda": set(),
        "singularity": set(),
        "docker": set(),
        "tools": {},
    }

    workflow_modules = parse_workflows(
        bactopia_path, wf, include_merlin=True, build_all=build_all
    )

    seen = set()
    for workflow, modules in workflow_modules.items():
        for module, config in modules.items():
            if config in seen:
                continue
            seen.add(config)
            info = parse_module_config(config, registry)
            if not info:
                continue

            # Conda name (same transform as download.py:99-101)
            conda_envname = (
                info["conda"].replace("=", "-").replace(":", "-").replace(" ", "-")
            )
            current["conda"].add(conda_envname)

            # Build base name for matching stale envs (part before version)
            # e.g. "bioconda::abricate=1.0.3" -> base "bioconda--abricate"
            conda_base = info["conda"].split("=")[0].replace(":", "-").replace(" ", "-")

            # Extract tool name and version from conda spec
            conda_spec = info["conda"]
            tool_name = (
                conda_spec.split("::")[-1].split("=")[0]
                if "::" in conda_spec
                else conda_spec.split("=")[0]
            )
            tool_version = conda_spec.split("=")[1] if "=" in conda_spec else ""

            # Docker name
            current["docker"].add(info["docker"])

            # Singularity name (same logic as download.py:105-116)
            if use_build:
                sing_name = info["docker"].replace(":", "-").replace("/", "-")
            elif not info.get("singularity"):
                sing_name = info["docker"].replace(":", "-").replace("/", "-")
            else:
                sing_name = (
                    info["singularity"]
                    .replace("https://", "")
                    .replace(":", "-")
                    .replace("/", "-")
                )
            sing_full = f"{sing_name}.img"
            current["singularity"].add(sing_full)

            # Docker base for matching singularity filenames
            docker_base = info["docker"].split(":")[0].replace("/", "-")

            # Store full tool info for grouped output
            current["tools"][conda_base] = {
                "name": tool_name,
                "version": tool_version,
                "conda": conda_envname,
                "singularity": sing_full,
                "docker": info["docker"],
                "docker_base": docker_base,
            }

    return current


def find_stale_conda(conda_path: str, current_names: set, tools: dict) -> list:
    """Find conda environment directories not in the current set.

    Args:
        conda_path: Path to the conda cache directory.
        current_names: Set of current conda env directory names.
        tools: Dict mapping conda base names to tool info.

    Returns:
        List of dicts with 'path', 'name', 'size', and 'base' keys.
    """
    stale = []
    conda_dir = Path(conda_path)
    if not conda_dir.exists():
        logging.warning(f"Conda directory does not exist: {conda_path}")
        return stale

    for entry in sorted(conda_dir.iterdir()):
        if entry.is_dir() and entry.name not in current_names:
            size = get_directory_size(entry)
            # Find matching tool by base name prefix
            matched_base = None
            for base in tools:
                if entry.name.startswith(f"{base}-"):
                    matched_base = base
                    break
            stale.append(
                {"path": entry, "name": entry.name, "size": size, "base": matched_base}
            )

    return stale


def find_stale_singularity(
    singularity_path: str, current_names: set, tools: dict
) -> list:
    """Find singularity image files not in the current set.

    Args:
        singularity_path: Path to the singularity cache directory.
        current_names: Set of current singularity image filenames (with .img).
        tools: Dict mapping conda base names to tool info.

    Returns:
        List of dicts with 'path', 'name', 'size', and 'base' keys.
    """
    stale = []
    sing_dir = Path(singularity_path)
    if not sing_dir.exists():
        logging.warning(f"Singularity directory does not exist: {singularity_path}")
        return stale

    # Build tool_name -> conda_base lookup for matching singularity filenames
    # Singularity files look like: depot.galaxyproject.org-singularity-<tool>-<version>--<build>.img
    tool_name_to_conda_base = {}
    for conda_base, info in tools.items():
        tool_name_to_conda_base[info["name"]] = conda_base

    for entry in sorted(sing_dir.iterdir()):
        if (
            entry.is_file()
            and entry.suffix == ".img"
            and entry.name not in current_names
        ):
            matched_base = None
            for tool_name, conda_base in tool_name_to_conda_base.items():
                # Match tool name in the singularity filename
                # e.g. "depot.galaxyproject.org-singularity-abricate-1.0.1--ha8f3691_1.img"
                if f"-{tool_name}-" in entry.name:
                    matched_base = conda_base
                    break
            stale.append(
                {
                    "path": entry,
                    "name": entry.name,
                    "size": entry.stat().st_size,
                    "base": matched_base,
                }
            )

    return stale


def find_stale_docker(current_names: set, tools: dict) -> list:
    """Find docker images not in the current set.

    Only considers images from biocontainer registries. Docker images are
    reported but not removed.

    Args:
        current_names: Set of current docker image strings.
        tools: Dict mapping conda base names to tool info.

    Returns:
        List of dicts with 'image' and 'base' keys.
    """
    stale = []
    output, stderr_out = execute(
        "docker images --format '{{.Repository}}:{{.Tag}}'",
        capture=True,
        allow_fail=True,
    )
    if output is None:
        logging.warning("Docker is not available, skipping docker check")
        return stale

    # Build docker image base -> conda_base lookup
    docker_to_conda_base = {}
    for conda_base, info in tools.items():
        # e.g. "quay.io/biocontainers/abricate" -> conda_base
        docker_repo = info["docker"].split(":")[0]
        docker_to_conda_base[docker_repo] = conda_base

    for line in output.strip().split("\n"):
        line = line.strip().strip("'\"")
        if not line or line == "<none>:<none>":
            continue
        # Only consider biocontainer-related images
        if "biocontainers" not in line:
            continue
        if line not in current_names:
            matched_base = None
            repo = line.split(":")[0]
            if repo in docker_to_conda_base:
                matched_base = docker_to_conda_base[repo]
            stale.append({"image": line, "base": matched_base})

    return stale


@click.command()
@click.version_option(bactopia.__version__, "--version")
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--envtype",
    default="all",
    show_default=True,
    type=click.Choice(["conda", "docker", "singularity", "all"], case_sensitive=False),
    help="The type of environment to check for stale items.",
)
@click.option(
    "--wf",
    default=None,
    help="Only check environments for the given workflow (default: all workflows)",
)
@click.option(
    "--condadir",
    default=CONDA_CACHEDIR,
    show_default=True,
    help="Directory where Conda environments are stored (NXF_CONDA_CACHEDIR env variable takes precedence)",
)
@click.option(
    "--registry",
    default="quay.io",
    show_default=True,
    help="Registry to match Docker containers against.",
)
@click.option(
    "--singularity_cache",
    default=SINGULARITY_CACHEDIR,
    show_default=True,
    help="Directory where Singularity images are stored (NXF_SINGULARITY_CACHEDIR env variable takes precedence)",
)
@click.option(
    "--singularity_pull_docker_container",
    is_flag=True,
    help="Use Docker-based naming for Singularity images",
)
@click.option(
    "--execute",
    "execute_removal",
    is_flag=True,
    help="Actually remove stale environments. Default is dry-run (report only).",
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
def prune(
    bactopia_path,
    envtype,
    wf,
    condadir,
    registry,
    singularity_cache,
    singularity_pull_docker_container,
    execute_removal,
    verbose,
    silent,
):
    """Removes stale Bactopia environments that no longer match current module versions."""
    # Setup logs
    logging.basicConfig(
        format="%(message)s",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                console=rich.console.Console(stderr=True),
                show_time=False,
                show_path=False,
            )
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )

    # Resolve paths
    bactopia_path = str(Path(bactopia_path).absolute())
    conda_path = str(Path(condadir).absolute())
    singularity_path = str(Path(singularity_cache).absolute())

    # Build current environment names (all workflows unless --wf is given)
    build_all = wf is None
    if build_all:
        wf = "bactopia"
    logging.info("Scanning module configs for current environment versions...")
    current = get_current_env_names(
        bactopia_path, wf, build_all, registry, singularity_pull_docker_container
    )
    logging.info(
        f"Found {len(current['conda'])} current conda, "
        f"{len(current['singularity'])} current singularity, "
        f"{len(current['docker'])} current docker environments"
    )

    check_conda = envtype in ("conda", "all")
    check_singularity = envtype in ("singularity", "all")
    check_docker = envtype in ("docker", "all")
    tools = current["tools"]

    # Collect stale items
    logging.info("Scanning for stale environments...")
    if check_conda:
        logging.info(f"[condadir] {conda_path}")
    if check_singularity:
        logging.info(f"[singularity_cache] {singularity_path}")
    if check_docker:
        logging.info("[docker] local daemon")

    stale_conda = (
        find_stale_conda(conda_path, current["conda"], tools) if check_conda else []
    )
    stale_singularity = (
        find_stale_singularity(singularity_path, current["singularity"], tools)
        if check_singularity
        else []
    )
    stale_docker = find_stale_docker(current["docker"], tools) if check_docker else []

    # Group stale items by tool base name
    grouped = {}
    for item in stale_conda:
        base = item["base"] or item["name"]
        grouped.setdefault(base, {"conda": [], "singularity": [], "docker": []})
        grouped[base]["conda"].append(item)
    for item in stale_singularity:
        base = item["base"] or item["name"]
        grouped.setdefault(base, {"conda": [], "singularity": [], "docker": []})
        grouped[base]["singularity"].append(item)
    for item in stale_docker:
        base = item["base"] or item["image"]
        grouped.setdefault(base, {"conda": [], "singularity": [], "docker": []})
        grouped[base]["docker"].append(item)

    if not grouped:
        logging.info("No stale environments found")
        return

    # Display grouped output
    total_freed = 0
    stale_count = 0
    for base in sorted(grouped):
        group = grouped[base]
        tool_info = tools.get(base)

        # Header line: tool name with version change
        if tool_info:
            # Extract stale version from conda dir name or docker tag
            stale_version = ""
            if group["conda"]:
                prefix = f"{base}-"
                name = group["conda"][0]["name"]
                if name.startswith(prefix):
                    stale_version = name[len(prefix) :]
            elif group["docker"]:
                img = group["docker"][0]["image"]
                if ":" in img:
                    stale_version = img.split(":")[1]
            current_version = tool_info["version"]
            logging.info(
                f"[stale] {tool_info['name']} {stale_version} -> {current_version}"
            )
        else:
            logging.info(f"[stale] {base} (unknown tool)")

        # Sub-lines for each env type
        for item in group["conda"]:
            size_str = format_size(item["size"])
            if execute_removal:
                logging.info(f"[conda] removing {item['name']} ({size_str})")
                try:
                    shutil.rmtree(item["path"])
                except OSError as e:
                    logging.error(f"  [conda] failed to remove {item['path']}: {e}")
            else:
                logging.info(f"  [conda] {item['name']} ({size_str})")
            total_freed += item["size"]
            stale_count += 1

        for item in group["singularity"]:
            size_str = format_size(item["size"])
            if execute_removal:
                logging.info(f"  [singularity] removing {item['name']} ({size_str})")
                try:
                    item["path"].unlink()
                except OSError as e:
                    logging.error(
                        f"  [singularity] failed to remove {item['path']}: {e}"
                    )
            else:
                logging.info(f"  [singularity] {item['name']} ({size_str})")
            total_freed += item["size"]
            stale_count += 1

        for item in group["docker"]:
            logging.info(f"  [docker] {item['image']}")
            stale_count += 1

    # Summary
    logging.info(
        f"{'Removed' if execute_removal else 'Found'} {stale_count} stale "
        f"environment(s) ({format_size(total_freed)})"
    )
    if not execute_removal and total_freed > 0:
        logging.info("Use --execute to remove stale environments.")


def main():
    if len(sys.argv) == 1:
        prune.main(["--help"])
    else:
        prune()


if __name__ == "__main__":
    main()
