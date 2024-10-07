import gzip
import logging
import sys
from pathlib import Path
from sys import platform

import requests
import tqdm
from executor import ExternalCommand, ExternalCommandFailed
from tqdm.contrib.concurrent import process_map

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
        logging.debug(f"STDOUT: {command.decoded_stdout}")
        logging.debug(f"STDERR: {command.decoded_stderr}")

        if capture:
            return [command.decoded_stdout, command.decoded_stderr]
        return True
    except ExternalCommandFailed as e:
        if allow_fail:
            logging.error(e)
            sys.exit(e.returncode)
        else:
            return None


def pgzip(files: list, cpus: int) -> list:
    """
    Parallel gzip a list of files

    Args:
        files (list): A list of files to gzip
        cpus (int): The number of cpus to use

    Returns:
        list: A list of gzipped files
    """
    return process_map(
        _gzip,
        files,
        max_workers=cpus,
        chunksize=1,
        bar_format="{l_bar}{bar:80}{r_bar}{bar:-80b}",
        desc="Gzipping",
    )


def _gzip(filename: str) -> str:
    """
    Gzip a file

    Args:
        filename (str): The file to gzip

    Returns:
        str: The path to the gzipped file
    """
    stdout, stderr = execute(f"gzip --force {filename}", capture=True, allow_fail=True)
    return f"{filename}.gz"


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


def mkdir(directory: str) -> Path:
    """
    Create a directory if it does not exist

    Args:
        directory (str): The directory to create

    Returns:
        Path: The Path object of the created directory
    """
    d = Path(directory)
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
    return d


def file_exists(filename: str) -> bool:
    """
    Check if a file exists

    Args:
        filename (str): The file to check for existence

    Returns:
        bool: True if the file exists, False otherwise
    """
    f = Path(filename)
    return f.exists()


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
    return f.resolve()


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


def download_url(url: str, save_path: str, show_progress: bool) -> str:
    """
    Download a file from a URL

    Modified from: https://github.com/tqdm/tqdm/blob/master/examples/tqdm_requests.py

    Args:
        url (str): The URL to download
        save_path (str): The path to save the downloaded file
        show_progress (bool): Show a progress bar while downloading

    Returns:
        str: The path to the downloaded file
    """
    r = requests.get(url, stream=True)
    if r.status_code == requests.codes.ok:
        total_size = int(r.headers.get("content-length", 0))
        with open(save_path, "wb") as f:
            if show_progress:
                with tqdm.tqdm(
                    desc=save_path,
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    bar_format="{l_bar}{bar:80}{r_bar}{bar:-80b}",
                ) as pbar:
                    for data in r.iter_content(chunk_size=1024):
                        f.write(data)
                        pbar.update(len(data))
            else:
                for data in r.iter_content(chunk_size=1024):
                    f.write(data)
    else:
        logging.error(f"Unable to download {url}, please try again later.")
        sys.exit(1)

    return validate_file(save_path)


def chunk_list(lst: list, n: int) -> list:
    """
    Yield successive n-sized chunks from input list.

    Args:
        l (list): The list to chunk
        n (int): The size of each chunk

    Returns:
        list: A list of n-sized chunks
    """
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
