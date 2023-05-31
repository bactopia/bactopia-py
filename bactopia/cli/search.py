import datetime
import logging
import random
import re
import sys
from pathlib import Path

import pandas as pd
import requests
import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.utils import get_ncbi_genome_size

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-search": [
        {"name": "Required Options", "options": ["--query"]},
        {
            "name": "Query Options",
            "options": [
                "--exact-taxon",
                "--limit",
                "--accession-limit",
                "--biosample-subset",
                "--include-empty",
            ],
        },
        {
            "name": "Filtering Options",
            "options": [
                "--min-base-count",
                "--min-read-length",
                "--min-coverage",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--genome-size",
                "--outdir",
                "--prefix",
                "--force",
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}
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
            cols = line.rstrip().split("\t")
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


def parse_accessions(
    results: dict,
    min_read_length: int,
    min_base_count: int,
    genome_size: int,
    genome_sizes: dict,
) -> list:
    """
    _summary_

    Args:
        results (dict): _description_
        min_read_length (int): _description_
        min_base_count (int): _description_
        genome_size (int): _description_
        genome_sizes (dict): _description_

    Returns:
        list: _description_
    """
    accessions = []
    filtered = {
        "min_base_count": 0,
        "min_read_length": 0,
        "technical": 0,
        "filtered": [],
    }
    for result in results:
        instrument_key = (
            "instrument_platform"
            if "instrument_platform" in result
            else "instrument_model_desc"
        )
        if (
            result[instrument_key] == "ILLUMINA"
            or result[instrument_key] == "OXFORD_NANOPORE"
        ):
            technology = (
                "ont" if result[instrument_key] == "OXFORD_NANOPORE" else "illumina"
            )
            passes = True
            reason = []
            if not result["fastq_bytes"]:
                passes = False
                reason.append("Missing FASTQs")
                filtered["technical"] += 1
            else:
                if min_read_length:
                    total_fastqs = len(result["fastq_bytes"].rstrip(";").split(";"))
                    read_length = int(
                        float(result["base_count"])
                        / (float(result["read_count"]) * total_fastqs)
                    )
                    if read_length < min_read_length:
                        passes = False
                        reason.append(
                            f"Failed mean read length ({read_length} bp) filter, expected > {min_read_length} bp"
                        )
                        filtered["min_read_length"] += 1

                if min_base_count:
                    if float(result["base_count"]) < min_base_count:
                        passes = False
                        reason.append(
                            f'Failed base count ({result["base_count"]} bp) filter, expected > {min_base_count} bp'
                        )
                        filtered["min_base_count"] += 1

            # Genome size
            gsize = genome_size
            if not gsize:
                if result["tax_id"] in genome_sizes:
                    gsize = genome_sizes[result["tax_id"]]["expected_ungapped_length"]
                else:
                    logging.warning(
                        f"Could not find genome size for {result['scientific_name']} (Tax ID {result['tax_id']})"
                    )

            if passes:
                accessions.append(
                    f"{result['experiment_accession']}\t{technology}\t{result['scientific_name']}\t{gsize}"
                )
            else:
                filtered["filtered"].append(
                    {
                        "accession": result["experiment_accession"],
                        "technology": technology,
                        "scientific_name": result["scientific_name"],
                        "genome_size": gsize,
                        "reason": ";".join(reason),
                    }
                )
    return [list(set(accessions)), filtered]


def is_biosample(accession):
    """Check if input accession is a BioSample."""
    return (
        True
        if re.match(r"SAM(E|D|N)[A-Z]?[0-9]+|(E|D|S)RS[0-9]{6,}", accession)
        else False
    )


def chunks(chunk: list, total: int) -> list:
    """
    Yield successive n-sized chunks from l.
    https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks?page=1&tab=votes#tab-top
    """
    for i in range(0, len(chunk), total):
        yield chunk[i : i + total]


def parse_query(q, accession_limit, exact_taxon=False):
    """Return the query based on if Taxon ID or BioProject/Study accession."""
    import re

    queries = []
    if Path(q).exists():
        with open(q, "r") as handle:
            for line in handle:
                line = line.rstrip()
                if line:
                    queries.append(line)
    elif "," in q:
        queries = q.split(",")
    else:
        queries.append(q)
    results = []
    bioproject_accessions = []
    biosample_accessions = []
    experiment_accessions = []
    run_accessions = []

    for query in queries:
        try:
            taxon_id = int(query)
            if exact_taxon:
                results.append(
                    ["taxon", f"tax_eq({taxon_id})", f"txid{taxon_id}[Organism:noexp]"]
                )
            else:
                results.append(
                    [
                        "taxon_tree",
                        f"tax_tree({taxon_id})",
                        f"txid{taxon_id}[Organism:exp]",
                    ]
                )
        except ValueError:
            # It is a accession or scientific name
            # Test Accession
            # Thanks! https://ena-docs.readthedocs.io/en/latest/submit/general-guide/accessions.html#accession-numbers
            if re.match(r"^PRJ[EDN][A-Z][0-9]+$|^[EDS]RP[0-9]{6,}$", query):
                bioproject_accessions.append(query)
            elif re.match(r"^SAM[EDN][A-Z]?[0-9]+$|^[EDS]RS[0-9]{6,}$", query):
                biosample_accessions.append(query)
            elif re.match(r"^[EDS]RX[0-9]{6,}$", query):
                experiment_accessions.append(query)
            elif re.match(r"^[EDS]RR[0-9]{6,}$", query):
                run_accessions.append(query)
            else:
                # Assuming it is a scientific name
                results.append(["taxon_name", f'tax_name("{query}")', f"'{query}'"])

    # Split the accessions into set number
    for chunk in chunks(bioproject_accessions, accession_limit):
        results.append(["bioproject_accession", ",".join(chunk), " OR ".join(chunk)])
    for chunk in chunks(biosample_accessions, accession_limit):
        results.append(["biosample_accession", ",".join(chunk), " OR ".join(chunk)])
    for chunk in chunks(experiment_accessions, accession_limit):
        results.append(["experiment_accession", ",".join(chunk), " OR ".join(chunk)])
    for chunk in chunks(run_accessions, accession_limit):
        results.append(["run_accession", ",".join(chunk), " OR ".join(chunk)])

    return results


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--query",
    "-q",
    required=True,
    help="Taxon ID or Study, BioSample, or Run accession (can also be comma separated or a file of accessions)",
)
@click.option("--exact-taxon", is_flag=True, help="Exclude Taxon ID descendants")
@click.option(
    "--outdir", "-o", default="./", show_default=True, help="Directory to write output"
)
@click.option(
    "--prefix",
    "-p",
    default="bactopia",
    show_default=True,
    help="Prefix to use for output file names",
)
@click.option(
    "--limit",
    "-l",
    default=1000000,
    show_default=True,
    help="Maximum number of results (per query) to return",
)
@click.option(
    "--accession-limit",
    "-al",
    default=5000,
    show_default=True,
    help="Maximum number of accessions to query at once",
)
@click.option(
    "--biosample-subset",
    default=0,
    show_default=True,
    help="If a BioSample has multiple Experiments, maximum number to randomly select (0 = disabled)",
)
@click.option(
    "--min-base-count",
    "-mbc",
    default=0,
    show_default=True,
    help="Filters samples based on minimum base pair count (0 = disabled)",
)
@click.option(
    "--min-read-length",
    "-mrl",
    default=0,
    show_default=True,
    help="Filters samples based on minimum mean read length (0 = disabled)",
)
@click.option(
    "--min-coverage",
    "-mc",
    default=0,
    show_default=True,
    help="Filter samples based on minimum coverage (requires --genome_size, 0 = disabled)",
)
@click.option(
    "--genome-size",
    "-gsize",
    default=0,
    show_default=True,
    help="Genome size to be used for all samples, and for calculating min coverage",
)
@click.option(
    "--include-empty",
    is_flag=True,
    help="Include metadata columns that are empty for all rows",
)
@click.option("--force", is_flag=True, help="Overwrite existing reports")
@click.option("--verbose", is_flag=True, help="Increase the verbosity of output")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def search(
    query,
    exact_taxon,
    outdir,
    prefix,
    limit,
    accession_limit,
    biosample_subset,
    min_base_count,
    min_read_length,
    min_coverage,
    genome_size,
    include_empty,
    force,
    verbose,
    silent,
):
    """Query against ENA and SRA for public accessions to process with Bactopia"""
    # Setup logs
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )

    # if not os.path.exists(args.outdir):
    #    os.makedirs(args.outdir, exist_ok=True)

    if min_coverage and genome_size:
        if min_base_count:
            logging.error(
                "--min_base_count cannot be used with --coverage/--genome_size. Exiting...",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            min_base_count = min_coverage * genome_size
    elif min_coverage or genome_size:
        logging.error(
            "--coverage and --genome_size must be used together. Exiting...",
            file=sys.stderr,
        )
        sys.exit(1)

    if biosample_subset > 0:
        if not is_biosample(query):
            logging.error(
                "--biosample_subset requires a single BioSample. Input query: {query} is not a BioSample. Exiting...",
                file=sys.stderr,
            )
            sys.exit(1)

    results = []

    accessions = []
    filtered = {
        "min_base_count": 0,
        "min_read_length": 0,
        "technical": 0,
        "filtered": {},
    }
    summary = []
    queries = parse_query(query, accession_limit, exact_taxon=exact_taxon)
    i = 1

    # Output files
    metadata_file = f"{outdir}/{prefix}-metadata.txt".replace("//", "/")
    accessions_file = f"{outdir}/{prefix}-accessions.txt".replace("//", "/")
    filtered_file = f"{outdir}/{prefix}-filtered.txt".replace("//", "/")
    summary_file = f"{outdir}/{prefix}-search.txt".replace("//", "/")
    genome_sizes = get_ncbi_genome_size()
    for query_type, ena_query, sra_query in queries:
        logging.info(f"Submitting query (type - {query_type})")
        is_accession = True if query_type.endswith("accession") else False
        success, query_results = get_run_info(
            sra_query, ena_query, is_accession, limit=limit
        )
        results += query_results
        if success:
            query_accessions, query_filtered = parse_accessions(
                query_results,
                min_read_length=min_read_length,
                min_base_count=min_base_count,
                genome_size=genome_size,
                genome_sizes=genome_sizes,
            )
            if len(query_accessions):
                WARNING_MESSAGE = None
                if query_type == "biosample" and biosample_subset > 0:
                    if len(query_accessions) > biosample_subset:
                        WARNING_MESSAGE = f"WARNING: Selected {biosample_subset} Experiment accession(s) from a total of {len(query_accessions)}"
                        query_accessions = random.sample(
                            query_accessions, biosample_subset
                        )
                accessions = list(set(accessions + query_accessions))
                filtered["min_base_count"] += query_filtered["min_base_count"]
                filtered["min_read_length"] += query_filtered["min_read_length"]
                filtered["technical"] += query_filtered["technical"]
                for filtered_sample in query_filtered["filtered"]:
                    filtered["filtered"][
                        filtered_sample["accession"]
                    ] = filtered_sample["reason"]
            else:
                if query_results:
                    WARNING_MESSAGE = f"WARNING: {query} did not return any Illumina or Ont results from ENA."
                else:
                    WARNING_MESSAGE = (
                        f"WARNING: {query} did not return any results from ENA."
                    )

            # Create Summary
            query_string = query
            if query_type == "accession":
                total_accessions = len(query.split(","))
                if total_accessions > 5:
                    query_string = f"{total_accessions} accessions were queried"
                else:
                    query_string = query
            if len(queries) > 1:
                summary.append(f"QUERY ({i} of {len(queries)}): {query_string}")
                i += 1
            else:
                summary.append(f"QUERY: {query_string}")
            summary.append(
                f"DATE: {datetime.datetime.now().replace(microsecond=0).isoformat()}"
            )
            summary.append(f"LIMIT: {limit}")
            summary.append(f"RESULTS: {len(results)} ({metadata_file})")
            summary.append(
                f"ILLUMINA ACCESSIONS: {len(query_accessions)} ({accessions_file})"
            )

            if WARNING_MESSAGE:
                summary.append(f"\t{WARNING_MESSAGE}")

            if min_read_length or min_base_count:
                summary.append(f'FILTERED ACCESSIONS: {len(filtered["filtered"])}')
                if min_read_length:
                    summary.append(
                        f'\tFAILED MIN READ LENGTH ({min_read_length} bp): {query_filtered["min_read_length"]}'
                    )
                if min_base_count:
                    summary.append(
                        f'\tFAILED MIN BASE COUNT ({min_base_count} bp): {query_filtered["min_base_count"]}'
                    )
            else:
                summary.append("FILTERED ACCESSIONS: no filters applied")

            summary.append(f'\tMISSING FASTQS: {filtered["technical"]}')
            summary.append("")
        else:
            logging.error(f"ERROR: Unable to retrieve metadata for query ({query})")

    # Output the results
    logging.info(f"Writing results to {metadata_file}")
    with open(metadata_file, "w") as output_fh:
        df = pd.DataFrame.from_dict(results)
        if not include_empty:
            logging.debug(f"Removing empty columns from {metadata_file}")
            df.replace("", float("NaN"), inplace=True)
            df.dropna(inplace=True, how="all", axis=1)
            df.replace(float("NaN"), "", inplace=True)
        df.to_csv(output_fh, sep="\t", index=False)

    logging.info(f"Writing accessions to {accessions_file}")
    with open(accessions_file, "w") as output_fh:
        for accession in accessions:
            output_fh.write(f"{accession}\n")

    logging.info(f"Writing filtered accessions to {filtered_file}")
    with open(filtered_file, "w") as output_fh:
        output_fh.write("accession\treason\n")
        for accession, reason in filtered["filtered"].items():
            output_fh.write(f"{accession}\t{reason}\n")

    logging.info(f"Writing summary to {summary_file}")
    with open(summary_file, "w") as output_fh:
        output_fh.write("\n".join(summary))


def main():
    if len(sys.argv) == 1:
        search.main(["--help"])
    else:
        search()


if __name__ == "__main__":
    main()
