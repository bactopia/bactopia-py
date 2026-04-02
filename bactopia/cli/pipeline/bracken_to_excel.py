"""Write Bracken abundances to an Excel file."""

import sys

import pandas as pd
import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.argument("prefix", help="Prefix to use for output files.")
@click.argument("bracken_abundances", help="The Bracken output with abundances.")
@click.option(
    "--limit", type=int, default=5, help="Limit the result to the top N rows."
)
@click.option(
    "--include_unclassified",
    is_flag=True,
    help="Include results for unclassified reads.",
)
def bracken_to_excel(prefix, bracken_abundances, limit, include_unclassified):
    """Write Bracken abundances to an Excel file."""
    bracken = pd.read_csv(bracken_abundances, sep="\t")
    samples = bracken["sample"].unique()

    with pd.ExcelWriter(f"{prefix}.xlsx") as writer:
        for sample in samples:
            sheet_name = sample
            if len(sample) > 31:
                sheet_name = sample[:31]
            df = bracken[bracken["sample"] == sample]
            if not include_unclassified:
                df = df[df["name"] != "unclassified"]

            df.sort_values(by="fraction_total_reads", ascending=False).head(
                limit
            ).to_excel(writer, sheet_name=sheet_name, index=False)


def main():
    if len(sys.argv) == 1:
        bracken_to_excel.main(["--help"])
    else:
        bracken_to_excel()


if __name__ == "__main__":
    main()
