"""Verify input FASTQs meet minimum requirements."""

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


def write_error(filename, error_msg):
    print(error_msg, file=sys.stderr)
    with open(filename, "wt") as fh_out:
        fh_out.write(error_msg)


def check_reads(fq1, sample, min_reads, fq2=None):
    total_reads = fq1 + fq2 if fq2 else fq1

    if total_reads < min_reads:
        error_msg = (
            f"{sample} FASTQ(s) contain {total_reads} total reads. This does not \n"
            f"exceed the required minimum {min_reads} read count. Further analysis is \n"
            "discontinued.\n"
        )
        write_error(f"{sample}-low-read-count-error.txt", error_msg)

    if fq2:
        if fq1 != fq2:
            error_msg = (
                f"{sample} FASTQs have different read counts (R1: {fq1}, R2: {fq2}). Please \n"
                "investigate these FASTQs. Further analysis is discontinued.\n"
            )
            write_error(f"{sample}-different-read-count-error.txt", error_msg)


def check_basepairs(fq1, sample, min_basepairs, fq2=None, min_proportion=0.0):
    total_bp = fq1 + fq2 if fq2 else fq1

    if total_bp < min_basepairs:
        error_msg = (
            f"{sample} FASTQ(s) contain {total_bp} total basepairs. This does not \n"
            f"exceed the required minimum {min_basepairs} bp. Further analysis is \n"
            "discontinued.\n"
        )
        write_error(f"{sample}-low-sequence-depth-error.txt", error_msg)

    if fq2:
        proportion = float(fq1) / float(fq2) if fq1 < fq2 else float(fq2) / float(fq1)
        if proportion < float(min_proportion):
            error_msg = (
                f"{sample} FASTQs failed to meet the minimum shared basepairs ({min_proportion}). \n"
                f"They shared {proportion:.4f} basepairs, with R1 having {fq1} bp and \n"
                f"R2 having {fq2} bp. Further analysis is discontinued.\n"
            )
            write_error(f"{sample}-low-basepair-proportion-error.txt", error_msg)


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option("--sample", required=True, help="Name of the input sample.")
@click.option("--fq1", required=True, help="Stats for SE or R1 FASTQ in JSON format.")
@click.option("--fq2", default=None, help="Stats for R2 FASTQ in JSON format.")
@click.option(
    "--min_proportion",
    type=float,
    default=0.0,
    help="Minimum basepair proportion for R1/R2.",
)
@click.option("--min_reads", type=int, default=0, help="Minimum number of reads.")
@click.option(
    "--min_basepairs",
    type=int,
    default=0,
    help="Minimum number of sequenced basepairs.",
)
@click.option(
    "--runtype", default="illumina", help="The input technology of the FASTQs."
)
def check_fastqs(sample, fq1, fq2, min_proportion, min_reads, min_basepairs, runtype):
    """Verify input FASTQs meet minimum requirements."""
    if fq1 and fq2:
        r1 = parse_json(fq1)
        r2 = parse_json(fq2)
        check_reads(
            r1["qc_stats"]["read_total"],
            sample,
            min_reads,
            fq2=r2["qc_stats"]["read_total"],
        )
        check_basepairs(
            r1["qc_stats"]["total_bp"],
            sample,
            min_basepairs,
            fq2=r2["qc_stats"]["total_bp"],
            min_proportion=min_proportion,
        )
    else:
        se = parse_json(fq1)
        if runtype != "ont":
            check_reads(se["qc_stats"]["read_total"], sample, min_reads)
        check_basepairs(se["qc_stats"]["total_bp"], sample, min_basepairs)

    sys.exit(0)


def main():
    if len(sys.argv) == 1:
        check_fastqs.main(["--help"])
    else:
        check_fastqs()


if __name__ == "__main__":
    main()
