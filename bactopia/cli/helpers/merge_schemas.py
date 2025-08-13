import json
import logging
import os
import sys
import time
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from jinja2 import Environment, FileSystemLoader
from rich.logging import RichHandler

import bactopia
from bactopia.parsers.generic import parse_json, parse_yaml

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    # Use underscores in parameters, since these are also passed to Nextflow
    "bactopia-merge-schemas": [
        {
            "name": "Required Options",
            "options": [
                "--bactopia-path",
                "--wf",
            ],
        },
        {
            "name": "Output Options",
            "options": [
                "--outdir",
                "--force",
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
    required=True,
    help="The workflow to create a nextflow_schema.json for.",
)
@click.option(
    "--outdir",
    type=click.Path(),
    default=".",
    help="Directory to write output files to",
)
@click.option("--force", is_flag=True, help="Overwrite existing output files")
@click.option("--verbose", is_flag=True, help="Print debug related text.")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed.")
@click.argument("unknown", nargs=-1, type=click.UNPROCESSED)
def merge_schemas(
    bactopia_path,
    wf,
    outdir,
    force,
    verbose,
    silent,
    unknown,
):
    """Builds a Nextflow Schema and/or Nextflow config for a given workflow."""
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

    # bactopia paths
    bactopia_path = str(Path(bactopia_path).absolute())

    # Set up output directory and files
    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)

    schema_file = f"{outdir_path}/nextflow_schema.json"
    config_file = f"{outdir_path}/nextflow.config"

    # Check if files exist and handle accordingly
    if Path(schema_file).exists() and not force:
        logging.error(
            f"Output file {schema_file} already exists. Use --force to overwrite."
        )
        sys.exit(1)

    if Path(config_file).exists() and not force:
        logging.error(
            f"Output file {config_file} already exists. Use --force to overwrite."
        )
        sys.exit(1)

    # parse the workflows
    workflows = parse_yaml(f"{bactopia_path}/conf/workflows.yaml")

    if wf not in workflows["workflows"]:
        # Let nextflow handle unknown workflows
        logging.error(f"{wf} is not a known workflow, skipping")
        sys.exit()

    # Get the modules associated with the workflow
    modules = []
    if "modules" in workflows["workflows"][wf]:
        modules = workflows["workflows"][wf]["modules"]

    final_schema = None
    # determine if this is Bactopia, named workflow or a Bactopia Tool
    is_workflow = workflows["workflows"][wf].get("is_workflow", False)
    if is_workflow:
        if wf == "bactopia":
            # This is the Bactopia workflow
            final_schema = parse_json(f"{bactopia_path}/conf/schema/bactopia.json")
        else:
            # This is a named workflow
            final_schema = parse_json(f"{bactopia_path}/conf/schema/{wf}.json")
    else:
        # This is a Bactopia Tool
        final_schema = parse_json(f"{bactopia_path}/conf/schema/bactopia-tools.json")

    # Set some defaults
    final_schema["title"] = wf
    final_schema["description"] = workflows["workflows"][wf]["description"]

    for module in modules:
        # Get the schema for each module
        # Modules follow a standard path pattern where underscores become slashes
        # e.g., abricate_run -> abricate/run, mlst -> mlst
        module_path = f"modules/{module.replace('_', '/')}"
        schema = parse_json(f"{bactopia_path}/{module_path}/schema.json")

        # determine if the module schema has a required field, that should be moved to
        # final_schema['$defs']['input_parameters']['properties'], then removed from the
        # module schema
        for definition in schema["$defs"]:
            for property, vals in schema["$defs"][definition]["properties"].items():
                # Check if the property is required
                if "is_required" in property:
                    final_schema["$defs"]["input_parameters"]["properties"][
                        property
                    ] = vals
                    del schema["$defs"][definition]["properties"][property]

            # add the definitions to the final schema
            if definition not in final_schema["$defs"]:
                final_schema["$defs"][definition] = schema["$defs"][definition]
            else:
                # raise an error if the definitions are the same
                logging.error(
                    f"Duplicate definition ({definition}) found will parsing the following modules: {module}"
                )
                sys.exit(1)

        final_schema["allOf"].extend(schema["allOf"])

    # Add the final generic schema to the end of the final schema
    generic_schema = parse_json(f"{bactopia_path}/conf/schema/generic.json")
    final_schema["$defs"].update(generic_schema["$defs"])
    final_schema["allOf"].extend(generic_schema["allOf"])

    # Write the final schema to file
    with open(schema_file, "w") as f:
        json.dump(final_schema, f, indent=4, separators=(",", ": "))
    logging.info(f"Generated nextflow_schema.json at {schema_file}")

    # Generate Nextflow config file
    # Set up Jinja2 environment
    template_dir = Path(__file__).parent.parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("nextflow-config.j2")

    # Determine logo_name based on is_workflow
    logo_name = wf if is_workflow else "bactopia-tools"

    # Build module paths dictionary
    module_paths = {}
    for module in modules:
        # All modules follow the standard path pattern where underscores become slashes
        module_paths[module] = f"modules/{module.replace('_', '/')}"

    # Render the template
    config_content = template.render(
        workflow_name=wf,
        logo_name=logo_name,
        description=workflows["workflows"][wf]["description"],
        ext=workflows["workflows"][wf].get("ext", None),
        modules=modules,
        module_paths=module_paths,
    )

    # Write the config to file
    with open(config_file, "w") as f:
        f.write(config_content)
    logging.info(f"Generated nextflow.config at {config_file}")


def main():
    if len(sys.argv) == 1:
        merge_schemas.main(["--help"])
    else:
        merge_schemas()


if __name__ == "__main__":
    main()
