import logging
import os
import sys
import time
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.utils import execute, validate_file

BACTOPIA_CACHEDIR = os.getenv("BACTOPIA_CACHEDIR", f"{Path.home()}/.bactopia")
CONDA_CACHEDIR = os.getenv("NXF_CONDA_CACHEDIR", f"{BACTOPIA_CACHEDIR}/conda")
SINGULARITY_CACHEDIR = os.getenv(
    "NXF_SINGULARITY_CACHEDIR", f"{BACTOPIA_CACHEDIR}/singularity"
)

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-download": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Build Related Options",
            "options": [
                "--envtype",
                "--wf",
                "--build-all",
                "--build-nfcore",
                "--condadir",
                "--use-conda",
                "--singularity_cache",
                "--singularity_pull_docker_container",
                "--force-rebuild",
                "--max_retry",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--verbose",
                "--silent",
                "--version",
                "--help",
            ],
        },
    ]
}
BUILT_ALREADY = {"conda": {}, "singularity": {}}


def cleanup_value(value):
    """Remove some characters Nextflow param values"""
    if value.startswith("["):
        # return a list
        return value.lstrip("[").rstrip("]").replace("'", "").replace(",", "").split()
    elif value == "true" or value == "false":
        return bool(value)
    else:
        return value.lstrip("'").rstrip("'").replace("\\", "")


def parse_module(main_nf):
    """Pull out the Conda, Docker and singularity info"""
    envs = {}
    with open(main_nf, "rt") as main_fh:
        read_container = 0
        for line in main_fh:
            line = line.strip()
            if line.startswith("conda_tools"):
                # Conda
                envs["conda"] = (
                    line.replace("conda_tools", "")
                    .lstrip()
                    .replace("= ", "")
                    .replace('"', "")
                )
            elif line.startswith("container") and "containerEngine" in line:
                # Next two lines are singularity and docker
                read_container = 1
            elif line.startswith("container"):
                # There is not singularity image
                envs["singularity"] = False
                envs["docker"] = line.replace("container ", "").replace("'", "")
            elif read_container == 1:
                # Galaxy Project image
                envs["singularity"] = line.replace("'", "").split(" ")[0].strip()
                read_container = 2
            elif read_container == 2:
                # Biocontainer
                envs["docker"] = line.replace("'", "").replace('}"', "").strip()
                read_container = 0
    return envs


def parse_workflows(bactopia_path, include_merlin=False, build_all=False):
    """Parse Bactopia's workflows.conf to get modules per-workflow"""
    workflows = {}
    available_workflows = []
    nf_config, stderr = execute(
        f"nextflow config -flat {bactopia_path}/main.nf", capture=True
    )
    for line in nf_config.split("\n"):
        if line.startswith("params.available_workflows.") or line.startswith(
            "params.workflows."
        ):
            param, val = line.split(" = ")
            if line.startswith("params.available_workflows."):
                # Available workflow definitions
                for wf in cleanup_value(val):
                    available_workflows.append(wf)
            elif line.startswith("params.workflows."):
                # Workflow definitions
                wf, key = param.replace("params.workflows.", "").split(".")
                if wf not in workflows:
                    workflows[wf] = {}
                workflows[wf][key] = cleanup_value(val)

    # Merged the two
    final_workflows = {}
    for wf in available_workflows:
        final_workflows[wf] = {}
        modules = {}
        if "includes" in workflows[wf]:
            for include in workflows[wf]["includes"]:
                if "modules" in workflows[include]:
                    for module in workflows[include]["modules"]:
                        modules[module] = True
        if "modules" in workflows[wf]:
            for module in workflows[wf]["modules"]:
                modules[module] = True
        if "path" in workflows[wf]:
            modules[wf] = True

        if include_merlin and wf == "bactopia":
            for module in workflows["merlin"]["modules"]:
                modules[module] = True

        for module in modules:
            final_workflows[wf][module] = parse_module(
                f'{bactopia_path}/{workflows[module]["path"]}/main.nf'
            )

        final_workflows[wf]["custom_dumpsoftwareversions"] = parse_module(
            f'{bactopia_path}/{workflows["custom_dumpsoftwareversions"]["path"]}/main.nf'
        )
        final_workflows[wf]["csvtk_concat"] = parse_module(
            f'{bactopia_path}/{workflows["csvtk_concat"]["path"]}/main.nf'
        )

    return final_workflows


def build_env(
    envname: str,
    envinfo: dict,
    conda_path: str,
    conda_method: str,
    singularity_path: str,
    env_type: str,
    force: bool = False,
    max_retry: int = 5,
    use_build: bool = False,
) -> None:
    """
    Build a Conda, Docker, and/or Singularity environment

    Args:
        envname (str): The module for which to build the environment
        envinfo (dict): Information about Conda, Docker, and Singularity builds
        conda_path (str): Path to build Conda environments
        conda_method (str): Whether to use Conda or Mamba
        singularity_path (str): Path to build Singularity images
        env_type (str): Which environment types to build
        force (bool, optional): Force a rebuild if existing, Defaults to False.
        max_retry (int, optional): Maximum number of retries, Defaults to 5.
        use_build (bool, optional): Use 'singularity build' Defaults to False.
    """
    # Determine which environment types to build
    build_conda = True if env_type == "conda" or env_type == "all" else False
    build_docker = True if env_type == "docker" or env_type == "all" else False
    build_singularity = (
        True if env_type == "singularity" or env_type == "all" else False
    )

    # Conda
    # ISMapper is a special case, must always use conda
    conda_method = "conda" if envname == "ismapper" else conda_method
    conda_envname = (
        envinfo["conda"].replace("=", "-").replace(":", "-").replace(" ", "-")
    )
    conda_prefix = f"{conda_path}/{conda_envname}"

    singularity_name = None
    if use_build:
        singularity_name = envinfo["docker"].replace(":", "-").replace("/", "-")
    elif not envinfo["singularity"]:
        singularity_name = envinfo["docker"].replace(":", "-").replace("/", "-")
        use_build = True
    else:
        singularity_name = (
            envinfo["singularity"]
            .replace("https://", "")
            .replace(":", "-")
            .replace("/", "-")
        )

    # Check for completion files
    singularity_img = f"{singularity_path}/{singularity_name}.img"
    conda_complete = f"{conda_path}/{conda_envname}/env-built.txt"

    # Check if Conda build is needed
    if build_conda and Path(conda_complete).exists():
        if conda_prefix in BUILT_ALREADY["conda"]:
            logging.debug(BUILT_ALREADY["conda"][conda_prefix])
            build_conda = False
        elif force:
            logging.debug(f"Overwriting existing Conda environment in {conda_prefix}")
        else:
            logging.debug(
                f"Found Conda environment in {conda_prefix}, if a complete rebuild is needed please use --force_rebuild"
            )
            build_conda = False

    # Check if Docker build is needed
    if build_docker and not needs_docker_pull(envinfo["docker"]):
        if not force:
            logging.debug(
                f"Found Docker container for {envinfo['docker']}, if a complete rebuild is needed please manually remove the containers"
            )
            build_docker = False

    # Check if Singularity build is needed
    if build_singularity and Path(singularity_img).exists():
        if singularity_img in BUILT_ALREADY["singularity"]:
            logging.debug(BUILT_ALREADY["singularity"][singularity_img])
            build_singularity = False
        elif force:
            logging.debug(f"Overwriting existing Singularity image {singularity_img}")
        else:
            logging.debug(
                f"Found Singularity image {singularity_img}, if a complete rebuild is needed please use --force_rebuild"
            )
            build_singularity = False

    if build_conda:
        # Build necessary Conda environments
        logging.info(f"Begin {envname} create to {conda_prefix}")
        build_conda_env(
            conda_method, envinfo["conda"], conda_prefix, max_retry=max_retry
        )
        execute(f"date > {conda_complete}")
        BUILT_ALREADY["conda"][
            conda_prefix
        ] = f"Already built {envname} ({conda_prefix}) this run, skipping rebuild"

    if build_docker:
        # Pull necessary Docker containers
        if needs_docker_pull(envinfo["docker"]):
            logging.info(f"Begin docker pull of {envinfo['docker']}")
            docker_pull(envinfo["docker"], max_retry=max_retry)

    if build_singularity:
        # Build necessary Singularity images
        if needs_singularity_build(singularity_img, force=force):
            execute(f"mkdir -p {singularity_path}")
            if use_build:
                logging.info(f"Begin {envname} build to {singularity_img}")
                build_singularity_image(
                    singularity_img,
                    f"docker://{envinfo['docker']}",
                    max_retry=max_retry,
                    force=force,
                    use_build=use_build,
                )
            else:
                logging.info(f"Begin {envname} download to {singularity_img}")
                build_singularity_image(
                    singularity_img,
                    envinfo["singularity"],
                    max_retry=max_retry,
                    force=force,
                    use_build=use_build,
                )
            BUILT_ALREADY["singularity"][
                singularity_img
            ] = f"Already built {envname} ({singularity_img}) this run, skipping rebuild"


def check_md5sum(expected_md5, current_md5):
    """Compare the two md5 files to see if a rebuild is needed."""
    expected = None
    current = None
    with open(expected_md5, "r") as f:
        expected = f.readline().rstrip()

    with open(current_md5, "r") as f:
        current = f.readline().rstrip()

    return expected == current


def needs_conda_create(observed_md5, expected_md5, prefix, force=False):
    """Check if a new Conda environment needs to be built."""
    needs_build = False
    if Path(observed_md5).exists() and not force:
        if check_md5sum(expected_md5, observed_md5):
            logging.debug(
                f"Existing env ({prefix}) found, skipping unless --force is used"
            )
        else:
            logging.debug(f"Existing env ({prefix}) is out of sync, it will be updated")
            needs_build = True
    elif prefix in BUILT_ALREADY["conda"]:
        logging.debug(BUILT_ALREADY["conda"][prefix])
    else:
        needs_build = True
    return needs_build


def needs_docker_pull(pull_name):
    """Check if a new container needs to be pulled."""
    output = execute(f"docker inspect {pull_name} || true", capture=True)
    if output[1].startswith("Error: No such object"):
        return True
    logging.debug(
        f"Existing container ({pull_name}) found, skipping unless manually removed"
    )
    return False


def needs_singularity_build(image, force=False):
    """Check if a new image needs to be built."""
    if Path(image).exists() and not force:
        logging.debug(
            f"Existing image ({image}) found, skipping unless --force is used"
        )
        return False
    elif image in BUILT_ALREADY["singularity"]:
        logging.debug(BUILT_ALREADY["singularity"][image])
        return False
    return True


def build_conda_env(
    program: str, conda_env: str, conda_path: str, max_retry: int = 5
) -> bool:
    """Build Conda env, with chance to retry."""
    retry = 0
    allow_fail = False
    success = False
    while not success:
        result = execute(
            f"{program} create -y -p {conda_path} -c conda-forge -c bioconda --force {conda_env}",
            allow_fail=allow_fail,
        )
        if not result:
            if retry > max_retry:
                allow_fail = True
            retry += 1
            logging.error(
                "Error creating Conda environment, retrying after short sleep."
            )
            time.sleep(30 * retry)
        else:
            success = True
    return success


def docker_pull(container, max_retry=5):
    """Pull docker container, with chance to retry."""
    retry = 0
    allow_fail = False
    success = False
    while not success:
        result = execute(f"docker pull {container}", allow_fail=allow_fail)
        if not result:
            if retry > max_retry:
                allow_fail = True
            retry += 1
            logging.error("Error pulling container, retrying after short sleep.")
            time.sleep(30 * retry)
        else:
            success = True
    return success


def build_singularity_image(image, pull, max_retry=5, force=False, use_build=False):
    """Build Conda env, with chance to retry."""
    force = "--force" if force else ""
    retry = 0
    allow_fail = False
    success = False
    while not success:
        result = None
        if use_build:
            result = execute(
                f"singularity build {force} {image} {pull}", allow_fail=allow_fail
            )
        else:
            # Download from Galaxy Project
            result = execute(f"wget --quiet -O {image} {pull}", allow_fail=allow_fail)
        if not result:
            if retry > max_retry:
                allow_fail = True
            retry += 1
            logging.error("Error creating image, retrying after short sleep.")
            time.sleep(30 * retry)
        else:
            success = True
    return success


@click.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@click.version_option(bactopia.__version__, "--version")
# Use underscores in parameters and only --, since Nextflow parameters are passed in
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--envtype",
    default="conda",
    show_default=True,
    type=click.Choice(["conda", "docker", "singularity", "all"], case_sensitive=False),
    help="The type of environment to build.",
)
@click.option(
    "--wf",
    default="bactopia",
    show_default=True,
    help="Build a environment for a the given workflow",
)
@click.option(
    "--build-all",
    is_flag=True,
    help="Builds all environments for Bactopia workflows",
)
@click.option(
    "--build-nfcore",
    is_flag=True,
    help="Builds all nf-core related environments",
)
@click.option(
    "--condadir",
    default=CONDA_CACHEDIR,
    show_default=True,
    help="Directory to create Conda environments (NXF_CONDA_CACHEDIR env variable takes precedence)",
)
@click.option(
    "--use-conda",
    is_flag=True,
    help="Use Conda for building Conda environments instead of Mamba",
)
@click.option(
    "--singularity_cache",
    default=SINGULARITY_CACHEDIR,
    show_default=True,
    help="Directory to download Singularity images (NXF_SINGULARITY_CACHEDIR env variable takes precedence)",
)
@click.option(
    "--singularity_pull_docker_container",
    is_flag=True,
    help="Force conversion of Docker containers, instead downloading Singularity images directly",
)
@click.option(
    "--force-rebuild",
    is_flag=True,
    help="Force overwrite of existing pre-built environments.",
)
@click.option(
    "--max_retry",
    default=3,
    help="Maximum times to attempt creating Conda environment. (Default: 3)",
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
@click.argument("unknown", nargs=-1, type=click.UNPROCESSED)
def download(
    bactopia_path,
    envtype,
    wf,
    build_all,
    build_nfcore,
    singularity_cache,
    singularity_pull_docker_container,
    condadir,
    use_conda,
    force_rebuild,
    max_retry,
    verbose,
    silent,
    unknown,
):
    """Builds Bactopia environments for use with Nextflow."""
    # Setup logs
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )

    # Install paths
    bactopia_path = str(Path(bactopia_path).absolute())
    conda_path = str(Path(condadir).absolute())
    singularity_path = str(Path(singularity_cache).absolute())
    conda_method = "conda" if use_conda else "mamba"

    # Current Bactopia workflows
    include_merlin = True if "--ask_merlin" in unknown else False
    workflow_modules = parse_workflows(
        bactopia_path, include_merlin=include_merlin, build_all=build_all
    )

    if wf not in workflow_modules:
        # Let nextflow handle unknown workflows
        logging.error(f"{wf} is not a known workflow, skipping")
        sys.exit()

    logging.info(
        "Checking if environment pre-builds are needed (this may take a while if building for the first time)"
    )
    for workflow, modules in workflow_modules.items():
        if workflow == wf or build_all or build_nfcore:
            logging.debug(f"Working on {workflow} (--wf)")
            for module, info in modules.items():
                logging.debug(f"Building required environment: {module}")
                build_env(
                    module,
                    info,
                    conda_path,
                    conda_method,
                    singularity_path,
                    envtype,
                    force=force_rebuild,
                    max_retry=max_retry,
                    use_build=singularity_pull_docker_container,
                )


def main():
    if len(sys.argv) == 1:
        download.main(["--help"])
    else:
        download()


if __name__ == "__main__":
    main()
