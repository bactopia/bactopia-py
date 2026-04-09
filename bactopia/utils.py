import logging
import subprocess
import sys
from pathlib import Path
from sys import platform

import requests
import tqdm
from tqdm.contrib.concurrent import process_map


def execute(
    cmd,
    directory=Path.cwd(),
    capture=False,
    allow_fail=False,
):
    """A simple wrapper around executor.

    Args:
        cmd (str): A command to execute.
        directory (str, optional): Set the working directory for command. Defaults to str(Path.cwd()).
        capture (bool, optional): Capture and return the STDOUT of a command. Defaults to False.
        allow_fail (bool, optional): Allow command to fail without raising an error. Defaults to False.

    Raises:
        error: An unexpected error occurred.

    Returns:
        str: Exit code, accepted error message, or STDOUT of command.
    """
    logging.debug(f"Executing command: {cmd}")
    logging.debug(f"Working directory: {directory}")
    try:
        command = subprocess.run(
            cmd.split(" "),  # Replace with your command and arguments
            cwd=directory,
            capture_output=True,
            text=True,  # Decodes stdout/stderr as strings using default encoding
            check=True,  # Raises CalledProcessError for non-zero exit codes
        )
        logging.debug(f"Exit code: {command.returncode}")
        logging.debug(f"STDOUT: \n{command.stdout}")
        logging.debug(f"STDERR:\n{command.stderr}")

        if capture:
            return [command.stdout, command.stderr]
        else:
            return command.returncode
    except subprocess.CalledProcessError as e:
        if allow_fail:
            logging.debug(f'"{cmd}" return exit code {e.returncode}')
            logging.debug(e)
            return None
        else:
            logging.error(f'"{cmd}" return exit code {e.returncode}')
            logging.error(e)
            sys.exit(e.returncode)


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


def get_git_info(repo_path: Path) -> dict:
    """Get git branch, short commit hash, and modified file count for a repo.

    Args:
        repo_path: Path to a git repository.

    Returns:
        A dict with branch, commit, and modified keys.
    """
    info = {"branch": "unknown", "commit": "unknown", "modified": 0}
    try:
        info["branch"] = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        info["commit"] = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        info["modified"] = len(porcelain.splitlines()) if porcelain else 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return info


def is_local(filename: str) -> bool:
    """
    Check if a filename is a local path (not cloud or remote storage).

    Args:
        filename (str): The filename or path to check

    Returns:
        bool: True if the path is local, False if it is a cloud/remote path
    """
    if (
        filename.startswith("gs://")
        or filename.startswith("s3://")
        or filename.startswith("az://")
        or filename.startswith("https://")
    ):
        return False
    return True


def chunk_list(lst: list, n: int) -> list:
    """
    Yield successive n-sized chunks from input list.
    https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks?page=1&tab=votes#tab-top

    Args:
        l (list): The list to chunk
        n (int): The size of each chunk

    Returns:
        list: A list of n-sized chunks
    """
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
