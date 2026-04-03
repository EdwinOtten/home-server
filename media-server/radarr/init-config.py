#!/usr/bin/env python3

# This script is executed indirectly by the LinuxServer.io container customization
# mechanism (mounted at /opt/init-config.py). A small bash wrapper at
# /custom-cont-init.d/init-config.sh calls `exec python3 /opt/init-config.py`
# because LinuxServer runs custom-cont-init.d scripts via /bin/bash, so Python
# scripts cannot be placed in that directory directly.
#
# It forks a background process that:
#   1. Waits for Radarr's API to become ready (the service starts after this script exits).
#   2. Updates media management settings via /api/v3/config/mediamanagement (idempotent):
#      - autoRenameFolders: true
#   3. Updates naming settings via /api/v3/config/naming (idempotent):
#      - renameMovies: true
#      - replaceIllegalCharacters: true
#      - standardMovieFormat: {Movie Title} ({Release Year})
#      - movieFolderFormat: {Movie Title} ({Release Year})
#   4. Adds /media/movies as a root folder if it does not already exist.
#   5. Upserts a SABnzbd download client (idempotent):
#      - Creates the client if it does not exist
#      - Updates host, port and apiKey if they changed
#   6. Upserts an Emby/Jellyfin notification (idempotent):
#      - Connects to jellyfin:8096
#      - Enables update library
#      - Enables: On Download (File Import), On Upgrade, On Rename,
#        On Movie Delete, On Movie File Delete
#
# All steps are idempotent: re-running on a subsequent restart is safe.

import json
import os
import sys
import time
import urllib.request

RADARR_URL = "http://localhost:7878"
PREFIX = "[radarr-init]"


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def api_get(path, api_key):
    req = urllib.request.Request(
        f"{RADARR_URL}{path}",
        headers={"X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_put(path, payload, api_key):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{RADARR_URL}{path}",
        data=data,
        method="PUT",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_post(path, payload, api_key):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{RADARR_URL}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def wait_for_radarr(api_key):
    log("Waiting for Radarr API to be ready...")
    while True:
        try:
            api_get("/api/v3/health", api_key)
            break
        except Exception:
            time.sleep(5)
    log("Radarr API is up.")


def normalize_name(value):
    return str(value or "").strip().lower()


def to_positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def get_field_value(fields, field_name):
    for field in fields:
        if normalize_name(field.get("name")) == normalize_name(field_name):
            return field.get("value")
    return None


def set_field_value(fields, field_name, field_value):
    for field in fields:
        if normalize_name(field.get("name")) == normalize_name(field_name):
            field["value"] = field_value
            return True
    return False


def field_value_matches(field_name, current_value, desired_value):
    if current_value is None:
        return False

    if normalize_name(field_name) == "port":
        current_port = to_positive_int(current_value)
        desired_port = to_positive_int(desired_value)
        if current_port and desired_port:
            return current_port == desired_port

    return str(current_value) == str(desired_value)


def upsert_sabnzbd_download_client(api_key, sabnzbd_api_key, sabnzbd_host, sabnzbd_port):
    log("Checking existing download clients...")
    try:
        clients = api_get("/api/v3/downloadclient", api_key)
    except Exception:
        log("WARNING: Could not fetch download clients.")
        return

    existing = None
    for client in clients:
        if normalize_name(client.get("implementation")) == "sabnzbd":
            existing = client
            break

    desired = {
        "host": sabnzbd_host,
        "port": str(sabnzbd_port),
        "apiKey": sabnzbd_api_key,
    }
    desired_optional = {
        "movieCategory": "movies",
    }

    if existing is None:
        log("Fetching SABnzbd download client schema...")
        try:
            schemas = api_get("/api/v3/downloadclient/schema", api_key)
        except Exception:
            log("WARNING: Could not fetch download client schemas.")
            return

        sabnzbd_schema = None
        for schema in schemas:
            if (
                normalize_name(schema.get("implementation")) == "sabnzbd"
                or normalize_name(schema.get("name")) == "sabnzbd"
                or normalize_name(schema.get("sortName")) == "sabnzbd"
            ):
                sabnzbd_schema = schema
                break

        if sabnzbd_schema is None:
            log("WARNING: SABnzbd schema not found in available download client schemas.")
            return

        fields = sabnzbd_schema.get("fields", [])
        for field_name, field_value in desired.items():
            if not set_field_value(fields, field_name, field_value):
                log(f"WARNING: SABnzbd schema missing expected field '{field_name}'.")
                return
        for field_name, field_value in desired_optional.items():
            set_field_value(fields, field_name, field_value)

        sabnzbd_schema["name"] = "SABnzbd"
        sabnzbd_schema["enable"] = True

        log("Adding SABnzbd download client...")
        try:
            api_post("/api/v3/downloadclient", sabnzbd_schema, api_key)
            log("SABnzbd download client added.")
        except Exception:
            log("WARNING: Could not add SABnzbd download client.")
        return

    fields = existing.get("fields", [])
    needs_update = False
    for field_name, desired_value in desired.items():
        current_value = get_field_value(fields, field_name)
        if not field_value_matches(field_name, current_value, desired_value):
            needs_update = True
            if not set_field_value(fields, field_name, desired_value):
                log(f"WARNING: Existing SABnzbd client missing expected field '{field_name}'.")
                return
    for field_name, desired_value in desired_optional.items():
        current_value = get_field_value(fields, field_name)
        if current_value is None:
            continue
        if not field_value_matches(field_name, current_value, desired_value):
            if not set_field_value(fields, field_name, desired_value):
                log(f"WARNING: Existing SABnzbd client missing optional field '{field_name}'.")
                continue
            needs_update = True

    if not needs_update:
        log("SABnzbd download client already configured, skipping.")
        return

    existing_id = existing.get("id")
    if not existing_id:
        log("WARNING: Existing SABnzbd download client has no id; cannot update.")
        return

    log("Updating SABnzbd download client...")
    try:
        api_put(f"/api/v3/downloadclient/{existing_id}", existing, api_key)
        log("SABnzbd download client updated.")
    except Exception:
        log("WARNING: Could not update SABnzbd download client.")


def notification_needs_update(existing, desired):
    for key, desired_value in desired.items():
        if existing.get(key) != desired_value:
            return True
    return False


def upsert_jellyfin_notification(api_key, jellyfin_api_key, jellyfin_host, jellyfin_port):
    log("Checking existing notifications...")
    try:
        notifications = api_get("/api/v3/notification", api_key)
    except Exception:
        log("WARNING: Could not fetch notifications.")
        return

    existing = None
    for notification in notifications:
        implementation = normalize_name(notification.get("implementation"))
        name = normalize_name(notification.get("name"))
        sort_name = normalize_name(notification.get("sortName"))
        if (
            implementation in {"emby", "mediabrowser"}
            or sort_name in {"emby", "mediabrowser"}
            or "emby / jellyfin" in name
        ):
            existing = notification
            break

    desired_fields = {
        "host": jellyfin_host,
        "port": str(jellyfin_port),
        "apiKey": jellyfin_api_key,
        "useSsl": False,
        "updateLibrary": True,
    }
    desired_settings = {
        "name": "Jellyfin",
        "enable": True,
        "onGrab": False,
        "onDownload": True,
        "onUpgrade": True,
        "onRename": True,
        "onMovieAdded": False,
        "onMovieDelete": True,
        "onMovieFileDelete": True,
        "onMovieFileDeleteForUpgrade": False,
        "onHealthIssue": False,
        "onHealthRestored": False,
        "onApplicationUpdate": False,
        "onManualInteractionRequired": False,
        "includeHealthWarnings": False,
    }

    if existing is None:
        log("Fetching notification schema...")
        try:
            schemas = api_get("/api/v3/notification/schema", api_key)
        except Exception:
            log("WARNING: Could not fetch notification schemas.")
            return

        notification_schema = None
        for schema in schemas:
            implementation = normalize_name(schema.get("implementation"))
            name = normalize_name(schema.get("name"))
            sort_name = normalize_name(schema.get("sortName"))
            if (
                implementation in {"emby", "mediabrowser"}
                or sort_name in {"emby", "mediabrowser"}
                or "emby / jellyfin" in name
            ):
                notification_schema = schema
                break

        if notification_schema is None:
            log("WARNING: Emby/Jellyfin notification schema not found.")
            return

        fields = notification_schema.get("fields", [])
        for field_name, field_value in desired_fields.items():
            if not set_field_value(fields, field_name, field_value):
                log(f"WARNING: Notification schema missing expected field '{field_name}'.")
                return
        for setting_name, setting_value in desired_settings.items():
            notification_schema[setting_name] = setting_value

        log("Adding Jellyfin notification...")
        try:
            api_post("/api/v3/notification", notification_schema, api_key)
            log("Jellyfin notification added.")
        except Exception:
            log("WARNING: Could not add Jellyfin notification.")
        return

    fields = existing.get("fields", [])
    needs_update = False
    for field_name, desired_value in desired_fields.items():
        current_value = get_field_value(fields, field_name)
        if not field_value_matches(field_name, current_value, desired_value):
            if not set_field_value(fields, field_name, desired_value):
                log(f"WARNING: Existing notification missing expected field '{field_name}'.")
                return
            needs_update = True

    if notification_needs_update(existing, desired_settings):
        needs_update = True
        for setting_name, setting_value in desired_settings.items():
            existing[setting_name] = setting_value

    if not needs_update:
        log("Jellyfin notification already configured, skipping.")
        return

    existing_id = existing.get("id")
    if not existing_id:
        log("WARNING: Existing Jellyfin notification has no id; cannot update.")
        return

    log("Updating Jellyfin notification...")
    try:
        api_put(f"/api/v3/notification/{existing_id}", existing, api_key)
        log("Jellyfin notification updated.")
    except Exception:
        log("WARNING: Could not update Jellyfin notification.")


def configure_media_management(api_key):
    log("Fetching current media management settings...")
    try:
        settings = api_get("/api/v3/config/mediamanagement", api_key)
    except Exception:
        log("WARNING: Could not fetch media management settings.")
        return

    desired = {
        "autoRenameFolders": True,
    }

    needs_update = any(settings.get(k) != v for k, v in desired.items())
    if not needs_update:
        log("Media management settings already correct, skipping.")
        return

    settings.update(desired)
    config_id = settings["id"]
    log("Updating media management settings...")
    try:
        api_put(f"/api/v3/config/mediamanagement/{config_id}", settings, api_key)
        log("Media management settings updated.")
    except Exception:
        log("WARNING: Could not update media management settings.")


def configure_naming(api_key):
    log("Fetching current naming settings...")
    try:
        settings = api_get("/api/v3/config/naming", api_key)
    except Exception:
        log("WARNING: Could not fetch naming settings.")
        return

    desired = {
        "renameMovies": True,
        "replaceIllegalCharacters": True,
        "standardMovieFormat": "{Movie Title} ({Release Year})",
        "movieFolderFormat": "{Movie Title} ({Release Year})",
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
    except Exception:
        log("WARNING: Could not update naming settings.")


def add_root_folder(api_key):
    root_folder_path = "/media/movies"
    log(f"Checking root folders...")
    try:
        folders = api_get("/api/v3/rootfolder", api_key)
    except Exception:
        log("WARNING: Could not fetch root folders.")
        return

    existing_paths = {f["path"] for f in folders}
    if root_folder_path in existing_paths:
        log(f"Root folder '{root_folder_path}' already exists, skipping.")
        return

    log(f"Adding root folder '{root_folder_path}'...")
    try:
        api_post("/api/v3/rootfolder", {"path": root_folder_path}, api_key)
        log(f"Root folder '{root_folder_path}' added.")
    except Exception:
        log(f"WARNING: Could not add root folder '{root_folder_path}'.")


def main():
    api_key = os.environ.get("RADARR__AUTH__APIKEY", "")
    if not api_key:
        log("ERROR: RADARR__AUTH__APIKEY is not set. Aborting.")
        sys.exit(1)

    sabnzbd_api_key = os.environ.get("SABNZBD_API_KEY", "")
    if not sabnzbd_api_key:
        log("ERROR: SABNZBD_API_KEY is not set. Aborting.")
        sys.exit(1)

    sabnzbd_host = os.environ.get("SABNZBD_HOST", "sabnzbd")
    sabnzbd_port = os.environ.get("SABNZBD_PORT", "8080")
    jellyfin_api_key = os.environ.get("JELLYFIN_API_KEY", "")
    if not jellyfin_api_key:
        log("ERROR: JELLYFIN_API_KEY is not set. Aborting.")
        sys.exit(1)
    jellyfin_host = os.environ.get("JELLYFIN_HOST", "jellyfin")
    jellyfin_port = os.environ.get("JELLYFIN_PORT", "8096")

    wait_for_radarr(api_key)
    configure_media_management(api_key)
    configure_naming(api_key)
    add_root_folder(api_key)
    upsert_sabnzbd_download_client(api_key, sabnzbd_api_key, sabnzbd_host, sabnzbd_port)
    upsert_jellyfin_notification(api_key, jellyfin_api_key, jellyfin_host, jellyfin_port)
    log("Init complete.")


if __name__ == "__main__":
    if os.fork() == 0:
        try:
            main()
        except Exception:
            log("ERROR: Unhandled exception in init.")
            sys.exit(1)
    else:
        sys.exit(0)
