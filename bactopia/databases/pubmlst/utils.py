import datetime
import json
import logging
import shutil
import sys
from pathlib import Path

from rauth import OAuth1Service, OAuth1Session

from bactopia.databases.pubmlst.constants import (
    AVAILABLE_DATABASES,
    BASE_API_URL,
    BASE_WEB_URL,
)
from bactopia.parsers.generic import parse_json
from bactopia.utils import execute


def print_citation():
    """
    Print the citation for PubMLST and Bactopia
    """
    logging.info(
        "\n\n"
        "If you make use of 'bactopia-pubmlst-(setup|build)' commands and 'PubMLST' database files, please cite the following:\n\n"
        "'PubMLST'\n"
        "Jolley, K. A., Bray, J. E., & Maiden, M. C. J. (2018). Open-access bacterial population genomics: BIGSdb software, the Pubmlst.org website and their applications. Wellcome Open Research, 3, 124. https://doi.org/10.12688/wellcomeopenres.14826.1\n\n"
        "'Bactopia'\n"
        "Petit III RA, Read TD Bactopia - a flexible pipeline for complete analysis of bacterial genomes. mSystems 5 (2020) https://doi.org/10.1128/mSystems.00190-20\n\n"
        "adios!"
    )


def setup_pubmlst(
    site: str, database: str, token_file: str, client_id: str, client_secret: str
):
    """
    Setup a requests session for interacting with the PubMLST/Pasteur API. This function will
    require user interaction to retrieve the token for the session. THis should only have to
    be done once per site.

    Args:
        site (str): The site (publmst or pasteur) to interact with
        database (str): The organism database to interact with
        token_file (str): The file to save the tokens to
        client_id (str): The site client ID
        client_secret (str): The site client secret
    """
    # Setup the OAuth1Service
    service = OAuth1Service(
        name="bactopia-updater",
        consumer_key=client_id,
        consumer_secret=client_secret,
        request_token_url=f"{BASE_API_URL[site]}/db/{database}/oauth/get_request_token",
        access_token_url=f"{BASE_API_URL[site]}/db/{database}/oauth/get_access_token",
        base_url=BASE_API_URL[site],
    )

    # Generate a temporary request token
    logging.info(f"Getting temporary request token for {site} {database}")
    r = service.get_raw_request_token(
        params={"oauth_callback": "oob"}, headers={"User-Agent": "bactopia-updater"}
    )

    if r.status_code == 200:
        temp_token = r.json()["oauth_token"]
        temp_secret = r.json()["oauth_token_secret"]
    else:
        raise Exception(f"Failed to get request token: {r.text}")

    # Ask user to open link to retrieve verification code
    web_url = f"{BASE_WEB_URL[site]}?db={database}&page=authorizeClient&oauth_token={temp_token}"
    print("-----------------------------")
    print(f"{site} API Setup")
    print("-----------------------------")
    print(
        "You will need to log in using your user account using a web browser to obtain a verification code."
    )
    print(f"To do this, please open the following URL in your browser: {web_url}")
    print("-----------------------------")
    oauth_verifier = input("Enter the verification code and press enter: ").strip()
    logging.info(f"Verification code: {oauth_verifier}")

    # Generate the request token
    logging.info(f"Getting access token for {site} {database}")
    r = service.get_raw_access_token(
        temp_token,
        temp_secret,
        params={"oauth_verifier": oauth_verifier},
        headers={"User-Agent": "bactopia-updater"},
    )

    if r.status_code == 200:
        access_token = r.json()["oauth_token"]
        access_secret = r.json()["oauth_token_secret"]
        logging.info(f"Access token: {access_token}")
        logging.info(f"Access secret: {access_secret}")
        logging.info(
            f"The tokens will not expire, but can be revoked at any time by yourself or {site}"
        )
        logging.info(f"Saving access secret to {token_file}")
        with open(token_file, "wt") as fh:
            json_data = {
                "access_token": access_token,
                "access_secret": access_secret,
                "client_id": client_id,
                "client_secret": client_secret,
                "session_token": None,
                "session_secret": None,
            }
            json.dump(json_data, fh, indent=4, sort_keys=True)
    else:
        raise Exception(f"Failed to get access token: {r.text}")


def check_session(site: str, token_file: str, database: str = "yersinia") -> dict:
    """
    Check the current session token and generate a new one if it has expired.

    Args:
        site (str): The site (publmst or pasteur) to interact with
        database (str): The organism database to interact with
        token_file (str): The file to save the updated tokens to

    returns:
        updated_tokens (dict): The updated tokens
    """
    updated_tokens = None
    needs_update = False
    tokens = parse_json(token_file)

    if not tokens["session_token"] or not tokens["session_secret"]:
        logging.debug("Session token not found, will request a new one")
        needs_update = True
    else:
        # Try querying the API to see if the session token is still valid
        url = f"{BASE_API_URL[site]}/db/pubmlst_{database}_seqdef/schemes/1"
        session = OAuth1Session(
            tokens["client_id"],
            tokens["client_secret"],
            access_token=tokens["session_token"],
            access_token_secret=tokens["session_token"],
        )
        r = session.get(
            url,
            params={},
            headers={"User-Agent": "bactopia-downloader"},
        )

        if r.status_code == 400:
            logging.error("Request failed with status code 400")
            logging.error(r.json()["message"])
            sys.exit(1)
        elif r.status_code == 401:
            if "unauthorized" in r.json()["message"]:
                logging.error("Access denied - client is unauthorized")
                logging.error(
                    "Please run `bactopia-pubmlst-setup` to recreate the token file. Then try again"
                )
                sys.exit(1)
            else:
                needs_update = True
                logging.debug("Session token has expired, will request a new one")
        else:
            logging.error(f"Request returned status code {r.status_code}")
            logging.error(f"Error Message: {r.text}")
            sys.exit(1)

    if needs_update:
        logging.debug("Requesting new session token")
        url = (
            f"{BASE_API_URL[site]}/db/pubmlst_{database}_seqdef/oauth/get_session_token"
        )
        session = OAuth1Session(
            tokens["client_id"],
            tokens["client_secret"],
            access_token=tokens["access_token"],
            access_token_secret=tokens["access_secret"],
        )
        r = session.get(url, headers={"User-Agent": "bactopia-downloader"})
        if r.status_code == 200:
            token = r.json()["oauth_token"]
            secret = r.json()["oauth_token_secret"]
            updated_tokens = {
                "access_token": tokens["access_token"],
                "access_secret": tokens["access_secret"],
                "client_id": tokens["client_id"],
                "client_secret": tokens["client_secret"],
                "session_token": token,
                "session_secret": secret,
            }

            # Make a backup of the old token file
            logging.debug(f"Making backup of old session token file: {token_file}")
            shutil.copy(token_file, f"{token_file}.bak")

            # Save the new token file
            logging.debug(f"Saving new session token to {token_file}")
            with open(token_file, "wt") as fh:
                json.dump(updated_tokens, fh, indent=4, sort_keys=True)

        if not updated_tokens:
            logging.error(
                f"Request to renew session failed with status code {r.status_code}"
            )
            logging.error(f"Error Message: {r.text}")
            sys.exit(1)

        # Return the updated tokens
        return updated_tokens
    else:
        logging.debug("Session token is still valid")

    # Return the original tokens, as no update was needed
    return tokens


def query(site: str, tokens: dict, url: str, return_text: bool = False) -> dict:
    """
    A generic function for submitting a query to the PubMLST/Pasteur API.

    Args:
        site (str): The site (publmst or pasteur) to interact with
        tokens (dict): The tokens for the session
        url (str): The URL to query
        return_text (bool): Return the text of the response instead of JSON

    Returns:
        response (dict): The response from the API in JSON format

    Raises:
        Exception: If the query fails
    """
    # Setup Session
    session = OAuth1Session(
        tokens["client_id"],
        tokens["client_secret"],
        access_token=tokens["session_token"],
        access_token_secret=tokens["session_secret"],
    )

    r = session.get(
        url,
        params={},
        headers={"User-Agent": "bactopia-downloader"},
    )

    if r.status_code == 200 or r.status_code == 201:
        if return_text:
            return r.text
        else:
            return r.json()
    else:
        raise Exception(f"Failed to query {url}: {r.text}")


def available_databases(
    site: str,
    token_file: str,
) -> dict:
    """
    Retrieve a list of available databases from PubMLST or Pasteur.

    Args:
        site (str): The site (publmst or pasteur) to interact with
        token_file (str): The file to load the tokens from

    Returns:
        databases (dict): The available databases
    """
    logging.debug(f"Gathering available databases from {site}")
    databases = {}
    tokens = check_session(site, token_file)
    logging.debug("Current Tokens")
    logging.debug(json.dumps(tokens, indent=4, sort_keys=True))

    # Setup Session
    url = f"{BASE_API_URL[site]}/db"
    json_data = query(
        site,
        tokens,
        url,
    )

    """
    End point description: https://bigsdb.readthedocs.io/en/latest/rest.html#get-or-db-list-site-resources

    Example response:
    [
        {
            "name":"achromobacter",
            "databases":[
            {
                "name":"pubmlst_achromobacter_isolates",
                "href":"https://rest.pubmlst.org/db/pubmlst_achromobacter_isolates",
                "description":"Achromobacter spp. isolates"
            },
            {
                "description":"Achromobacter spp. sequence/profile definitions",
                "href":"https://rest.pubmlst.org/db/pubmlst_achromobacter_seqdef",
                "name":"pubmlst_achromobacter_seqdef"
            }
            ]
        },
    ]
    """
    for organism in json_data:
        for db in organism["databases"]:
            # We only want the sequence definitions, skip isolates
            if db["name"].endswith("_seqdef"):
                name = db["name"].replace("pubmlst_", "").replace("_seqdef", "")
                description = db["description"].replace(
                    " sequence/profile definitions", ""
                )
                databases[name] = description
                logging.debug(f"Found database: {name} - {description}")

    # Add any databases that are not available from the API
    for db, description in AVAILABLE_DATABASES[site].items():
        if db not in databases:
            databases[db] = description
            logging.debug(
                f"Adding database not available from API: {db} - {description}"
            )

    return databases


def get_mlst_scheme(site: str, database: str, tokens: dict) -> str:
    """
    Determine which scheme to use for MLST for a given database.
    """
    # Setup Session
    url = f"{BASE_API_URL[site]}/db/pubmlst_{database}_seqdef/schemes"
    json_data = query(
        site,
        tokens,
        url,
    )

    """
    End point description: https://bigsdb.readthedocs.io/en/latest/rest.html#get-db-database-schemes-list-schemes

    Example response:
    {
        "schemes": [
            {
                "description": "MLST",
                "scheme": "https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/schemes/1"
            }
        ],
        "records": 1
    }
    """
    logging.debug(json.dumps(json_data, indent=4, sort_keys=True))

    mlst_scheme_ids = []
    for scheme in json_data["schemes"]:
        for word in scheme["description"].strip().split():
            if word.lower() == "mlst":
                logging.debug(
                    f"Found MLST scheme: {scheme['description']} - {scheme['scheme']}"
                )
                mlst_scheme_ids.append(scheme["scheme"].split("/")[-1])
            else:
                logging.debug(
                    f"Skipping scheme: {scheme['description']} - {scheme['scheme']}"
                )
    logging.debug(f"MLST Scheme ID(s): {', '.join(sorted(mlst_scheme_ids))}")

    return sorted(mlst_scheme_ids)


def write_profiles(
    profiles: str,
    site: str,
    database: str,
    out_dir: str,
    scheme_id: str,
    append_id: bool = False,
) -> dict:
    """
    Parse the profiles CSV file from PubMLST.

    Args:
        profiles (str): The profiles CSV file
        site (str): The site (publmst or pasteur) to interact with
        database (str): The organism database to interact with
        out_dir (str): The directory to save the profiles
        scheme_id (str): The MLST scheme ID
        append_id (bool): Append the scheme ID to the database name

    Returns:
        profiles (dict): The profiles as a dictionary
    """
    database_text = f"{database}_{scheme_id}" if append_id else database
    profile_path = f"{out_dir}/{database_text}"
    if not Path(profile_path).exists():
        Path(profile_path).mkdir(parents=True, exist_ok=True)
    profile_txt = f"{database_text}.txt"
    parsed_profiles = {}
    headers = None
    with open(f"{profile_path}/{profile_txt}", "wt") as fh:
        for line in profiles.split("\n"):
            if line:
                fh.write(f"{line}\n")
                if len(parsed_profiles) < 5:
                    logging.debug(line)
                data = line.strip().split("\t")
                if data[0] == "ST":
                    headers = data
                else:
                    profile = {}
                    for i, header in enumerate(headers):
                        try:
                            profile[header] = data[i]
                        except IndexError:
                            profile[header] = ""
                    parsed_profiles[profile["ST"]] = profile
    logging.info(f"Saved 'profiles' to '{profile_path}/{profile_txt}'")

    return parsed_profiles


def write_loci(
    loci_url: dict,
    site: str,
    database: str,
    tokens: dict,
    out_dir: str,
    scheme_id: str,
    append_id: bool = False,
):
    """
    Write the loci FASTA files.

    Args:
        loci (dict): The loci URL
        site (str): The site (publmst or pasteur) to interact with
        database (str): The organism database to interact with
        out_dir (str): The directory to save the loci
        scheme_id (str): The MLST scheme ID
        append_id (bool): Append the scheme ID to the database
    """

    loci = loci_url.split("/")[-1]
    database_text = f"{database}_{scheme_id}" if append_id else database
    loci_path = f"{out_dir}/{database_text}"
    if not Path(loci_path).exists():
        Path(loci_path).mkdir(parents=True, exist_ok=True)
    loci_tfa = f"{loci}.tfa"

    logging.debug(f"Downloading Loci ({loci}) FASTA file: {loci_url}")
    loci_fasta = query(
        site,
        tokens,
        f"{loci_url}/alleles_fasta",
        return_text=True,
    )
    total_alleles = 0
    with open(f"{loci_path}/{loci_tfa}", "wt") as fh:
        for line in loci_fasta.split("\n"):
            if line:
                if line.startswith(">"):
                    line = line.replace(">", f">{database_text}.")
                    total_alleles += 1
                fh.write(f"{line}\n")
    logging.info(
        f"Saved loci '{loci}' ({total_alleles} seqs) to '{loci_path}/{loci_tfa}'"
    )


def download_database(
    database: str,
    site: str,
    token_file: str,
    out_dir: str,
    force: bool,
    retry: bool = False,
):
    """
    Download specific database files from PubMLST or Pasteur.

    Need to get

    Args:
        database (str): The organism database to interact with
        site (str): The site (publmst or pasteur) to interact with
        token_file (str): The file to load the tokens from
        out_dir (str): The directory to save the database files
        force (bool): Overwrite existing files
        retry (bool): Retry the download if it fails
    """
    logging.info(f"Working on '{database}' from '{site}'")
    # Setup Session
    tokens = check_session(site, token_file, database=database)
    logging.debug("Tokens")
    logging.debug(json.dumps(tokens, indent=4, sort_keys=True))

    # Determine MLST Scheme ID
    mlst_scheme_ids = get_mlst_scheme(site, database, tokens)
    if len(mlst_scheme_ids) > 1:
        logging.info(
            f"Multiple MLST schemes found for '{database}', will download each"
        )

    for i, mlst_scheme_id in enumerate(mlst_scheme_ids):
        database_text = database if i == 0 else f"{database}_{mlst_scheme_id}"
        if len(mlst_scheme_ids) > 1:
            logging.info(
                f"Working on {database_text} (schema {i+1} of {len(mlst_scheme_ids)})"
            )
        # Gather Profiles
        profiles_url = f"{BASE_API_URL[site]}/db/pubmlst_{database}_seqdef/schemes/{mlst_scheme_id}/profiles_csv"
        profiles_data = query(
            site,
            tokens,
            profiles_url,
            return_text=True,
        )
        write_profiles(
            profiles_data,
            site,
            database,
            out_dir,
            mlst_scheme_id,
            append_id=True if len(mlst_scheme_ids) > 1 and i > 0 else False,
        )
        # Gather Loci
        loci_url = f"{BASE_API_URL[site]}/db/pubmlst_{database}_seqdef/schemes/{mlst_scheme_id}/loci"
        loci_data = query(
            site,
            tokens,
            loci_url,
        )
        """
        Example loci_data:
        {
            'loci': [
                'https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/loci/aarF',
                'https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/loci/dfp',
                'https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/loci/galR',
                'https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/loci/glnS',
                'https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/loci/hemA',
                'https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/loci/rfaE',
                'https://rest.pubmlst.org/db/pubmlst_yersinia_seqdef/loci/speA'
            ],
            'records': 7
        }
        """
        logging.debug(f"Downloading Loci FASTA files for {database_text}")
        for loci_url in loci_data["loci"]:
            write_loci(
                loci_url,
                site,
                database,
                tokens,
                out_dir,
                mlst_scheme_id,
                append_id=True if len(mlst_scheme_ids) > 1 and i > 0 else False,
            )

    logging.info(f"'{database}' complete")


def build_blast_db(out_dir: str):
    """
    Build a BLAST database from the loci FASTA files that is compatible with 'tseemann/mlst'

    Args:
        out_dir (str): The directory containing the loci FASTA files
    """
    database_dir = f"{out_dir}/mlstdb"
    blast_db_dir = f"{database_dir}/blast"
    if not Path(blast_db_dir).exists():
        Path(blast_db_dir).mkdir(parents=True, exist_ok=True)
    logging.info(f"Building MLST BLAST database at '{blast_db_dir}'")

    # Find all the loci FASTA files (*.tfa), in database_dir
    fasta_files = list(Path(database_dir).rglob("*.tfa"))
    logging.info(f"Found {len(fasta_files)} loci FASTA files")

    # Concatenate all the loci FASTA files into a single file
    mlst_fasta = f"{blast_db_dir}/mlst.fa"
    total_sequences = 0
    with open(mlst_fasta, "wt") as fh:
        for fasta_file in fasta_files:
            logging.debug(f"Concatenating '{fasta_file}'")
            with open(fasta_file, "rt") as f:
                for line in f:
                    if line.startswith(">"):
                        total_sequences += 1
                    fh.write(line)
    logging.info(f"Concatenated {total_sequences} sequences to '{mlst_fasta}'")

    # Build the BLAST database
    execute(
        "makeblastdb -hash_index -in mlst.fa -dbtype nucl -title 'PubMLST' -parse_seqids",
        directory=blast_db_dir,
    )

    # Create timestamp of when the database was built
    with open(f"{database_dir}/DB_VERSION", "wt") as fh:
        fh.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Tar the BLAST database
    logging.info(f"Save BLAST database to '{database_dir}/mlst.tar.gz'")
    execute("tar -czvf mlst.tar.gz mlstdb/", directory=out_dir)
    shutil.move(f"{out_dir}/mlst.tar.gz", f"{database_dir}/mlst.tar.gz")
