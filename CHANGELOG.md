# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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
