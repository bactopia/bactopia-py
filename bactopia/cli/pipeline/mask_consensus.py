"""Snippy consensus (subs) with coverage masking."""

import sys

import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.parsers.coverage import read_coverage
from bactopia.parsers.generic import read_fasta, read_vcf
from bactopia.utils import chunk_list

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


def mask_sequence(sequence, coverages, subs, mincov):
    """Mask positions with low or no coverage in the input FASTA."""
    masked_seqs = {}

    for accession, vals in coverages.items():
        bases = []
        coverage = vals["positions"]
        for i, cov in enumerate(coverage):
            if cov >= mincov:
                if accession in subs:
                    if str(i + 1) in subs[accession]:
                        bases.append(sequence[accession][i].lower())
                    else:
                        bases.append(sequence[accession][i])
                else:
                    bases.append(sequence[accession][i])
            elif cov:
                bases.append("N")
            else:
                bases.append("n")

        if len(bases) != len(sequence[accession]):
            print(
                f"Masked sequence ({len(bases)} for {accession} not expected length ({len(sequence[accession])}).",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            masked_seqs[accession] = bases

    return masked_seqs


def format_header(sample, reference, accession, length):
    """Return a newly formatted header."""
    title = "Pseudo-seq with called substitutions and low coverage masked"
    return f">gnl|{accession}|{sample} {title} [assembly_accession={reference}] [length={length}]"


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.argument("sample", help="Name of the input sample.")
@click.argument("reference", help="The reference assembly accession.")
@click.argument("fasta", help="The consensus FASTA file.")
@click.argument("vcf", help="The VCF file with called substitutions.")
@click.argument("coverage", help="The per-base coverage file.")
@click.option(
    "--mincov", type=int, default=10, help="Minimum required coverage to not mask."
)
def mask_consensus(sample, reference, fasta, vcf, coverage, mincov):
    """Snippy consensus (subs) with coverage masking."""
    coverages = read_coverage(coverage)
    sub_positions = read_vcf(vcf)
    seqs = read_fasta(fasta)
    masked_seqs = mask_sequence(seqs, coverages, sub_positions, mincov)
    for accession, seq in masked_seqs.items():
        header = format_header(sample, reference, accession, len(seq))
        print(header)
        for chunk in chunk_list(seq, 60):
            print("".join(chunk))


def main():
    if len(sys.argv) == 1:
        mask_consensus.main(["--help"])
    else:
        mask_consensus()


if __name__ == "__main__":
    main()
