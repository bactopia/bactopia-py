"""
Parsers for Gather related results.
"""
from bactopia.parsers.generic import parse_table


def parse(path: str, name: str) -> dict:
    """
    Parse the metadata from an the gather step

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: parsed results
    """
    return parse_table(path)[0]
