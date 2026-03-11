import json
import logging
import sys
import time
from pathlib import Path

import requests
import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.nf import parse_all_conda_tools

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-update": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Module Options",
            "options": [
                "--module",
                "--max_retry",
            ],
        },
        {
            "name": "Output Options",
            "options": [
                "--json",
                "--pretty",
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
ANACONDA_API = "https://api.anaconda.org/package/bioconda"


def get_latest_info(tool: str, max_retry: int) -> dict | None:
    """Query Anaconda API for the latest version and build of a bioconda tool.

    Args:
        tool: The bioconda package name (e.g. "bakta").
        max_retry: Maximum number of query attempts.

    Returns:
        Dict with 'version' and 'build' keys, or None on failure.
    """
    attempt = 1
    url = f"{ANACONDA_API}/{tool}"
    while attempt <= max_retry:
        logging.debug(f"Querying {url} (attempt {attempt} of {max_retry})")
        r = requests.get(url)
        if r.status_code == requests.codes.ok:
            data = r.json()
            version = data.get("latest_version") or data.get("versions", [None])[-1]

            # Find the latest linux-64 build string from the files array
            # Bioconda publishes separate builds per platform (linux-64,
            # osx-64, linux-aarch64, etc.) and Bactopia only targets linux-64.
            build = None
            if "files" in data:
                for f in reversed(data["files"]):
                    attrs = f.get("attrs", {})
                    if (
                        f.get("version") == version
                        and attrs.get("subdir") == "linux-64"
                    ):
                        build = attrs.get("build")
                        break

            return {"version": version, "build": build}
        else:
            attempt += 1
            time.sleep(5)
    logging.warning(f"Unable to query {url} after {max_retry} attempts.")
    return None


@click.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@click.version_option(bactopia.__version__, "--version")
# Use underscores in parameters and only --, since Nextflow parameters are passed in
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--module",
    default=None,
    help="Only check a specific module for updates (e.g. 'fastp')",
)
@click.option(
    "--max_retry",
    default=3,
    help="Maximum times to attempt API queries. (Default: 3)",
)
@click.option("--json", "output_json", is_flag=True, help="Output flat JSON.")
@click.option("--pretty", is_flag=True, help="Output pretty-printed JSON.")
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
@click.argument("unknown", nargs=-1, type=click.UNPROCESSED)
def update(
    bactopia_path,
    module,
    max_retry,
    output_json,
    pretty,
    verbose,
    silent,
    unknown,
):
    """Check if modules used by Bactopia Tools have newer versions available"""
    # Setup logs
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )

    # Install paths
    bactopia_path = str(Path(bactopia_path).absolute())
    logging.debug(f"Using bactopia path: {bactopia_path}")

    # Get modules to update
    modules = parse_all_conda_tools(bactopia_path, module_filter=module)

    if module and not modules:
        # Re-parse without filter to show available modules in error
        all_modules = parse_all_conda_tools(bactopia_path)
        logging.error(
            f"'{module}' does not match any Bactopia modules. "
            f"Use --verbose to see available modules."
        )
        for m in sorted(all_modules):
            logging.debug(f"  Available module: {m}")
        sys.exit(1)

    if module:
        logging.info(f"Checking {len(modules)} module(s) matching '{module}'")

    # Query Anaconda for latest versions, caching to avoid duplicate queries
    results = []
    info_cache = {}
    for mod_name, mod_info in sorted(modules.items()):
        is_multi_tool = len(mod_info["tools"]) > 1

        if is_multi_tool:
            # Multi-tool modules use mulled containers that can't be
            # constructed programmatically -- flag for user review
            primary = mod_info["tools"][0]
            logging.debug(
                f"Skipping API queries for multi-tool module {mod_name}, "
                f"flagging for user review"
            )
            results.append(
                {
                    "tool": primary["name"],
                    "module": mod_name,
                    "config": mod_info["config"],
                    "installed_version": primary["version"],
                    "needs_user_review": True,
                }
            )
            continue

        for tool in mod_info["tools"]:
            tool_name = tool["name"]

            # Tools with a build pin in the conda string (e.g.
            # bioconda::tool=1.0=h123_0) need manual review
            if tool.get("pinned"):
                logging.debug(
                    f"Skipping API queries for build-pinned tool {tool_name}, "
                    f"flagging for user review"
                )
                results.append(
                    {
                        "tool": tool_name,
                        "module": mod_name,
                        "config": mod_info["config"],
                        "installed_version": tool["version"],
                        "needs_user_review": True,
                    }
                )
                continue

            if tool_name not in info_cache:
                logging.debug("Checking for newer version of %s", tool_name)
                info_cache[tool_name] = get_latest_info(tool_name, max_retry)
                if info_cache[tool_name]:
                    logging.debug(
                        f"Found {info_cache[tool_name]['version']} "
                        f"(build: {info_cache[tool_name]['build']}) for {tool_name}"
                    )
                time.sleep(1)
            else:
                logging.debug(f"Using cached info for {tool_name}")

            latest = info_cache[tool_name]
            version_changed = (
                latest is not None and latest["version"] != tool["version"]
            )
            build_changed = (
                latest is not None
                and latest["build"] is not None
                and latest["build"] != tool.get("build")
            )
            needs_update = version_changed or build_changed
            entry = {
                "tool": tool_name,
                "module": mod_name,
                "config": mod_info["config"],
                "installed_version": tool["version"],
                "installed_build": tool.get("build"),
                "latest_version": latest["version"] if latest else None,
                "latest_build": latest["build"] if latest else None,
                "needs_update": needs_update,
            }

            if latest and latest["build"]:
                version = latest["version"]
                build = latest["build"]
                entry["latest_toolName"] = f"bioconda::{tool_name}={version}"
                entry["latest_docker"] = f"biocontainers/{tool_name}:{version}--{build}"
                entry["latest_image"] = (
                    f"https://depot.galaxyproject.org/singularity/"
                    f"{tool_name}:{version}--{build}"
                )

            results.append(entry)

    if output_json:
        print(json.dumps(results))
    elif pretty:
        print(json.dumps(results, indent=2))
    else:
        for entry in results:
            if entry.get("needs_user_review"):
                print(
                    f"[REVIEW] {entry['module']}: {entry['tool']} "
                    f"{entry['installed_version']}"
                )
            else:
                status = "UPDATE" if entry["needs_update"] else "OK"
                installed = entry["installed_version"]
                latest = entry["latest_version"]
                if entry.get("installed_build") or entry.get("latest_build"):
                    installed = f"{installed}--{entry.get('installed_build', '?')}"
                    latest = f"{latest}--{entry.get('latest_build', '?')}"
                print(
                    f"[{status}] {entry['module']}: {entry['tool']} "
                    f"{installed} -> {latest}"
                )


def main():
    if len(sys.argv) == 1:
        update.main(["--help"])
    else:
        update()


if __name__ == "__main__":
    main()
