# Changelog

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
