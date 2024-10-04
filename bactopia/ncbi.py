import logging
import re

import requests

from bactopia.utils import chunk_list


def is_biosample(accession: str) -> bool:
    """
    Check if input accession is a BioSample.

    Args:
        accession (str): The accession to check

    Returns:
        bool: True if the accession is a BioSample, False otherwise
    """
    return (
        True
        if re.match(r"SAM(E|D|N)[A-Z]?[0-9]+|(E|D|S)RS[0-9]{6,}", accession)
        else False
    )


def taxid2name(taxids: list, ncbi_api_key: str, chunk_size: int) -> dict:
    """
    Convert a list of NCBI TaxIDs to species names.

    For this query we will use NCBI Datasets v2 API
    Docs: https://www.ncbi.nlm.nih.gov/datasets/docs/v2/reference-docs/rest-api/

    For this we will query the following endpoint:
    https://api.ncbi.nlm.nih.gov/datasets/v2alpha/taxonomy/name_report

    It expects the query to be delivered via POST with the following JSON payload:
    {
        "taxons": [
            "1280",
            "1281"
        ],
        "returned_content": "METADATA",
        "page_size": 1000,
        "include_tabular_header": "INCLUDE_TABULAR_HEADER_FIRST_PAGE_ONLY",
        "page_token": "string",
        "table_format": "SUMMARY",
        "children": false,
        "ranks": [
            "SPECIES"
        ]
    }

    The query will then include the following headers:
        accept: application/json
        api-key: ncbi-api-key
        content-type: application/json

    NCBI will only allow a maximum for 1000 taxids per query, so we will need to
    split the list into chunks of a user defined size.

    Args:
        taxids (list): A list of NCBI TaxIDs
        ncbi_api_key (str): The API key to use for the NCBI API
        chunk_size (int): The size of the chunks to split the list into

    Returns:
        dict: A dictionary of TaxIDs and species names
    """
    logging.info(f"Converting {len(taxids)} TaxIDs to species names")
    logging.debug(f"Using NCBI API key: {ncbi_api_key}")
    tax_names = {}
    url = "https://api.ncbi.nlm.nih.gov/datasets/v2alpha/taxonomy"
    headers = {
        "accept": "application/json",
        "api-key": ncbi_api_key,
        "content-type": "application/json",
    }

    taxid_chunks = list(chunk_list(taxids, chunk_size))
    for i, chunk in enumerate(taxid_chunks):
        logging.debug(f"Processing chunk {i} of {len(taxid_chunks)}")
        payload = {
            "taxons": chunk,
            "returned_content": "METADATA",
            "page_size": 1000,
            "include_tabular_header": "INCLUDE_TABULAR_HEADER_FIRST_PAGE_ONLY",
            "page_token": "string",
            "table_format": "SUMMARY",
            "children": False,
            "ranks": ["SPECIES"],
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        for row in data["taxonomy_nodes"]:
            tax_names[str(row["taxonomy"]["tax_id"])] = row["taxonomy"]["organism_name"]

    logging.info(f"Converted {len(tax_names)} TaxIDs to species names")
    return tax_names
