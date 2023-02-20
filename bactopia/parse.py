"""
Bactopia's parser entry-point.

Example: bactopia.parse(result_type, filename)
"""
from pathlib import Path

IGNORE_LIST = [
    ".nextflow",
    ".nextflow.log",
    "nf-reports",
    "work",
]


def parse_bactopia_directory(path: str) -> list:
    """
    Scan a Bactopia directory and return parsed results.

    Args:
        path (str):  a path to expected Bactopia results

    Returns:
        list: Parsed results for all samples in a Bactopia directory
    """
    results = []
    for directory in Path(f"{path}/bactopia-samples").iterdir():
        if directory.is_dir():
            if directory.name not in IGNORE_LIST:
                results.append(
                    {
                        "id": directory.name,
                        "path": directory.absolute(),
                        "is_bactopia": _is_bactopia_dir(
                            directory.absolute(), directory.name
                        ),
                    }
                )

    return results


def _is_bactopia_dir(path: str, name: str) -> bool:
    """
    Check if a directory contains Bactopia output and any errors.

    Args:
        path (str): a path to expected Bactopia results
        name (str): the name of sample to test

    Returns:
        bool: path looks like Bactopia (True) or not (False)
    """
    return Path(f"{path}/bactopia-main/gather/{name}-meta.tsv").exists()
