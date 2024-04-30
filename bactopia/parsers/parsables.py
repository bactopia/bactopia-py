"""
A list of files that can be parsed by Bactopia
"""
import logging
from pathlib import Path

EXCLUDE_COLUMNS = [
    "qc_final_per_base_quality",
    "qc_final_r1_per_base_quality",
    "qc_final_r2_per_base_quality",
    "qc_final_read_lengths",
    "qc_final_r1_read_lengths",
    "qc_final_r2_read_lengths",
    "qc_original_is_paired",
    "qc_original_per_base_quality",
    "qc_original_r1_per_base_quality",
    "qc_original_r2_per_base_quality",
    "qc_original_read_lengths",
    "qc_original_r1_read_lengths",
    "qc_original_r2_read_lengths",
    "amrfinderplus_hits",
]


def get_parsable_files(path: str, name: str) -> list:
    parsable_files = {
        # main
        # assembler
        f"{path}/main/assembler/{name}.tsv": "assembler",
        # gather
        f"{path}/main/gather/{name}-meta.tsv": "gather",
        # sketcher
        f"{path}/main/sketcher/{name}-mash-refseq88-k21.txt": "sketcher",
        f"{path}/main/sketcher/{name}-sourmash-gtdb-rs207-k31.txt": "sketcher",
        # bactopia-tools
        # amrfinderplus
        f"{path}/tools/amrfinderplus/{name}.tsv": "amrfinderplus",
        # mlst
        f"{path}/tools/mlst/{name}.tsv": "mlst",
    }

    is_complete = True
    missing_files = []
    for output_file, output_type in parsable_files.items():
        if not Path(output_file).exists():
            is_complete = False
            missing_files.append(output_file)

    # Check annotation files seperately, since Prokka or Bakta can be used
    if Path(f"{path}/main/annotator/bakta/{name}.txt").exists():
        logging.debug(
            f"Found Bakta annotation file: {path}/main/annotator/bakta/{name}.txt"
        )
        parsable_files[f"{path}/main/annotator/bakta/{name}.txt"] = "annotator"
    elif Path(f"{path}/main/annotator/prokka/{name}.txt").exists():
        logging.debug(
            f"Found Prokka annotation file: {path}/main/annotator/prokka/{name}.txt"
        )
        parsable_files[f"{path}/main/annotator/prokka/{name}.txt"] = "annotator"
    else:
        is_complete = False
        missing_files.append(f"{path}/main/annotator/prokka/{name}.txt")
        missing_files.append(f"{path}/main/annotator/bakta/{name}.txt")

    logging.debug(f"Missing Files: {missing_files}")
    logging.debug(f"Is Complete: {is_complete}")

    if is_complete:
        parsable_files[f"{path}/main/qc/summary/{name}-original.json"] = "qc"
        parsable_files[f"{path}/main/qc/summary/{name}-final.json"] = "qc"
        return [is_complete, parsable_files]
    else:
        return [is_complete, missing_files]
