import json
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

import bactopia
from bactopia.lint.citations import validate_citations
from bactopia.parsers.citations import parse_citations
from bactopia.utils import validate_file

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


def _render_validation_report(report: dict, silent: bool, plain_text: bool) -> None:
    """Pretty-print a validate_citations() report using Rich tables."""
    console = Console(color_system=None if plain_text else "auto")
    orphans = report["orphans"]
    expected_orphans = report.get("expected_orphans", {})
    missing = report["missing_workflow_keys"]
    summary = report["summary"]

    if summary["orphans_total"] == 0 and summary["missing_total"] == 0:
        if not silent:
            console.print(
                f"[green]All {summary['yml_total']} citations are referenced "
                "and all workflow @citation keys resolve.[/green]"
            )
            if summary.get("expected_orphans_total"):
                _render_expected_orphans(console, expected_orphans)
        return

    if summary["orphans_total"]:
        table = Table(title="Orphan citation keys", show_header=True)
        table.add_column("Section")
        table.add_column("Keys")
        for section, keys in orphans.items():
            if not keys:
                continue
            table.add_row(section, ", ".join(keys))
        console.print(table)

    if summary["missing_total"]:
        table = Table(title="Workflow @citation keys not in citations.yml")
        table.add_column("Component")
        table.add_column("File")
        table.add_column("Line")
        table.add_column("Key")
        for item in missing:
            table.add_row(
                item["component"],
                item["file"],
                str(item["line"]) if item["line"] else "?",
                item["key"],
            )
        console.print(table)

    if summary.get("expected_orphans_total"):
        _render_expected_orphans(console, expected_orphans)

    console.print(
        f"\nSummary: {summary['orphans_total']} orphan key(s), "
        f"{summary['missing_total']} workflow reference(s) unresolved."
    )


def _render_expected_orphans(console: Console, expected_orphans: dict) -> None:
    """Render the provenance-only orphan bucket as an informational note."""
    flat = sorted(key for keys in expected_orphans.values() for key in keys)
    if not flat:
        return
    console.print(
        f"[dim]Expected orphans (provenance-only, not flagged): {', '.join(flat)}[/dim]"
    )


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--bactopia-path",
    "-b",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option("--name", "-n", help="Only print citation matching a given name")
@click.option("--plain-text", "-p", is_flag=True, help="Disable rich formatting")
@click.option(
    "--validate",
    is_flag=True,
    help="Validate citation integrity: orphan keys + workflow @citation references",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit validation results as JSON (use with --validate)",
)
@click.option(
    "--silent",
    is_flag=True,
    help="Suppress non-error output when validation is clean",
)
def citations(
    bactopia_path: str,
    name: str,
    plain_text: bool,
    validate: bool,
    as_json: bool,
    silent: bool,
) -> None:
    """Print or validate citations used throughout Bactopia.

    Default mode prints the full citation list (or one entry with --name).
    Pass --validate to instead scan the repo for orphan keys (defined but
    never referenced) and workflow @citation keys that don't resolve to
    an entry in citations.yml. Module and subworkflow @citation keys are
    validated by bactopia-lint (rules M035 and S019).
    """

    if validate:
        # Validation mode requires the repo root so we can locate
        # data/citations.yml and walk modules/subworkflows/workflows.
        repo_root = Path(bactopia_path)
        if not (repo_root / "data" / "citations.yml").exists():
            raise click.ClickException(
                f"{repo_root}/data/citations.yml not found. "
                "Pass the Bactopia repo root via --bactopia-path."
            )
        report = validate_citations(repo_root)

        if as_json:
            click.echo(json.dumps(report, indent=2, sort_keys=True))
        else:
            _render_validation_report(report, silent=silent, plain_text=plain_text)

        has_issues = (
            report["summary"]["orphans_total"] or report["summary"]["missing_total"]
        )
        if has_issues:
            sys.exit(1)
        return

    # Default (print) mode — unchanged behaviour.
    citations_yml = validate_file(f"{bactopia_path}/citations.yml")
    citations, module_citations = parse_citations(citations_yml)

    markdown = []
    if name:
        if name.lower() in module_citations:
            markdown.append(f"{module_citations[name.lower()]['name']}  ")
            markdown.append(module_citations[name.lower()]["cite"].rstrip())
        else:
            raise KeyError(f'"{name}" does not match available citations')
    else:
        for group, refs in citations.items():
            if group.startswith("datasets"):
                markdown.append(f"# {group.replace('_', ' ').title()}")
            else:
                markdown.append(f"# {group.title()}")
            for ref, vals in refs.items():
                markdown.append(f"{vals['name']}  ")
                markdown.append(vals["cite"])

    md = None
    if plain_text:
        md = "\n".join(markdown)
    else:
        md = Markdown("\n".join(markdown))
    console = Console(color_system=None if plain_text else "auto")
    console.print(md)


def main():
    if len(sys.argv) == 1:
        citations.main(["--help"])
    else:
        citations()


if __name__ == "__main__":
    main()
