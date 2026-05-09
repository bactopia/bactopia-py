import logging

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
    sra_query: str,
    ena_query: str,
    is_accession: bool,
    limit: int = 1000000,
    provider: str = "ena",
    only_provider: bool = False,
) -> tuple:
    """Retrieve a list of samples available from ENA and/or SRA.

    By default, the provider is queried first and the other is used as fallback. When
    only_provider is True, no fallback is attempted.

    Args:
        sra_query: A formatted query for SRA searches.
        ena_query: A formatted query for ENA searches.
        is_accession: If the query is an accession or not.
        limit: The maximum number of records to return.
        provider: Which provider to query first ("ena" or "sra").
        only_provider: If True, skip fallback to the other provider.

    Returns:
        tuple: (success, data, source) where source is "ena", "sra", or "none".
    """
    from bactopia.databases.sra import get_sra_metadata

    fallback = "sra" if provider == "ena" else "ena"

    def _query_ena():
        logging.debug("Querying ENA for metadata...")
        success, data = get_ena_metadata(ena_query, is_accession, limit=limit)
        if success and data:
            return True, data
        if not success:
            logging.warning(f"ENA query failed (status {data[0]}).")
        else:
            logging.debug("ENA query returned no results.")
        return False, []

    def _query_sra():
        logging.debug("Querying SRA for metadata...")
        return get_sra_metadata(sra_query, is_accession, limit=limit)

    query_fn = {"ena": _query_ena, "sra": _query_sra}

    success, data = query_fn[provider]()
    if success:
        return True, data, provider

    if only_provider:
        logging.error(f"{provider.upper()} returned no results (--only-provider).")
        return False, [], "none"

    logging.info(f"No results from {provider.upper()}, checking {fallback.upper()}...")
    success, data = query_fn[fallback]()
    if success:
        return True, data, fallback

    logging.error("Both ENA and SRA returned no results.")
    return False, [], "none"
