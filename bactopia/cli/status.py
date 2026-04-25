"""CLI command for reporting Bactopia repository status."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import rich
import rich.console
import rich.table
import rich.traceback
import rich_click as click

import bactopia
from bactopia.cli.common import common_options, setup_logging
from bactopia.nf import (
    check_tier,
    find_main_nf,
    get_empty_placeholders,
    get_nftest_coverage,
)
from bactopia.utils import get_git_info

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.OPTION_GROUPS = {
    "bactopia-status": [
        {"name": "Required Options", "options": ["--bactopia-path"]},
        {
            "name": "Output Options",
            "options": [
                "--json",
                "--pretty",
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


def collect_status(bp: Path) -> dict:
    """Collect all status data for a Bactopia repo into a dict.

    Args:
        bp: Resolved path to the Bactopia repository.

    Returns:
        A dict containing all status information.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    git = get_git_info(bp)

    modules_dir = bp / "modules"
    subworkflows_dir = bp / "subworkflows"
    workflows_dir = bp / "workflows"

    tiers_config = [
        ("modules", modules_dir, ["module.config", "schema.json"], False),
        ("subworkflows", subworkflows_dir, [], False),
        ("workflows", workflows_dir, [], True),
    ]

    tiers = {}
    for tier_name, tier_dir, required, nftest in tiers_config:
        tiers[tier_name] = check_tier(
            bp, tier_name, tier_dir, required, check_nftest=nftest
        )

    nftest = get_nftest_coverage(bp)
    placeholders = get_empty_placeholders(bp)

    return {
        "timestamp": now,
        "repo": str(bp),
        "git": git,
        "counts": {
            "modules": len(find_main_nf(modules_dir)),
            "subworkflows": len(find_main_nf(subworkflows_dir)),
            "workflows": len(find_main_nf(workflows_dir)),
        },
        "tiers": tiers,
        "nftest": nftest,
        "placeholders": placeholders,
    }


def print_rich(console: rich.console.Console, data: dict):
    """Render status data as Rich tables."""
    console.print(f"[bold]Bactopia Project Status[/bold]  ({data['timestamp']})")
    console.print(f"Repo: {data['repo']}\n")

    # Git state
    git = data["git"]
    git_table = rich.table.Table(title="Git State", show_header=False, box=None)
    git_table.add_row("Branch:", git["branch"])
    git_table.add_row("Commit:", git["commit"])
    git_table.add_row("Modified:", f"{git['modified']} file(s)")
    console.print(git_table)
    console.print()

    # Component counts
    counts = data["counts"]
    counts_table = rich.table.Table(
        title="Component Counts", show_header=False, box=None
    )
    counts_table.add_row("Modules:", str(counts["modules"]))
    counts_table.add_row("Subworkflows:", str(counts["subworkflows"]))
    counts_table.add_row("Workflows:", str(counts["workflows"]))
    console.print(counts_table)
    console.print()

    # Per-tier detail
    for tier_name, result in data["tiers"].items():
        tier_table = rich.table.Table(
            title=tier_name.title(), show_header=False, box=None
        )
        tier_table.add_row("Total:", str(result["total"]))
        tier_table.add_row("GroovyDoc:", f"{result['doc_count']} / {result['total']}")

        if result["issues"]:
            tier_table.add_row("Issues:", f"{len(result['issues'])} found")
        else:
            tier_table.add_row("Issues:", "none")
        console.print(tier_table)

        if result["issues"]:
            for issue in result["issues"]:
                console.print(f"  {issue}", highlight=False, markup=False)

        # Tag coverage
        tag_cov = result.get("tag_coverage", {})
        if tag_cov:
            tag_table = rich.table.Table(
                title=f"{tier_name.title()} Tag Coverage",
                show_header=True,
                box=None,
            )
            tag_table.add_column("Tag", style="bold")
            tag_table.add_column("Count", justify="right")
            for tag, count in tag_cov.items():
                coverage = f"{count} / {result['total']}"
                tag_table.add_row(f"@{tag}", coverage)
            console.print(tag_table)
        console.print()

    # nf-test coverage
    nftest = data["nftest"]
    nftest_table = rich.table.Table(
        title="nf-test Coverage", show_header=False, box=None
    )
    nftest_table.add_row(
        "Components with tests:", f"{nftest['tested']} / {nftest['total']}"
    )
    if nftest["root_test"]:
        nftest_table.add_row("Root pipeline test:", "yes")
    console.print(nftest_table)
    console.print()

    # EMPTY_* placeholders
    placeholders = data["placeholders"]
    if placeholders:
        empty_table = rich.table.Table(
            title="EMPTY_* Placeholders", show_header=False, box=None
        )
        empty_table.add_row("Count:", str(len(placeholders)))
        console.print(empty_table)
        for f in placeholders:
            console.print(f"  - {f}")
        console.print()


@click.command()
@common_options
@click.option(
    "--bactopia-path",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.option(
    "--pretty", is_flag=True, help="Pretty-print JSON output (implies --json)"
)
def status(bactopia_path, use_json, pretty, verbose, silent):
    """Show a snapshot of the Bactopia project state.

    Reports component counts, GroovyDoc coverage, nf-test coverage,
    missing required files, and structural issues.
    """
    setup_logging(verbose, silent)

    # Validate path
    bp = Path(bactopia_path).absolute().resolve()
    if not bp.exists():
        logging.error(f"Bactopia path {bactopia_path} does not exist.")
        sys.exit(1)

    # Quick sanity check: does this look like a Bactopia repo?
    if not (bp / "main.nf").exists():
        logging.error(f"No main.nf found in {bp}, is this a valid Bactopia repository?")
        sys.exit(1)

    data = collect_status(bp)

    if use_json or pretty:
        indent = 2 if pretty else None
        print(json.dumps(data, indent=indent))
    else:
        print_rich(rich.console.Console(), data)


def main():
    if len(sys.argv) == 1:
        status.main(["--help"])
    else:
        status()


if __name__ == "__main__":
    main()
