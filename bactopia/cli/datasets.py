import logging
import os
import sys
import time
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.utils import execute, validate_file

BACTOPIA_CACHEDIR = os.getenv("BACTOPIA_CACHEDIR", f"{Path.home()}/.bactopia")

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-datasets": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Download Related Options",
            "options": [
                "--datasets_cache",
                "--force",
                "--max_retry",
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


def parse_urls(bactopia_path, datasets_path):
    """Parse Bactopia's workflows.conf to get modules per-workflow"""
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


def download_file(url, save_path, max_retry=5):
    """Download file, with chance to retry."""
    retry = 0
    allow_fail = False
    success = False

    # Make sure the directory exists
    if not Path(save_path).parent.exists():
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    while not success:
        result = execute(f"wget -O {save_path} {url}", allow_fail=allow_fail)
        if not result:
            if retry > max_retry:
                allow_fail = True
            retry += 1
            logging.error("Error downloading file, retrying after short sleep.")
            time.sleep(30 * retry)
        else:
            success = True

    return success


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
    "--datasets_cache",
    default=BACTOPIA_CACHEDIR,
    show_default=True,
    help="Base directory to download datasets to (Defaults to env variable BACTOPIA_CACHEDIR, a subfolder called datasets will be created)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force overwrite of existing pre-built environments.",
)
@click.option(
    "--max_retry",
    default=3,
    help="Maximum times to attempt creating Conda environment. (Default: 3)",
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
@click.argument("unknown", nargs=-1, type=click.UNPROCESSED)
def datasets(
    bactopia_path,
    datasets_cache,
    force,
    max_retry,
    verbose,
    silent,
    unknown,
):
    """Download optional datasets to supplement your analyses with Bactopia"""
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
    datasets_path = str(Path(datasets_cache).absolute())
    datasets_path = f"{datasets_path}/datasets"

    # Current Bactopia workflows
    workflow_urls = parse_urls(bactopia_path, datasets_path)
    for url in workflow_urls:
        if Path(url["save_path"]).exists() and not force:
            logging.warn(
                f"Found {url['dataset']} at {url['save_path']}, will not overwrite unless --force is used."
            )
        else:
            logging.info(f"Downloading {url['dataset']} dataset to {url['save_path']}")
            download_file(url["url"], url["save_path"], max_retry)


def main():
    if len(sys.argv) == 1:
        datasets.main(["--help"])
    else:
        datasets()


if __name__ == "__main__":
    main()
