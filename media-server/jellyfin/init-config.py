#!/usr/bin/env python3

# This script is executed indirectly by the LinuxServer.io container customization
# mechanism (mounted at /opt/init-config.py). A small bash wrapper at
# /custom-cont-init.d/init-config.sh calls `exec python3 /opt/init-config.py`
# because LinuxServer runs custom-cont-init.d scripts via /bin/bash, so Python
# scripts cannot be placed in that directory directly.
#
# It forks a background process that:
#   1. Waits for Jellyfin to become ready (the service starts after this script exits).
#   2. Completes the setup wizard via Jellyfin's Startup API (if not already done):
#      - Sets English locale and metadata language.
#      - Sets the admin username and password from JELLYFIN_ADMIN_USER / JELLYFIN_ADMIN_PASSWORD.
#      - Enables remote access (disables UPnP auto-mapping).
#      - Marks the wizard as complete.
#   3. Adds two media libraries via the Jellyfin API (if they don't already exist):
#      - "Movies"  (collectionType=movies)  pointing at /media/movies
#      - "Series"  (collectionType=tvshows) pointing at /media/series
#   4. Injects JELLYFIN_API_KEY into the ApiKeys table via the built-in sqlite3 module.
#      (The Jellyfin API does not allow specifying a pre-determined key value; it always
#      generates a random one, so the exact key must be written directly to the database.)
#
# All steps are idempotent: re-running on a subsequent restart is safe.

import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

JELLYFIN_URL = "http://localhost:8096"
DB_PATH = "/config/data/data/jellyfin.db"
PREFIX = "[jellyfin-init]"


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def http_get(url):
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def http_post(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def wait_for_jellyfin():
    log("Waiting for Jellyfin to be ready...")
    while True:
        try:
            with urllib.request.urlopen(f"{JELLYFIN_URL}/health"):
                break
        except Exception:
            time.sleep(5)
    log("Jellyfin is up. Sleeping for 20 seconds...")
    time.sleep(20)


def complete_wizard_if_needed():
    try:
        info = json.loads(http_get(f"{JELLYFIN_URL}/System/Info/Public"))
    except Exception:
        log("WARNING: Could not determine wizard status; skipping wizard setup.")
        return

    if info.get("StartupWizardCompleted", False):
        log("Setup wizard already complete, skipping.")
        return

    admin_user = os.environ.get("JELLYFIN_ADMIN_USER", "")
    admin_pass = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "")
    if not admin_user or not admin_pass:
        log("ERROR: JELLYFIN_ADMIN_USER and JELLYFIN_ADMIN_PASSWORD must be set to complete the wizard.")
        sys.exit(1)

    log("Completing setup wizard...")

    # Set English locale and metadata language
    http_post(f"{JELLYFIN_URL}/Startup/Configuration", {
        "ServerName": "jellyfin",
        "UICulture": "en-US",
        "MetadataCountryCode": "US",
        "PreferredMetadataLanguage": "en",
    })

    # Initialize the first user via GET before updating it via POST.
    # Without this GET call, POST /Startup/User fails with "Sequence contains no elements"
    # because Jellyfin has not yet created the initial user record.
    http_get(f"{JELLYFIN_URL}/Startup/User")

    # Set admin username and password
    payload = {"Name": admin_user, "Password": admin_pass}
    log(f"Payload to be sent to /Startup/User: {json.dumps({**payload, 'Password': '***'})}")
    http_post(f"{JELLYFIN_URL}/Startup/User", payload)

    # Enable remote access, disable UPnP auto-mapping
    http_post(f"{JELLYFIN_URL}/Startup/RemoteAccess", {
        "EnableRemoteAccess": True,
        "EnableAutomaticPortMapping": False,
    })

    # Complete the wizard
    http_post(f"{JELLYFIN_URL}/Startup/Complete")

    log("Setup wizard complete.")


def add_media_libraries():
    """Add Movies and Series media libraries if they don't already exist."""
    admin_user = os.environ.get("JELLYFIN_ADMIN_USER", "")
    admin_pass = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "")
    if not admin_user or not admin_pass:
        log("JELLYFIN_ADMIN_USER/JELLYFIN_ADMIN_PASSWORD not set, skipping media library setup.")
        return

    log("Setting up media libraries...")

    # Authenticate with admin credentials to obtain a session token.
    # The Authorization header is required by Jellyfin even for the login endpoint.
    # Note: Jellyfin's AuthenticateByName API uses 'Pw' (not 'Password') for the password field.
    client_auth = (
        'MediaBrowser Client="init-config", Device="init-config", '
        'DeviceId="init-config", Version="1.0.0"'
    )
    data = json.dumps({"Username": admin_user, "Pw": admin_pass}).encode()
    req = urllib.request.Request(
        f"{JELLYFIN_URL}/Users/AuthenticateByName",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": client_auth},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            auth_result = json.loads(resp.read())
    except Exception as exc:
        log(f"WARNING: Could not authenticate to add media libraries: {exc}")
        return
    token = auth_result["AccessToken"]
    auth_header = f'MediaBrowser Token="{token}"'

    # Fetch the list of existing virtual folders so this step is idempotent.
    req = urllib.request.Request(
        f"{JELLYFIN_URL}/Library/VirtualFolders",
        headers={"Authorization": auth_header},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            folders = json.loads(resp.read())
    except Exception as exc:
        log(f"WARNING: Could not fetch existing media libraries: {exc}")
        return
    existing_names = {f["Name"].lower() for f in folders}

    # Libraries to create, mapped to the paths inside the container.
    libraries = [
        {"name": "Movies", "collectionType": "movies", "path": "/media/movies"},
        {"name": "Series", "collectionType": "tvshows", "path": "/media/series"},
    ]

    for lib in libraries:
        if lib["name"].lower() in existing_names:
            log(f"Library '{lib['name']}' already exists, skipping.")
            continue

        log(f"Adding '{lib['name']}' library at {lib['path']}...")
        params = urllib.parse.urlencode([
            ("name", lib["name"]),
            ("collectionType", lib["collectionType"]),
            ("paths", lib["path"]),
            ("refreshLibrary", "false"),
        ])
        req = urllib.request.Request(
            f"{JELLYFIN_URL}/Library/VirtualFolders?{params}",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": auth_header},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                resp.read()
            log(f"Library '{lib['name']}' added.")
        except Exception as exc:
            log(f"WARNING: Could not add library '{lib['name']}': {exc}")

    log("Media library setup complete.")


def inject_api_key():
    api_key = os.environ.get("JELLYFIN_API_KEY", "")
    if not api_key:
        log("JELLYFIN_API_KEY not set, skipping API key injection")
        return

    # Wait until the database file exists (created by Jellyfin on first run)
    while not os.path.isfile(DB_PATH):
        log("Waiting for Jellyfin database...")
        time.sleep(5)

    log("Injecting API key...")
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR IGNORE INTO ApiKeys (DateCreated, DateLastActivity, Name, AccessToken) "
            "VALUES (datetime('now'), datetime('now'), 'docker-managed', ?)",
            (api_key,),
        )
    log("API key injection complete.")


def main():
    wait_for_jellyfin()
    complete_wizard_if_needed()
    add_media_libraries()
    inject_api_key()


if __name__ == "__main__":
    if os.fork() == 0:
        main()
    else:
        sys.exit(0)
