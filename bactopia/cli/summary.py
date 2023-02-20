import logging
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import pandas as pd
import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
import bactopia.parsers as parsers
from bactopia.parse import parse_bactopia_directory
from bactopia.parsers.error import parse_errors
from bactopia.parsers.parsables import EXCLUDE_COLUMNS, get_parsable_files
from bactopia.parsers.versions import parse_versions
from bactopia.summary import get_rank, print_cutoffs, print_failed

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-summary": [
        {"name": "Required Options", "options": ["--bactopia"]},
        {
            "name": "Gold Cutoffs",
            "options": [
                "--gold-coverage",
                "--gold-quality",
                "--gold-read-length",
                "--gold-contigs",
            ],
        },
        {
            "name": "Silver Cutoffs",
            "options": [
                "--silver-coverage",
                "--silver-quality",
                "--silver-read-length",
                "--silver-contigs",
            ],
        },
        {
            "name": "Fail Cutoffs",
            "options": [
                "--min-coverage",
                "--min-quality",
                "--min-read-length",
                "--max-contigs",
                "--min-assembled-size",
                "--max-assembled-size",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
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
COUNTS = defaultdict(int)
FAILED = defaultdict(list)
CATEGORIES = defaultdict(list)


def increment_and_append(key: str, name: str) -> None:
    """
    Increment COUNTS and append to CATEGORIES.

    Args:
        key (str): The key value to use
        name (str): The value to append
    """
    COUNTS[key] += 1
    CATEGORIES[key].append(name)


def process_errors(name: str, errors: dict) -> None:
    """
    Process a set of errors.

    Args:
        name (str): the sample name
        errors (dict): Errors encountered during processing (keys: 'error_type', 'description')
    """
    error_msg = []
    for error in errors:
        error_msg.append(error["description"])
        COUNTS[error["error_type"]] += 1
        FAILED[error["error_type"]].append(name)
    COUNTS["total-excluded"] += 1
    COUNTS["qc-failure"] += 1
    CATEGORIES["failed"].append([name, f"Not processed, reason: {';'.join(error_msg)}"])
    logging.debug(f"\t{name}: Not processed, reason: {'; '.join(error_msg)}")
    return None


def process_sample(df: pd.DataFrame, rank_cutoff: dict) -> list:
    """
    Process the results of a sample.

    Args:
        sample (pd.DataFrame): all the parsed results associated with a sample
        rank_cutoff (dict): the set of cutoffs for each rank

    Returns:
        list: 0: the sample rank, 1: reason for rank
    """
    rank, reason = get_rank(
        rank_cutoff,
        df["qc_final_coverage"].iloc[0],
        df["qc_final_qual_mean"].iloc[0],
        df["qc_final_read_mean"].iloc[0],
        df["assembler_total_contig"].iloc[0],
        df["genome_size"].iloc[0],
        df["qc_final_is_paired"].iloc[0],
    )
    increment_and_append("processed", df["sample"].iloc[0])
    increment_and_append(rank, df["sample"].iloc[0])

    if rank == "exclude":
        COUNTS["total-excluded"] += 1
        FAILED["failed-cutoff"].append(df["sample"].iloc[0])
        CATEGORIES["failed"].append(
            [df["sample"].iloc[0], f"Failed to pass minimum cutoffs, reason: {reason}"]
        )
    else:
        COUNTS["pass"] += 1

    return [rank, reason]


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--bactopia",
    "-b",
    required=True,
    help="Directory where Bactopia results are stored",
)
@click.option(
    "--gold-coverage",
    "-gcov",
    type=int,
    default=100,
    show_default=True,
    help="Minimum amount of coverage required for Gold status",
)
@click.option(
    "--gold-quality",
    "-gqual",
    type=int,
    default=30,
    show_default=True,
    help="Minimum per-read mean quality score required for Gold status",
)
@click.option(
    "--gold-read-length",
    "-glen",
    type=int,
    default=95,
    show_default=True,
    help="Minimum mean read length required for Gold status",
)
@click.option(
    "--gold-contigs",
    "-gcontigs",
    type=int,
    default=100,
    show_default=True,
    help="Maximum contig count required for Gold status",
)
@click.option(
    "--silver-coverage",
    "-scov",
    type=int,
    default=50,
    show_default=True,
    help="Minimum amount of coverage required for Silver status",
)
@click.option(
    "--silver-quality",
    "-squal",
    type=int,
    default=20,
    show_default=True,
    help="Minimum per-read mean quality score required for Silver status",
)
@click.option(
    "--silver-read-length",
    "-slen",
    type=int,
    default=75,
    show_default=True,
    help="Minimum mean read length required for Silver status",
)
@click.option(
    "--silver-contigs",
    "-scontigs",
    type=int,
    default=200,
    show_default=True,
    help="Maximum contig count required for Silver status",
)
@click.option(
    "--min-coverage",
    "-mincov",
    type=int,
    default=20,
    show_default=True,
    help="Minimum amount of coverage required to pass",
)
@click.option(
    "--min-quality",
    "-minqual",
    type=int,
    default=12,
    show_default=True,
    help="Minimum per-read mean quality score required to pass",
)
@click.option(
    "--min-read-length",
    "-minlen",
    type=int,
    default=49,
    show_default=True,
    help="Minimum mean read length required to pass",
)
@click.option(
    "--max-contigs",
    type=int,
    default=500,
    show_default=True,
    help="Maximum contig count required to pass",
)
@click.option(
    "--min-assembled-size",
    type=int,
    help="Minimum assembled genome size",
)
@click.option(
    "--max-assembled-size",
    type=int,
    help="Maximum assembled genome size",
)
@click.option(
    "--outdir",
    "-o",
    type=click.Path(exists=False),
    default="./",
    show_default=True,
    help="Directory to write output",
)
@click.option(
    "--prefix",
    "-p",
    type=str,
    default="bactopia",
    show_default=True,
    help="Prefix to use for output files",
)
@click.option("--force", is_flag=True, help="Overwrite existing reports")
@click.option("--verbose", is_flag=True, help="Increase the verbosity of output")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def summary(
    bactopia,
    gold_coverage,
    gold_quality,
    gold_read_length,
    gold_contigs,
    silver_coverage,
    silver_quality,
    silver_read_length,
    silver_contigs,
    min_coverage,
    min_quality,
    min_read_length,
    max_contigs,
    min_assembled_size,
    max_assembled_size,
    outdir,
    prefix,
    force,
    verbose,
    silent,
):
    """Generate a summary table from the Bactopia results."""
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

    # Set rank cutoffs defaults
    RANK_CUTOFF = {
        "gold": {
            "coverage": gold_coverage,
            "quality": gold_quality,
            "length": gold_read_length,
            "contigs": gold_contigs,
        },
        "silver": {
            "coverage": silver_coverage,
            "quality": silver_quality,
            "length": silver_read_length,
            "contigs": silver_contigs,
        },
        "bronze": {
            "coverage": min_coverage,
            "quality": min_quality,
            "length": min_read_length,
            "contigs": max_contigs,
        },
        "min-assembled-size": min_assembled_size,
        "max-assembled-size": max_assembled_size,
    }

    # Output files
    txt_report = f"{outdir}/{prefix}-report.tsv".replace("//", "/")
    exclusion_report = f"{outdir}/{prefix}-exclude.tsv".replace("//", "/")
    summary_report = f"{outdir}/{prefix}-summary.txt".replace("//", "/")

    if Path(txt_report).exists() and not force:
        logging.error(f"Report already exists! Use --force to overwrite: {txt_report}")
        sys.exit(1)
    else:
        logging.debug(f"Creating output directory: {outdir}")
        Path(outdir).mkdir(parents=True, exist_ok=True)

    processed_samples = {}
    versions = []
    dfs = []
    samples = parse_bactopia_directory(bactopia)
    logging.info(f"Found {len(samples)} samples in {bactopia} to process")
    if samples:
        for sample in samples:
            if sample["is_bactopia"]:
                COUNTS["total"] += 1
                logging.debug(f"Processing {sample['id']} ({sample['path']})")

                # Get the versions files to parse
                versions += parse_versions(
                    [file for file in sample["path"].rglob("versions.yml")],
                    sample["id"],
                )

                # Check if has errors
                errors = parse_errors(sample["path"], sample["id"])
                if errors:
                    # Sample has errors, skip parsing
                    process_errors(sample["id"], errors)
                else:
                    # Get list of files to parse
                    df = pd.DataFrame()
                    for path, parser in get_parsable_files(
                        sample["path"], sample["id"]
                    ).items():
                        if Path(path).exists() or parser == "qc":
                            logging.debug(f"\tParsing {path} ({parser})")
                            if df.empty:
                                df = pd.DataFrame(
                                    [getattr(parsers, parser).parse(path, sample["id"])]
                                )
                            else:
                                df = pd.merge(
                                    df,
                                    pd.DataFrame(
                                        [
                                            getattr(parsers, parser).parse(
                                                path, sample["id"]
                                            )
                                        ]
                                    ),
                                    on="sample",
                                    how="inner",
                                )
                    rank, reason = process_sample(df, RANK_CUTOFF)
                    processed_samples[sample["id"]] = True
                    df["rank"] = rank
                    df["reason"] = reason
                    dfs.append(df)
                    logging.debug(f"\tRank: {rank} ({reason})")

            else:
                logging.debug(
                    f"Skipping {sample['id']} ({sample['path']}), incomplete or not a Bactopia directory"
                )
                increment_and_append("ignore-unknown", sample["id"])
    final_df = pd.concat(dfs)
    for col in EXCLUDE_COLUMNS:
        if col in final_df.columns:
            final_df.drop(col, axis=1, inplace=True)

    # Reorder the columns
    col_order = [
        "sample",
        "rank",
        "reason",
        "genome_size",
        "species",
        "runtype",
        "original_runtype",
        "mlst_scheme",
        "mlst_st",
    ]
    for col in final_df.columns:
        if col not in col_order:
            col_order.append(col)
    final_df = final_df[col_order]

    # Tab-delimited report
    logging.info(f"Writing report: {txt_report}")
    final_df.to_csv(txt_report, sep="\t", index=False)

    # Exclusion report
    logging.info(f"Writing exclusion report: {exclusion_report}")
    cutoff_counts = defaultdict(int)
    with open(exclusion_report, "w") as exclude_fh:
        exclude_fh.write("sample\tstatus\treason\n")
        for name, reason in CATEGORIES["failed"]:
            if name in processed_samples:
                reasons = reason.split(":")[1].split(";")
                cutoffs = []
                for r in reasons:
                    cutoffs.append(r.split("(")[0].strip().title())
                cutoff_counts[";".join(sorted(cutoffs))] += 1
                exclude_fh.write(f"{name}\texclude\t{reason}\n")
            else:
                exclude_fh.write(f"{name}\tqc-fail\t{reason}\n")

    # Screen report
    logging.info(f"Writing summary report: {summary_report}")
    with open(summary_report, "w") as summary_fh:
        summary_fh.write("Bactopia Summary Report\n")
        summary_fh.write(
            textwrap.dedent(
                f"""
            Total Samples: {COUNTS['total']}

            Passed: {COUNTS["pass"]}
                Gold: {COUNTS["gold"]}
                Silver: {COUNTS["silver"]}
                Bronze: {COUNTS["bronze"]}

            Excluded: {COUNTS["total-excluded"]}
                Failed Cutoff: {COUNTS["exclude"]}\n"""
            )
        )
        summary_fh.write(f"{print_cutoffs(cutoff_counts)}\n")
        summary_fh.write(f'    QC Failure: {COUNTS["qc-failure"]}\n')
        summary_fh.write(f"{print_failed(FAILED)}\n")
        summary_fh.write(
            textwrap.dedent(
                f"""
            Reports:
                Full Report (txt): {txt_report}
                Exclusion: {exclusion_report}
                Summary: {summary_report}

            Rank Cutoffs:
                Gold:
                    Coverage >= {RANK_CUTOFF['gold']['coverage']}x
                    Quality >= Q{RANK_CUTOFF['gold']['quality']}
                    Read Length >= {RANK_CUTOFF['gold']['length']}bp
                    Total Contigs < {RANK_CUTOFF['gold']['contigs']}
                Silver:
                    Coverage >= {RANK_CUTOFF['silver']['coverage']}x
                    Quality >= Q{RANK_CUTOFF['silver']['quality']}
                    Read Length >= {RANK_CUTOFF['silver']['length']}bp
                    Total Contigs < {RANK_CUTOFF['silver']['contigs']}
                Bronze:
                    Coverage >= {RANK_CUTOFF['bronze']['coverage']}x
                    Quality >= Q{RANK_CUTOFF['bronze']['quality']}
                    Read Length >= {RANK_CUTOFF['bronze']['length']}bp
                    Total Contigs < {RANK_CUTOFF['bronze']['contigs']}

            Assembly Length Exclusions:
                Minimum: {RANK_CUTOFF['min-assembled-size']}
                Maximum: {RANK_CUTOFF['min-assembled-size']}
        """
            )
        )


def main():
    if len(sys.argv) == 1:
        summary.main(["--help"])
    else:
        summary()


if __name__ == "__main__":
    main()
