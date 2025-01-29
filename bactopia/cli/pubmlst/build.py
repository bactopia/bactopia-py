import logging
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.databases.pubmlst.utils import (
    available_databases,
    build_blast_db,
    download_database,
    print_citation,
)

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-pubmlst-build": [
        {
            "name": "Required Options",
            "options": [
                "--database",
            ],
        },
        {
            "name": "Build Options",
            "options": [
                "--ignore",
                "--skip-download",
                "--skip-blast",
                "--force",
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
    help="A known organism database to download. (Use 'all' to download all databases.)",
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
    default=f"{Path.home()}/.bactopia",
    show_default=True,
    help="The directory where the token file is saved.",
)
@click.option(
    "--out-dir",
    "-o",
    default="./bactopia-mlst",
    show_default=True,
    help="The directory where the database files will be saved.",
)
@click.option(
    "--ignore",
    default="afumigatus,blastocystis,calbicans,cbotulinum,cglabrata,ckrusei,ctropicalis,csinensis,kseptempunctata,rmlst,sparasitica,test,tpallidum,tvaginalis",
    show_default=True,
    help="A comma separated list of databases to ignore.",
)
@click.option(
    "--skip-download", is_flag=True, help="Skip downloading the database files."
)
@click.option("--skip-blast", is_flag=True, help="Skip building the BLAST database.")
@click.option("--force", is_flag=True, help="Force overwrite of existing files.")
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
def pubmlst_download(
    database: str,
    site: str,
    token_dir: str,
    out_dir: str,
    ignore: str,
    skip_download: bool,
    skip_blast: bool,
    force: bool,
    verbose: bool,
    silent: bool,
):
    """Build PubMLST databases for use with the 'mlst' Bactopia Tool."""
    # Setup logs
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                console=rich.console.Console(stderr=True),
                show_time=True if verbose else False,
                show_level=True if verbose else False,
                show_path=True,
                markup=True,
            )
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )

    # Ignore DBs
    ignore_dbs = ignore.split(",")

    # check if out-dir exists
    mlst_dir = Path(f"{out_dir}/mlstdb/{site}")
    if mlst_dir.exists() and not force:
        logging.error(f"Output directory exists: {mlst_dir}")
        logging.error("Use --force to overwrite existing files.")
        sys.exit(1)
    else:
        logging.debug(f"Creating output directory: {mlst_dir}")
        mlst_dir.mkdir(parents=True, exist_ok=True)

    if not skip_download:
        # Setup tokens for pubmlst
        token_file = f"{token_dir}/{site}-token.json"
        if not Path(token_file).exists() and not force:
            logging.error(f"Token file does not exist: {token_file}")
            logging.error(
                "Please run `bactopia-pubmlst-setup` to create the token file."
            )
            sys.exit(1)
        else:
            logging.info(f"Using token file: '{token_file}'")

        # Get available databases
        databases = available_databases(site, token_file)
        database_found = False
        for db, description in databases.items():
            if db == database:
                database_found = True
                if db in ignore_dbs:
                    logging.info(f"Ignoring database: {db} (use --ignore to change)")
                    continue
                download_database(database, site, token_file, mlst_dir, force)
            elif database == "all":
                database_found = True
                if db in ignore_dbs:
                    logging.info(f"Ignoring database: {db} (use --ignore to change)")
                    continue
                download_database(db, site, token_file, mlst_dir, force)

        if not database_found:
            logging.error(f"Database '{database}' not found in {site} databases.")
            logging.error(f"Available databases: {', '.join(databases.keys())}")
            sys.exit(1)

    if not skip_blast:
        # Build MLST database
        build_blast_db(
            out_dir,
        )

    print_citation()


def main():
    if len(sys.argv) == 1:
        pubmlst_download.main(["--help"])
    else:
        pubmlst_download()


if __name__ == "__main__":
    main()
