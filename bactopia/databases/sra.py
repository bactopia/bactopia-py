import logging

from pysradb.sraweb import SRAweb

INSTRUMENT_PLATFORM_MAP = {
    "illumina": "ILLUMINA",
    "nextseq": "ILLUMINA",
    "hiseq": "ILLUMINA",
    "miseq": "ILLUMINA",
    "novaseq": "ILLUMINA",
    "miniseq": "ILLUMINA",
    "genome analyzer": "ILLUMINA",
    "minion": "OXFORD_NANOPORE",
    "gridion": "OXFORD_NANOPORE",
    "promethion": "OXFORD_NANOPORE",
    "nanopore": "OXFORD_NANOPORE",
    "pacbio": "PACBIO_SMRT",
    "sequel": "PACBIO_SMRT",
    "revio": "PACBIO_SMRT",
    "ion torrent": "ION_TORRENT",
}

SRA_TO_ENA_FIELDS = {
    "run_total_bases": "base_count",
    "run_total_spots": "read_count",
    "organism_taxid": "tax_id",
    "organism_name": "scientific_name",
}


def instrument_to_platform(instrument: str) -> str:
    """Map an SRA instrument model name to the ENA platform constant.

    Args:
        instrument: Instrument model name from SRA (e.g. "Illumina MiniSeq").

    Returns:
        str: Platform constant (e.g. "ILLUMINA") or the original value if unknown.
    """
    lower = instrument.lower()
    for key, platform in INSTRUMENT_PLATFORM_MAP.items():
        if key in lower:
            return platform
    return instrument


def normalize_sra_fields(records: list[dict]) -> list[dict]:
    """Rename SRA fields to their ENA equivalents so parse_accessions() works unchanged.

    Args:
        records: List of dicts from pysradb search results.

    Returns:
        list[dict]: Records with critical fields renamed in place.
    """
    for record in records:
        for sra_field, ena_field in SRA_TO_ENA_FIELDS.items():
            if sra_field in record:
                record[ena_field] = record.pop(sra_field)

        if "instrument" in record and "instrument_model_desc" not in record:
            record["instrument_model_desc"] = instrument_to_platform(
                record["instrument"]
            )

        layout = record.get("library_layout", "SINGLE").upper()
        record["fastq_bytes"] = "0;0" if layout == "PAIRED" else "0"

    return records


def get_sra_metadata(query: str, is_accession: bool, limit: int) -> list:
    """Fetch metadata from SRA via pysradb.

    Args:
        query: The query to search for (accession or NCBI query string).
        is_accession: If the query is an accession or not.
        limit: The maximum number of records to return.

    Returns:
        list: [success: bool, data: list[dict]]
    """
    try:
        db = SRAweb()
        df = db.search_sra(
            query,
            detailed=True,
            sample_attribute=True,
            expand_sample_attributes=True,
        )
        if df is None or df.empty:
            logging.debug(f"SRA query returned no results for: {query}")
            return [False, []]

        if len(df) > limit:
            logging.debug(f"SRA returned {len(df)} results, truncating to {limit}")
            df = df.head(limit)

        records = df.to_dict(orient="records")
        return [True, normalize_sra_fields(records)]
    except Exception as e:
        logging.error(f"Error querying SRA: {e}")
        return [False, []]
