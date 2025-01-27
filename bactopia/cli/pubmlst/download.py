import logging
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.databases.pubmlst import download_database

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-pubmlst-download": [
        {
            "name": "Required Options",
            "options": [
                "--database",
            ],
        },
        {
            "name": "API Options",
            "options": [
                "--site",
                "--token-dir",
                "--out-dir",
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
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--database",
    "-d",
    default="pubmlst_yersinia_seqdef",
    show_default=True,
    help="The organism database to interact with for setup.",
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
    "--token-dir",
    "-t",
    default=".bactopia/pubmlst",
    show_default=True,
    help="The directory where the token file is saved.",
)
@click.option(
    "--out-dir",
    "-o",
    default="./pubmlst",
    show_default=True,
    help="The directory where the database files will be saved.",
)
@click.option("--force", is_flag=True, help="Force overwrite of existing files.")
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
def pubmlst_download(
    database: str,
    site: str,
    token_dir: str,
    out_dir: str,
    force: bool,
    verbose: bool,
    silent: bool,
):
    """Download specific database files from PubMLST or Pasteur."""
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

    # Setup tokens for pubmlst
    token_file = f"{token_dir}/{site}-token.json"
    if not Path(token_file).exists() and not force:
        logging.error(f"Token file does not exist: {token_file}")
        logging.error("Please run `bactopia-pubmlst-setup` to create the token file.")
        sys.exit(1)
    else:
        logging.info(f"Using token file: {token_file}")

    # check if out-dir exists
    out_dir = Path(f"{out_dir}/{site}/{database}")
    if out_dir.exists() and not force:
        logging.error(f"Output directory exists: {out_dir}")
        logging.error("Use --force to overwrite existing files.")
        sys.exit(1)
    else:
        logging.debug(f"Creating output directory: {out_dir}")
        out_dir.mkdir(parents=True, exist_ok=True)

    logging.info(f"Downloading {database} from {site}")
    download_database(database, site, token_file, out_dir, force)


def main():
    if len(sys.argv) == 1:
        pubmlst_download.main(["--help"])
    else:
        pubmlst_download()


if __name__ == "__main__":
    main()
