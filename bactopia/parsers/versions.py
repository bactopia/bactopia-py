"""
Parse the versions.yml files produced by Bactopia
"""
from bactopia.parsers.generic import parse_yaml


def parse_versions(paths: list, name: str) -> dict:
    """
    Parse the versions.yml file produced by Bactopia

    Args:
        path (str): a path to the versions.yml file
        name (str): the name of the sample

    Returns:
        dict: The parsed versions.yml file
    """
    versions = []
    for path in paths:
        version = parse_yaml(path)
        for process_name, tools in version.items():
            for tool_name, tool_version in tools.items():
                versions.append(
                    {
                        "sample": name,
                        "process": process_name,
                        "tool": tool_name,
                        "version": tool_version,
                    }
                )
    return versions
