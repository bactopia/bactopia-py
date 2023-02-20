"""
Parsers for Minmer related results.
"""
import re


def parse(path: str, name: str) -> dict:
    """
    Check input file is an accepted file, then select the appropriate parsing method.

    Args:
        path (str): input file to be parsed
        name (str): the name of the sample

    Returns:
        dict: parsed results
    """
    # if filetype.startswith("genbank"):
    #    return _parse_sourmash(filename)
    # elif filetype == "refseq-k21.txt" or filetype == "plsdb-k21.txt":
    #    return parse_table(filename)
    return {
        "sample": name,
    }


def _parse_sourmash(filename: str) -> dict:
    """
    Parse Sourmash output.

    Example Format:
        overlap     p_query p_match
        ---------   ------- --------
        2.7 Mbp       7.3%   99.3%      Staphylococcus aureus (** 2 equal matches)
        430.0 kbp     1.1%    0.5%      Tetrahymena thermophila
        90.0 kbp      0.2%    0.1%      Paramecium tetraurelia
        80.0 kbp      0.2%    2.7%      Staphylococcus aureus (** 8 equal matches)
        80.0 kbp      0.2%    1.2%      Staphylococcus haemolyticus
        10.0 kbp      0.0%    0.2%      Alcanivorax xenomutans

        74.6% (28.0 Mbp) of hashes have no assignment.

    Args:
        filename (str): input file to be parsed

    Returns:
        dict: the parsed Sourmash results
    """
    re_sourmash = re.compile(
        r"(?P<overlap>[0-9]+.[0-9]+ [A-Za-z]+)\s+(?P<p_query>[0-9]+.[0-9]+%)\s+(?P<p_match>[0-9]+.[0-9]+%)\s+(?P<match>.*)"
    )
    count = 0
    data = {"matches": [], "no_assignment": ""}
    with open(filename, "rt") as fh:
        parse_row = False
        parse_no_assignment = False
        for line in fh:
            line = line.rstrip()
            if parse_no_assignment:
                data["no_assignment"] = line
            elif parse_row:
                if line:
                    re_match = re_sourmash.match(line)
                    data["matches"].append(
                        {
                            "overlap": re_match.group("overlap"),
                            "p_query": re_match.group("p_query"),
                            "p_match": re_match.group("p_match"),
                            "match": re_match.group("match"),
                        }
                    )
                    count += 1
                else:
                    parse_no_assignment = True
            elif line.startswith("----"):
                parse_row = True
    return data


def add_minmers(minmers: dict) -> dict:
    """
    Read through minmer results and create column for top hit.

    Args:
        minmers (dict): Mash and Sourmash results against RefSeq and GenBank

    Returns:
        dict: Top hit description for each set of databases
    """
    results = {}
    for key in ["refseq-k21", "genbank-k21", "genbank-k31", "genbank-k51"]:
        if key in minmers:
            prefix = key.replace("-", "_")
            if len(minmers[key]):
                if key.startswith("genbank"):
                    # Sourmash keys: "overlap", "p_query", "p_match", "match"
                    if minmers[key]["matches"]:
                        results[f"{prefix}_match"] = (
                            minmers[key]["matches"][0]["match"].split("(")[0].rstrip()
                        )
                        results[f"{prefix}_overlap"] = minmers[key]["matches"][0][
                            "overlap"
                        ]
                        results[f"{prefix}_p_query"] = minmers[key]["matches"][0][
                            "p_query"
                        ]
                        results[f"{prefix}_p_match"] = minmers[key]["matches"][0][
                            "p_match"
                        ]
                    else:
                        results[f"{prefix}_match"] = None
                        results[f"{prefix}_overlap"] = None
                        results[f"{prefix}_p_query"] = None
                        results[f"{prefix}_p_match"] = None

                    results[f"{prefix}_no_assignment"] = minmers[key]["no_assignment"]
                    results[f"{prefix}_total"] = len(minmers[key]["matches"])

                else:
                    # Mash keys: "identity", "shared-hashes", "median-multiplicity", "p-value", "query-ID", "query-comment"
                    results[f"{prefix}_id"] = minmers[key][0]["query-ID"]
                    results[f"{prefix}_identity"] = minmers[key][0]["identity"]
                    results[f"{prefix}_shared_hashes"] = minmers[key][0][
                        "shared-hashes"
                    ]
                    results[f"{prefix}_median_multiplicity"] = minmers[key][0][
                        "median-multiplicity"
                    ]
                    results[f"{prefix}_p_value"] = minmers[key][0]["p-value"]
                    results[f"{prefix}_comment"] = minmers[key][0]["query-comment"]
                    results[f"{prefix}_total"] = len(minmers[key])
    return results
