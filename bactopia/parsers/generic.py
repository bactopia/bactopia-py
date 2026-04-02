"""
Shared functions used by parsers.
"""

import csv
import json
import logging
from typing import Union

import yaml


def parse_table(
    csvfile: str, delimiter: str = "\t", has_header: bool = True
) -> Union[list, dict]:
    """
    Parse a delimited file.

    Args:
        csvfile (str): input delimited file to be parsed
        delimiter (str, optional): delimiter used to separate column values. Defaults to '\t'.
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
    logging.debug(f"Parsing JSON file: {jsonfile}")
    with open(jsonfile, "rt") as fh:
        return json.load(fh)


def parse_yaml(yamlfile: str) -> dict:
    """
    Parse a YAML file.

    Args:
        yamlfile (str): input YAML file to be read

    Returns:
        Union[list, dict]: the values parsed from the YAML file
    """
    with open(yamlfile, "rt") as fh:
        return yaml.safe_load(fh)


def read_vcf(vcf: str) -> dict:
    """
    Get positions with a substitution from a VCF file.

    Args:
        vcf (str): input VCF file to be parsed

    Returns:
        dict: substitution positions keyed by contig then position
    """
    subs = {}
    with open(vcf, "rt") as vcf_fh:
        for line in vcf_fh:
            if not line.startswith("#"):
                line = line.split("\t")
                if line[0] not in subs:
                    subs[line[0]] = {}
                subs[line[0]][line[1]] = True
    return subs


def read_fasta(fasta: str) -> dict:
    """
    Parse the input FASTA file.

    Args:
        fasta (str): input FASTA file to be parsed

    Returns:
        dict: sequences keyed by record name
    """
    from Bio import SeqIO

    seqs = {}
    with open(fasta, "r") as fasta_fh:
        for record in SeqIO.parse(fasta_fh, "fasta"):
            seqs[record.name] = str(record.seq)
    return seqs
