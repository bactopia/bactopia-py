"""
Parsers for QC (FASTQ) related results.
"""
from pathlib import Path

from bactopia.parsers.generic import parse_json


def parse(path: str, name: str) -> dict:
    """
    Check input file is an accepted file, then select the appropriate parsing method.

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Raises:
        ValueError: summary results to not have a matching origin (e.g. original vs final FASTQ)

    Returns:
        dict: parsed results
    """
    r1 = None
    r2 = None

    if Path(path).exists():
        # Single end
        r1 = Path(path)
    else:
        r1_path = None
        r2_path = None
        if "original" in path:
            r1_path = path.replace("-original.json", "_R1-original.json")
            r2_path = path.replace("-original.json", "_R2-original.json")
        else:
            r1_path = path.replace("-final.json", "_R1-final.json")
            r2_path = path.replace("-final.json", "_R2-final.json")

        if Path(r1_path).exists() and Path(r2_path).exists():
            r1 = Path(r1_path)
            r2 = Path(r2_path)

    final_results = {"sample": name}
    if r1:
        which_step = "original" if "original" in str(r1) else "final"
        final_results[f"qc_{which_step}_is_paired"] = True if r2 else False
        if r1 and r2:
            # Paired End
            results = _merge_qc_stats(parse_json(r1), parse_json(r2))
        elif r1:
            # Single End
            results = parse_json(r1)

        for key, val in results.items():
            if key != "sample":
                if key == "qc_stats":
                    for qc_key, qc_val in val.items():
                        final_results[f"qc_{which_step}_{qc_key}"] = qc_val
                else:
                    # Add prefix to key name
                    final_results[f"qc_{which_step}_{key}"] = val
            else:
                final_results[key] = val
    return final_results


def _merge_qc_stats(r1: dict, r2: dict) -> dict:
    """
    Merge appropriate metrics (e.g. coverage) for R1 and R2 FASTQs.

    Args:
        r1 (dict): parsed metrics associated with R1 FASTQ
        r2 (dict): parsed metrics associated with R2 FASTQ

    Returns:
        dict: the merged FASTQ metrics
    """
    from statistics import mean

    merged = {
        "qc_stats": {},
        "r1_per_base_quality": r1["per_base_quality"],
        "r2_per_base_quality": r2["per_base_quality"],
        "r1_read_lengths": r1["read_lengths"],
        "r2_read_lengths": r2["read_lengths"],
    }
    for key in r1["qc_stats"]:
        if key in ["total_bp", "coverage", "read_total"]:
            merged["qc_stats"][key] = (
                r1["qc_stats"][key] + r2["qc_stats"][key] if r2 else r1["qc_stats"][key]
            )
        else:
            val = (
                mean([r1["qc_stats"][key], r2["qc_stats"][key]])
                if r2
                else r1["qc_stats"][key]
            )
            merged["qc_stats"][key] = f"{val:.4f}" if isinstance(val, float) else val

    return merged
