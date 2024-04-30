import logging
import shutil
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-atb-formatter": [
        {"name": "Required Options", "options": ["--path"]},
        {
            "name": "Bactopia Directory Structure Options",
            "options": [
                "--bactopia-dir",
                "--publish-mode",
                "--recursive",
                "--extension",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}


def search_path(path, pattern, recursive=False):
    if recursive:
        return Path(path).rglob(pattern)
    else:
        return Path(path).glob(pattern)


def create_sample_directory(sample, assembly, bactopia_dir, publish_mode="symlink"):
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


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--path", "-p", required=True, help="Directory where FASTQ files are stored"
)
@click.option(
    "--bactopia-dir",
    "-b",
    default="bactopia",
    show_default=True,
    help="The path you would like to place bactopia structure",
)
@click.option(
    "--publish-mode",
    "-m",
    default="symlink",
    show_default=True,
    type=click.Choice(["symlink", "copy"], case_sensitive=False),
    help="Designates plascement of assemblies will be handled",
)
@click.option(
    "--extension",
    "-e",
    default=".fa",
    show_default=True,
    help="The extension of the FASTA files",
)
@click.option(
    "--recursive", "-r", is_flag=True, help="Traverse recursively through provided path"
)
@click.option("--verbose", is_flag=True, help="Increase the verbosity of output")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def atb_formatter(
    path,
    bactopia_dir,
    publish_mode,
    extension,
    recursive,
    verbose,
    silent,
):
    """Restructure All-the-Bacteria assemblies to allow usage with Bactopia Tools"""
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

    # Match Assemblies
    count = 0
    logging.info(
        "Setting up Bactopia directory structure (use --verbose to see more details)"
    )
    for fasta in search_path(abspath, f"*{extension}", recursive=recursive):
        fasta_name = fasta.name.replace(extension, "")
        create_sample_directory(fasta_name, fasta, bactopia_dir, publish_mode)
        count += 1
    logging.info(f"Bactopia directory structure created at {bactopia_dir}")
    logging.info(f"Total assemblies processed: {count}")


def main():
    if len(sys.argv) == 1:
        atb_formatter.main(["--help"])
    else:
        atb_formatter()


if __name__ == "__main__":
    main()
