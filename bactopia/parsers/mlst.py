"""
Parsers for MLST related results.
"""

from bactopia.parsers.generic import parse_table


def parse(path: str, name: str) -> dict:
    """
    Parse the results of an MLST analysis.

    Bactopia runs `mlst --full`, which emits a header row followed by a single
    row of results: FILE, SCHEME, ST, STATUS, SCORE, ALLELES.

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: parsed results
    """
    result = parse_table(path)[0]
    return {
        "sample": name,
        "mlst_scheme": result["SCHEME"],
        "mlst_st": result["ST"],
    }
