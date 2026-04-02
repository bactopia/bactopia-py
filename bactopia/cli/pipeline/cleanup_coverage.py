"""Reduce redundancy in per-base coverage from genomeCoverageBed output."""

import sys

import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.parsers.coverage import read_coverage

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.argument("coverage", help="The per-base coverage file from genomeCoverageBed.")
def cleanup_coverage(coverage):
    """Reduce redundancy in per-base coverage from genomeCoverageBed output."""
    coverages = read_coverage(coverage, format="tabbed")
    for accession, vals in coverages.items():
        print(f"##contig=<ID={accession},length={vals['length']}>")
        for cov in vals["positions"]:
            print(cov)


def main():
    if len(sys.argv) == 1:
        cleanup_coverage.main(["--help"])
    else:
        cleanup_coverage()


if __name__ == "__main__":
    main()
