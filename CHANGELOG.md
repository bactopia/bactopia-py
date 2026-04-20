# Changelog

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
