"""bactopia-docs CLI: validate reference-doc staleness."""

import json
import sys
from pathlib import Path

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.console import Console
from rich.table import Table

import bactopia
from bactopia.cli.common import common_options, setup_logging
from bactopia.lint.docs import (
    DEFAULT_DOCS_PATH,
    DEFAULT_PATTERNS_FILE,
    validate_docs,
)

stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True

click.rich_click.OPTION_GROUPS = {
    "bactopia-docs": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Validation Options",
            "options": [
                "--docs-path",
                "--patterns-file",
                "--bactopia-py-path",
                "--skip-path-check",
                "--validate",
            ],
        },
        {
            "name": "Output Options",
            "options": [
                "--json",
                "--plain-text",
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


def _render_report(report: dict, silent: bool, plain_text: bool) -> None:
    """Pretty-print a validate_docs() report using Rich tables."""
    console = Console(color_system=None if plain_text else "auto")
    summary = report["summary"]
    deprecated = report["deprecated_patterns"]
    violations = report["ground_truth_violations"]

    if summary["fail"] == 0 and summary["warn"] == 0:
        if not silent:
            console.print(
                f"[green]All {summary['files_scanned']} docs clean. "
                f"({summary['patterns_loaded']} deprecated patterns, "
                f"{report['ground_truth']['cli_commands_total']} CLI commands, "
                f"{report['ground_truth']['lint_rule_ids_total']} lint rule IDs "
                f"checked.)[/green]"
            )
        return

    if deprecated:
        table = Table(title="Deprecated patterns (D0xx)", show_header=True)
        table.add_column("Rule")
        table.add_column("File")
        table.add_column("Line", justify="right")
        table.add_column("Match")
        table.add_column("Hint")
        for hit in deprecated:
            table.add_row(
                hit["rule_id"],
                hit["file"],
                str(hit["line"]),
                hit["match"][:80],
                hit.get("hint", ""),
            )
        console.print(table)

    if violations:
        table = Table(title="Ground-truth violations (D1xx)", show_header=True)
        table.add_column("Rule")
        table.add_column("File")
        table.add_column("Line", justify="right")
        table.add_column("Detail")
        for hit in violations:
            if "actual" in hit and "claim" in hit:
                detail = f"claim: {hit['claim']} | actual: {hit['actual']}"
            elif "reference" in hit:
                detail = f"reference: {hit['reference']} — {hit.get('hint', '')}"
            else:
                detail = hit.get("hint", "")
            table.add_row(
                hit["rule_id"],
                hit["file"],
                str(hit["line"]),
                detail[:100],
            )
        console.print(table)

    console.print(
        f"\nSummary: {summary['deprecated_pattern_hits']} deprecated-pattern hit(s), "
        f"{summary['ground_truth_violations']} ground-truth violation(s) "
        f"across {summary['files_scanned']} doc(s)."
    )


@click.command()
@common_options
@click.option(
    "--bactopia-path",
    "-b",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option(
    "--docs-path",
    default=DEFAULT_DOCS_PATH,
    show_default=True,
    help="Docs directory relative to --bactopia-path",
)
@click.option(
    "--patterns-file",
    default=DEFAULT_PATTERNS_FILE,
    show_default=True,
    help="Deprecated-patterns YAML relative to --bactopia-path",
)
@click.option(
    "--bactopia-py-path",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to bactopia-py repo (for D105 CLI / D106 lint-rule checks). "
    "Defaults to <bactopia-path>/../bactopia-py",
)
@click.option(
    "--skip-path-check",
    is_flag=True,
    help="Skip D108 markdown-link target resolution",
)
@click.option(
    "--validate",
    is_flag=True,
    help="Run validation (default action; flag is accepted for parity with bactopia-citations)",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit results as JSON",
)
@click.option(
    "--plain-text",
    "-p",
    is_flag=True,
    help="Disable rich formatting",
)
def docs(
    bactopia_path: str,
    docs_path: str,
    patterns_file: str,
    bactopia_py_path: Path | None,
    skip_path_check: bool,
    validate: bool,
    as_json: bool,
    verbose: bool,
    silent: bool,
    plain_text: bool,
) -> None:
    """Validate reference-doc staleness across a Bactopia repo.

    Two checks run against every .md file under [b]--docs-path[/b]:

    [b]Deprecated patterns (D0xx)[/b]: regex matches against
    [b]--patterns-file[/b] entries — phrases retired by past migrations
    (e.g. ``flattenPaths``, the 4-channel emission framing).

    [b]Ground-truth assertions (D1xx)[/b]: counts (D101-D103), Nextflow
    version (D104), bactopia-py CLI references (D105), lint rule IDs
    (D106), markdown link targets (D108).

    Suppress a rule on a single line with
    ``<!-- bactopia-docs: ignore D0xx -->`` (or a comma-separated list).

    Exits 1 if any FAIL is found.
    """
    setup_logging(verbose, silent)
    repo_root = Path(bactopia_path)
    if not repo_root.is_dir():
        raise click.ClickException(f"--bactopia-path {repo_root} is not a directory.")
    if not (repo_root / docs_path).is_dir():
        raise click.ClickException(
            f"Docs directory {repo_root / docs_path} not found. "
            "Pass --bactopia-path pointing at the Bactopia repo root."
        )

    # validate flag is decorative — there's no other mode for now.
    _ = validate

    report = validate_docs(
        bactopia_path=repo_root,
        docs_path=docs_path,
        patterns_file=patterns_file,
        bactopia_py_path=bactopia_py_path,
        skip_path_check=skip_path_check,
    )

    if as_json:
        click.echo(json.dumps(report, indent=2, sort_keys=True))
    else:
        _render_report(report, silent=silent, plain_text=plain_text)

    if report["summary"]["fail"]:
        sys.exit(1)


def main():
    if len(sys.argv) == 1:
        docs.main(["--help"])
    else:
        docs()


if __name__ == "__main__":
    main()
