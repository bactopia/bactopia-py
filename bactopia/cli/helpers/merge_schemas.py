import json
import logging
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from jinja2 import Environment, FileSystemLoader
from rich.logging import RichHandler

import bactopia
import bactopia.parsers.nextflow as nf_parsers
from bactopia.parsers.generic import parse_json, parse_yaml
from bactopia.parsers.workflows import get_modules_by_workflow

MODULE_PRIORITY = [
    "csvtk_concat",
    "csvtk_join",
    "wget",
]

SHOW_PARAMETERS = [
    "input_parameters",
    "assembler_parameters",
    "dataset_parameters",
    "gather_parameters",
    "qc_parameters",
    "sketcher_parameters",
    "optional_parameters",
    "max_job_request_parameters",
    "nextflow_parameters",
    "nextflow_profile_parameters",
    "generic_parameters",
]

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
    params_file = f"{outdir_path}/params.config"
    process_file = f"{outdir_path}/process.config"
    nf_config_file = f"{outdir_path}/nextflow.config"

    # Check if files exist and handle accordingly
    for file in [schema_file, params_file, process_file, nf_config_file]:
        if Path(file).exists() and not force:
            logging.error(
                f"Output file {file} already exists. Use --force to overwrite."
            )
            sys.exit(1)

    # parse the workflows
    workflows = parse_yaml(f"{bactopia_path}/conf/workflows.yaml")

    if wf not in workflows["workflows"]:
        # Let nextflow handle unknown workflows
        logging.error(f"{wf} is not a known workflow, skipping")
        sys.exit()

    # Get the modules associated with the workflow
    modules = get_modules_by_workflow(wf, workflows)
    logging.info(f"Modules associated with {wf}: {', '.join(modules)}")

    final_schema = None
    # determine if this is Bactopia, named workflow or a Bactopia Tool
    is_workflow = workflows["workflows"][wf].get("is_workflow", False)
    if is_workflow:
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
            if schema["$defs"][definition]["properties"]:
                for property, vals in schema["$defs"][definition]["properties"].items():
                    # Set hidden
                    if is_workflow and definition not in SHOW_PARAMETERS:
                        schema["$defs"][definition]["properties"][property][
                            "hidden"
                        ] = True
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
                        f"Duplicate definition ({definition}) found while parsing the following modules: {module}"
                    )
                    sys.exit(1)

                final_schema["allOf"].extend(schema["allOf"])
            else:
                logging.warning(
                    f"No properties found in definition ({definition}) while parsing the following module: {module}"
                )

    # Add the final generic schema to the end of the final schema
    generic_schema = parse_json(f"{bactopia_path}/conf/schema/generic.json")
    final_schema["$defs"].update(generic_schema["$defs"])
    final_schema["allOf"].extend(generic_schema["allOf"])

    # Write the final schema to file
    with open(schema_file, "w") as f:
        json.dump(final_schema, f, indent=4, separators=(",", ": "))
    logging.info(f"Generated nextflow_schema.json at {schema_file}")

    # Generate Nextflow config files

    # Determine logo_name based on is_workflow
    logo_name = wf if is_workflow else "bactopia-tools"

    # Build module paths dictionary
    module_paths = {}
    depth = len(workflows["workflows"][wf]["path"].split("/"))
    include_prefix = "./" if depth == 1 else "../" * depth
    logging.debug(f"Include prefix: {include_prefix} ({depth})")
    for module in modules:
        module_paths[module] = f"{include_prefix}modules/{module.replace('_', '/')}"

    # Reorder modules list based on priority
    config_modules = []
    for priority_module in MODULE_PRIORITY:
        if priority_module in modules:
            config_modules.append(priority_module)
    for module in modules:
        if module not in config_modules:
            config_modules.append(module)

    # Parse config files
    base = f"{include_prefix}conf/base.config"
    profiles = f"{include_prefix}conf/profiles.config"

    generic_params = []
    generic_params.append(f"{include_prefix}conf/params.config")

    extra_wf = None
    if is_workflow:
        if wf != "bactopia":
            extra_wf = f"{include_prefix}conf/params/{wf}.config"
        generic_params.append(f"{include_prefix}conf/params/bactopia.config")
    else:
        generic_params.append(f"{include_prefix}conf/params/bactopia-tools.config")

    # Generate Nextflow config file
    # Set up Jinja2 environment
    template_dir = Path(__file__).parent.parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))
    nf_template = env.get_template("nextflow/nextflow.config.j2")

    # nextflow.config
    nf_config_content = nf_template.render(
        workflow_name=wf,
        logo_name=logo_name,
        description=workflows["workflows"][wf]["description"],
        ext=workflows["workflows"][wf].get("ext", None),
        generic_params=generic_params,
        modules=config_modules,
        module_paths=module_paths,
        base=base,
        profiles=profiles,
        extra_wf=extra_wf,
    )

    # Write the config to file
    with open(nf_config_file, "w") as f:
        f.write(nf_config_content)
    logging.info(f"Generated nextflow.config at {nf_config_file}")


def main():
    if len(sys.argv) == 1:
        merge_schemas.main(["--help"])
    else:
        merge_schemas()


if __name__ == "__main__":
    main()
