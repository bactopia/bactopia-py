def get_rank(
    cutoff: dict,
    coverage: float,
    quality: float,
    length: int,
    contigs: int,
    genome_size: int,
    is_paired: bool,
) -> list:
    """
    Determine the rank (gold, silver, bronze, fail) based on user cutoffs.

    Args:
        cutoff (dict): Cutoffs set by users to determine rank
        coverage (float): Estimated coverage of the sample
        quality (float): Per-read average quality
        length (int): Median length of reads
        contigs (int): Total number of contigs
        genome_size (int): Genome size of sample used in analysis
        is_paired (bool): Sample used paired-end reads

    Returns:
        list: the rank and reason for the ranking
    """
    rank = None
    reason = []
    coverage = float(f"{float(coverage):.2f}")
    quality = float(f"{float(quality):.2f}")
    length = round(float(f"{float(length):.2f}"))
    contigs = int(contigs)
    genome_size = int(genome_size)
    gold = cutoff["gold"]
    silver = cutoff["silver"]
    bronze = cutoff["bronze"]

    if (
        coverage >= gold["coverage"]
        and quality >= gold["quality"]
        and length >= gold["length"]
        and contigs <= gold["contigs"]
        and is_paired
    ):
        reason.append("passed all cutoffs")
        rank = "gold"
    elif (
        coverage >= silver["coverage"]
        and quality >= silver["quality"]
        and length >= silver["length"]
        and contigs <= silver["contigs"]
        and is_paired
    ):
        if coverage < gold["coverage"]:
            reason.append(
                f"Low coverage ({coverage:.2f}x, expect >= {gold['coverage']}x)"
            )
        if quality < gold["quality"]:
            reason.append(
                f"Poor read quality (Q{quality:.2f}, expect >= Q{gold['quality']})"
            )
        if length < gold["length"]:
            reason.append(
                f"Short read length ({length}bp, expect >= {gold['length']} bp)"
            )
        if contigs > gold["contigs"]:
            reason.append(f"Too many contigs ({contigs}, expect <= {gold['contigs']})")
        rank = "silver"
    elif (
        coverage >= bronze["coverage"]
        and quality >= bronze["quality"]
        and length >= bronze["length"]
        and contigs <= bronze["contigs"]
    ):
        if coverage < silver["coverage"]:
            reason.append(
                f"Low coverage ({coverage:.2f}x, expect >= {silver['coverage']}x)"
            )
        if quality < silver["quality"]:
            reason.append(
                f"Poor read quality (Q{quality:.2f}, expect >= Q{silver['quality']})"
            )
        if length < silver["length"]:
            reason.append(
                f"Short read length ({length}bp, expect >= {silver['length']} bp)"
            )
        if contigs > silver["contigs"]:
            reason.append(
                f"Too many contigs ({contigs}, expect <= {silver['contigs']})"
            )
        if not is_paired:
            reason.append("Single-end reads")
        rank = "bronze"

    if not rank:
        rank = "exclude"

    if coverage < bronze["coverage"]:
        reason.append(
            f"Low coverage ({coverage:.2f}x, expect >= {bronze['coverage']}x)"
        )
    if quality < bronze["quality"]:
        reason.append(
            f"Poor read quality (Q{quality:.2f}, expect >= Q{bronze['quality']})"
        )
    if length < bronze["length"]:
        reason.append(
            f"Short read length ({length:.2f}bp, expect >= {bronze['length']} bp)"
        )
    if contigs > bronze["contigs"]:
        reason.append(f"Too many contigs ({contigs}, expect <= {bronze['contigs']})")

    if cutoff["min-assembled-size"]:
        if genome_size < cutoff["min-assembled-size"]:
            reason.append(
                f"Assembled size is too small ({genome_size} bp, expect <= {cutoff['min-assembled-size']})"
            )

    if cutoff["max-assembled-size"]:
        if genome_size < cutoff["max-assembled-size"]:
            reason.append(
                f"Assembled size is too large ({genome_size} bp, expect <= {cutoff['max-assembled-size']})"
            )

    reason = ";".join(sorted(reason))
    return [rank, reason]


def print_failed(failed: list, spaces: int = 8) -> str:
    """
    Format the strings of samples that failed

    Args:
        failed (list): A list of samples that failed for a particular reason
        spaces (int, optional): Total number of spaces to indent. Defaults to 8.

    Returns:
        str: The set of formatted strings
    """
    lines = []
    for key, val in sorted(failed.items()):
        if key != "failed-cutoff":
            lines.append(f'{spaces * " "}{key.replace("-", " ").title()}: {len(val)}')
    return "\n".join(lines) if lines else ""


def print_cutoffs(cutoffs: list, spaces: int = 8) -> str:
    """
    Format strings for samples that failed a cutoff.

    Args:
        cutoffs (list): A list of samples that failed for a cutoff
        spaces (int, optional): Total number of spaces to indent. Defaults to 8.

    Returns:
        str:  The set of formatted strings
    """
    lines = []
    for key, val in sorted(cutoffs.items()):
        lines.append(f'{spaces * " "}{key}: {val}')
    return "\n".join(lines) if lines else ""
