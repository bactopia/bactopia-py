"""Parsers for Kraken2 and Bracken report files."""


def kraken2_unclassified_count(kraken2_report):
    """Get the unclassified read count from a Kraken2 report."""
    with open(kraken2_report, "rt") as fh:
        for line in fh:
            line = line.rstrip()
            cols = line.split("\t")
            if cols[3] == "U":
                return float(cols[2])


def bracken_root_count(bracken_report):
    """Get the root-level read count from a Bracken report."""
    with open(bracken_report, "rt") as fh:
        for line in fh:
            line = line.rstrip()
            cols = line.split("\t")
            if cols[3] == "R":
                return float(cols[1])
