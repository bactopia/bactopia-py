import sys

import rich
import rich.console
import rich.traceback
import rich_click as click
from rich.console import Console
from rich.markdown import Markdown

import bactopia
from bactopia.parsers.citations import parse_citations
from bactopia.utils import validate_file

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


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
def citations(bactopia_path: str, name: str, plain_text: bool) -> None:
    """Print out tools and citations used throughout Bactopia"""

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
