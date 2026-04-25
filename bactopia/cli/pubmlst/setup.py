"""CLI command for setting up PubMLST API access tokens."""

import logging
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.cli.common import common_options, setup_logging
from bactopia.databases.pubmlst.utils import print_citation, setup_pubmlst

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-pubmlst-setup": [
        {"name": "Required Options", "options": ["--client-id", "--client-secret"]},
        {
            "name": "API Options",
            "options": [
                "--site",
                "--database",
                "--save-dir",
                "--force",
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


@click.command()
@common_options
@click.option(
    "--client-id",
    "-ci",
    required=True,
    help="The client ID for the site",
)
@click.option(
    "--client-secret",
    "-cs",
    required=True,
    help="The client secret for the site",
)
@click.option(
    "--site",
    "-s",
    default="pubmlst",
    show_default=True,
    type=click.Choice(["pubmlst", "pasteur"], case_sensitive=True),
    help="Only print citation matching a given name",
)
@click.option(
    "--database",
    "-d",
    default="pubmlst_yersinia_seqdef",
    show_default=True,
    help="The organism database to interact with for setup. Note: the default is available from both PubMLST and Pasteur",
)
@click.option(
    "--save-dir",
    "-sd",
    default=f"{Path.home()}/.bactopia",
    show_default=True,
    help="The directory to save the token",
)
@click.option("--force", is_flag=True, help="Force overwrite of existing token files")
def pubmlst_setup(
    site: str,
    database: str,
    client_id: str,
    client_secret: str,
    save_dir: str,
    force: bool,
    verbose: bool,
    silent: bool,
):
    """One-time setup for interacting with the PubMLST API"""
    setup_logging(verbose, silent)

    # Setup tokens for pubmlst
    save_dir = Path(save_dir)
    if not save_dir.exists():
        logging.debug(f"Creating {save_dir}")
        save_dir.mkdir(parents=True, exist_ok=True)
    token_file = f"{save_dir}/{site}-token.json"
    if Path(token_file).exists() and not force:
        logging.error(
            f"Token file already exists at {token_file}. Will not overwrite unless --force is used."
        )
        sys.exit(1)
    setup_pubmlst(site, database, token_file, client_id, client_secret)
    print_citation()


def main():
    if len(sys.argv) == 1:
        pubmlst_setup.main(["--help"])
    else:
        pubmlst_setup()


if __name__ == "__main__":
    main()
