"""
A list of files that can be parsed by Bactopia
"""
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
    "amrfinderplus_genes_hits",
    "amrfinderplus_proteins_hits",
]


def get_parsable_files(path: str, name: str) -> list:
    parsable_files = {
        # main
        # annotator
        f"{path}/main/annotator/prokka/{name}.txt": "annotator",
        # assembler
        f"{path}/main/assembler/{name}.tsv": "assembler",
        # gather
        f"{path}/main/gather/{name}-meta.tsv": "gather",
        # qc
        f"{path}/main/qc/summary/{name}-final.json": "qc",
        f"{path}/main/qc/summary/{name}-original.json": "qc",
        # sketcher
        f"{path}/main/sketcher/summary/{name}-mash-refseq88-k21.txt": "sketcher",
        f"{path}/main/sketcher/summary/{name}-sourmash-gtdb-rs207-k31.txt": "sketcher",
        # bactopia-tools
        # amrfinderplus
        f"{path}/tools/amrfinderplus/{name}-genes.tsv": "amrfinderplus",
        f"{path}/tools/amrfinderplus/{name}-proteins.tsv": "amrfinderplus",
        # mlst
        f"{path}/tools/mlst/{name}.tsv": "mlst",
    }

    is_complete = True
    missing_files = []
    for output_file, output_type in parsable_files.items():
        if not Path(output_file).exists():
            is_complete = False
            missing_files.append(output_file)

    if is_complete:
        return [is_complete, parsable_files]
    else:
        return [is_complete, missing_files]
