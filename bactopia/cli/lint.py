"""CLI command for linting Bactopia pipeline components."""

import json
import logging
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.logging import RichHandler

import bactopia
from bactopia.lint.runner import run_lint

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-lint": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Scope Options",
            "options": [
                "--modules",
                "--subworkflows",
                "--workflows",
                "--module",
                "--subworkflow",
                "--workflow",
            ],
        },
        {
            "name": "Output Options",
            "options": [
                "--quiet",
                "--json",
                "--pretty",
            ],
        },
        {
            "name": "Additional Options",
            "options": [
                "--verbose",
                "--version",
                "--help",
            ],
        },
    ]
}


def _status_style(status: str) -> str:
    """Return a Rich markup style for a status string."""
    if status == "PASS":
        return "[green]PASS[/green]"
    elif status == "WARN":
        return "[yellow]WARN[/yellow]"
    else:
        return "[red]FAIL[/red]"


def print_rich(
    console: rich.console.Console, data: dict, version: str, quiet: bool = False
):
    """Render lint results as Rich terminal output."""
    console.print(f"[bold]bactopia-lint[/bold] v{version}")
    console.print(f"Linting {data['bactopia_path']}\n")

    for tier_name, tier_components in data["components"].items():
        if not tier_components:
            continue

        shown = [c for c in tier_components if not quiet or c["status"] != "PASS"]
        checked = len(tier_components)
        console.print(f"[bold]{tier_name.title()}[/bold] ({checked} checked)")

        for comp in shown:
            component = comp["component"]
            status = comp["status"]
            style = _status_style(status)

            # Create dotted line between component name and status
            max_width = 60
            name_len = len(component)
            dots = "." * max(2, max_width - name_len)
            console.print(f"  {component} {dots} {style}")

            # Show details for non-PASS results
            non_pass = [r for r in comp["results"] if not r["is_pass"]]
            for r in non_pass:
                sev_style = (
                    "[yellow]WARN[/yellow]"
                    if r["severity"] == "WARN"
                    else "[red]FAIL[/red]"
                )
                console.print(f"    [{r['rule_id']}] {sev_style}: {r['message']}")

        console.print()

    # Summary
    s = data["summary"]
    console.print(
        f"[bold]Summary:[/bold] "
        f"[green]{s['pass']} PASS[/green] | "
        f"[yellow]{s['warn']} WARN[/yellow] | "
        f"[red]{s['fail']} FAIL[/red]"
    )

    # Show ignore hint if there are any failures or warnings
    if s["fail"] > 0 or s["warn"] > 0:
        console.print(
            "\n[dim]Ignore rules with: // bactopia-lint: ignore RULE_ID[/dim]"
        )


@click.command()
@click.version_option(bactopia.__version__, "--version")
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--modules/--no-modules",
    default=True,
    help="Lint modules (default: on)",
)
@click.option(
    "--subworkflows/--no-subworkflows",
    default=True,
    help="Lint subworkflows (default: on)",
)
@click.option(
    "--workflows/--no-workflows",
    default=True,
    help="Lint workflows (default: on)",
)
@click.option(
    "--module",
    "module_filter",
    default=None,
    help="Lint a single module by name (e.g. 'mlst', 'bakta/run')",
)
@click.option(
    "--subworkflow",
    "subworkflow_filter",
    default=None,
    help="Lint a single subworkflow by name (e.g. 'mlst')",
)
@click.option(
    "--workflow",
    "workflow_filter",
    default=None,
    help="Lint a single workflow by name (e.g. 'mlst', 'bactopia-tools/mlst')",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Only show components with warnings or failures.",
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.option(
    "--pretty", is_flag=True, help="Pretty-print JSON output (implies --json)."
)
@click.option("--verbose", is_flag=True, help="Print debug related text.")
def lint(
    bactopia_path,
    modules,
    subworkflows,
    workflows,
    module_filter,
    subworkflow_filter,
    workflow_filter,
    quiet,
    use_json,
    pretty,
    verbose,
):
    """Lint Bactopia pipeline components against style guidelines.

    Checks modules, subworkflows, and workflows for compliance with
    Bactopia's GroovyDoc, structural, and configuration standards.
    """
    # Setup logs
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.WARNING)

    # Validate path
    bp = Path(bactopia_path).absolute().resolve()
    if not bp.exists():
        logging.error(f"Bactopia path {bactopia_path} does not exist.")
        sys.exit(1)

    if not (bp / "main.nf").exists():
        logging.error(f"No main.nf found in {bp}, is this a valid Bactopia repository?")
        sys.exit(1)

    # If filtering by module, only lint modules (unless other filters also set)
    if module_filter and not subworkflow_filter and not workflow_filter:
        subworkflows = False
        workflows = False

    # Run the linter
    lint_data = run_lint(
        bactopia_path=bp,
        lint_modules=modules,
        lint_subworkflows=subworkflows,
        lint_workflows=workflows,
        module_filter=module_filter,
        subworkflow_filter=subworkflow_filter,
        workflow_filter=workflow_filter,
    )

    # Build serializable output
    output = {
        "version": bactopia.__version__,
        "bactopia_path": str(bp),
        "summary": lint_data["summary"],
        "components": {},
    }
    for tier_name, tier_components in lint_data["components"].items():
        output["components"][tier_name] = [
            {
                "component": c["component"],
                "status": c["status"],
                "results": [
                    {**r.to_dict(), "is_pass": r.is_pass()}
                    for r in c["results"]
                    if not r.is_pass()
                ],
            }
            for c in tier_components
        ]

    if use_json or pretty:
        indent = 2 if pretty else None
        print(json.dumps(output, indent=indent))
    else:
        print_rich(rich.console.Console(), output, bactopia.__version__, quiet)

    # Exit with non-zero if any FAILs
    if lint_data["summary"]["fail"] > 0:
        sys.exit(1)


def main():
    if len(sys.argv) == 1:
        lint.main(["--help"])
    else:
        lint()


if __name__ == "__main__":
    main()
