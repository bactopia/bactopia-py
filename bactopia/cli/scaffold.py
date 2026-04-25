"""Scaffold Bactopia components from bioconda/conda-forge packages."""

import json
import logging
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia
from bactopia.cli.common import setup_logging
from bactopia.conda import (
    check_component_exists,
    construct_container_refs,
    get_latest_info_with_fallback,
)
from bactopia.scaffold import (
    FIELD_PATTERNS,
    discover_test_data,
    render_all_files,
    render_module_files,
    render_subworkflow_files,
    render_workflow_files,
    validate_config,
    write_files,
)

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-scaffold": [
        {"name": "Commands", "options": []},
        {
            "name": "Additional Options",
            "options": ["--verbose", "--silent", "--version", "--help"],
        },
    ],
    "bactopia-scaffold lookup": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Query Options",
            "options": ["--channel", "--max-retry"],
        },
        {
            "name": "Output Options",
            "options": ["--json", "--pretty"],
        },
        {
            "name": "Additional Options",
            "options": ["--verbose", "--silent", "--help"],
        },
    ],
    "bactopia-scaffold test-data": [
        {"name": "Required Options", "options": ["--input-type", "--bactopia-path"]},
        {
            "name": "Output Options",
            "options": ["--json", "--pretty"],
        },
        {
            "name": "Additional Options",
            "options": ["--verbose", "--silent", "--help"],
        },
    ],
}


@click.group()
@click.version_option(bactopia.__version__, "--version", "-V")
def scaffold():
    """Scaffold Bactopia components from bioconda/conda-forge packages."""
    pass


@scaffold.command()
@click.argument("package")
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--channel",
    default=None,
    help="Force a specific channel (bioconda or conda-forge). Default: try bioconda first, then conda-forge",
)
@click.option(
    "--max-retry",
    default=3,
    help="Maximum times to attempt API queries. (Default: 3)",
)
@click.option("--json", "output_json", is_flag=True, help="Output flat JSON")
@click.option("--pretty", is_flag=True, help="Output pretty-printed JSON")
@click.option("--verbose", is_flag=True, help="Print debug related text")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def lookup(
    package, bactopia_path, channel, max_retry, output_json, pretty, verbose, silent
):
    """Look up package info from Anaconda and check for existing components."""
    setup_logging(verbose, silent)

    bactopia_path = str(Path(bactopia_path).absolute())
    logging.debug(f"Using bactopia path: {bactopia_path}")

    if channel:
        from bactopia.conda import get_latest_info

        info = get_latest_info(package, max_retry=max_retry, channel=channel)
        if info:
            info["channel"] = channel
    else:
        info = get_latest_info_with_fallback(package, max_retry=max_retry)

    if info is None:
        logging.error(f"Package '{package}' not found on bioconda or conda-forge.")
        sys.exit(1)

    refs = construct_container_refs(package, info["version"], info["build"])
    existing = check_component_exists(bactopia_path, package)

    result = {
        "package": package,
        "channel": info.get("channel", "bioconda"),
        "version": info["version"],
        "build": info["build"],
        "summary": info.get("summary", ""),
        "home": info.get("home", ""),
        "container_refs": refs,
        "existing_components": existing,
    }

    if output_json:
        print(json.dumps(result))
    elif pretty:
        print(json.dumps(result, indent=2))
    else:
        print(f"Package:    {result['package']}")
        print(f"Channel:    {result['channel']}")
        print(f"Version:    {result['version']}")
        print(f"Build:      {result['build']}")
        print(f"Summary:    {result['summary']}")
        print(f"Home:       {result['home']}")
        print()
        print("Container References:")
        print(f"  toolName: {refs['toolName']}")
        print(f"  docker:   {refs['docker']}")
        print(f"  image:    {refs['image']}")
        print()
        print("Existing Components:")
        for component, exists in existing.items():
            status = "EXISTS" if exists else "not found"
            print(f"  {component}: {status}")


@scaffold.command("test-data")
@click.option(
    "--input-type",
    required=True,
    type=click.Choice(sorted(FIELD_PATTERNS.keys())),
    help="Input type to search for in existing tests",
)
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option("--json", "output_json", is_flag=True, help="Output flat JSON")
@click.option("--pretty", is_flag=True, help="Output pretty-printed JSON")
@click.option("--verbose", is_flag=True, help="Print debug related text")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def test_data(input_type, bactopia_path, output_json, pretty, verbose, silent):
    """Discover test data paths from existing module tests."""
    setup_logging(verbose, silent)
    bactopia_path = Path(bactopia_path).absolute()

    results = discover_test_data(bactopia_path, input_type)

    output = {"input_type": input_type, "test_data": results}

    if output_json:
        print(json.dumps(output))
    elif pretty:
        print(json.dumps(output, indent=2))
    else:
        print(f"Input type: {input_type}")
        print(f"Found {len(results)} species/accession combinations:\n")
        for entry in results:
            print(f"  {entry['species']}/{entry['accession']}")
            print(f"    Used by: {', '.join(entry['modules_using'])}")
            print(f"    compressed:   {'yes' if entry['has_compressed'] else 'no'}")
            print(f"    uncompressed: {'yes' if entry['has_uncompressed'] else 'no'}")
            print(f"    test_data_path:        {entry['test_data_path']}")
            print(f"    test_uncompressed_path: {entry['test_uncompressed_path']}")
            if entry["datasets"]:
                print(f"    datasets: {', '.join(entry['datasets'])}")
            print()


def _run_generate(
    config_path,
    bactopia_path,
    dry_run,
    output_json,
    pretty,
    verbose,
    silent,
    tier,
    render_fn,
):
    """Shared logic for module/subworkflow/tool subcommands."""
    setup_logging(verbose, silent)
    bactopia_path = Path(bactopia_path).absolute()

    with open(config_path) as f:
        config = json.load(f)

    errors = validate_config(config, tier)
    if errors:
        for err in errors:
            logging.error(err)
        sys.exit(1)

    # Inject container_refs if not already present
    if "container_refs" not in config:
        config["container_refs"] = construct_container_refs(
            config["package"], config["version"], config.get("build")
        )

    files = render_fn(config, bactopia_path)
    created = write_files(files, bactopia_path, dry_run=dry_run)

    result = {"tier": tier, "created_files": created, "dry_run": dry_run}
    if output_json:
        print(json.dumps(result))
    elif pretty:
        print(json.dumps(result, indent=2))
    else:
        action = "Would create" if dry_run else "Created"
        print(f"{action} {len(created)} files:")
        for path in created:
            print(f"  {path}")


@scaffold.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="JSON design config file",
)
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be created without writing files"
)
@click.option("--json", "output_json", is_flag=True, help="Output flat JSON")
@click.option("--pretty", is_flag=True, help="Output pretty-printed JSON")
@click.option("--verbose", is_flag=True, help="Print debug related text")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def module(config_path, bactopia_path, dry_run, output_json, pretty, verbose, silent):
    """Generate module files from a design config."""
    _run_generate(
        config_path,
        bactopia_path,
        dry_run,
        output_json,
        pretty,
        verbose,
        silent,
        "module",
        render_module_files,
    )


@scaffold.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="JSON design config file",
)
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be created without writing files"
)
@click.option("--json", "output_json", is_flag=True, help="Output flat JSON")
@click.option("--pretty", is_flag=True, help="Output pretty-printed JSON")
@click.option("--verbose", is_flag=True, help="Print debug related text")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def subworkflow(
    config_path, bactopia_path, dry_run, output_json, pretty, verbose, silent
):
    """Generate subworkflow files from a design config."""
    _run_generate(
        config_path,
        bactopia_path,
        dry_run,
        output_json,
        pretty,
        verbose,
        silent,
        "subworkflow",
        render_subworkflow_files,
    )


@scaffold.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="JSON design config file",
)
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be created without writing files"
)
@click.option("--json", "output_json", is_flag=True, help="Output flat JSON")
@click.option("--pretty", is_flag=True, help="Output pretty-printed JSON")
@click.option("--verbose", is_flag=True, help="Print debug related text")
@click.option("--silent", is_flag=True, help="Only critical errors will be printed")
def tool(config_path, bactopia_path, dry_run, output_json, pretty, verbose, silent):
    """Generate all three tiers (module + subworkflow + workflow) for a bactopia-tool."""
    _run_generate(
        config_path,
        bactopia_path,
        dry_run,
        output_json,
        pretty,
        verbose,
        silent,
        "tool",
        render_all_files,
    )


def main():
    if len(sys.argv) == 1:
        scaffold.main(["--help"])
    else:
        scaffold()


if __name__ == "__main__":
    main()
