import logging
import sys

import requests

ENA_URL = "https://www.ebi.ac.uk/ena/portal/api/search"


def get_ena_metadata(query: str, is_accession: bool, limit: int):
    """Fetch metadata from ENA.
    https://docs.google.com/document/d/1CwoY84MuZ3SdKYocqssumghBF88PWxUZ/edit#heading=h.ag0eqy2wfin5

    Args:
        query (str): The query to search for.
        is_accession (bool): If the query is an accession or not.
        limit (int): The maximum number of records to return.

    Returns:
        list: Records associated with the accession.
    """
    data = {
        "dataPortal": "ena",
        "dccDataOnly": "false",
        "download": "false",
        "result": "read_run",
        "format": "tsv",
        "limit": limit,
        "fields": "all",
    }

    if is_accession:
        data["includeAccessions"] = query
    else:
        data["query"] = (
            f'"{query} AND library_source=GENOMIC AND '
            "(library_strategy=OTHER OR library_strategy=WGS OR "
            "library_strategy=WGA) AND (library_selection=MNase OR "
            "library_selection=RANDOM OR library_selection=unspecified OR "
            'library_selection="size fractionation")"'
        )

    headers = {"accept": "*/*", "Content-type": "application/x-www-form-urlencoded"}

    r = requests.post(ENA_URL, headers=headers, data=data)
    if r.status_code == requests.codes.ok:
        data = []
        col_names = None
        for line in r.text.split("\n"):
            cols = line.split("\t")
            if line:
                if col_names:
                    data.append(dict(zip(col_names, cols)))
                else:
                    col_names = cols
        return [True, data]
    else:
        return [False, [r.status_code, r.text]]


def get_run_info(
    sra_query: str, ena_query: str, is_accession: bool, limit: int = 1000000
) -> tuple:
    """Retrieve a list of samples available from ENA.

    The first attempt will be against ENA, and if that fails, SRA will be queried. This should
    capture those samples not yet synced between ENA and SRA.

    Args:
        sra_query (str): A formatted query for SRA searches.
        ena_query (str): A formatted query for ENA searches.
        is_accession (bool): If the query is an accession or not.
        limit (int): The maximum number of records to return.

    Returns:
        tuple: Records associated with the accession.
    """

    logging.debug("Querying ENA for metadata...")
    success, ena_data = get_ena_metadata(ena_query, is_accession, limit=limit)
    if success:
        return success, ena_data
    else:
        logging.error("There was an issue querying ENA, exiting...")
        logging.error(f"STATUS: {ena_data[0]}")
        logging.error(f"TEXT: {ena_data[1]}")
        sys.exit(1)
