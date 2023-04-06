[![Gitpod ready-to-code](https://img.shields.io/badge/Gitpod-ready--to--code-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/bactopia/bactopia-py)

![Bactopia Logo](https://raw.githubusercontent.com/bactopia/bactopia/master/data/bactopia-logo.png)

# bactopia-py
A Python package for working with [Bactopia](https://bactopia.github.io/)

## Bactopia Subcommands

There are many subcommands available in Bactopia. Here is a brief description of each command:

| Command              | Description                                                                |
|----------------------|----------------------------------------------------------------------------|
| `bactopia-citations` | Print out tools and citations used throughout Bactopia                     |
| `bactopia-download`  | Builds Bactopia environments for use with Nextflow.                        |
| `bactopia-prepare`   | Create a 'file of filenames' (FOFN) of samples to be processed by Bactopia |
| `bactopia-search`    | Query against ENA and SRA for public accessions to process with Bactopia   |
| `bactopia-summary`   | Generate a summary table from the Bactopia results.                        |

Below is the `--help` output for each subcommand.

### `bactopia-citations`

```{bash}
 Usage: bactopia-citations [OPTIONS]

 Print out tools and citations used throughout Bactopia

╭─ Options ────────────────────────────────────────────────────────────────────────────╮
│    --version     -V        Show the version and exit.                                │
│ *  --bactopia    -b  TEXT  Directory where Bactopia repository is stored [required]  │
│    --name        -n  TEXT  Only print citation matching a given name                 │
│    --plain-text  -p        Disable rich formatting                                   │
│    --help                  Show this message and exit.                               │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

### `bactopia-download`

```{bash}
 Usage: bactopia-download [OPTIONS] [UNKNOWN]...

 Builds Bactopia environments for use with Nextflow.

╭─ Required Options ───────────────────────────────────────────────────────────────────╮
│ *  --bactopia-path    TEXT  Directory where Bactopia results are stored [required]   │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Build Related Options ──────────────────────────────────────────────────────────────╮
│ --envtype                     [conda|docker|singularity|  The type of environment to │
│                               all]                        build.                     │
│                                                           [default: conda]           │
│ --wf                          TEXT                        Build a environment for a  │
│                                                           the given workflow         │
│                                                           [default: bactopia]        │
│ --condadir                    TEXT                        Directory to create Conda  │
│                                                           environments               │
│                                                           (NXF_CONDA_CACHEDIR env    │
│                                                           variable takes precedence) │
│ --use_conda                                               Use Conda for building     │
│                                                           Conda environments instead │
│                                                           of Mamba                   │
│ --singularity_cache           TEXT                        Directory to download      │
│                                                           Singularity images         │
│                                                           (NXF_SINGULARITY_CACHEDIR  │
│                                                           env variable takes         │
│                                                           precedence)                │
│ --singularity_pull_docker…                                Force conversion of Docker │
│                                                           containers, instead        │
│                                                           downloading Singularity    │
│                                                           images directly            │
│ --force_rebuild                                           Force overwrite of         │
│                                                           existing pre-built         │
│                                                           environments.              │
│ --max_retry                   INTEGER                     Maximum times to attempt   │
│                                                           creating Conda             │
│                                                           environment. (Default: 3)  │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Additional Options ─────────────────────────────────────────────────────────────────╮
│ --verbose      Print debug related text.                                             │
│ --silent       Only critical errors will be printed.                                 │
│ --version      Show the version and exit.                                            │
│ --help         Show this message and exit.                                           │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────╮
│ --build-all         Builds all environments for Bactopia workflows                   │
│ --build-nfcore      Builds all nf-core related environments                          │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

### `bactopia-prepare`

```{bash}
 Usage: bactopia-prepare [OPTIONS]

 Create a 'file of filenames' (FOFN) of samples to be processed by Bactopia

╭─ Required Options ───────────────────────────────────────────────────────────────────╮
│ *  --path  -p  TEXT  Directory where FASTQ files are stored [required]               │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Matching Options ───────────────────────────────────────────────────────────────────╮
│ --assembly-ext     -a  TEXT  Extension of the FASTA assemblies [default: .fna.gz]    │
│ --fastq-ext        -f  TEXT  Extension of the FASTQs [default: .fastq.gz]            │
│ --fastq-separator      TEXT  Split FASTQ name on the last occurrence of the          │
│                              separator                                               │
│                              [default: _]                                            │
│ --pe1-pattern          TEXT  Designates difference first set of paired-end reads     │
│                              [default: [Aa]|[Rr]1|1]                                 │
│ --pe2-pattern          TEXT  Designates difference second set of paired-end reads    │
│                              [default: [Bb]|[Rr]2|2]                                 │
│ --merge                      Flag samples with multiple read sets to be merged by    │
│                              Bactopia                                                │
│ --ont                        Single-end reads should be treated as Oxford Nanopore   │
│                              reads                                                   │
│ --recursive        -r        Directories will be traversed recursively               │
│ --prefix               TEXT  Prefix to add to the path                               │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Sample Information Options ─────────────────────────────────────────────────────────╮
│ --metadata             TEXT     Metadata per sample with genome size and species     │
│                                 information                                          │
│ --genome-size  -gsize  INTEGER  Genome size to use for all samples                   │
│ --species      -s      TEXT     Species to use for all samples (If available, can be │
│                                 used to determine genome size)                       │
│ --taxid                TEXT     Use the genome size of the Taxon ID for all samples  │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Additional Options ─────────────────────────────────────────────────────────────────╮
│ --examples        Print example usage                                                │
│ --verbose         Increase the verbosity of output                                   │
│ --silent          Only critical errors will be printed                               │
│ --version   -V    Show the version and exit.                                         │
│ --help            Show this message and exit.                                        │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

### `bactopia-search`

```{bash}
 Usage: bactopia-search [OPTIONS]

 Query against ENA and SRA for public accessions to process with Bactopia

╭─ Required Options ───────────────────────────────────────────────────────────────────╮
│ *  --query  -q  TEXT  Taxon ID or Study, BioSample, or Run accession (can also be    │
│                       comma separated or a file of accessions)                       │
│                       [required]                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Query Options ──────────────────────────────────────────────────────────────────────╮
│ --exact-taxon                     Exclude Taxon ID descendants                       │
│ --limit             -l   INTEGER  Maximum number of results (per query) to return    │
│                                   [default: 1000000]                                 │
│ --accession-limit   -al  INTEGER  Maximum number of accessions to query at once      │
│                                   [default: 5000]                                    │
│ --biosample-subset       INTEGER  If a BioSample has multiple Experiments, maximum   │
│                                   number to randomly select (0 = disabled)           │
│                                   [default: 0]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Filtering Options ──────────────────────────────────────────────────────────────────╮
│ --min-base-count   -mbc  INTEGER  Filters samples based on minimum base pair count   │
│                                   (0 = disabled)                                     │
│                                   [default: 0]                                       │
│ --min-read-length  -mrl  INTEGER  Filters samples based on minimum mean read length  │
│                                   (0 = disabled)                                     │
│                                   [default: 0]                                       │
│ --min-coverage     -mc   INTEGER  Filter samples based on minimum coverage (requires │
│                                   --genome_size, 0 = disabled)                       │
│                                   [default: 0]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Additional Options ─────────────────────────────────────────────────────────────────╮
│ --genome-size  -gsize  INTEGER  Genome size to be used for all samples, and for      │
│                                 calculating min coverage                             │
│                                 [default: 0]                                         │
│ --outdir       -o      TEXT     Directory to write output [default: ./]              │
│ --prefix       -p      TEXT     Prefix to use for output file names                  │
│                                 [default: bactopia]                                  │
│ --force                         Overwrite existing reports                           │
│ --verbose                       Increase the verbosity of output                     │
│ --silent                        Only critical errors will be printed                 │
│ --version      -V               Show the version and exit.                           │
│ --help                          Show this message and exit.                          │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

### `bactopia-summary`

```{bash}
 Usage: bactopia-summary [OPTIONS]

 Generate a summary table from the Bactopia results.

╭─ Required Options ───────────────────────────────────────────────────────────────────╮
│ *  --bactopia  -b  TEXT  Directory where Bactopia results are stored [required]      │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Gold Cutoffs ───────────────────────────────────────────────────────────────────────╮
│ --gold-coverage     -gcov      INTEGER  Minimum amount of coverage required for Gold │
│                                         status                                       │
│                                         [default: 100]                               │
│ --gold-quality      -gqual     INTEGER  Minimum per-read mean quality score required │
│                                         for Gold status                              │
│                                         [default: 30]                                │
│ --gold-read-length  -glen      INTEGER  Minimum mean read length required for Gold   │
│                                         status                                       │
│                                         [default: 95]                                │
│ --gold-contigs      -gcontigs  INTEGER  Maximum contig count required for Gold       │
│                                         status                                       │
│                                         [default: 100]                               │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Silver Cutoffs ─────────────────────────────────────────────────────────────────────╮
│ --silver-coverage     -scov      INTEGER  Minimum amount of coverage required for    │
│                                           Silver status                              │
│                                           [default: 50]                              │
│ --silver-quality      -squal     INTEGER  Minimum per-read mean quality score        │
│                                           required for Silver status                 │
│                                           [default: 20]                              │
│ --silver-read-length  -slen      INTEGER  Minimum mean read length required for      │
│                                           Silver status                              │
│                                           [default: 75]                              │
│ --silver-contigs      -scontigs  INTEGER  Maximum contig count required for Silver   │
│                                           status                                     │
│                                           [default: 200]                             │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Fail Cutoffs ───────────────────────────────────────────────────────────────────────╮
│ --min-coverage        -mincov   INTEGER  Minimum amount of coverage required to pass │
│                                          [default: 20]                               │
│ --min-quality         -minqual  INTEGER  Minimum per-read mean quality score         │
│                                          required to pass                            │
│                                          [default: 12]                               │
│ --min-read-length     -minlen   INTEGER  Minimum mean read length required to pass   │
│                                          [default: 49]                               │
│ --max-contigs                   INTEGER  Maximum contig count required to pass       │
│                                          [default: 500]                              │
│ --min-assembled-size            INTEGER  Minimum assembled genome size               │
│ --max-assembled-size            INTEGER  Maximum assembled genome size               │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Additional Options ─────────────────────────────────────────────────────────────────╮
│ --outdir   -o  PATH  Directory to write output [default: ./]                         │
│ --prefix   -p  TEXT  Prefix to use for output files [default: bactopia]              │
│ --force              Overwrite existing reports                                      │
│ --verbose            Increase the verbosity of output                                │
│ --silent             Only critical errors will be printed                            │
│ --version  -V        Show the version and exit.                                      │
│ --help               Show this message and exit.                                     │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

# Feedback
Your feedback is very valuable! If you run into any issues using Bactopia, have questions, or have some ideas to improve Bactopia, I highly encourage you to submit it to the [Issue Tracker](https://github.com/bactopia/bactopia/issues).

# License
[MIT License](https://raw.githubusercontent.com/bactopia/bactopia/master/LICENSE)

# Citation

Petit III RA, Read TD, *Bactopia: a flexible pipeline for complete analysis of bacterial genomes.* __mSystems__. 5 (2020), https://doi.org/10.1128/mSystems.00190-20.

# Author

* Robert A. Petit III
* Twitter: [@rpetit3](https://twitter.com/rpetit3)
