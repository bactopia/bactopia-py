import json
import logging
import shutil
import sys

from rauth import OAuth1Service, OAuth1Session

from bactopia.parsers.generic import parse_json

BASE_WEB_URL = {
    "pubmlst": "https://pubmlst.org/bigsdb",
    "pasteur": "https://bigsdb.pasteur.fr/cgi-bin/bigsdb/bigsdb.pl",
}

BASE_API_URL = {
    "pubmlst": "https://rest.pubmlst.org",
    "pasteur": "https://bigsdb.pasteur.fr/api",
}


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


def check_session(site: str, database: str, token_file: str):
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
        logging.warning("Session token not found, will request a new one")
        needs_update = True
    else:
        # Try querying the API to see if the session token is still valid
        url = f"{BASE_API_URL[site]}/db/{database}/schemes/1"
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
                logging.warning("Session token has expired, will request a new one")
        else:
            logging.error(f"Request returned status code {r.status_code}")
            logging.error(f"Error Message: {r.text}")
            sys.exit(1)

    if needs_update:
        logging.debug("Requesting new session token")
        url = f"{BASE_API_URL[site]}/db/{database}/oauth/get_session_token"
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
    tokens = check_session(site, database, token_file)
    logging.debug("Tokens")
    logging.debug(json.dumps(tokens, indent=4, sort_keys=True))

    # Setup Session
    url = f"{BASE_API_URL[site]}/db/{database}/schemes/1"
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
        print(r.text)
    else:
        print(dir(r))
        print(r.status_code)
        if not retry:
            download_database(database, site, token_file, out_dir, force, retry=True)
        else:
            raise Exception(f"Failed to download database: {r.text}")
