#!/usr/bin/env python3

# This script is executed indirectly by the LinuxServer.io container customization
# mechanism (mounted at /opt/sonarr-init-config.py). A small bash wrapper at
# /custom-cont-init.d/init-config.sh calls `exec python3 /opt/sonarr-init-config.py`
# because LinuxServer runs custom-cont-init.d scripts via /bin/bash, so Python
# scripts cannot be placed in that directory directly.
#
# It forks a background process that:
#   1. Waits for Sonarr's API to become ready (the service starts after this script exits).
#   2. Updates naming settings via /api/v3/config/naming (idempotent):
#      - renameEpisodes: true
#      - replaceIllegalCharacters: true
#      - colonReplacementFormat: 4 (Smart Replace)
#      - multiEpisodeStyle: 5 (Prefixed Range)
#      - standardEpisodeFormat: {Series Title} - S{season:00}E{episode:00} - {Episode Title}
#      - dailyEpisodeFormat: {Series Title} - {Air-Date} - {Episode Title}
#      - animeEpisodeFormat: {Series Title} - S{season:00}E{episode:00} - {Episode Title}
#      - seriesFolderFormat: {Series TitleYear}
#      - seasonFolderFormat: Season {season}
#   3. Adds /media/series as a root folder if it does not already exist.
#
# All steps are idempotent: re-running on a subsequent restart is safe.

import json
import os
import sys
import time
import urllib.request

SONARR_URL = "http://localhost:8989"
PREFIX = "[sonarr-init]"


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def api_get(path, api_key):
    req = urllib.request.Request(
        f"{SONARR_URL}{path}",
        headers={"X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_put(path, payload, api_key):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SONARR_URL}{path}",
        data=data,
        method="PUT",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_post(path, payload, api_key):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SONARR_URL}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def wait_for_sonarr(api_key):
    log("Waiting for Sonarr API to be ready...")
    while True:
        try:
            api_get("/api/v3/health", api_key)
            break
        except Exception:
            time.sleep(5)
    log("Sonarr API is up.")


def configure_naming(api_key):
    log("Fetching current naming settings...")
    try:
        settings = api_get("/api/v3/config/naming", api_key)
    except Exception as exc:
        log(f"WARNING: Could not fetch naming settings: {exc}")
        return

    desired = {
        "renameEpisodes": True,
        "replaceIllegalCharacters": True,
        "colonReplacementFormat": 4,
        "multiEpisodeStyle": 5,
        "standardEpisodeFormat": "{Series Title} - S{season:00}E{episode:00} - {Episode Title}",
        "dailyEpisodeFormat": "{Series Title} - {Air-Date} - {Episode Title}",
        "animeEpisodeFormat": "{Series Title} - S{season:00}E{episode:00} - {Episode Title}",
        "seriesFolderFormat": "{Series TitleYear}",
        "seasonFolderFormat": "Season {season}",
    }

    needs_update = any(settings.get(k) != v for k, v in desired.items())
    if not needs_update:
        log("Naming settings already correct, skipping.")
        return

    settings.update(desired)
    config_id = settings["id"]
    log("Updating naming settings...")
    try:
        api_put(f"/api/v3/config/naming/{config_id}", settings, api_key)
        log("Naming settings updated.")
    except Exception as exc:
        log(f"WARNING: Could not update naming settings: {exc}")


def add_root_folder(api_key):
    root_folder_path = "/media/series"
    log("Checking root folders...")
    try:
        folders = api_get("/api/v3/rootfolder", api_key)
    except Exception as exc:
        log(f"WARNING: Could not fetch root folders: {exc}")
        return

    existing_paths = {f["path"] for f in folders}
    if root_folder_path in existing_paths:
        log(f"Root folder '{root_folder_path}' already exists, skipping.")
        return

    log(f"Adding root folder '{root_folder_path}'...")
    try:
        api_post("/api/v3/rootfolder", {"path": root_folder_path}, api_key)
        log(f"Root folder '{root_folder_path}' added.")
    except Exception as exc:
        log(f"WARNING: Could not add root folder '{root_folder_path}': {exc}")


def main():
    api_key = os.environ.get("SONARR__AUTH__APIKEY", "")
    if not api_key:
        log("ERROR: SONARR__AUTH__APIKEY is not set. Aborting.")
        sys.exit(1)

    wait_for_sonarr(api_key)
    configure_naming(api_key)
    add_root_folder(api_key)
    log("Init complete.")


if __name__ == "__main__":
    if os.fork() == 0:
        try:
            main()
        except Exception as exc:
            log(f"ERROR: Unhandled exception in init: {exc}")
            sys.exit(1)
    else:
        sys.exit(0)
