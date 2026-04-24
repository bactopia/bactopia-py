"""Template rendering library for scaffolding Bactopia components."""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES_DIR = Path(__file__).parent / "templates" / "scaffold"

ICON_MAP = {
    "string": "fas fa-font",
    "integer": "fas fa-hashtag",
    "number": "fas fa-percentage",
    "boolean": "fas fa-toggle-on",
}

INPUT_TYPE_MAP = {
    "assembly": {
        "channel": "assembly",
        "ext": "['fna']",
        "record_fields": [
            {
                "name": "fna",
                "type": "Path",
                "description": "Assembled contigs in FASTA format",
            }
        ],
    },
    "reads": {
        "channel": "reads",
        "ext": "['fastq']",
        "record_fields": [
            {
                "name": "r1",
                "type": "Path?",
                "description": "Forward reads in FASTQ format",
            },
            {
                "name": "r2",
                "type": "Path?",
                "description": "Reverse reads in FASTQ format",
            },
            {
                "name": "se",
                "type": "Path?",
                "description": "Single-end reads in FASTQ format",
            },
            {
                "name": "lr",
                "type": "Path?",
                "description": "Long reads in FASTQ format",
            },
        ],
    },
    "assembly_reads": {
        "channel": "assembly_reads",
        "ext": "['fna', 'fastq']",
        "record_fields": [
            {
                "name": "fna",
                "type": "Path",
                "description": "Assembled contigs in FASTA format",
            },
            {
                "name": "r1",
                "type": "Path?",
                "description": "Forward reads in FASTQ format",
            },
            {
                "name": "r2",
                "type": "Path?",
                "description": "Reverse reads in FASTQ format",
            },
            {
                "name": "se",
                "type": "Path?",
                "description": "Single-end reads in FASTQ format",
            },
            {
                "name": "lr",
                "type": "Path?",
                "description": "Long reads in FASTQ format",
            },
        ],
    },
    "proteins": {
        "channel": "proteins",
        "ext": "['faa']",
        "record_fields": [
            {
                "name": "faa",
                "type": "Path",
                "description": "Protein sequences in FASTA format",
            }
        ],
    },
    "gff": {
        "channel": "gff",
        "ext": "['gff']",
        "record_fields": [
            {
                "name": "gff",
                "type": "Path",
                "description": "Genome annotation in GFF3 format",
            }
        ],
    },
    "genbank": {
        "channel": "gbff",
        "ext": "['gbk']",
        "record_fields": [
            {
                "name": "gbff",
                "type": "Path",
                "description": "Genome annotation in GenBank format",
            }
        ],
    },
}

REQUIRED_FIELDS = [
    "tool",
    "display_name",
    "description",
    "process_name",
    "package",
    "version",
    "build",
    "input_type",
    "resource_label",
    "version_command",
    "citation_key",
    "keywords",
    "outputs",
    "parameters",
]


def get_template_env() -> Environment:
    """Create Jinja2 environment for scaffold templates."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
    )


def validate_config(config: dict, tier: str = "tool") -> list[str]:
    """Validate a scaffold design config.

    Args:
        config: The design configuration dict.
        tier: One of "module", "subworkflow", or "tool".

    Returns:
        List of error messages (empty if valid).
    """
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in config:
            errors.append(f"Missing required field: {field}")

    if config.get("input_type") and config["input_type"] not in INPUT_TYPE_MAP:
        errors.append(
            f"Invalid input_type: {config['input_type']}. "
            f"Must be one of: {', '.join(INPUT_TYPE_MAP)}"
        )

    agg = config.get("aggregation", {})
    if agg and agg.get("strategy") not in (
        "csvtk_concat",
        "dedicated_summary",
        "none",
        None,
    ):
        errors.append(
            f"Invalid aggregation strategy: {agg.get('strategy')}. "
            f"Must be one of: csvtk_concat, dedicated_summary, none"
        )

    if not config.get("outputs"):
        errors.append("At least one output must be defined")

    return errors


def _enrich_config(config: dict) -> dict:
    """Add derived fields to a config for template rendering."""
    enriched = dict(config)

    input_info = INPUT_TYPE_MAP.get(
        config.get("input_type", "assembly"), INPUT_TYPE_MAP["assembly"]
    )
    enriched["input_fields"] = input_info["record_fields"]
    enriched["channel_name"] = input_info["channel"]
    enriched["workflow_ext"] = input_info["ext"]

    enriched["icon_map"] = ICON_MAP
    enriched["layout"] = config.get("layout", "flat")
    enriched["has_database"] = config.get("has_database", False)
    enriched["handles_gz"] = config.get("handles_gz", False)
    enriched["home_url"] = config.get("home_url", "")

    agg = config.get("aggregation", {"strategy": "none"})
    enriched["aggregation"] = agg
    enriched["has_csvtk"] = agg.get("strategy") == "csvtk_concat"
    enriched["has_summary"] = agg.get("strategy") == "dedicated_summary"
    enriched["has_aggregation"] = agg.get("strategy") in (
        "csvtk_concat",
        "dedicated_summary",
    )

    # Primary output field (for downstream named access)
    if config.get("outputs"):
        enriched["primary_output"] = config["outputs"][0]
    else:
        enriched["primary_output"] = {"name": "results_file", "extension": "txt"}

    # Test data defaults
    enriched.setdefault("test_species", "portiera")
    enriched.setdefault("test_sample_id", "GCF_000292685")
    enriched.setdefault(
        "test_data_path",
        "species/portiera/compressed/GCF_000292685/main/assembler/GCF_000292685.fna.gz",
    )
    enriched.setdefault(
        "test_uncompressed_path",
        "species/portiera/uncompressed/GCF_000292685/main/assembler/GCF_000292685.fna",
    )
    enriched.setdefault("test_dataset", "")
    enriched.setdefault("test_dataset2", "")
    enriched.setdefault("test_dataset3", "")

    # Database-specific test settings
    if enriched["has_database"]:
        db_info = config.get("database", {})
        enriched["db_test_path"] = db_info.get("test_path", "")
        enriched["db_param_name"] = db_info.get("param_name", f"{config['tool']}_db")
    else:
        enriched["db_test_path"] = ""
        enriched["db_param_name"] = ""

    return enriched


def render_module_files(
    config: dict, bactopia_path: Path | None = None
) -> dict[str, str]:
    """Render all module files from a design config.

    Args:
        config: Enriched design configuration.
        bactopia_path: Optional repo root (unused in rendering, but available for path resolution).

    Returns:
        Dict mapping relative file paths to rendered content.
    """
    env = get_template_env()
    ctx = _enrich_config(config)
    tool = config["tool"]
    base = f"modules/{tool}"

    files = {
        f"{base}/main.nf": env.get_template("module/main.nf.j2").render(**ctx),
        f"{base}/module.config": env.get_template("module/module.config.j2").render(
            **ctx
        ),
        f"{base}/schema.json": env.get_template("module/schema.json.j2").render(**ctx),
        f"{base}/tests/main.nf.test": env.get_template(
            "module/tests/main.nf.test.j2"
        ).render(**ctx),
        f"{base}/tests/nextflow.config": env.get_template(
            "module/tests/nextflow.config.j2"
        ).render(**ctx),
        f"{base}/tests/nf-test.config": env.get_template(
            "module/tests/nf-test.config.j2"
        ).render(**ctx),
    }
    return files


def render_subworkflow_files(
    config: dict, bactopia_path: Path | None = None
) -> dict[str, str]:
    """Render all subworkflow files from a design config."""
    env = get_template_env()
    ctx = _enrich_config(config)
    tool = config["tool"]
    base = f"subworkflows/{tool}"

    files = {
        f"{base}/main.nf": env.get_template("subworkflow/main.nf.j2").render(**ctx),
        f"{base}/tests/main.nf.test": env.get_template(
            "subworkflow/tests/main.nf.test.j2"
        ).render(**ctx),
        f"{base}/tests/nextflow.config": env.get_template(
            "subworkflow/tests/nextflow.config.j2"
        ).render(**ctx),
        f"{base}/tests/nf-test.config": env.get_template(
            "subworkflow/tests/nf-test.config.j2"
        ).render(**ctx),
        f"{base}/tests/.nftignore": env.get_template(
            "subworkflow/tests/nftignore.j2"
        ).render(**ctx),
    }
    return files


def render_workflow_files(
    config: dict, bactopia_path: Path | None = None
) -> dict[str, str]:
    """Render all workflow files from a design config."""
    env = get_template_env()
    ctx = _enrich_config(config)
    tool = config["tool"]
    base = f"workflows/bactopia-tools/{tool}"

    files = {
        f"{base}/main.nf": env.get_template("workflow/main.nf.j2").render(**ctx),
        f"{base}/nextflow.config": env.get_template(
            "workflow/nextflow.config.j2"
        ).render(**ctx),
        f"{base}/tests/main.nf.test": env.get_template(
            "workflow/tests/main.nf.test.j2"
        ).render(**ctx),
        f"{base}/tests/nf-test.config": env.get_template(
            "workflow/tests/nf-test.config.j2"
        ).render(**ctx),
        f"{base}/tests/.nftignore": env.get_template(
            "workflow/tests/nftignore.j2"
        ).render(**ctx),
    }
    return files


def render_all_files(config: dict, bactopia_path: Path | None = None) -> dict[str, str]:
    """Render all files for a complete bactopia-tool (all three tiers)."""
    files = {}
    files.update(render_module_files(config, bactopia_path))
    files.update(render_subworkflow_files(config, bactopia_path))
    files.update(render_workflow_files(config, bactopia_path))
    return files


def write_files(
    files: dict[str, str],
    bactopia_path: Path,
    dry_run: bool = False,
) -> list[str]:
    """Write rendered files to disk.

    Args:
        files: Dict mapping relative paths to content.
        bactopia_path: Root of the Bactopia repository.
        dry_run: If True, don't actually write files.

    Returns:
        List of created file paths (relative).
    """
    created = []
    for rel_path, content in sorted(files.items()):
        full_path = bactopia_path / rel_path
        if dry_run:
            logging.info(f"[dry-run] Would create: {rel_path}")
        else:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            logging.info(f"Created: {rel_path}")
        created.append(rel_path)
    return created


FIELD_PATTERNS: dict[str, str] = {
    "assembly": r'fna:\s*file\("([^"]+)"\)',
    "reads": r'r1:\s*file\("([^"]+)"\)',
    "assembly_reads": r'fna:\s*file\("([^"]+)"\)',
    "proteins": r'faa:\s*file\("([^"]+)"\)',
    "gff": r'gff:\s*file\("([^"]+)"\)',
    "genbank": r'gbff:\s*file\("([^"]+)"\)',
}

SPECIES_PATH_RE = re.compile(
    r"species/([^/]+)/(compressed|uncompressed)/([^/]+)/main/([^/]+)/(.+)"
)

DATASET_RE = re.compile(r'file\("\$\{params\.test_data_dir\}/(datasets/[^"]+)"\)')


def discover_test_data(bactopia_path: Path, input_type: str) -> list[dict]:
    """Scan existing module tests to discover valid test data paths.

    Args:
        bactopia_path: Root of the Bactopia repository.
        input_type: One of the INPUT_TYPE_MAP keys (assembly, reads, etc.).

    Returns:
        List of dicts with test data options, each containing:
        species, accession, test_species, test_sample_id,
        test_data_path, test_uncompressed_path, modules_using,
        has_compressed, has_uncompressed, datasets.
    """
    field_pattern = FIELD_PATTERNS.get(input_type)
    if not field_pattern:
        logging.warning(f"No field pattern for input_type: {input_type}")
        return []

    field_re = re.compile(field_pattern)
    modules_dir = bactopia_path / "modules"

    # species/accession -> collected info
    entries: dict[tuple[str, str], dict] = {}
    # species/accession -> set of module names using it
    usage: dict[tuple[str, str], set[str]] = defaultdict(set)
    # species/accession -> set of dataset paths found alongside
    datasets_found: dict[tuple[str, str], set[str]] = defaultdict(set)

    for test_file in sorted(modules_dir.glob("*/tests/main.nf.test")):
        module_name = test_file.parent.parent.name
        content = test_file.read_text()

        for match in field_re.finditer(content):
            raw_path = match.group(1)
            # Strip the ${params.test_data_dir}/ prefix
            clean = raw_path.replace("${params.test_data_dir}/", "")

            m = SPECIES_PATH_RE.match(clean)
            if not m:
                continue

            species, fmt, accession, _stage, _filename = m.groups()
            key = (species, accession)
            usage[key].add(module_name)

            if key not in entries:
                entries[key] = {
                    "species": species,
                    "accession": accession,
                    "has_compressed": False,
                    "has_uncompressed": False,
                }

            if fmt == "compressed":
                entries[key]["has_compressed"] = True
            elif fmt == "uncompressed":
                entries[key]["has_uncompressed"] = True

        # Also scan for dataset paths in the same file
        for ds_match in DATASET_RE.finditer(content):
            ds_path = ds_match.group(1)
            # Associate with the first species/accession found in this file
            for fld_match in field_re.finditer(content):
                fld_raw = fld_match.group(1).replace("${params.test_data_dir}/", "")
                fld_m = SPECIES_PATH_RE.match(fld_raw)
                if fld_m:
                    ds_key = (fld_m.group(1), fld_m.group(3))
                    datasets_found[ds_key].add(ds_path)
                    break

    results = []
    for key, info in sorted(entries.items()):
        species, accession = key
        # Determine file extension based on input type
        ext_map = {
            "assembly": ("fna.gz", "fna"),
            "assembly_reads": ("fna.gz", "fna"),
            "reads": ("fastq.gz", "fastq.gz"),
            "proteins": ("faa.gz", "faa"),
            "gff": ("gff.gz", "gff"),
            "genbank": ("gbk.gz", "gbk"),
        }
        gz_ext, plain_ext = ext_map.get(input_type, ("fna.gz", "fna"))
        # Determine the stage directory from the input type
        stage_map = {
            "assembly": "assembler",
            "assembly_reads": "assembler",
            "reads": "qc",
            "proteins": "annotator/prokka",
            "gff": "annotator/prokka",
            "genbank": "annotator/prokka",
        }
        stage = stage_map.get(input_type, "assembler")

        result = {
            "species": species,
            "accession": accession,
            "modules_using": sorted(usage[key]),
            "test_species": species,
            "test_sample_id": accession,
            "test_data_path": f"species/{species}/compressed/{accession}/main/{stage}/{accession}.{gz_ext}",
            "test_uncompressed_path": f"species/{species}/uncompressed/{accession}/main/{stage}/{accession}.{plain_ext}",
            "has_compressed": info["has_compressed"],
            "has_uncompressed": info["has_uncompressed"],
            "datasets": sorted(datasets_found.get(key, [])),
        }
        results.append(result)

    return results
