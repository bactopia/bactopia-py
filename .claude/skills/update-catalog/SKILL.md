---
name: update-catalog
description: Regenerate catalog.json and llms.txt in the bactopia-py repo root by introspecting pyproject.toml entry points and CLI modules. Use this skill whenever the user asks to update the catalog, refresh catalog.json, sync llms.txt, or after adding/removing/renaming CLI commands. Also use when the user mentions that catalog.json or llms.txt is out of date, stale, or drifted from the actual commands.
---

# Update Catalog

Regenerate the two discovery files at the bactopia-py repo root:

- **`catalog.json`** -- machine-readable index of every CLI command (name, description, entry point, category, tags)
- **`llms.txt`** -- AI-discovery surface describing the project, its commands, documentation links, and related projects

Both files drift when commands are added, removed, or renamed. This skill introspects the codebase and rewrites them to match reality.

## Steps

### 1. Safety check

Check for uncommitted edits before overwriting:

```
git -C /home/rpetit3/repos/bactopia/bactopia-py status --porcelain catalog.json llms.txt
```

If either file is dirty, show the diff and confirm with the user before proceeding. These files are overwritten in place -- uncommitted changes would be lost.

### 2. Collect the authoritative command list

Read `pyproject.toml` and extract every entry under `[tool.poetry.scripts]`. This is the single source of truth for which commands exist and their entry points.

For each entry, note:
- **name**: the script name (e.g., `bactopia-prepare`)
- **entry_point**: the dotted path (e.g., `bactopia.cli.prepare:main`)
- **module_path**: convert the entry point to a file path (e.g., `bactopia/cli/prepare.py`)

### 3. Read each CLI module for its description

Open each module file and find the description. Commands define their description in one of two places -- check both:

1. **Docstring on the decorated function** -- the function decorated with `@click.command()` or `@click.group()` may have a docstring (e.g., `"""Scaffold Bactopia components."""`)
2. **`help=` parameter in `OPTION_GROUPS`** -- some modules define `click.rich_click.OPTION_GROUPS` with a top-level description

If neither is found, read the first 50 lines of the module for any module-level docstring or comment that describes the command's purpose.

### 4. Assign categories and tags

Infer the category from the module's location in the source tree:

| Module path pattern | Category |
|---|---|
| `cli/pipeline/` | `pipeline` |
| `cli/atb/` | `atb` |
| `cli/pubmlst/` | `pubmlst` |
| `cli/helpers/` | `utility` |
| Top-level `cli/` modules | Infer from purpose (see below) |

For top-level CLI modules, use these category assignments based on what the command does:

- `documentation` -- citations, workflows, status
- `input` -- prepare, search
- `data` -- datasets
- `environment` -- download, prune
- `analysis` -- summary
- `maintenance` -- update
- `development` -- lint, catalog, testing, review, docs, scaffold
- `utility` -- merge-schemas, sysinfo, jsonify

Generate 3-6 tags per command based on key concepts from the description and the command's domain. Tags should be lowercase and use hyphens for multi-word tags. Look at the existing `catalog.json` for tag style reference.

### 5. Write catalog.json

Write the file to the repo root at `/home/rpetit3/repos/bactopia/bactopia-py/catalog.json`.

Follow this exact schema (match the existing structure):

```json
{
  "name": "bactopia-py",
  "version": "<from bactopia/__init__.py __version__>",
  "description": "Python CLI tools for working with Bactopia",
  "repository": "https://github.com/bactopia/bactopia-py",
  "license": "MIT",
  "python_requires": ">=3.10",
  "command_count": <total number of commands>,
  "commands": [
    {
      "name": "bactopia-<cmd>",
      "description": "<one-line description>",
      "entry_point": "<dotted.path:main>",
      "category": "<category>",
      "tags": ["tag1", "tag2", "..."]
    }
  ]
}
```

Important details:
- Read `bactopia/__init__.py` to get the current `__version__` value
- Read `pyproject.toml` for the `python_requires` value (under `[tool.poetry.dependencies]` as `python = "^3.10.0"` -- normalize to `>=3.10`)
- Use 2-space indentation (pretty-printed) so diffs are clean
- Order commands: user-facing commands first (alphabetically by name within each group), then pipeline utilities (alphabetically), matching the grouping in `pyproject.toml`
- `command_count` must equal the length of the `commands` array

### 6. Write llms.txt

Write the file to the repo root at `/home/rpetit3/repos/bactopia/bactopia-py/llms.txt`.

Use this structure, updating counts and details to match the current state:

```
# bactopia-py

> Python CLI tools for working with Bactopia, a Nextflow pipeline for complete analysis of bacterial genomes.

<One paragraph describing what bactopia-py provides. Include the total command count, broken down by user-facing vs pipeline utility. Mention the key capabilities: input preparation, public database querying, environment building, dataset management, result summarization, pipeline linting, testing, and database integration. Note the tech stack: Python 3.10+, Poetry, and rich-click.>

## Documentation

- [README](https://github.com/bactopia/bactopia-py/blob/main/README.md): Full documentation with CLI help output for all commands
- [CHANGELOG](https://github.com/bactopia/bactopia-py/blob/main/CHANGELOG.md): Version history
- [Bactopia Documentation](https://bactopia.github.io/): Main Bactopia pipeline documentation

## Source Code

- [CLI Commands](https://github.com/bactopia/bactopia-py/tree/main/bactopia/cli): <N> user-facing CLI command implementations
- [Pipeline Utilities](https://github.com/bactopia/bactopia-py/tree/main/bactopia/cli/pipeline): <N> scripts called from Nextflow module shell blocks
- [Database Clients](https://github.com/bactopia/bactopia-py/tree/main/bactopia/databases): ENA, NCBI, PubMLST API clients
- [Parsers](https://github.com/bactopia/bactopia-py/tree/main/bactopia/parsers): Output parsers for 20+ bioinformatics tools
- [Lint System](https://github.com/bactopia/bactopia-py/tree/main/bactopia/lint): <N>+ lint rules for modules, subworkflows, and workflows
- [Tests](https://github.com/bactopia/bactopia-py/tree/main/tests): pytest test suite with <N> test modules
- [pyproject.toml](https://github.com/bactopia/bactopia-py/blob/main/pyproject.toml): Build configuration and entry points
- [catalog.json](https://github.com/bactopia/bactopia-py/blob/main/catalog.json): Machine-readable command catalog

## Related Projects

- [bactopia](https://github.com/bactopia/bactopia): Main Bactopia Nextflow pipeline
- [nf-bactopia](https://github.com/bactopia/nf-bactopia): Nextflow plugin providing utility functions for Bactopia pipelines

## Optional

- [AllTheBacteria](https://github.com/iqbal-lab-org/AllTheBacteria): ~2M pre-assembled bacterial genomes
- [PubMLST API Docs](https://bigsdb.readthedocs.io/en/latest/rest.html): Authentication setup for PubMLST commands
- [Citation](https://doi.org/10.1128/mSystems.00190-20): Petit III RA, Read TD, mSystems 2020
```

To fill in the dynamic counts:
- Count user-facing commands vs pipeline utilities from the `pyproject.toml` grouping (pipeline utilities are under the `# Pipeline utility scripts` comment)
- Count lint rules by running: `grep -c "def check_" bactopia/lint/rules/*.py` or by counting rule classes/functions
- Count test modules by running: `ls tests/test_*.py | wc -l`

### 7. Show the result

After writing both files, show the user:
- `git diff --stat catalog.json llms.txt` to summarize changes
- Any commands that were added or removed compared to the previous version
- The new `command_count`

Do NOT stage or commit the files -- let the user review the diffs first.

## Notes

- The `pyproject.toml` `[tool.poetry.scripts]` section is the single source of truth. If a command exists there but not in `catalog.json`, it needs to be added. If it's in `catalog.json` but not in `pyproject.toml`, it needs to be removed.
- Some commands use `@click.group()` instead of `@click.command()` (e.g., `scaffold`). These are still single entry points and should appear as one entry in `catalog.json`.
- Pipeline utility scripts (in `cli/pipeline/`) are called from within Nextflow module shell blocks, not directly by users. They still get catalog entries but with category `pipeline`.
- Keep descriptions concise -- one line, no period at the end, starting with a verb or noun phrase.
