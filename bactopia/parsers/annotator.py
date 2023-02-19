"""
Parsers for Annotation related results.
"""


def parse(path: str, name: str) -> dict:
    """
    Parse basic annotation information from Prokka and Bakta

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: parsed results
    """
    if "prokka" in str(path):
        return _parse_prokka_annotation(path, name)
    # else:
    #    return _parse_bakta_annotation(path)


def _parse_prokka_annotation(path: str, name: str) -> dict:
    """
    Parse Prokka summary text file.

    Args:
        filename (str): input file to be parsed

    Returns:
        dict: the parsed Prokka summary
    """
    results = {
        "sample": name,
    }
    with open(path, "rt") as fh:
        for line in fh:
            line = line.rstrip()
            key, val = line.split(":")
            if key not in ["organism", "contigs", "bases"]:
                results[f"annotator_total_{key}"] = int(val.lstrip())
    return results
