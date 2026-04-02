"""Update Bracken abundances with unclassified counts and produce summary."""

import sys

import pandas as pd
import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.parsers.kraken import bracken_root_count, kraken2_unclassified_count

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.argument("prefix", help="Prefix to use for output files.")
@click.argument("kraken2_report", help="The Kraken2 report.")
@click.argument("bracken_report", help="The Bracken updated Kraken2 report.")
@click.argument("bracken_abundances", help="The Bracken output with abundances.")
@click.option(
    "--max_secondary_percent",
    type=float,
    default=0.01,
    help="The maximum percent abundance for the secondary species, if exceeded, sample will remain unclassified.",
)
def kraken_bracken_summary(
    prefix, kraken2_report, bracken_report, bracken_abundances, max_secondary_percent
):
    """Update the Bracken abundances with unclassified counts."""
    unclassified_count = kraken2_unclassified_count(kraken2_report)

    # Allow for if 100% of reads are successfully assigned
    if unclassified_count is None:
        total_count = 100
    else:
        total_count = unclassified_count + bracken_root_count(bracken_report)

    bracken = pd.read_csv(bracken_abundances, sep="\t")
    bracken["fraction_total_reads"] = bracken["new_est_reads"] / total_count
    bracken = bracken.sort_values(by="fraction_total_reads", ascending=False)

    # Write top two and unclassified
    cols = [
        "sample",
        "bracken_primary_species",
        "bracken_primary_species_abundance",
        "bracken_secondary_species",
        "bracken_secondary_species_abundance",
        "bracken_unclassified_abundance",
    ]
    results = [
        prefix,
        bracken["name"].iloc[0]
        if bracken["fraction_total_reads"].iloc[0] >= 0.01
        else "No primary abundance > 1%",
        "{0:.5f}".format(bracken["fraction_total_reads"].iloc[0])
        if bracken["fraction_total_reads"].iloc[0] >= 0.01
        else "",
        bracken["name"].iloc[1]
        if bracken["fraction_total_reads"].iloc[1] >= 0.01
        else "No secondary abundance > 1%",
        "{0:.5f}".format(bracken["fraction_total_reads"].iloc[1])
        if bracken["fraction_total_reads"].iloc[1] >= 0.01
        else "",
        "{0:.5f}".format(unclassified_count / total_count)
        if unclassified_count is not None
        else "",
    ]
    with open(f"{prefix}.bracken.tsv", "wt") as fh_out:
        fh_out.write("{}\n".format("\t".join(cols)))
        fh_out.write("{}\n".format("\t".join(results)))

    if unclassified_count is not None:
        # Add unclassified to data table and re-sort
        unclassified = pd.DataFrame.from_dict(
            {
                "name": ["unclassified"],
                "taxonomy_id": [0],
                "taxonomy_lvl": ["U"],
                "kraken_assigned_reads": [unclassified_count],
                "added_reads": [0],
                "new_est_reads": [unclassified_count],
                "fraction_total_reads": [unclassified_count / total_count],
            }
        )
        bracken = pd.concat([bracken, unclassified], axis=0)
    bracken = bracken.sort_values(by="fraction_total_reads", ascending=False)
    bracken.insert(0, "sample", prefix)
    bracken["percent_total_reads"] = (bracken["new_est_reads"] / total_count) * 100
    bracken.to_csv(
        f"{prefix}.bracken.adjusted.abundances.txt",
        sep="\t",
        float_format="%.5f",
        index=False,
    )

    # Write classification based on secondary species abundance
    with open(f"{prefix}.bracken.classification.txt", "wt") as fh_out:
        fh_out.write("sample\tclassification\n")
        non_unclassified = bracken[bracken["name"] != "unclassified"]
        secondary_abundance = non_unclassified["fraction_total_reads"].iloc[1]
        if secondary_abundance < max_secondary_percent:
            fh_out.write(f"{prefix}\t{non_unclassified['name'].iloc[0]}\n")
        else:
            fh_out.write(f"{prefix}\tUNKNOWN_SPECIES\n")


def main():
    if len(sys.argv) == 1:
        kraken_bracken_summary.main(["--help"])
    else:
        kraken_bracken_summary()


if __name__ == "__main__":
    main()
