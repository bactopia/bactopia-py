"""
Parsers for Assembly related results.
"""
from bactopia.parsers.generic import parse_table


def parse(path: str, name: str) -> dict:
    """
    Parse the results of an assembler analysis.

    Output columns from assembly-scan: https://github.com/rpetit3/assembly-scan#output-columns

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: parsed results
    """
    final_result = {}
    for key, val in parse_table(path)[0].items():
        if key == "sample":
            final_result[key] = val
        else:
            final_result[f"assembler_{key}"] = val
    return final_result
