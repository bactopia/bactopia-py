import gzip
import logging
import sys
from pathlib import Path
from sys import platform

import requests
from executor import ExternalCommand, ExternalCommandFailed

NCBI_GENOME_SIZE_URL = (
    "https://ftp.ncbi.nlm.nih.gov/genomes/ASSEMBLY_REPORTS/species_genome_size.txt.gz"
)


def execute(
    cmd,
    directory=Path.cwd(),
    capture=False,
    stdout_file=None,
    stderr_file=None,
    allow_fail=False,
):
    """A simple wrapper around executor."""
    try:
        command = ExternalCommand(
            cmd,
            directory=directory,
            capture=True,
            capture_stderr=True,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
        )

        command.start()
        logging.debug(command.decoded_stdout)
        logging.debug(command.decoded_stderr)

        if capture:
            return [command.decoded_stdout, command.decoded_stderr]
        return True
    except ExternalCommandFailed as e:
        if allow_fail:
            logging.error(e)
            sys.exit(e.returncode)
        else:
            return None


def get_platform() -> str:
    """
    Get the platform of the executing machine

    Returns:
        str: The platform of the executing machine
    """
    if platform == "darwin":
        return "mac"
    elif platform == "win32":
        # Windows is not supported
        logging.error("Windows is not supported.")
        sys.exit(1)
    return "linux"


def validate_file(filename: str) -> str:
    """
    Validate a file exists and return the absolute path

    Args:
        filename (str): a file to validate exists

    Returns:
        str: absolute path to file
    """
    f = Path(filename)
    if not f.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    return f.absolute()


def prefix_keys(results: dict, prefix: str) -> dict:
    """
    Add a prefix to existing keys

    Args:
        results (dict): The dictionary of results
        prefix (str): A string to prefix each key with

    Returns:
        dict: The result dictionary with prefixed keys.
    """
    prefixed = {}
    for key, val in results.items():
        prefixed[f"{prefix}_{key}"] = val
    return prefixed


def remove_keys(results: dict, remove: list) -> dict:
    """
    Remove a set of keys from a dictionary.

    Args:
        results (dict): The dictionary of results
        remove (list): the keys to remove

    Returns:
        dict: The altered dictionary
    """
    removed = {}
    for key, val in results.items():
        if key not in remove:
            removed[key] = val
    return removed


def get_taxid_from_species(species: str) -> str:
    """
    Convert a species name into a tax_id

    Args:
        species (str): A species name

    Returns:
        str: The corresponding tax_id
    """
    r = requests.get(
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=taxonomy&term={species}"
    )
    taxid = None
    if r.status_code == requests.codes.ok:
        for line in r.text.split("\n"):
            line = line.strip()
            if line.startswith("<Id>"):
                taxid = line.replace("<Id>", "").replace("</Id>", "")
        if taxid:
            logging.debug(f"Found taxon ID ({taxid}) for {species}")
            return taxid
        else:
            logging.error(
                f"Unable to determine taxon ID from {species}, please check spelling or try again later."
            )
            sys.exit(1)
    else:
        logging.error("Unexpected error querying NCBI, please try again later.")
        sys.exit(1)


def get_ncbi_genome_size() -> dict:
    """
    Get the NCBI's species genome size file.

    Returns:
        str: A dictionary of species genome sizes byt tax_id
    """
    r = requests.get(NCBI_GENOME_SIZE_URL, stream=True)
    if r.status_code == requests.codes.ok:
        sizes = {}
        header = None
        with r as res:
            extracted = gzip.decompress(res.content)
            for line in extracted.split(b"\n"):
                cols = line.decode().rstrip().split("\t")
                if header is None:
                    header = cols
                else:
                    hit = dict(zip(header, cols))
                    sizes[hit["#species_taxid"]] = hit
        return sizes
    else:
        logging.error(
            f"Unable to download NCBI's species genome size file ({NCBI_GENOME_SIZE_URL}), please try again later."
        )
        sys.exit(1)
