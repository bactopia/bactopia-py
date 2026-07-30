# Changelog

## 2.4.0

### New Features

- `bactopia-test` runs each component across `docker`, `conda`, `singularity_galaxy`, `singularity_pull` profiles
    - Snapshots are based on `docker` results
    - `bactopia-test` will now build unbuilt envs at startup
    - `summary.json` has been expanded to include better debugging and error class messages
- `bactopia-review-tests` updated to support expanded `summary.json`

### Changed

- **Breaking:** `bactopia-test` changed multiple parameters
    - `--keep` is now the default behavior
    - `--condadir`, `--singularity_cache` are now `--cachedir` (`conda/` and `singularity/` subdirs)
    - Added `--force-rebuild` and `--max-retry`
    - running tests now requires docker, conda/mamba, and singularity/apptainer
        - `--profile` is no longer needed due to this
- Both Galaxy images and singularity pull images are now tested

## 2.3.0

### New Lint Rules

- `W022` - workflow `nextflow.config` must declare `params.bactopia_dir` before the module includes (FAIL)
- `MC016` - module.config path-like params must be anchored via `${params.bactopia_dir}` and resolve to existing data files (FAIL)
- `V001` - version-bearing files must match the pipeline `versions.yml`: pipeline version across `nextflow.config`, `catalog.json`, `bin/bactopia`, `meta.yaml`, `CITATION.cff`, and `bactopia_version`/`nf-bactopia@` literals in every `*.config` (FAIL)
- `V002` - `versions.yml` pipeline version must match the top `## vX.Y.Z` heading in `CHANGELOG.md` (FAIL)
- `V003` - `nf-bactopia` pin should match the latest release from sibling `../nf-bactopia/build.gradle` (WARN)

### Enhancements

- `bactopia-merge-schemas` emits a `params.bactopia_dir` anchor so generated configs can reference vendored `data/`
- `nf.py` config parser now brace-matches `params { ... }` blocks and captures `${...}`-interpolated values
- `bactopia-merge-schemas` and `bactopia-catalog` source the pipeline version and `nf-bactopia` pin from the pipeline `versions.yml`, so pipeline bumps no longer require a `bactopia-py` release

### Bug Fixes

- `bactopia-summary` now reads `mlst --full` header columns for `mlst_scheme`/`mlst_st` ([bactopia#673](https://github.com/bactopia/bactopia/issues/673))
- `bactopia-merge-schemas` no longer strips the trailing newline from the generated `nextflow.config`
- `bactopia-download` `--envtype` now accepts `apptainer`
- `bactopia.utils.execute` uses `shlex.split` and logs full STDOUT/STDERR on failure
- `bactopia-test` and `bactopia-review-tests` write run logs under `logs/run-tests`

### Template Updates

- `nextflow/nextflow.config.j2` version and `nf-bactopia@` literals now injected from the pipeline `versions.yml`
- Added `params.bactopia_dir` anchor to the `nextflow/` and scaffold workflow templates
- Scaffold `workflow/nextflow.config.j2` injects version and `nf-bactopia@` pin from `versions.yml` (via `bactopia-scaffold --bactopia-path`)
- Scaffold `module`/`subworkflow` test configs now inherit version and pin from `conf/test_base.config`

### Build

- CI and `environment.yml`: install via `python -m pip` and add explicit `pip` dependency

## 2.2.0

### New Features

- `bactopia-search` now falls back to SRA (via `pysradb`) when ENA returns no results, addressing sync delays between the two databases
    - Added `--provider [ena|sra]` flag to control which database is queried first (default: `ena`)
    - Added `--only-provider` flag to disable fallback and query only the selected provider
    - Search summary output now includes a `PROVIDER` line indicating which database returned results

### New Dependencies

- Added `pysradb` (>=2.2.0) for SRA metadata queries

### Bug Fixes

- Fixed docs lint tests to match updated Nextflow version (26.04.0)

### Template Updates

- Bumped `nf-bactopia` plugin version from 2.1.3 to 2.1.5 in all Nextflow config templates
- Updated `nextflowVersion` requirement from `>=25.04.6` to `>=26.04.0` in scaffold templates

## 2.1.6

- fix "bactopia-summary" for v4 outputs
- change url from https://bactopia.github.io/ to https://bactopia.io/

## 2.1.5

- fix `bactopia-prepare` to output v4 column headers

## 2.1.4

- changes to templates replated to Nextflow 26.04 updates

## 2.1.3

### Enhancements

- Added shared `@common_options` decorator and `setup_logging()` helper in new `bactopia/cli/common.py` to prevent drift of `--verbose`, `--silent`, and `--version/-V` flags across CLI commands
- Migrated 21 CLI modules to use `@common_options` (all user-facing commands except `jsonify`, `sysinfo`, and pipeline scripts)
- Standardized version flag: all commands now accept both `--version` and `-V`
- Added missing `--silent` flag to `bactopia-catalog` and `bactopia-lint`
- Added missing `--verbose` flag to `bactopia-citations` and `bactopia-docs`
- Added `OPTION_GROUPS` for organized `--help` output to `bactopia-catalog`, `bactopia-citations`, and `bactopia-docs`
- Added module-level docstrings to 12 CLI modules that were missing them
- Removed trailing periods from all CLI help text for consistency
- Standardized `--verbose` help text across all commands (was split between two variants)
- Replaced `scaffold.py`'s private `_setup_logging` with the shared `setup_logging()` helper
- Added `-V` short flag to `bactopia-scaffold` group command
- Updated CLAUDE.md CLI module pattern documentation to reflect `common_options` usage

### Build

- Updated justfile to resolve `poetry` and `python` paths via `which` for more reliable environment handling
- `just install` now includes test dependencies (`--with test`)
- Test commands now use `poetry run <python> -m pytest` to ensure correct interpreter

## 2.1.2

### New Commands

- `bactopia-scaffold` - scaffold Bactopia components (modules, subworkflows, workflows) from bioconda/conda-forge packages with subcommands: `lookup`, `test-data`, `module`, `subworkflow`, `tool`

### New Lint Rules

- `W021` - Workflow `params` block: `Value<Path>` / `Value<Path?>` wrappers must be replaced with bare `Path` / `Path?` (FAIL)
- `S025` - Subworkflow `take:` block: `Value<Path>` / `Value<Path?>` wrappers must be replaced with bare `Path` / `Path?` (FAIL)
- `S026` - All emit channels must have a corresponding `@output` tag (FAIL/WARN)
- `S027` - `@output` field descriptions must not exist for `channel.empty()` emits (FAIL)

### Bug Fixes

- Fixed `_infer_scope` classifying run-scope subworkflows as sample scope when `sample_outputs` was declared but empty
- Fixed `_extract_tool_info` returning build hash as version for conda specs with build strings (e.g., `midas=1.3.2=pyh7cba7a3_7`)
- Hardcoded merlin subworkflow as sample scope (dynamic dispatcher with no fixed output fields)

### Enhancements

- `bactopia-lint` gains `--subworkflow` and `--workflow` filter options to complement existing `--module`
- Lint runner now supports `subworkflow_filter` and `workflow_filter` for fine-grained single-component linting
- Extracted shared `bactopia.conda` module for Anaconda API queries (bioconda/conda-forge version lookup, container ref construction, component existence checking); refactored `bactopia-update` to use it
- `bactopia-catalog` improved scope inference and tool info extraction
- Workflow param parser now captures type annotations (e.g., `String`, `Value<Path>`)
- Subworkflow `take:` block inputs are now parsed with name, type, and line number
- GroovyDoc parser now tracks per-`@output` field presence (`doc_output_has_fields`)
- Structure parser now detects `channel.empty()` emit channels (`empty_emit_channels`)

### Tests

- Tests for `bactopia.conda` module (API queries, retry logic, container refs, component checking)
- Tests for `bactopia-scaffold` (config validation, template rendering for modules/subworkflows/workflows)
- 11 tests for W021/S025 rules (pass/fail/edge cases for both workflow and subworkflow)
- Tests for S026/S027 rules (matching/missing/extra @output tags, channel.empty() field validation)

## 2.1.1

### Bug Fixes

- Fixed QC summary file paths in `bactopia-summary` parser (`qc/summary/` -> `qc/supplemental/`)
- Fixed incorrect path in `bactopia-workflows` error message for missing `catalog.json`
- `bactopia-sysinfo` now only emits `--max_memory`/`--max_cpus` when detected values are below the cap (MEM_CAP raised to 144 GB), avoiding redundant flags on large hosts
- `bactopia-sysinfo` bare invocations now detect resources instead of showing help text

### Tests

- Updated `bactopia-sysinfo` tests to match new cap-silence and no-args behavior

## 2.1.0

### New Commands

- `bactopia-sysinfo` - auto-detect host resources and emit Nextflow `--max_memory`/`--max_cpus` overrides for local profiles
- `bactopia-docs` - validate reference documentation for deprecated patterns (D0xx) and ground-truth assertions (D1xx)

### New Lint Modules

- `bactopia/lint/citations.py` - cross-repository citation validation: orphan detection, missing workflow `@citation` keys, provenance-only filtering
- `bactopia/lint/docs.py` - documentation staleness checker: deprecated pattern detection, count/version/reference assertions, skill inventory sync

### Enhancements

- `bactopia-citations` gains `--validate` flag for citation integrity checking with Rich table output and `--json` for CI
- `bactopia-catalog` expanded output to better support Claude Code skills on the Bactopia side
- `bactopia-merge-schemas` minor fix for schema merging
- Updated GroovyDoc parser in `nf.py` to handle Nextflow 25.04.6+ syntax (`record()`, `stage:` block, balanced-paren inputs)
- Module lint rule M018 updated for both legacy and current meta initialization patterns

### New Dependencies

- `psutil >=5.9.0` (used by `bactopia-sysinfo`)

### Tests

- 19 tests for `bactopia-sysinfo` (eligibility, profile gating, flag parsing)
- 25 tests for citation linting (orphan detection, provenance filtering, potential homes)
- 60+ tests for docs linting (D0xx/D1xx rules, inline ignores, CLI integration)

## 2.0.2

### Bug Fixes

- `bactopia-download` will print debug message is docker image not available
- fixed incorrect paths in the catalog output of `bactopia-catalog`

## 2.0.1

### Bug Fixes

- Loosened dependency pins from `^` (caret) to `>=` to avoid artificial upper bounds that broke bioconda builds (e.g., pandas 3.x, rich 14.x)
- Removed Nextflow runtime dependency from `bactopia-datasets` by reading `conf/params.config` directly instead of running `nextflow config`

### Improvements

- Extracted shared `get_bactopia_version()` helper in `bactopia/nf.py`, reused by `bactopia-catalog`

## 2.0.0

### Pipeline Utility Scripts

Migrated 9 Python scripts from Nextflow module shell blocks into bactopia-py as
standalone CLI commands. These are called by the pipeline at runtime:

- `bactopia-check-fastqs` - verify input FASTQs meet minimum read/basepair requirements
- `bactopia-check-assembly-accession` - verify NCBI Assembly accessions are current and not excluded
- `bactopia-cleanup-coverage` - reduce redundancy in per-base coverage output
- `bactopia-mask-consensus` - apply coverage masking to Snippy consensus sequences
- `bactopia-kraken-bracken-summary` - update Bracken abundances with unclassified counts
- `bactopia-scrubber-summary` - create before-and-after reports from human read scrubbing
- `bactopia-teton-prepare` - prepare sample sheets for downstream Teton workflow analysis
- `bactopia-bracken-to-excel` - export Bracken abundances to Excel format

### New Tools

- `bactopia-lint` - Bactopia-specific linter for Nextflow workflows, subworkflows, and modules
- `bactopia-catalog` - generate a catalog of available Bactopia workflows and modules
- `bactopia-test` - helper for running and reviewing nf-test results
- `bactopia-review-tests` - review nf-test work directories with output validation
- `bactopia-prune` - prune stale Nextflow work directories
- `bactopia-status` - show project status and recent activity

### New Dependencies

- `biopython` - used by `bactopia-check-assembly-accession` and `bactopia-mask-consensus`
- `openpyxl` - used by `bactopia-bracken-to-excel` for Excel output

### Improvements

- Migrated to `ruff` for formatting and linting (replaced black/flake8)
- Added test suite with pytest (182 tests covering CLI, parsers, core, and databases)
- Added GitHub Actions CI workflow for Python 3.9-3.12

## 1.7.0

- `bactopia-download`
    - Use appropriate executable for singularity and apptainer
    - support Bactopia v4
- `bactopia-workflows` will print the path for a specific Bactopia wf
- `bactopia-merge-schemes` will merge schemes and configs for a given wf

## 1.6.1

- shuffle ncbi related module out of `utils` and into `ncbi`
- fixed missing import in `bactopia-prepare`

## 1.6.0

- `bactopia-search`
    - fixed issue when no tax id is associated with an accession
    - NCBI genome size is now optional (`--use-ncbi-genome-size`)
    - moved modules to specific database files
- Remove `executor` dependency

## 1.5.1

- fix ena metadata parsing in `bactopia-search` to handle missing columns

## 1.5.0

- actually remove `--force` from `mamba|conda` commands

## 1.4.0

- added:
    - `bactopia-pubmlst-setup` to setup PubMLST REST API connections
    - `bactopia-pubmlst-build` to build PubMLST databases compatible with `mlst` Bactopia Tool

## 1.3.0

- replace conda/mamba `--force` with simple `rm -rf`
    - latest version of mamba removed `--force`

## 1.2.1

- added parallel gzipping of assemblies in `bactopia-atb-formatter`
- added size estimation to `bactopia-atb-formatter` output

## 1.2.0

- added `bactopia-atb-downloader` to download All-the-Bacteria assemblies

## 1.1.1

- fixed `bactopia-summary` not working with Bakta annotations
- added support for alternative extensions in `bactopia-atb-formatter` @nickjhathaway 🎉

## 1.1.0

- rework `bactopia-summary` for new AMRFinder+ outputs

## 1.0.9

- added `bactopia-atb-formatter` to format All-the-Bacteria assemblies for Bactopia

## 1.0.8

- Fixed `bactopia-prepare` usage of `--prefix` not working

## 1.0.7

- Fixed `bactopia-search` not including header name in accessions.txt
- Added `--hybrid` and `--short-polish` to `bactopia-prepare`

## 1.0.6

- Fixed `bactopia-summary` handling of empty searches

## 1.0.5

- Fixed `bactopia-download` not building prokka and bakta conda envs

## 1.0.4

- Fixed `bactopia-summary` working with new output structure

## 1.0.3

- Fixed `bactopia-search` using missing columns in the query
- dropped pysradb dependency

## 1.0.2

- Added `bactopia-datasets` to download optional datasets outside of Nextflow
- consistently use `--bactopia-path` across sub-commands

## 1.0.1

Renamed parameter `--bactopia` to `--bactopia-path` in `bactopia-download`

## 1.0.0

Initial release of the `bactopia-py` package. This release ports the Python helper scripts from the main Bactopia repo.
