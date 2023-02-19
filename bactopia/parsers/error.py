"""
Parsers for Error related results.
"""
ERROR_TYPES = {
    "assembly": "Assembled size was not withing an acceptable range",
    "different-read-count": "Paired-end read count mismatch",
    "genome-size": "Poor estimate of genome size",
    "low-read-count": "Low number of reads",
    "low-sequence-depth": "Low depth of sequencing",
    "low-basepair-proportion": "Paired-end base pair counts are out of acceptable proportions",
    "paired-end": "Paired-end reads were not in acceptable format",
}


def parse_errors(path: str, name: str) -> dict:
    """
    Check is a sample processed by Bactopia has any errors.

    Args:
        path (str): input directory to be checked
        name (str): the name of the sample

    Returns:
        list: observed error and a brief description
    """
    errors = []
    for e in path.rglob("*-error.txt"):
        error = e.name.split("-error.txt")[0].split("-", 1)[-1]
        if error in ERROR_TYPES:
            errors.append(
                {
                    "error_type": error,
                    "description": ERROR_TYPES[error],
                }
            )
        else:
            errors.append(
                {
                    "error_type": error,
                    "description": "Undocumented error, please submit a bug report.",
                }
            )
    return errors
