"""
Shared functions used by parsers.
"""
import csv
import json
from typing import Union

import yaml


def parse_table(
    csvfile: str, delimiter: str = "\t", has_header: bool = True
) -> Union[list, dict]:
    """
    Parse a delimited file.

    Args:
        csvfile (str): input delimited file to be parsed
        delimiter (str, optional): delimter used to separate column values. Defaults to '\t'.
        has_header (bool, optional): the first line should be treated as a header. Defaults to True.

    Returns:
        Union[list, dict]: A dict is returned if a header is present, otherwise a list is returned
    """
    data = []
    with open(csvfile, "rt") as fh:
        for row in (
            csv.DictReader(fh, delimiter=delimiter)
            if has_header
            else csv.reader(fh, delimiter=delimiter)
        ):
            data.append(row)
    return data


def parse_json(jsonfile: str) -> Union[list, dict]:
    """
    Parse a JSON file.

    Args:
        jsonfile (str): input JSON file to be read

    Returns:
        Union[list, dict]: the values parsed from the JSON file
    """
    with open(jsonfile, "rt") as fh:
        return json.load(fh)


def parse_yaml(yamlfile: str) -> Union[list, dict]:
    """
    Parse a YAML file.

    Args:
        yamlfile (str): input YAML file to be read

    Returns:
        Union[list, dict]: the values parsed from the YAML file
    """
    with open(yamlfile, "rt") as fh:
        return yaml.safe_load(fh)
