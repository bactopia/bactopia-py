import logging
import shutil
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.atb import create_sample_directory, search_path
from bactopia.utils import validate_file

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-atb-formatter": [
        {"name": "Required Options", "options": ["--path"]},
        {
            "name": "Bactopia Directory Structure Options",
            "options": [
                "--bactopia-dir",
                "--publish-mode",
                "--recursive",
                "--extension",
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
    "--path",
    "-p",
    required=True,
    help="Directory where ATB assemblies are stored",
)
@click.option(
    "--bactopia-dir",
    "-b",
    default="bactopia",
    show_default=True,
    help="The path you would like to place bactopia structure",
)
@click.option(
    "--publish-mode",
    "-m",
    default="symlink",
    show_default=True,
    type=click.Choice(["symlink", "copy"], case_sensitive=False),
    help="Specifies how assemblies will be saved in the Bactopia directory",
)
@click.option(
    "--extension",
    "-e",
    default=".fa",
    show_default=True,
    help="The extension of the FASTA files",
)
@click.option(
    "--recursive", "-r", is_flag=True, help="Traverse recursively through provided path"
)
@click.option("--verbose", is_flag=True, help="Increase the verbosity of output")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def atb_formatter(
    path,
    bactopia_dir,
    publish_mode,
    extension,
    recursive,
    verbose,
    silent,
):
    """Restructure All-the-Bacteria assemblies to allow usage with Bactopia Tools"""
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

    # Get absolute path of input
    abspath = validate_file(path)

    # Match Assemblies
    count = 0
    logging.info(
        "Setting up Bactopia directory structure (use --verbose to see more details)"
    )
    for fasta in search_path(abspath, f"*{extension}", recursive=recursive):
        fasta_name = fasta.name.replace(extension, "")
        create_sample_directory(fasta_name, fasta, bactopia_dir, publish_mode)
        count += 1
    logging.info(f"Bactopia directory structure created at {bactopia_dir}")
    logging.info(f"Total assemblies processed: {count}")


def main():
    if len(sys.argv) == 1:
        atb_formatter.main(["--help"])
    else:
        atb_formatter()


if __name__ == "__main__":
    main()
