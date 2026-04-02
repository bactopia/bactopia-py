"""Verify NCBI Assembly accession is latest and still available."""

import sys

import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.databases.ncbi import check_assembly_version

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.argument("reference", help="The assembly accession to verify.")
def check_assembly_accession(reference):
    """Verify NCBI Assembly accession is latest and still available."""
    accession = reference.split(".")[0]
    current_accession, excluded = check_assembly_version(accession)
    if excluded:
        print(f"Skipping {accession}. Reason: {current_accession}", file=sys.stderr)
    else:
        print(f"Using {current_accession} for {reference}", file=sys.stderr)
        print(current_accession)


def main():
    if len(sys.argv) == 1:
        check_assembly_accession.main(["--help"])
    else:
        check_assembly_accession()


if __name__ == "__main__":
    main()
