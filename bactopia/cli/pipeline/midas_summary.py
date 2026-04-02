"""Consolidate MIDAS species abundance to species-level resolution."""

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
@click.argument("midas_report", help="The MIDAS species abundance report.")
def midas_summary(prefix, midas_report):
    """Consolidate MIDAS species abundance to species-level resolution."""
    midas = pd.read_csv(midas_report, sep="\t")

    # Use "representatives" later
    midas.rename(columns={"species_id": "representatives"}, inplace=True)

    # Split to genus and species then merge them with a space
    midas["genus"] = midas["representatives"].apply(lambda x: x.split("_")[0])
    midas["species"] = midas["representatives"].apply(lambda x: x.split("_")[1])
    midas["species_id"] = midas["genus"].astype(str) + " " + midas["species"]
    midas.drop(columns=["genus", "species"], inplace=True)

    # Reorder columns
    midas = midas[
        [
            "species_id",
            "count_reads",
            "coverage",
            "relative_abundance",
            "representatives",
        ]
    ]

    # Group by species and aggregate results
    midas_uniq = midas.groupby(midas["species_id"], as_index=False).aggregate(
        {
            "count_reads": "sum",
            "coverage": "max",
            "relative_abundance": "sum",
            "representatives": ",".join,
        }
    )
    midas_uniq = midas_uniq.sort_values(by="relative_abundance", ascending=False)

    midas_uniq.to_csv(
        f"{prefix}.midas.adjusted.abundances.txt",
        sep="\t",
        float_format="%.5f",
        index=False,
    )

    # Summary
    cols = [
        "sample",
        "midas_primary_species",
        "midas_primary_species_abundance",
        "midas_secondary_species",
        "midas_secondary_species_abundance",
    ]
    results = [
        prefix,
        midas_uniq["species_id"].iloc[0]
        if midas_uniq["relative_abundance"].iloc[0] >= 0.01
        else "No primary abundance > 1%",
        "{0:.5f}".format(midas_uniq["relative_abundance"].iloc[0])
        if midas_uniq["relative_abundance"].iloc[0] >= 0.01
        else "",
        midas_uniq["species_id"].iloc[1]
        if midas_uniq["relative_abundance"].iloc[1] >= 0.01
        else "No secondary abundance > 1%",
        "{0:.5f}".format(midas_uniq["relative_abundance"].iloc[1])
        if midas_uniq["relative_abundance"].iloc[1] >= 0.01
        else "",
    ]
    with open(f"{prefix}.midas.tsv", "wt") as fh_out:
        fh_out.write("{}\n".format("\t".join(cols)))
        fh_out.write("{}\n".format("\t".join(results)))


def main():
    if len(sys.argv) == 1:
        midas_summary.main(["--help"])
    else:
        midas_summary()


if __name__ == "__main__":
    main()
