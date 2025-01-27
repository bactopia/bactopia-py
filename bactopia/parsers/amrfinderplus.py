"""
Parsers for Antimicrobial Resistance related results.
"""
from .generic import parse_table


def parse(path: str, name: str) -> dict:
    """
    Check input file is an accepted file, then select the appropriate parsing method.

    Args:
        path (str): input file to be parsed

    Returns:
        dict: parsed results
    """
    return {"sample": name, "amrfinderplus_hits": parse_table(path)}
