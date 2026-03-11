"""Parser for Bactopia citations.yml files."""

import yaml


def parse_citations(yml: str) -> list:
    """
    Parse the citations.yml file from Bactopia's repository

    Args:
        yml (str): A yaml file containing citations

    Returns:
        list: A list of [citations dict, module_citations dict]
    """
    module_citations = {}
    with open(yml, "rt") as yml_fh:
        citations = yaml.safe_load(yml_fh)
        for group, refs in citations.items():
            for ref, vals in refs.items():
                module_citations[ref.lower()] = vals
        return [citations, module_citations]
