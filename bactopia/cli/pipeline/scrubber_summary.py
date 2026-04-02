"""Create a before-and-after report from human read scrubbing."""

import sys

import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.parsers.generic import parse_json

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.argument("sample", help="Name of the input sample.")
@click.argument("original", help="Original FASTQ stats in JSON format.")
@click.argument("scrubbed", help="Scrubbed FASTQ stats in JSON format.")
def scrubber_summary(sample, original, scrubbed):
    """Create a before-and-after report from human read scrubbing."""
    original_json = parse_json(original)
    scrubbed_json = parse_json(scrubbed)

    cols = [
        "sample",
        "original_read_total",
        "scrubbed_read_total",
        "host_read_total",
    ]
    results = [
        sample,
        str(original_json["qc_stats"]["read_total"]),
        str(scrubbed_json["qc_stats"]["read_total"]),
        str(
            original_json["qc_stats"]["read_total"]
            - scrubbed_json["qc_stats"]["read_total"]
        ),
    ]

    print("\t".join(cols))
    print("\t".join(results))


def main():
    if len(sys.argv) == 1:
        scrubber_summary.main(["--help"])
    else:
        scrubber_summary()


if __name__ == "__main__":
    main()
