import logging
import os
import sys

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.atb import parse_atb_file_list
from bactopia.ncbi import is_biosample, taxid2name
from bactopia.utils import (
    download_url,
    execute,
    file_exists,
    mkdir,
    pgzip,
    validate_file,
)

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-atb-downloader": [
        {
            "name": "Required Options",
            "options": [
                "--query",
            ],
        },
        {
            "name": "ATB Download Options",
            "options": [
                "--outdir",
                "--atb-file-list-url",
                "--dry-run",
                "--progress",
                "--cpus",
                "--uncompressed",
                "--remove-archives",
            ],
        },
        {
            "name": "NCBI API Options",
            "options": [
                "--ncbi-api-key",
                "--chunk-size",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--force",
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--query",
    "-q",
    required=True,
    help="The species name, taxid, accession to query and download",
)
@click.option(
    "--outdir",
    "-o",
    default="./atb-assemblies",
    show_default=True,
    help="Directory to download ATB assemblies to",
)
@click.option(
    "--atb-file-list-url",
    "-a",
    default="https://osf.io/download/4yv85/",
    show_default=True,
    help="The URL to the ATB file list",
)
@click.option(
    "--dry-run",
    "-d",
    is_flag=True,
    help="Do not download any files, just show what would be downloaded",
)
@click.option(
    "--progress",
    "-p",
    is_flag=True,
    help="Show download progress bar",
)
@click.option(
    "--cpus",
    default=4,
    help="The total number of cpus to use for downloading and compressing",
)
@click.option(
    "--uncompressed",
    "-u",
    is_flag=True,
    help="Do not compress the downloaded files",
)
@click.option(
    "--remove-archives",
    "-r",
    is_flag=True,
    help="Remove the downloaded tar.xz archives after extracting samples",
)
@click.option(
    "--ncbi-api-key",
    "-k",
    required=False,
    default=os.environ.get("NCBI_API_KEY", None),
    help="The API key to use for the NCBI API",
)
@click.option(
    "--chunk-size",
    "-c",
    default=200,
    help="The size of the chunks to split the list into",
)
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--verbose", is_flag=True, help="Increase the verbosity of output")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def atb_downloader(
    query,
    outdir,
    atb_file_list_url,
    dry_run,
    progress,
    cpus,
    uncompressed,
    remove_archives,
    ncbi_api_key,
    chunk_size,
    force,
    verbose,
    silent,
):
    """Download All-the-Bacteria assemblies based on input query"""
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

    # If outdir does not exist, create it
    outdir = mkdir(outdir)

    # Download the ATB file list
    atb_file_list = f"{str(outdir)}/file_list.all.latest.tsv.gz"
    if file_exists(atb_file_list):
        logging.info(f"Using existing file list: {atb_file_list}")
        atb_file_list = validate_file(atb_file_list)
    else:
        logging.info(f"Downloading file list to: {atb_file_list}")
        atb_file_list = download_url(atb_file_list_url, atb_file_list, progress)

    # Parse the ATB file list
    logging.info(f"Parsing ATB file list: {atb_file_list}")
    samples, archives, species = parse_atb_file_list(atb_file_list)

    # Determine query type
    matched_samples = []
    archives_to_download = {}
    if is_biosample(query):
        logging.info(f"Query is a BioSample: {query}")
        if query in samples:
            archives_to_download[samples[query]["tar_xz"]] = archives[
                samples[query]["tar_xz"]
            ]
            matched_samples.append(query)
        else:
            logging.error(f"Sample not found in ATB file list: {query}")
            sys.exit(1)
    else:
        query_species = query
        if query.isdigit():
            if not ncbi_api_key:
                logging.error("NCBI API key is required for TaxID queries")
                sys.exit(1)
            query_species = taxid2name([query], ncbi_api_key, chunk_size)[query]
            logging.info(f"Converted TaxID ({query}) in to {query_species}")
        logging.info(f"Query is a species: {query_species}")

        if query_species in species:
            for sample in species[query_species]:
                archives_to_download[samples[sample]["tar_xz"]] = archives[
                    samples[sample]["tar_xz"]
                ]
        else:
            logging.error(f"Species not found in ATB file list: {query_species}")
            sys.exit(1)
        matched_samples = species[query_species]

    # Estimate total size of downloads
    total_size = 0
    for archive, info in archives_to_download.items():
        total_size += float(info["size"])

    logging.info(f"Found {len(matched_samples)} samples to extract")
    logging.debug(f"Samples: {matched_samples}")
    logging.info(
        f"Found {len(archives_to_download)} archives (~{int(total_size):,} MB) to download"
    )
    if verbose:
        for archive in archives_to_download:
            logging.debug(f"Archive: {archive}")

    # Check if archives exist, otherwise download
    if not dry_run:
        logging.info(f"Downloading archives to: {outdir}/archives")
        mkdir(f"{outdir}/archives")
        for archive, info in archives_to_download.items():
            archive_path = f"{str(outdir)}/archives/{archive}"
            if file_exists(archive_path):
                logging.info(f"Using existing archive: {archive_path}")
                archive_path = validate_file(archive_path)
            else:
                logging.info(f"Downloading archive to: {archive_path}")
                if dry_run:
                    logging.info(f"Would download: {info['url']} to {archive_path}")
                else:
                    archive_path = download_url(info["url"], archive_path, progress)

        # Extract each of the archives
        cleanup = []
        for archive, info in archives_to_download.items():
            archive_path = f"{str(outdir)}/archives/{archive}"
            if dry_run:
                logging.info(f"Would have extracted: {archive_path}")
            else:
                logging.info(f"Extracting: {archive_path}")
                stdout, stderr = execute(
                    f"tar xf {archive_path} -C {outdir}", capture=True, allow_fail=True
                )
                cleanup_dir = f"{outdir}/{archive.replace('.tar.xz', '')}"
                logging.debug(f"Adding {cleanup_dir} to cleanup list")
                cleanup.append(f"{outdir}/{archive.replace('.tar.xz', '')}")
    else:
        logging.info("Would have downloaded and extracted archives")

    # Move samples into species directories, then compress
    species_dirs = {}
    needs_compression = []
    if not dry_run:
        logging.info(f"Moving {len(matched_samples)} samples to: {outdir}")
        for i, sample in enumerate(matched_samples):
            logging.debug(f"Moving sample {i+1} of {len(matched_samples)}: {sample}")
            info = samples[sample]
            species = info["species_sylph"].lower().replace(" ", "_")
            if species not in species_dirs:
                species_dirs[species] = True
                mkdir(f"{outdir}/{species}")

            archive_file = f"{outdir}/{info['filename']}"
            if file_exists(archive_file):
                sample_filename = info["filename"].split("/")[-1]
                sample_out = f"{outdir}/{species}/{sample_filename}"

                if file_exists(archive_file):
                    if (file_exists(sample_out) and not force) or ():
                        logging.debug(
                            f"Sample already exists: {sample_out}...skipping unless --force provided"
                        )

                        # Compress unless --uncompressed provided
                        if not uncompressed:
                            needs_compression.append(sample_out)
                    elif file_exists(f"{sample_out}.gz") and not force:
                        logging.debug(
                            f"Sample already exists: {sample_out}.gz...skipping unless --force provided"
                        )
                    else:
                        logging.debug(f"Moving {archive_file} to {sample_out}")
                        stdout, stderr = execute(
                            f"mv {archive_file} {sample_out}",
                            capture=True,
                            allow_fail=True,
                        )

                        # Compress unless --uncompressed provided
                        if not uncompressed:
                            needs_compression.append(sample_out)
                else:
                    logging.warning(f"Unable to find {info['filename']}")
            else:
                logging.warning(f"{outdir}/{info['filename']}")

        # Compress samples
        if len(needs_compression):
            logging.info(f"Compressing {len(needs_compression)} samples")
            pgzip(needs_compression, cpus)

        # Cleanup
        for archive in cleanup:
            if file_exists(archive):
                logging.info(f"Removing extracted files: {archive}")
                stdout, stderr = execute(
                    f"rm -rf {archive}", capture=True, allow_fail=True
                )

        if remove_archives:
            logging.info(
                "Provided --remove-archives, removing all downloaded archives in {outdir}/archives"
            )
            stdout, stderr = execute(
                f"rm -rf {outdir}/archives", capture=True, allow_fail=True
            )
    else:
        logging.info(
            "Would have moved samples to species directories and cleaned up archives"
        )


def main():
    if len(sys.argv) == 1:
        atb_downloader.main(["--help"])
    else:
        atb_downloader()


if __name__ == "__main__":
    main()
