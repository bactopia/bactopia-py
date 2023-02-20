import sys

import rich
import rich.console
import rich.traceback
import rich_click as click
import yaml
from rich.console import Console
from rich.markdown import Markdown

import bactopia
from bactopia.utils import validate_file

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True


def parse_citations(yml: str) -> list:
    """
    Parse the citations.yml file from Bactopia's repository

    Args:
        yml (str): A yaml file containing citations

    Returns:
        list: A list of dictionaries containing citation information
    """
    module_citations = {}
    with open(yml, "rt") as yml_fh:
        citations = yaml.safe_load(yml_fh)
        for group, refs in citations.items():
            for ref, vals in refs.items():
                module_citations[ref.lower()] = vals
        return [citations, module_citations]


@click.command()
@click.version_option(bactopia.__version__, "--version", "-V")
@click.option(
    "--bactopia",
    "-b",
    required=True,
    help="Directory where Bactopia repository is stored",
)
@click.option("--name", "-n", help="Only print citation matching a given name")
@click.option("--plain-text", "-p", is_flag=True, help="Disable rich formatting")
def citations(bactopia: str, name: str, plain_text: bool) -> None:
    """Print out tools and citations used throughout Bactopia"""

    citations_yml = validate_file(f"{bactopia}/citations.yml")
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
                markdown.append(f'# {group.replace("_", " ").title()}')
            else:
                markdown.append(f"# {group.title()}")
            for ref, vals in refs.items():
                markdown.append(f'{vals["name"]}  ')
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
