"""
Parsers for Nextflow related files.
"""
import logging

from bactopia.utils import validate_file


def parse(path: str, name: str, file_type: str) -> dict:
    """
    Parse the results of an assembler analysis.

    Output columns from assembly-scan: https://github.com/rpetit3/assembly-scan#output-columns

    Args:
        path (str): input file to be parsed
        name (str): the name of the file being parsed
        file_type (str): The type of Nextflow file to parse. One of: base, params, process, profiles

    Returns:
        dict: parsed results
    """
    path = validate_file(path)
    if file_type == "base":
        return _parse_base_config(path, name)
    elif file_type == "params":
        return _parse_params(path, name)
    elif file_type == "process":
        return _parse_process_config(path, name)
    elif file_type == "profiles":
        return _parse_profiles_config(path, name)
    else:
        raise ValueError(f"Unknown file_type: {file_type}")


def _parse_base_config(path: str, name: str) -> dict:
    """
    Parse a Nextflow profiles.config file into a string.

    Args:
        path (str): The path to the base.config file
        name (str): The name of the base (used for comments)

    Returns:
        dict: The parsed configuration as a dictionary
    """
    base_config = []
    logging.debug(f"Parsing profiles.config: {path}")
    with open(path, "rt") as f:
        for line in f:
            base_config.append(line)

    return {
        "name": name,
        "path": f"<bactopia-path>/{str(path).split('bactopia/')[1]}",
        "contents": "".join(base_config),
    }


def _parse_process_config(path: str, name: str) -> str:
    """
    Parse a Nextflow process.config file into a string.

    Args:
        path (str): The path to the process.config file
        name (str): The name of the process (used for comments)

    Example process.config content:
    /*
    This file includes default process values for sccmec.
    */

    process {
        withName: 'SCCMEC' {
            // Optional arguments
            ext.args = [
                "--min-targets-pident ${params.sccmec_min_targets_pident}",
                "--min-targets-coverage ${params.sccmec_min_targets_coverage}",
                "--min-regions-pident ${params.sccmec_min_regions_pident}",
                "--min-regions-coverage ${params.sccmec_min_regions_coverage}",
            ].join(' ').replaceAll("\\s{2,}", " ").trim()

            // Environment information
            ext.env = [
                toolName: "bioconda::sccmec=1.2.0".replace("=", "-").replace(":", "-").replace(" ", "-"),
                docker: "biocontainers/sccmec:1.2.0--hdfd78af_0",
                image: "https://depot.galaxyproject.org/singularity/sccmec:1.2.0--hdfd78af_0",
                condaDir: "${params.condadir}",
            ]

            ext.wf = params.wf
            ext.rundir = params.rundir
            ext.subdir = ""
            ext.logs_subdir = ""
            ext.process_name = "sccmec"
        }
    }

    Returns:
        string: The parsed configuration as a string
    """
    process_config = []
    read_process = False
    logging.debug(f"Parsing process.config: {path}")
    with open(path, "rt") as f:
        for line in f:
            line = line.rstrip()
            if line.startswith("process {"):
                read_process = True
            elif line == "}" and read_process:
                read_process = False
            elif read_process:
                process_config.append(line)
            else:
                continue

    return {
        "name": name,
        "path": f"<bactopia-path>/{str(path).split('bactopia/')[1]}",
        "contents": "\n".join(process_config),
    }


def _parse_profiles_config(path: str, name: str) -> dict:
    """
    Parse a Nextflow profiles.config file into a string.

    Args:
        path (str): The path to the profiles.config file
        name (str): The name of the profile (used for comments)

    Returns:
        dict: The parsed configuration as a dictionary
    """
    profiles_config = []
    logging.debug(f"Parsing profiles.config: {path}")
    with open(path, "rt") as f:
        for line in f:
            profiles_config.append(line)

    return {
        "name": name,
        "path": f"<bactopia-path>/{str(path).split('bactopia/')[1]}",
        "contents": "".join(profiles_config),
    }


def _parse_params(path: str, name: str) -> dict:
    """
    Parse a Nextflow params.config file into a dictionary.

    Args:
        path (str): The path to the params.config file
        name (str): The name of the params (used for comments)

    Example params.config content:
    /*
    This file includes default parameter values.
    */

    params {
        // sccmec
        sccmec_min_targets_pident = 90
        sccmec_min_targets_coverage = 80
        sccmec_min_regions_pident = 85
        sccmec_min_regions_coverage = 93
    }

    Returns:
        dict: The parsed parameters as a dictionary
    """
    params_config = []
    read_params = False
    logging.debug(f"Parsing params.config: {path}")
    with open(path, "rt") as f:
        for line in f:
            line = line.rstrip()
            if line.startswith("params {"):
                read_params = True
            elif line == "}" and read_params:
                read_params = False
            elif read_params:
                params_config.append(line)
            else:
                continue

    return {
        "name": name,
        "path": f"<bactopia-path>/{str(path).split('bactopia/')[1]}",
        "contents": "\n".join(params_config),
    }
