import logging
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.parsers.generic import parse_yaml
from bactopia.templates.logos import BACTOPIA_LOGO

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-workflows": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Workflow Related Options",
            "options": [
                "--wf",
                "--list_wfs",
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
    "--wf",
    default="bactopia",
    show_default=True,
    help="Build a environment for a the given workflow",
)
@click.option(
    "--list_wfs",
    is_flag=True,
    help="List available Bactopia workflows and exit.",
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
@click.argument("unknown", nargs=-1, type=click.UNPROCESSED)
def download(
    bactopia_path,
    wf,
    list_wfs,
    verbose,
    silent,
    unknown,
):
    """Output the path to a Bactopia workflow main.nf file."""
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
    if not Path(bactopia_path).exists():
        logging.error(f"Bactopia path {bactopia_path} does not exist.")
        sys.exit(1)
    bactopia_path = str(Path(bactopia_path).absolute().resolve())

    # Load the workflows.yaml file
    workflows = None
    if Path(f"{bactopia_path}/conf/workflows.yaml").exists():
        workflows_yaml = parse_yaml(f"{bactopia_path}/conf/workflows.yaml")
        workflows = workflows_yaml["workflows"]
    else:
        logging.error(
            f"'workflows.yaml' could not be found in {bactopia_path}/conf/, is this a valid Bactopia installation?"
        )
        sys.exit(1)

    # List available workflows in a table and exit
    if list_wfs:
        rich.print(BACTOPIA_LOGO)
        table = rich.table.Table(title="Available Workflows")
        table.add_column("Name", style="bold", width=15)
        table.add_column("Description", style="dim", width=65)
        for workflow in workflows:
            if "is_workflow" in workflows[workflow]:
                if workflows[workflow]["is_workflow"]:
                    table.add_row(workflow, workflows[workflow]["description"])
        rich.print(table)

        table = rich.table.Table(title="Available Bactopia Tools")
        table.add_column("Name", style="bold", width=15)
        table.add_column("Description", style="dim", width=65)
        for workflow in workflows:
            if "is_workflow" not in workflows[workflow]:
                table.add_row(workflow, workflows[workflow]["description"])
        rich.print(table)

        sys.exit(0)

    # Print the path to the workflow
    if wf in workflows:
        if wf == "bactopia":
            print(f"{bactopia_path}/main.nf")
        else:
            print(f"{bactopia_path}/{workflows[wf]['path']}/main.nf")
    else:
        logging.error(f"'{wf}' is not a known workflow, please verify workflow name")
        sys.exit(1)


def main():
    if len(sys.argv) == 1:
        download.main(["--help"])
    else:
        download()


if __name__ == "__main__":
    main()
