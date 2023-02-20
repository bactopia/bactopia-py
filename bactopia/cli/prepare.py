import logging
import re
import sys
import textwrap
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.utils import get_ncbi_genome_size, get_taxid_from_species, validate_file

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-prepare": [
        {"name": "Required Options", "options": ["--path"]},
        {
            "name": "Matching Options",
            "options": [
                "--assembly-ext",
                "--fastq-ext",
                "--fastq-separator",
                "--pe1-pattern",
                "--pe2-pattern",
                "--merge",
                "--ont",
                "--recursive",
                "--prefix",
            ],
        },
        {
            "name": "Sample Information Options",
            "options": [
                "--metadata",
                "--genome-size",
                "--species",
                "--taxid",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--examples",
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}


def read_metadata(metadata: str) -> dict:
    """
    Read in metadata file

    Args:
        metadata (str): Path to a metadata file

    Returns:
        dict: A dictionary of metadata, associating genome size and species to a samples
    """
    metadata_dict = {}
    with open(metadata, "r") as fh:
        for line in fh:
            # Use replace, since final column may be empty
            if line:
                sample, species, gsize = line.rstrip().split("\t")
                if not gsize:
                    gsize = 0
                if not species:
                    species = "UNKNOWN_SPECIES"
                metadata_dict[sample] = {"genome_size": int(gsize), "species": species}
    return metadata_dict


def get_genome_size(
    genome_sizes: dict, genome_size: int, species: str, taxid: str
) -> int:
    """
    Determine which value to use for genome size

    Args:
        genome_sizes (dict): A dictionary of genome sizes from NCBI
        genome_size (int): The genome size provided by the user
        species (str): The species provided by the user
        taxid (str): The taxon ID provided by the user

    Returns:
        int: A genome size to use
    """

    if taxid:
        # Use the taxon ID to get the genome size
        return [genome_sizes[taxid]["expected_ungapped_length"], taxid]
    elif genome_size > 0:
        # User provided genome size
        return [genome_size, None]
    elif species and species != "UNKNOWN_SPECIES":
        # Get genome size from NCBI based on species
        taxid = get_taxid_from_species(species)
        return [genome_sizes[taxid]["expected_ungapped_length"], taxid]
    else:
        # No genome size provided, not ideal
        return [0, None]


def search_path(path, pattern, recursive=False):
    if recursive:
        return Path(path).rglob(pattern)
    else:
        return Path(path).glob(pattern)


def get_path(fastq, abspath, prefix):
    fastq_path = str(fastq.absolute())
    if prefix:
        return fastq_path.replace(abspath, prefix).replace("///", "//")
    return fastq_path


def print_examples():
    print(
        textwrap.dedent(
            """
        # Example '*_001.fastq.gz' FASTQ files:
        bactopia-prepare --path fastqs/ --fastq-ext '_001.fastq.gz' | head -n
        sample  runtype r1      r2      extra
        sample01        paired-end      /fastqs/sample01_R1_001.fastq.gz        /fastqs/sample01_R2_001.fastq.gz
        sample02        paired-end      /fastqs/sample02_R1_001.fastq.gz        /fastqs/sample02_R2_001.fastq.gz
        sample03        single-end      /fastqs/sample03_001.fastq.gz

        # Example '*.fq.gz' FASTQ files:
        bactopia prepare --path fastqs/ --fastq-ext '.fq.gz'
        sample  runtype r1      r2      extra
        sample01        single-end      /home/robert_petit/bactopia/fastqs/sample01.fq.gz
        sample02        single-end      /home/robert_petit/bactopia/fastqs/sample02.fq.gz
        sample03        single-end      /home/robert_petit/bactopia/fastqs/sample03.fq.gz

        # Example "*.fasta.gz" FASTA files:
        bactopia-prepare --path fastqs/ --assembly-ext '.fasta.gz'
        sample  runtype r1      r2      extra
        sample01        assembly                        /home/robert_petit/bactopia/temp/fastas/sample01.fasta.gz
        sample02        assembly                        /home/robert_petit/bactopia/temp/fastas/sample02.fasta.gz
        sample03        assembly                        /home/robert_petit/bactopia/temp/fastas/sample03.fasta.gz

        # Example changing the separator:
        bactopia-prepare --path fastqs/ --fastq-separator '.'
        sample  runtype r1      r2      extra
        my_sample01     ont     /home/robert_petit/bactopia/temp/fastqs/my_sample01.fastq.gz
        my_sample02     ont     /home/robert_petit/bactopia/temp/fastqs/my_sample02.fastq.gz
        my_sample03     ont     /home/robert_petit/bactopia/temp/fastqs/my_sample03.fastq.gz

        # Example metadata file (--metadata):
        sample01     Staphylococcus aureus  0
        sample02     Escherichia coli       0
        sample03                            2800000
    """
        )
    )
    sys.exit(0)


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--path", "-p", required=True, help="Directory where FASTQ files are stored"
)
@click.option(
    "--fastq-ext",
    "-f",
    default=".fastq.gz",
    show_default=True,
    help="Extension of the FASTQs",
)
@click.option(
    "--assembly-ext",
    "-a",
    default=".fna.gz",
    show_default=True,
    help="Extension of the FASTA assemblies",
)
@click.option(
    "--pe1-pattern",
    default="[Aa]|[Rr]1|1",
    show_default=True,
    help="Designates difference first set of paired-end reads",
)
@click.option(
    "--pe2-pattern",
    default="[Bb]|[Rr]2|2",
    show_default=True,
    help="Designates difference second set of paired-end reads",
)
@click.option(
    "--fastq-separator",
    default="_",
    show_default=True,
    help="Split FASTQ name on the last occurrence of the separator",
)
@click.option(
    "--metadata", help="Metadata per sample with genome size and species information"
)
@click.option(
    "--genome-size", "-gsize", default=0, help="Genome size to use for all samples"
)
@click.option(
    "--species",
    "-s",
    default="UNKNOWN_SPECIES",
    help="Species to use for all samples (If available, can be used to determine genome size)",
)
@click.option("--taxid", help="Use the genome size of the Taxon ID for all samples")
@click.option(
    "--recursive", "-r", is_flag=True, help="Directories will be traversed recursively"
)
@click.option(
    "--ont",
    is_flag=True,
    help="Single-end reads should be treated as Oxford Nanopore reads",
)
@click.option(
    "--merge",
    is_flag=True,
    help="Flag samples with multiple read sets to be merged by Bactopia",
)
@click.option("--prefix", default=None, help="Prefix to add to the path")
@click.option("--examples", is_flag=True, help="Print example usage")
@click.option("--verbose", is_flag=True, help="Increase the verbosity of output")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def prepare(
    path,
    fastq_ext,
    assembly_ext,
    pe1_pattern,
    pe2_pattern,
    fastq_separator,
    metadata,
    genome_size,
    species,
    taxid,
    recursive,
    ont,
    merge,
    prefix,
    examples,
    verbose,
    silent,
):
    """Create a 'file of filenames' (FOFN) of samples to be processed by Bactopia"""
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

    abspath = Path(path).absolute()
    SAMPLES = {}
    SPECIES_TAXIDS = {}

    # Get genome sizes
    genome_sizes = get_ncbi_genome_size()
    metadata_info = None
    if metadata:
        metadata_info = read_metadata(validate_file(metadata))

    genome_size, species_taxid = get_genome_size(
        genome_sizes, genome_size, species, taxid
    )
    if species_taxid:
        SPECIES_TAXIDS[species] = species_taxid

    # Match FASTQS
    for fastq in search_path(abspath, f"*{fastq_ext}", recursive=recursive):
        fastq_name = fastq.name.replace(fastq_ext, "")
        # Split the fastq file name on separator
        # Example MY_FASTQ_R1.rsplit('_', 1) becomes ['MY_FASTQ', 'R1'] (PE)
        # Example MY_FASTQ.rsplit('_', 1) becomes ['MY_FASTQ'] (SE)
        split_vals = fastq_name.rsplit(fastq_separator, 1)
        sample_name = split_vals[0]
        if sample_name not in SAMPLES:
            SAMPLES[sample_name] = {
                "pe": {"r1": [], "r2": []},
                "se": [],
                "assembly": [],
            }

        if len(split_vals) == 1:
            # single-end
            SAMPLES[sample_name]["se"].append(get_path(fastq, abspath, prefix))
        else:
            # paired-end
            pe1 = re.compile(pe1_pattern)
            pe2 = re.compile(pe2_pattern)
            if pe1.match(split_vals[1]):
                SAMPLES[sample_name]["pe"]["r1"].append(
                    get_path(fastq, abspath, prefix)
                )
            elif pe2.match(split_vals[1]):
                SAMPLES[sample_name]["pe"]["r2"].append(
                    get_path(fastq, abspath, prefix)
                )
            else:
                logging.error(
                    f'ERROR: Could not determine read set for "{fastq_name}".'
                )
                logging.error(
                    f"ERROR: Found {split_vals[1]} expected (R1: {pe1_pattern} or R2: {pe2_pattern})"
                )
                logging.error(
                    "ERROR: Please use --pe1-pattern and --pe2-pattern to correct and try again."
                )
                sys.exit(1)

    # Match assemblies
    for assembly in search_path(abspath, f"*{assembly_ext}", recursive=recursive):
        sample_name = Path(assembly).name.replace(assembly_ext, "")
        if sample_name not in SAMPLES:
            SAMPLES[sample_name] = {
                "pe": {"r1": [], "r2": []},
                "se": [],
                "assembly": [],
            }
        SAMPLES[sample_name]["assembly"].append(get_path(assembly, abspath, prefix))

    FOFN = []
    for sample, vals in sorted(SAMPLES.items()):
        r1_reads = vals["pe"]["r1"]
        r2_reads = vals["pe"]["r2"]
        se_reads = vals["se"]
        assembly = vals["assembly"]
        errors = []
        is_single_end = False
        multiple_read_sets = False
        pe_count = len(r1_reads) + len(r2_reads)

        # Validate everything
        if len(assembly) > 1:
            # Can't have multiple assemblies for the same sample
            errors.append(
                f'ERROR: "{sample}" cannot have more than two assembly FASTA, please check.'
            )
        elif len(assembly) == 1 and (pe_count or len(se_reads)):
            # Can't have an assembly and reads for a sample
            errors.append(
                f'ERROR: "{sample}" cannot have assembly and sequence reads, please check.'
            )

        if len(r1_reads) != len(r2_reads):
            # PE reads must be a pair
            errors.append(
                f'ERROR: "{sample}" must have equal paired-end read sets (R1 has {len(r1_reads)} and R2 has {len(r2_reads)}, please check.'
            )
        elif pe_count > 2:
            # PE reads must be a pair
            if merge:
                multiple_read_sets = True
            else:
                errors.append(
                    f'ERROR: "{sample}" cannot have more than two paired-end FASTQ, please check.'
                )

        if ont:
            if not pe_count and len(se_reads):
                is_single_end = True
        else:
            if len(se_reads) > 1:
                # Can't have multiple SE reads
                if merge:
                    multiple_read_sets = True
                else:
                    errors.append(
                        f'ERROR: "{sample}" has more than two single-end FASTQs, please check.'
                    )
            elif pe_count and len(se_reads):
                # Can't have SE and PE reads unless long reads
                errors.append(
                    f'ERROR: "{sample}" has paired and single-end FASTQs, please check.'
                )

        if errors:
            logging.error("\n".join(errors))
        else:
            runtype = ""
            sample_gsize = genome_size
            sample_species = species
            r1 = ""
            r2 = ""
            extra = ""

            if assembly:
                runtype = "assembly"
                extra = assembly[0]

            if pe_count:
                if multiple_read_sets:
                    if ont:
                        runtype = "hybrid-merge-pe"
                    else:
                        runtype = "merge-pe"
                    r1 = ",".join(sorted(r1_reads))
                    r2 = ",".join(sorted(r2_reads))
                else:
                    runtype = "paired-end"
                    r1 = r1_reads[0]
                    r2 = r2_reads[0]

            if se_reads:
                if ont and not is_single_end:
                    runtype = "hybrid"
                    extra = se_reads[0]
                elif ont and is_single_end:
                    runtype = "ont"
                    r1 = se_reads[0]
                else:
                    if multiple_read_sets:
                        runtype = "merge-se"
                        r1 = ",".join(se_reads)
                    else:
                        runtype = "single-end"
                        r1 = se_reads[0]

            if metadata_info:
                if sample in metadata_info:
                    meta_gsize = metadata_info[sample]["genome_size"]
                    sample_species = metadata_info[sample]["species"]
                    sample_taxid = (
                        SPECIES_TAXIDS[sample_species]
                        if sample_species in SPECIES_TAXIDS
                        else None
                    )
                    sample_gsize, species_taxid = get_genome_size(
                        genome_sizes, meta_gsize, sample_species, sample_taxid
                    )
                    if species_taxid:
                        # Save the taxid for the species, to prevent repeated lookups
                        SPECIES_TAXIDS[sample_species] = species_taxid

            FOFN.append(
                [sample, runtype, str(sample_gsize), sample_species, r1, r2, extra]
            )

    if FOFN:
        print("sample\truntype\tgenome_size\tspecies\tr1\tr2\textra")
        for line in FOFN:
            print("\t".join(line))
    else:
        logging.error(
            f"Unable to find any samples in {path}. Please try adjusting the following parameters to fit your needs."
        )
        logging.error("Values Used:")
        logging.error(f"    --assembly-ext => {assembly_ext}")
        logging.error(f"    --fastq-ext => {fastq_ext}")
        logging.error(f"    --fastq-separator => {fastq_separator}")
        logging.error(f"    --pe1-pattern => {pe1_pattern}")
        logging.error(f"    --pe2-pattern => {pe2_pattern}")
        logging.error("")
        logging.error(
            "You can also use '--examples' to see a few examples of using bactopia prepare"
        )
        sys.exit(1)


def main():
    if len(sys.argv) == 1:
        prepare.main(["--help"])
    elif "--examples" in sys.argv:
        print_examples()
    else:
        prepare()


if __name__ == "__main__":
    main()
