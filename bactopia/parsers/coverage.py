"""Parsers for per-base coverage output from genomeCoverageBed."""

import re
import sys


def read_coverage(coverage, format="single"):
    """Read the per-base coverage input.

    Args:
        coverage (str): Path to the coverage file.
        format (str): Format of non-header lines. "single" for one coverage
            value per line, "tabbed" for tab-separated accession/position/coverage.

    Returns:
        dict: Coverage data keyed by accession with length and positions.
    """
    coverages = {}
    with open(coverage, "rt") as coverage_fh:
        for line in coverage_fh:
            line = line.rstrip()
            if line.startswith("##"):
                contig = re.search(r"contig=<ID=(.*),length=([0-9]+)>", line)
                if contig:
                    accession = contig.group(1)
                    length = contig.group(2)
                    coverages[accession] = {"length": int(length), "positions": []}
                else:
                    print(f"{line} is an unexpected format.", file=sys.stderr)
                    sys.exit(1)
            else:
                if format == "tabbed":
                    accession, position, cov = line.split("\t")
                    coverages[accession]["positions"].append(int(cov))
                elif line:
                    coverages[accession]["positions"].append(int(line))

    for accession, vals in coverages.items():
        if len(vals["positions"]) != vals["length"]:
            print(
                f"Observed bases ({len(vals['positions'])} in {accession} not expected length ({vals['length']}).",
                file=sys.stderr,
            )
            sys.exit(1)

    return coverages
