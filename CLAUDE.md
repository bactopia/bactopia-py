# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

bactopia-py is a Python CLI companion package for [Bactopia](https://bactopia.github.io/), a flexible Nextflow pipeline for complete analysis of bacterial genomes. It provides 27 command-line tools: 19 user-facing commands for input preparation, public data search, environment building, dataset management, result summarization, pipeline linting, testing, and database integration; plus 8 pipeline utility scripts called from Nextflow module shell blocks.

- **Author:** Robert A. Petit III
- **License:** MIT
- **Python:** 3.10+

## Development Commands

### Environment Setup

The conda environment provides all dependencies: system tools (blast, pigz, wget), Python library deps, and dev/test tools. Poetry installs directly into the conda env (virtualenvs disabled via `poetry.toml`).

```bash
conda env create -f environment.yml -n bactopia-py-dev
conda run -n bactopia-py-dev just install
```

### Running Commands

Use `conda run -n bactopia-py-dev` to run commands in the conda environment:

```bash
conda run -n bactopia-py-dev bactopia-download --version
conda run -n bactopia-py-dev bactopia-prepare --help
conda run -n bactopia-py-dev just fmt
conda run -n bactopia-py-dev just lint
```

### Common Tasks

```bash
conda run -n bactopia-py-dev just install       # poetry install --no-interaction
conda run -n bactopia-py-dev just fmt           # ruff format + ruff check --fix
conda run -n bactopia-py-dev just check-fmt     # check formatting without changes
conda run -n bactopia-py-dev just lint          # ruff check
conda run -n bactopia-py-dev just check         # check-fmt + lint
conda run -n bactopia-py-dev just build         # poetry build
conda run -n bactopia-py-dev just test          # pytest (accepts extra args)
conda run -n bactopia-py-dev just test-cov      # pytest with coverage report
conda run -n bactopia-py-dev just test-unit     # pytest -m "not integration"
```

Tests use pytest with optional `integration` marker for tests requiring external data. Pre-commit hooks are configured (`.pre-commit-config.yaml`).

## Project Structure

```text
bactopia/
  cli/                  # CLI commands (one module per command)
    atb/                # AllTheBacteria commands (atb_formatter, atb_downloader)
    helpers/            # Utility commands (merge_schemas)
    pipeline/           # Pipeline utility scripts called from Nextflow shell blocks
      check_fastqs.py         # Verify FASTQs meet requirements
      check_assembly_accession.py  # Verify NCBI Assembly accession
      cleanup_coverage.py     # Reduce coverage file redundancy
      mask_consensus.py       # Snippy consensus masking with coverage
      kraken_bracken_summary.py    # Update Bracken with unclassified counts
      scrubber_summary.py     # Human read scrubbing report
teton_prepare.py        # Prepare sample sheets for Teton
      bracken_to_excel.py     # Export Bracken abundances to Excel
    pubmlst/            # PubMLST database commands (setup, build)
    catalog.py          # Generate component catalog.json
    citations.py        # Print tool citations
    datasets.py         # Download optional datasets
    download.py         # Build Conda/Docker/Singularity environments
    jsonify.py          # JSON conversion utility
    lint.py             # Lint pipeline components
    prepare.py          # Create file-of-filenames (FOFN) for samples
    prune.py            # Remove unused environments
    review.py           # Analyze nf-test timing and results
    search.py           # Query ENA/SRA for public accessions
    status.py           # Show repo status info
    summary.py          # Generate summary tables with quality rankings
    testing.py          # Run nf-test suites
    update.py           # Check for module version updates
    workflows.py        # List available Bactopia workflows
  databases/            # API clients
    ena.py              # ENA REST API
    ncbi.py             # NCBI API (genome sizes, taxonomy)
    pubmlst/            # PubMLST REST API (OAuth, database building)
  lint/                 # Pipeline linting system
    models.py           # LintResult data model
    runner.py           # Lint orchestration and execution
    rules/              # Lint rule definitions
      module_rules.py       # Module rules (M/MC/JS/FMT)
      subworkflow_rules.py  # Subworkflow rules (S001-S016)
      workflow_rules.py     # Workflow rules (W001-W020)
  parsers/              # Output parsers for bioinformatics tools
  reports/              # Test report generation
  templates/            # Jinja2 templates for Nextflow configs
  atb.py                # AllTheBacteria utilities
  nf.py                 # Nextflow repo introspection utilities
  outputs.py            # nf-test output validation
  parse.py              # Bactopia output directory parsing
  summary.py            # QC ranking logic (Gold/Silver/Bronze/Exclude)
  utils.py              # Shared utilities (file ops, downloads, command execution)
```

## CLI Entry Points

All 27 commands are defined in `pyproject.toml` under `[tool.poetry.scripts]`: 19 user-facing commands and 8 pipeline utility scripts. Every user-facing command uses `rich-click` and provides consistent flags: `--verbose`, `--silent`, `--version/-V`, `--help`.

## Coding Conventions

### CLI Module Pattern

Each CLI command is a module with a `main()` function using `@click.command()`. Every CLI module starts with the same Rich console boilerplate:

```python
import rich
import rich.console
import rich.traceback
import rich_click as click

stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
```

Commands with many options use `click.rich_click.OPTION_GROUPS` for organized `--help` output.

### General Conventions

- Logging via `rich.logging.RichHandler`
- Path handling via `pathlib.Path`
- Docstrings: Google-style with Args/Returns sections
- Formatting and linting: ruff (configured in `pyproject.toml`)

### Adding a New CLI Command

1. Create module in `bactopia/cli/` with a `main()` function
2. Add entry to `[tool.poetry.scripts]` in `pyproject.toml`
3. Follow the Rich console boilerplate pattern above
4. Use `OPTION_GROUPS` for organized help output
5. Include `--verbose`, `--silent`, `--version/-V` flags

## Key Dependencies

- `rich` / `rich-click` -- CLI output and framework
- `requests` -- HTTP/API calls (ENA, NCBI, PubMLST)
- `pandas` -- Data manipulation for summaries
- `tqdm` -- Progress bars (downloads, batch operations)
- `rauth` -- OAuth for PubMLST API
- `jinja2` -- Nextflow config template rendering
- `pyyaml` -- YAML parsing
- `biopython` -- Sequence and bioinformatics utilities
- `openpyxl` -- Excel file handling

## Related Projects

- [bactopia](https://github.com/bactopia/bactopia) -- Main Nextflow pipeline
- [nf-bactopia](https://github.com/bactopia/nf-bactopia) -- Nextflow plugin

## Citation

Petit III RA, Read TD, *Bactopia: a flexible pipeline for complete analysis of bacterial genomes.* mSystems. 5 (2020), <https://doi.org/10.1128/mSystems.00190-20>.
