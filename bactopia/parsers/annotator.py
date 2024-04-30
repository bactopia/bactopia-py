"""
Parsers for Annotation related results.
"""
BAKTA_METADATA = [
    "tRNAs",
    "tmRNAs",
    "rRNAs",
    "ncRNAs",
    "ncRNA regions",
    "CRISPR arrays",
    "CDSs",
    "pseudogenes",
    "hypotheticals",
    "signal peptides",
    "sORFs",
    "gaps",
    "oriCs",
    "oriVs",
    "oriTs",
]
PROKKA_METADATA = [
    "CDS",
    "rRNA",
    "tRNA",
]


def parse(path: str, name: str) -> dict:
    """
    Parse basic annotation information from Prokka and Bakta

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: parsed results
    """
    return _parse_annotation(path, name)


def _parse_annotation(path: str, name: str) -> dict:
    """
    Parse Prokka or Bakta summary text file.

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: the parsed Prokka summary
    """
    COLS = PROKKA_METADATA if "prokka" in path else BAKTA_METADATA
    results = {
        "sample": name,
    }
    with open(path, "rt") as fh:
        for line in fh:
            line = line.rstrip()
            if ":" in line:
                key, val = line.split(":")
                if key in COLS:
                    results[f"annotator_total_{key}"] = int(val.lstrip())
    return results
