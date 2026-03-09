# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

bactopia-py is a Python CLI companion package for [Bactopia](https://bactopia.github.io/), a flexible Nextflow pipeline for complete analysis of bacterial genomes. It provides 13 command-line tools for input preparation, public data search, environment building, dataset management, result summarization, and database integration.

- **Author:** Robert A. Petit III
- **License:** MIT
- **Python:** 3.9+

## Development Commands

### Environment Setup

The conda environment provides system dependencies (blast, pigz, wget, just, poetry) and Python. Poetry then manages a virtualenv for Python package dependencies.

```bash
conda env create -f environment.yml -n bactopia-py-dev
conda run -n bactopia-py-dev poetry env use $(conda run -n bactopia-py-dev which python)
conda run -n bactopia-py-dev just install
```

### Running Commands

Use `conda run -n bactopia-py-dev` to run commands in the conda environment. Poetry commands need `poetry run` to access the virtualenv:

```bash
conda run -n bactopia-py-dev poetry run bactopia-download --version
conda run -n bactopia-py-dev poetry run bactopia-prepare --help
```

The `just` recipes handle the `poetry run` prefix automatically, so you only need the `conda run` wrapper:

```bash
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
```

No test suite currently exists. Pre-commit hooks are configured (`.pre-commit-config.yaml`).

## Project Structure

```
bactopia/
  cli/                  # CLI commands (one module per command)
    atb/                # AllTheBacteria commands (atb_formatter, atb_downloader)
    pubmlst/            # PubMLST database commands (setup, build)
    helpers/            # Utility commands (merge_schemas)
    citations.py        # Print tool citations
    datasets.py         # Download optional datasets
    download.py         # Build Conda/Docker/Singularity environments
    prepare.py          # Create file-of-filenames (FOFN) for samples
    search.py           # Query ENA/SRA for public accessions
    summary.py          # Generate summary tables with quality rankings
    update.py           # Check for module version updates
    workflows.py        # List available Bactopia workflows
  databases/            # API clients
    ena.py              # ENA REST API
    ncbi.py             # NCBI API (genome sizes, taxonomy)
    pubmlst/            # PubMLST REST API (OAuth, database building)
  parsers/              # Output parsers for bioinformatics tools
  templates/            # Jinja2 templates for Nextflow configs
  utils.py              # Shared utilities (file ops, downloads, command execution)
  summary.py            # QC ranking logic (Gold/Silver/Bronze/Exclude)
  parse.py              # Bactopia output directory parsing
  atb.py                # AllTheBacteria utilities
```

## CLI Entry Points

All 13 commands are defined in `pyproject.toml` under `[tool.poetry.scripts]`. Every command uses `rich-click` and provides consistent flags: `--verbose`, `--silent`, `--version/-V`, `--help`.

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

## Related Projects

- [bactopia](https://github.com/bactopia/bactopia) -- Main Nextflow pipeline
- [nf-bactopia](https://github.com/bactopia/nf-bactopia) -- Nextflow plugin

## Citation

Petit III RA, Read TD, *Bactopia: a flexible pipeline for complete analysis of bacterial genomes.* mSystems. 5 (2020), https://doi.org/10.1128/mSystems.00190-20.
