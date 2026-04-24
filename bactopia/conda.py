"""Shared Anaconda API client for querying bioconda/conda-forge package info."""

import logging
import time
from pathlib import Path

import requests

ANACONDA_API_BASE = "https://api.anaconda.org/package"


def get_latest_info(
    tool: str,
    max_retry: int = 3,
    channel: str = "bioconda",
) -> dict | None:
    """Query Anaconda API for the latest version and build of a package.

    Args:
        tool: The package name (e.g. "bakta").
        max_retry: Maximum number of query attempts.
        channel: Anaconda channel to query (default "bioconda").

    Returns:
        Dict with 'version', 'build', 'summary', and 'home' keys, or None on failure.
    """
    attempt = 1
    url = f"{ANACONDA_API_BASE}/{channel}/{tool}"
    while attempt <= max_retry:
        logging.debug(f"Querying {url} (attempt {attempt} of {max_retry})")
        r = requests.get(url)
        if r.status_code == requests.codes.ok:
            data = r.json()
            version = data.get("latest_version") or data.get("versions", [None])[-1]

            # Find the latest linux-64 build string from the files array.
            # Bioconda publishes separate builds per platform (linux-64,
            # osx-64, linux-aarch64, etc.) and Bactopia only targets linux-64.
            # Fall back to noarch if no linux-64 build exists.
            build = None
            if "files" in data:
                for f in reversed(data["files"]):
                    attrs = f.get("attrs", {})
                    if f.get("version") == version and attrs.get("subdir") in (
                        "linux-64",
                        "noarch",
                    ):
                        build = attrs.get("build")
                        break

            return {
                "version": version,
                "build": build,
                "summary": data.get("summary", ""),
                "home": data.get("home", ""),
            }
        else:
            attempt += 1
            if attempt <= max_retry:
                time.sleep(5)
    logging.warning(f"Unable to query {url} after {max_retry} attempts.")
    return None


def get_latest_info_with_fallback(
    tool: str,
    max_retry: int = 3,
) -> dict | None:
    """Query bioconda first, then conda-forge as fallback.

    Args:
        tool: The package name.
        max_retry: Maximum number of query attempts per channel.

    Returns:
        Dict with 'version', 'build', 'summary', 'home', and 'channel' keys,
        or None if not found on either channel.
    """
    for channel in ("bioconda", "conda-forge"):
        result = get_latest_info(tool, max_retry=max_retry, channel=channel)
        if result is not None:
            result["channel"] = channel
            return result
    return None


def construct_container_refs(
    package: str,
    version: str,
    build: str | None,
) -> dict:
    """Construct Bactopia container reference strings.

    Args:
        package: The bioconda package name.
        version: The package version.
        build: The build string (e.g. "hdfd78af_0"). If None, placeholders
            are returned with TODO markers.

    Returns:
        Dict with 'toolName', 'docker', and 'image' keys.
    """
    if build:
        return {
            "toolName": f"bioconda::{package}={version}",
            "docker": f"biocontainers/{package}:{version}--{build}",
            "image": (
                f"https://depot.galaxyproject.org/singularity/"
                f"{package}:{version}--{build}"
            ),
        }
    return {
        "toolName": f"bioconda::{package}={version}",
        "docker": f"biocontainers/{package}:{version}--TODO_BUILD",
        "image": (
            f"https://depot.galaxyproject.org/singularity/"
            f"{package}:{version}--TODO_BUILD"
        ),
    }


def check_component_exists(bactopia_path: str | Path, tool_name: str) -> dict:
    """Check which Bactopia components already exist for a tool.

    Args:
        bactopia_path: Root of the Bactopia repository.
        tool_name: Tool name (used as directory name).

    Returns:
        Dict with 'module', 'subworkflow', and 'workflow' boolean keys.
    """
    bp = Path(bactopia_path)
    return {
        "module": (bp / "modules" / tool_name).is_dir(),
        "subworkflow": (bp / "subworkflows" / tool_name).is_dir(),
        "workflow": (bp / "workflows" / "bactopia-tools" / tool_name).is_dir(),
    }
