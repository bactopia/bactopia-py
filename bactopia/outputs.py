"""Scan nf-test work directories and compare actual outputs against declared outputs."""

import json
import logging
from fnmatch import fnmatch
from pathlib import Path

logger = logging.getLogger(__name__)

# Files produced by Nextflow itself, not by the tool
NEXTFLOW_INTERNALS = frozenset(
    [
        ".command.begin",
        ".command.err",
        ".command.log",
        ".command.out",
        ".command.run",
        ".command.sh",
        ".command.trace",
        ".exitcode",
    ]
)

# Patterns always ignored (applied before per-module .outputs-ignore)
DEFAULT_IGNORE_PATTERNS = [
    "staging/**",
]


def scan_work_dir(work_dir: Path) -> list[str]:
    """Find all actual output files in a Nextflow work directory.

    Inputs are identified as symlinks (Nextflow stages inputs via symlinks).
    Nextflow internal files (.command.*, .exitcode) are excluded.

    Args:
        work_dir: Path to a Nextflow work directory (e.g., work/53/0afa8f...).

    Returns:
        Sorted list of relative paths (strings) for all real output files.
    """
    outputs = []
    for item in work_dir.rglob("*"):
        if item.is_symlink():
            continue
        if not item.is_file():
            continue
        if item.name in NEXTFLOW_INTERNALS:
            continue
        outputs.append(str(item.relative_to(work_dir)))
    return sorted(outputs)


def parse_declared_outputs(meta_dir: Path) -> set[str]:
    """Parse output_*.json files to get all declared output file paths.

    nf-test captures the resolved output record in output_0.json (and
    output_1.json for subworkflows with multiple emit channels). Each record
    contains results, logs, versions, and nf_logs fields with absolute paths.
    Some entries may be directories rather than files.

    Args:
        meta_dir: Path to the nf-test meta directory containing output_*.json.

    Returns:
        Set of absolute file paths that are declared as outputs.
    """
    declared = set()
    declared_dirs = set()

    for output_json in sorted(meta_dir.glob("output_*.json")):
        with open(output_json) as f:
            data = json.load(f)

        for _channel, records in data.items():
            for rec in records:
                for field_name, field_val in rec.items():
                    if field_name == "meta":
                        continue
                    _collect_paths(field_val, declared, declared_dirs)

    # Expand directory entries: all files under a declared directory are declared
    for dir_path in declared_dirs:
        dp = Path(dir_path)
        if dp.exists():
            for item in dp.rglob("*"):
                if item.is_file() and not item.is_symlink():
                    declared.add(str(item))

    return declared


def _collect_paths(value, declared: set, declared_dirs: set):
    """Recursively collect file/directory paths from an output_*.json field value."""
    if isinstance(value, str):
        p = Path(value)
        if p.exists():
            if p.is_dir():
                declared_dirs.add(value)
            else:
                declared.add(value)
    elif isinstance(value, list):
        for item in value:
            _collect_paths(item, declared, declared_dirs)


def load_ignore_patterns(test_dir: Path) -> list[str]:
    """Load glob patterns from a .outputs-ignore file.

    The file format is one pattern per line. Lines starting with # are
    comments. Blank lines are ignored. Patterns are matched against file
    paths relative to the work directory using fnmatch.

    Args:
        test_dir: Path to the module's tests/ directory.

    Returns:
        List of glob pattern strings. Empty list if no ignore file exists.
    """
    ignore_file = test_dir / ".outputs-ignore"
    if not ignore_file.exists():
        return []

    patterns = []
    for line in ignore_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def filter_ignored(
    files: list[str], patterns: list[str]
) -> tuple[list[str], list[str]]:
    """Partition files into kept and ignored based on glob patterns.

    Args:
        files: List of relative file paths to check.
        patterns: Glob patterns from .outputs-ignore.

    Returns:
        Tuple of (kept files, ignored files).
    """
    if not patterns:
        return files, []

    kept = []
    ignored = []
    for f in files:
        if any(fnmatch(f, pat) for pat in patterns):
            ignored.append(f)
        else:
            kept.append(f)
    return kept, ignored


def compare_outputs(work_dir: Path, meta_dir: Path, ignore_patterns: list[str]) -> dict:
    """Compare actual work directory files against declared outputs.

    Args:
        work_dir: Path to a Nextflow work directory.
        meta_dir: Path to the nf-test meta directory with output_*.json.
        ignore_patterns: Glob patterns for files to ignore.

    Returns:
        Dict with keys:
            actual_outputs: all non-infrastructure files found
            declared_outputs: files accounted for by output record
            ignored_outputs: files matched by .outputs-ignore
            undeclared_outputs: files not declared and not ignored
    """
    actual = scan_work_dir(work_dir)
    declared_abs = parse_declared_outputs(meta_dir)

    # Convert declared absolute paths to relative-to-work-dir
    declared_rel = set()
    for abs_path in declared_abs:
        try:
            declared_rel.add(str(Path(abs_path).relative_to(work_dir)))
        except ValueError:
            continue

    # Find files not covered by declared outputs
    undeclared = [f for f in actual if f not in declared_rel]

    # Apply ignore patterns
    undeclared, ignored = filter_ignored(undeclared, ignore_patterns)

    # Declared files that were found
    declared_found = [f for f in actual if f in declared_rel]

    return {
        "actual_outputs": actual,
        "declared_outputs": declared_found,
        "ignored_outputs": ignored,
        "undeclared_outputs": undeclared,
    }


def _parse_trace_csv(meta_dir: Path) -> dict[str, str]:
    """Parse trace.csv to map work directory hash prefixes to process names.

    Args:
        meta_dir: Path to the nf-test meta directory.

    Returns:
        Dict mapping hash prefix (e.g., "53/0afa8f") to process name.
    """
    trace_file = meta_dir / "trace.csv"
    if not trace_file.exists():
        return {}

    mapping = {}
    lines = trace_file.read_text().splitlines()
    if not lines:
        return {}

    # Header line: find hash and name column indices
    headers = lines[0].split("\t")
    try:
        hash_idx = headers.index("hash")
        name_idx = headers.index("name")
    except ValueError:
        return {}

    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) > max(hash_idx, name_idx):
            mapping[cols[hash_idx]] = cols[name_idx]

    return mapping


def scan_test_outputs(test_dir: Path) -> dict:
    """Scan all nf-test work directories for a component and compare outputs.

    Args:
        test_dir: Path to the component's tests/ directory (contains .nf-test/).

    Returns:
        Dict with keys:
            has_nftest: whether .nf-test/tests/ exists
            undeclared_outputs: deduplicated list of undeclared file paths
            details: list of per-test-case dicts with process_name, work_dir,
                     and comparison results
    """
    nftest_dir = test_dir / ".nf-test" / "tests"
    if not nftest_dir.exists():
        return {"has_nftest": False, "undeclared_outputs": [], "details": []}

    ignore_patterns = DEFAULT_IGNORE_PATTERNS + load_ignore_patterns(test_dir)
    all_undeclared = set()
    details = []

    for test_hash_dir in sorted(nftest_dir.iterdir()):
        if not test_hash_dir.is_dir():
            continue

        meta_dir = test_hash_dir / "meta"
        work_dir = test_hash_dir / "work"
        if not meta_dir.exists() or not work_dir.exists():
            continue

        # Map work dir hashes to process names
        trace_map = _parse_trace_csv(meta_dir)

        # Find all work directories (work/{xx}/{hash}/)
        for d1 in sorted(work_dir.iterdir()):
            if not d1.is_dir():
                continue
            for d2 in sorted(d1.iterdir()):
                if not d2.is_dir():
                    continue

                # Determine process name from trace.csv
                hash_prefix = f"{d1.name}/{d2.name[:6]}"
                process_name = trace_map.get(hash_prefix, "unknown")

                result = compare_outputs(d2, meta_dir, ignore_patterns)
                all_undeclared.update(result["undeclared_outputs"])

                details.append(
                    {
                        "process_name": process_name,
                        "work_dir": str(d2),
                        "actual_outputs": result["actual_outputs"],
                        "declared_outputs": result["declared_outputs"],
                        "ignored_outputs": result["ignored_outputs"],
                        "undeclared_outputs": result["undeclared_outputs"],
                    }
                )

    return {
        "has_nftest": True,
        "undeclared_outputs": sorted(all_undeclared),
        "details": details,
    }
