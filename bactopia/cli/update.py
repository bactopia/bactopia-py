import logging
import os
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
from bactopia.utils import execute, validate_file

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-update": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Additional Options",
            "options": [
                "--max_retry",
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}
ANACONDA_API = "https://api.anaconda.org/package/bioconda"


def get_latest_version(tool: str, max_retry: int) -> str:
    """

    Args:
        tool (str): _description_
        max_retry (int): _description_

    Returns:
        str: _description_
    """
    attempt = 1
    url = f"{ANACONDA_API}/{tool}"
    while attempt <= max_retry:
        logging.debug(f"Querying {url} (attempt {attempt} of {max_retry})")
        r = requests.get(f"{ANACONDA_API}/{tool}")
        if r.status_code == requests.codes.ok:
            data = r.json()
            if "latest_version" in data:
                return data["latest_version"]
            else:
                return data["versions"][-1]
        else:
            # Query failed, wait 5 seconds and try again
            attempt += 1
            time.sleep(5)
    logging.warn(f"Unable to query {url} after {max_retry} attempts.")
    return None


def parse_module(module_path: str) -> list:
    """
    Parse a main.nf file and return the module name and version

    Args:
        module_path (str): Path to a main.nf file to parse

    Returns:
        list: Module name and version
    """
    tools = []
    with open(module_path) as fh:
        for line in fh:
            if line.startswith("conda_tools"):
                for tool in line.rstrip().split('"')[1].split():
                    if tool.startswith("bioconda::"):
                        info = tool.replace("bioconda::", "").split("=")
                        tools.append({"name": info[0], "version": info[1]})
    return tools


def parse_modules(bactopia_path: str) -> dict:
    """
    Find all `main.nf` files under the nf-core modules

    Args:
        bactopia_path (str): The path to a bactopia repository
    Returns:
        dict: Module names are keys and values are the path to the module
    """
    modules = {}
    for module in Path(bactopia_path).glob("modules/nf-core/**/main.nf"):
        module_name = (
            str(module).split("nf-core/")[1].split("/main.nf")[0].replace("/", "_")
        )
        tools = parse_module(module)
        modules[module_name] = tools
    return modules


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
    "--max_retry",
    default=3,
    help="Maximum times to attempt API queries. (Default: 3)",
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
@click.argument("unknown", nargs=-1, type=click.UNPROCESSED)
def update(
    bactopia_path,
    max_retry,
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
    needs_update = []
    modules = parse_modules(bactopia_path)
    for module, tools in sorted(modules.items()):
        for tool in tools:
            logging.debug("Checking for newer version of %s", tool["name"])
            latest_version = get_latest_version(tool["name"], max_retry)
            logging.debug(f"Found {latest_version} for {tool['name']}")
            logging.debug("Being nice to Anaconda, sleeping for 1 second")
            if latest_version != tool["version"]:
                needs_update.append(
                    {
                        "module": module,
                        "tool": tool["name"],
                        "current_version": tool["version"],
                        "latest_version": latest_version,
                    }
                )
            time.sleep(1)

    if needs_update:
        print("The following modules need to be updated:")
        for update in needs_update:
            print(
                f"{update['module']}: {update['tool']} {update['current_version']} -> {update['latest_version']}"
            )


def main():
    if len(sys.argv) == 1:
        update.main(["--help"])
    else:
        update()


if __name__ == "__main__":
    main()
