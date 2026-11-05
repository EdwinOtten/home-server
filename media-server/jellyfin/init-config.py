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
#   4. Creates or updates regular users from JELLYFIN_REGULAR_USERS and
#      JELLYFIN_REGULAR_USER_PASSWORDS with the required playback policy.
#   5. Injects JELLYFIN_API_KEY into the ApiKeys table via the built-in sqlite3 module.
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


def get_admin_auth_header():
    """Authenticate with the configured admin account and return its auth header."""
    admin_user = os.environ.get("JELLYFIN_ADMIN_USER", "")
    admin_pass = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "")
    if not admin_user or not admin_pass:
        log("JELLYFIN_ADMIN_USER/JELLYFIN_ADMIN_PASSWORD not set, skipping authenticated setup.")
        return None

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
            token = json.loads(resp.read()).get("AccessToken")
    except Exception as exc:
        log(f"WARNING: Could not authenticate with the Jellyfin admin account: {exc}")
        return None
    if not token:
        log("WARNING: Authentication response did not include an AccessToken.")
        return None
    return f'MediaBrowser Token="{token}"'


def add_media_libraries(auth_header):
    """Add Movies and Series media libraries if they don't already exist."""
    if not auth_header:
        log("No Jellyfin admin authentication available, skipping media library setup.")
        return

    log("Setting up media libraries...")

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
        {"name": "Movies (old)", "collectionType": "movies", "path": "/old-downloads/movies"},
        {"name": "Series (old)", "collectionType": "tvshows", "path": "/old-downloads/series"},
        {"name": "Music (old)", "collectionType": "music", "path": "/old-downloads/music"},
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
        body = json.dumps({
            "LibraryOptions": {
                "Enabled": True,
                "PreferredMetadataLanguage": "en",
                "MetadataCountryCode": "NL",
                "EnableEmbeddedTitles": True,
                "EnableEmbeddedExtrasTitles": False,
            },
        }).encode()
        req = urllib.request.Request(
            f"{JELLYFIN_URL}/Library/VirtualFolders?{params}",
            data=body,
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
def configure_library_scan_on_startup(auth_header):
    """Add an application-startup trigger to Jellyfin's library scan task."""
    if not auth_header:
        log("No Jellyfin admin authentication available, skipping library scan trigger upon startup.")
        return

    try:
        tasks = api_request("/ScheduledTasks", auth_header)
    except Exception as exc:
        log(f"WARNING: Could not retrieve scheduled tasks: {exc}")
        return

    scan_task = next(
        (
            task for task in tasks
            if task.get("Key") == "RefreshLibrary"
            or task.get("Name", "").casefold() == "scan media library"
        ),
        None,
    )
    if scan_task is None:
        log("WARNING: Could not find the Scan Media Library scheduled task.")
        return

    triggers = scan_task.get("Triggers") or []
    if any(trigger.get("Type") == "StartupTrigger" for trigger in triggers):
        log("Library scan already configured to run on application startup.")
        return

    triggers.append({"Type": "StartupTrigger"})
    try:
        api_request(
            f"/ScheduledTasks/{scan_task['Id']}/Triggers",
            auth_header,
            method="POST",
            payload=triggers,
        )
        log("Configured library scan to run on application startup.")
    except Exception as exc:
        log(f"WARNING: Could not configure library scan startup trigger: {exc}")


def regular_users_from_env():
    usernames = [value.strip() for value in os.environ.get("JELLYFIN_REGULAR_USERS", "").split(",")]
    passwords = [value.strip() for value in os.environ.get("JELLYFIN_REGULAR_USER_PASSWORDS", "").split(",")]

    if not any(usernames) and not any(passwords):
        return []
    if not all(usernames) or not all(passwords):
        raise ValueError("JELLYFIN_REGULAR_USERS and JELLYFIN_REGULAR_USER_PASSWORDS cannot contain empty values.")
    if len(usernames) != len(passwords):
        raise ValueError("JELLYFIN_REGULAR_USERS and JELLYFIN_REGULAR_USER_PASSWORDS must contain the same number of values.")

    return list(zip(usernames, passwords))


def api_request(path, auth_header, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": auth_header}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{JELLYFIN_URL}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req) as resp:
        response_body = resp.read()
        return json.loads(response_body) if response_body else None


def regular_user_policy(policy):
    policy.update({
        "IsAdministrator": False,
        "IsHidden": False,
        "EnableRemoteAccess": True,
        "EnableSharedDeviceControl": True,
        "EnableMediaPlayback": True,
        "EnableAudioPlaybackTranscoding": True,
        "EnableVideoPlaybackTranscoding": True,
        "EnablePlaybackRemuxing": True,
        "EnableContentDeletion": False,
        "EnableContentDeletionFromFolders": [],
        "EnableAllFolders": True,
    })
    return policy


def provision_regular_users(auth_header):
    try:
        regular_users = regular_users_from_env()
    except ValueError as exc:
        log(f"ERROR: {exc}")
        return
    if not regular_users:
        log("No regular Jellyfin users configured, skipping user provisioning.")
        return

    if not auth_header:
        log("No Jellyfin admin authentication available, skipping regular user provisioning.")
        return

    try:
        users = api_request("/Users", auth_header)
    except Exception as exc:
        log(f"WARNING: Could not retrieve Jellyfin users: {exc}")
        return
    users_by_name = {user["Name"].casefold(): user for user in users}

    for username, password in regular_users:
        user = users_by_name.get(username.casefold())
        try:
            if user is None:
                log(f"Creating regular user '{username}'.")
                user = api_request("/Users/New", auth_header, method="POST", payload={"Name": username, "Password": password})
            else:
                log(f"Updating regular user '{username}'.")
                api_request(
                    f"/Users/Password?{urllib.parse.urlencode({'userId': user['Id']})}",
                    auth_header,
                    method="POST",
                    payload={"NewPw": password, "ResetPassword": False},
                )

            policy = regular_user_policy(user["Policy"])
            api_request(f"/Users/{user['Id']}/Policy", auth_header, method="POST", payload=policy)
        except Exception as exc:
            log(f"WARNING: Could not provision regular user '{username}': {exc}")


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
        updated = con.execute(
            "UPDATE ApiKeys SET DateLastActivity = datetime('now'), AccessToken = ? "
            "WHERE Name = 'docker-managed'",
            (api_key,),
        )
        if updated.rowcount == 0:
            con.execute(
                "INSERT INTO ApiKeys (DateCreated, DateLastActivity, Name, AccessToken) "
                "VALUES (datetime('now'), datetime('now'), 'docker-managed', ?)",
                (api_key,),
            )
    log("API key injection complete.")


def main():
    wait_for_jellyfin()
    complete_wizard_if_needed()
    auth_header = get_admin_auth_header()
    add_media_libraries(auth_header)
    configure_library_scan_on_startup(auth_header)
    provision_regular_users(auth_header)
    inject_api_key()


if __name__ == "__main__":
    if os.fork() == 0:
        main()
    else:
        sys.exit(0)
