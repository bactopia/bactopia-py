import gzip
import logging
import shutil
from pathlib import Path


def search_path(path: str, pattern: str, recursive: bool = False) -> Path:
    """
    Search a directory for files matching a pattern

    Args:
        path (str): The directory to search
        pattern (str): The pattern to match
        recursive (bool): Search recursively

    Returns:
        Path object: A generator of files matching the pattern
    """
    if recursive:
        return Path(path).rglob(pattern)
    else:
        return Path(path).glob(pattern)


def create_sample_directory(
    sample: str, assembly: str, bactopia_dir: str, publish_mode: str = "symlink"
) -> bool:
    """
    Create a Bactopia directory structure for a sample

    Args:
        sample (str): The name of the sample
        assembly (str): The path to the assembly
        bactopia_dir (str): The path to the Bactopia directory
        publish_mode (str): The method to publish the assembly (symlink or copy)

    Returns:
        bool: True if the directory was created, False otherwise
    """
    logging.debug(f"Creating {sample} directory ({bactopia_dir}/{sample})")
    sample_dir = Path(f"{bactopia_dir}/{sample}")
    if not sample_dir.exists():
        sample_dir.mkdir(parents=True, exist_ok=True)

    # Make remaining subdirectories (which will be empty)
    Path(f"{bactopia_dir}/{sample}/main").mkdir(parents=True, exist_ok=True)
    Path(f"{bactopia_dir}/{sample}/main/gather").mkdir(parents=True, exist_ok=True)
    Path(f"{bactopia_dir}/{sample}/main/assembler").mkdir(parents=True, exist_ok=True)

    # Write the meta.tsv file
    logging.debug(f"Writing {sample}-meta.tsv")
    is_compressed = "true" if str(assembly).endswith(".gz") else "false"
    with open(f"{bactopia_dir}/{sample}/main/gather/{sample}-meta.tsv", "w") as meta_fh:
        meta_fh.write(
            "sample\truntype\toriginal_runtype\tis_paired\tis_compressed\tspecies\tgenome_size\n"
        )
        meta_fh.write(
            f"{sample}\tassembly_accession\tassembly_accession\tfalse\t{is_compressed}\tnull\t0\n"
        )

    # Write the assembly file
    final_assembly = f"{bactopia_dir}/{sample}/main/assembler/{sample}.fna"
    if is_compressed:
        final_assembly = f"{final_assembly}.gz"
    final_assembly_path = Path(final_assembly)

    if publish_mode == "symlink":
        logging.debug(f"Creating symlink of {assembly} at {final_assembly}")
        final_assembly_path.symlink_to(assembly)
    else:
        logging.debug(f"Copying {assembly} to {final_assembly}")
        shutil.copyfile(assembly, final_assembly)

    return True


def parse_atb_file_list(file_list: str) -> list:
    """
    Parse the ATB file list to get the sample name and assembly path

    'file_list.all.latest.tsv.gz' description from the docs

    The file list contains the following columns:
        sample = the INSDC sample accession
        species_sylph = inferred species call from running sylph on the reads (see below)
        species_miniphy = the name miniphy gave to the species (see below)
        filename_in_tar_xz = the FASTA filename for this sample inside the tar.xz file
        tar_xz = the name of the tar.xz file where this sample’s FASTA lives
        tar_xz_url = URL of tar_xz
        tar_xz_md5 = MD5 sum of tar_xz
        tar_xz_size_MB = size of the tar_xz file in MB

    Where the first line is the header and the remaining lines are the data.

    Docs URL: https://allthebacteria.readthedocs.io/en/latest/assemblies.html#downloading-assemblies

    Args:
        file_list (str): The path to the ATB file list

    Returns:
        list: A list of two dictionaries
            samples: A dictionary of dictionaries for sample names and associated columns
            archives: A dictionary of dictionaries for tar.xz archives and associated columns
            species: A dictionary of lists of samples for each species
    """
    samples = {}
    archives = {}
    species = {}
    with gzip.open(file_list, "rt") as fh:
        header = None
        for line in fh:
            line = line.rstrip()
            if header is None:
                header = line.split("\t")
            else:
                cols = line.split("\t")
                row = dict(zip(header, cols))

                # Capture information for each sample
                samples[row["sample"]] = {
                    "species_sylph": row["species_sylph"],
                    "species_miniphy": row["species_miniphy"],
                    "tar_xz": row["tar_xz"],
                    "filename": row["filename_in_tar_xz"],
                }

                # Reduce duplicates with a archive dictionary
                if row["tar_xz"] not in archives:
                    archives[row["tar_xz"]] = {
                        "url": row["tar_xz_url"],
                        "md5": row["tar_xz_md5"],
                        "size": row["tar_xz_size_MB"],
                    }

                # Reduce duplicates with a species dictionary
                if row["species_sylph"] not in species:
                    species[row["species_sylph"]] = []
                species[row["species_sylph"]].append(row["sample"])

    logging.debug(f"Found {len(samples)} samples in {file_list}")
    logging.debug(f"Found {len(archives)} archives in {file_list}")
    logging.debug(f"Found {len(species)} species in {file_list}")
    return [samples, archives, species]
