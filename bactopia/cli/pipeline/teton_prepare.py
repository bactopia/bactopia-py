"""Prepare sample sheets for downstream analysis in the Teton workflow."""

import sys
from pathlib import Path

import pandas as pd
import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.utils import is_local

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.argument("prefix", help="Prefix to use for output files.")
@click.argument("sizemeup", help="The SizeMeUp genome size estimate.")
@click.argument(
    "run_type", help="The input run type (e.g. paired-end, single-end, ont)."
)
@click.argument("fastqs", help="Comma-separated list of FASTQ filenames.")
@click.argument("outdir", help="The output directory for results.")
def teton_prepare(prefix, sizemeup, run_type, fastqs, outdir):
    """Prepare sample sheets for downstream analysis in the Teton workflow."""
    sample_sheet = {
        "sample": prefix,
        "runtype": run_type,
        "genome_size": 0,
        "species": "UNKNOWN_SPECIES",
        "r1": "",
        "r2": "",
        "extra": "",
    }

    df = pd.read_csv(sizemeup, sep="\t")
    df = df[["name", "size", "category"]]
    category = df["category"][0]
    sample_sheet["genome_size"] = str(df["size"][0])
    sample_sheet["species"] = str(df["name"][0])

    # Sort out fastqs
    fqs = fastqs.split(",")
    scrubber_outdir = f"{outdir}/{prefix}/teton/tools/scrubber"

    if run_type == "paired-end":
        sample_sheet["r1"] = f"{scrubber_outdir}/{fqs[0]}"
        sample_sheet["r2"] = f"{scrubber_outdir}/{fqs[1]}"
    elif run_type in ("single-end", "ont"):
        sample_sheet["r1"] = f"{scrubber_outdir}/{fqs[0]}"
    elif run_type in ("hybrid", "short-polish"):
        sample_sheet["r1"] = f"{scrubber_outdir}/{fqs[0]}"
        sample_sheet["r2"] = f"{scrubber_outdir}/{fqs[1]}"
        sample_sheet["extra"] = f"{scrubber_outdir}/{fqs[2]}"

    # Verify FASTQs exist if they are on local storage
    for key in ["r1", "r2", "extra"]:
        if sample_sheet[key]:
            if is_local(sample_sheet[key]):
                if Path(sample_sheet[key]).exists():
                    sample_sheet[key] = Path(sample_sheet[key]).resolve()
                elif Path(f"../../../{sample_sheet[key]}").exists():
                    sample_sheet[key] = Path(f"../../../{sample_sheet[key]}").resolve()
                else:
                    print(f"Error: {sample_sheet[key]} does not exist", file=sys.stderr)
                    sys.exit(1)

    if category == "bacteria":
        with open(f"{prefix}.bacteria.tsv", "w") as fh:
            print("\t".join(sample_sheet.keys()), file=fh)
            print("\t".join([str(x) for x in sample_sheet.values()]), file=fh)

        with open(f"{prefix}.nonbacteria.tsv", "w") as fh:
            print("\t".join(sample_sheet.keys()), file=fh)
    else:
        with open(f"{prefix}.bacteria.tsv", "w") as fh:
            print("\t".join(sample_sheet.keys()), file=fh)

        with open(f"{prefix}.nonbacteria.tsv", "w") as fh:
            print("\t".join(sample_sheet.keys()), file=fh)
            print("\t".join([str(x) for x in sample_sheet.values()]), file=fh)


def main():
    if len(sys.argv) == 1:
        teton_prepare.main(["--help"])
    else:
        teton_prepare()


if __name__ == "__main__":
    main()
