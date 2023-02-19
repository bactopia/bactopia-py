"""
Parsers for MLST related results.
"""
from bactopia.parsers.generic import parse_table


def parse(path: str, name: str) -> dict:
    """
    Parse the results of an MLST analysis.

    Columns
        0 - the filename
        1 - the matching PubMLST scheme name
        2 - the ST (sequence type)
        3-N - the allele IDs

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: parsed results
    """
    result = parse_table(path, has_header=False)[0]
    return {
        "sample": name,
        "mlst_scheme": result[1],
        "mlst_st": result[2],
    }
