[![Gitpod ready-to-code](https://img.shields.io/badge/Gitpod-ready--to--code-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/bactopia/bactopia-py)

![Bactopia Logo](https://raw.githubusercontent.com/bactopia/bactopia/master/data/bactopia-logo.png)

# bactopia-py
A Python package for working with [Bactopia](https://bactopia.github.io/)

## Bactopia Subcommands

There are many subcommands available in Bactopia. Here is a brief description of each command:

| Command              | Description                                                                |
|----------------------|----------------------------------------------------------------------------|
| `bactopia-citations` | Print out tools and citations used throughout Bactopia                     |
| `bactopia-datasets`  | Download optional datasets to supplement your analyses with Bactopia       |
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
│    --version        -V        Show the version and exit.                             │
│ *  --bactopia-path  -b  TEXT  Directory where Bactopia repository is stored          │
│                               [required]                                             │
│    --name           -n  TEXT  Only print citation matching a given name              │
│    --plain-text     -p        Disable rich formatting                                │
│    --help                     Show this message and exit.                            │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

### `bactopia-datasets`

```{bash}
 Usage: bactopia-datasets [OPTIONS] [UNKNOWN]...

 Download optional datasets to supplement your analyses with Bactopia

╭─ Required Options ───────────────────────────────────────────────────────────────────╮
│ *  --bactopia-path    TEXT  Directory where Bactopia repository is stored [required] │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Download Related Options ───────────────────────────────────────────────────────────╮
│ --datasets_cache    TEXT     Base directory to download datasets to (Defaults to env │
│                              variable BACTOPIA_CACHEDIR, a subfolder called datasets │
│                              will be created)                                        │
│                              [default: ${HOME}/.bactopia]                 │
│ --force                      Force overwrite of existing pre-built environments.     │
│ --max_retry         INTEGER  Maximum times to attempt creating Conda environment.    │
│                              (Default: 3)                                            │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Additional Options ─────────────────────────────────────────────────────────────────╮
│ --verbose      Print debug related text.                                             │
│ --silent       Only critical errors will be printed.                                 │
│ --version      Show the version and exit.                                            │
│ --help         Show this message and exit.                                           │
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
│ *  --bactopia-path  -b  TEXT  Directory where Bactopia results are stored [required] │
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

# All The Bacteria (ATB)

The [AllTheBacteria](https://www.biorxiv.org/content/10.1101/2024.03.08.584059v1) is a collection
of nearly 2,000,000 bacterial genomes. Using available FASTQ files from the European Nucleotide
Archive (ENA) and Sequence Read Archive (SRA), the genomes were assembled using [Shovill] and made
publicly available from the [Iqbal Lab](https://github.com/iqbal-lab-org/AllTheBacteria).

To make it easy to utilize [Bactopia Tools](https://bactopia.github.io/latest/bactopia-tools/) with
assemblies from AllTheBacteria, `bactopia-atb-formatter` was created. This tool will create a 
directory structure that resembles output from an actual Bactopia run.

### `bactopia-atb-formatter`

```{bash}
 Usage: bactopia-atb-formatter [OPTIONS]

 Restructure All-the-Bacteria assemblies to allow usage with Bactopia Tools

╭─ Required Options ───────────────────────────────────────────────────────────────────╮
│ *  --path  -p  TEXT  Directory where FASTQ files are stored [required]               │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Bactopia Directory Structure Options ───────────────────────────────────────────────╮
│ --bactopia-dir  -b  TEXT            The path you would like to place bactopia        │
│                                     structure                                        │
│                                     [default: bactopia]                              │
│ --publish-mode  -m  [symlink|copy]  Designates plascement of assemblies will be      │
│                                     handled                                          │
│                                     [default: symlink]                               │
│ --recursive     -r                  Traverse recursively through provided path       │
╰──────────────────────────────────────────────────────────────────────────────────────╯
╭─ Additional Options ─────────────────────────────────────────────────────────────────╮
│ --verbose        Increase the verbosity of output                                    │
│ --silent         Only critical errors will be printed                                │
│ --version  -V    Show the version and exit.                                          │
│ --help           Show this message and exit.                                         │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

### Example Usage for _Legionella pneumophila_

To demonstrate the usage of `bactopia-atb-formatter`, we will use assemblies for
_Legionella pneumophila_. The following steps will download the assemblies, build the
Bactopia directory structure, and then run [legsta](https://github.com/tseemann/legsta)
via the [Bactopia Tool](https://bactopia.github.io/latest/bactopia-tools/legsta/).

#### Download the Assemblies

First will download the _Legionella pneumophila_ assemblies from AllTheBacteria. After downloading
we will extract them into a folder called `legionella-assemblies`. Within this folder, there will be
subdirectories for each tarball that was downloaded.

```{bash}
mkdir atb-legionella
cd atb-legionella

# Download the assemblies
wget https://ftp.ebi.ac.uk/pub/databases/AllTheBacteria/Releases/0.1/assembly/legionella_pneumophila__01.asm.tar.xz
wget https://ftp.ebi.ac.uk/pub/databases/AllTheBacteria/Releases/0.1/assembly/legionella_pneumophila__02.asm.tar.xz

# Extract the assemblies
mkdir legionella-assemblies
tar -C legionella-assemblies -xJf legionella_pneumophila__01.asm.tar.xz
tar -C legionella-assemblies -xJf legionella_pneumophila__02.asm.tar.xz
```

#### Create the Bactopia Directory Structure

With the assemblies extracted, we can now create the Bactopia directory structure using
`bactopia-atb-formatter`. Once complete, each assembly will have its own folder created
which matches the BioSample accession of the assembly.

```{bash}
# Create the Bactopia directory structure
bactopia atb-formatter --path legionella-assemblies --recursive
2024-03-22 14:30:07 INFO     2024-03-22 14:30:07:root:INFO - Setting up Bactopia directory structure (use --verbose to see more details)                                                                                                                  atb_formatter.py:129
2024-03-22 14:30:08 INFO     2024-03-22 14:30:08:root:INFO - Bactopia directory structure created at bactopia                                                                                                                                             atb_formatter.py:134
                    INFO     2024-03-22 14:30:08:root:INFO - Total assemblies processed: 5393
```

Please note the usage of `--recursive` which will traverse the `legionella-assemblies` directory
to find all assemblies contained. At this point, the `bactopia` directory structure has been
created for 5,393 assemblies and is ready for use with Bactopia Tools.

#### Use Bactopia to run Legsta

As mentioned above, we will use [legsta](https://github.com/tseemann/legsta) to analyze each
of the _Legionella pneumophila_ assemblies. To do this, we will use the
[legsta Bactopia Tool](https://bactopia.github.io/latest/bactopia-tools/legsta/).

```{bash}
# Run legsta (please utilize Docker or Singularity only for reproducibility)
bactopia --wf legsta -profile singularity
```

Please note, for reproducibility, it is recommended to use Docker or Singularity with
Bactopia Tools.

Upon completion, you should be met with something like the following:

```{bash}

```

That's it! Now you can take advantage of any of the [Bactopia Tools](https://bactopia.github.io/latest/bactopia-tools/)
that utilize assemblies as inputs.

# Feedback
Your feedback is very valuable! If you run into any issues using Bactopia, have questions, or have some ideas to improve Bactopia, I highly encourage you to submit it to the [Issue Tracker](https://github.com/bactopia/bactopia/issues).

# License
[MIT License](https://raw.githubusercontent.com/bactopia/bactopia/master/LICENSE)

# Citation

Petit III RA, Read TD, *Bactopia: a flexible pipeline for complete analysis of bacterial genomes.* __mSystems__. 5 (2020), https://doi.org/10.1128/mSystems.00190-20.

# Author

* Robert A. Petit III
* Twitter: [@rpetit3](https://twitter.com/rpetit3)
