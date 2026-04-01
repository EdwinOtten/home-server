#!/usr/bin/env python3

# This script is executed indirectly by the LinuxServer.io container customization
# mechanism (mounted at /opt/prowlarr-init-config.py). A small bash wrapper at
# /custom-cont-init.d/init-config.sh calls `exec python3 /opt/prowlarr-init-config.py`
# because LinuxServer runs custom-cont-init.d scripts via /bin/bash, so Python
# scripts cannot be placed in that directory directly.
#
# It forks a background process that:
#   1. Waits for Prowlarr's API to become ready (the service starts after this script exits).
#   2. Adds the NZBGeek indexer if it does not already exist (idempotent):
#      - Fetches the NZBGeek indexer schema from /api/v1/indexer/schema
#      - Matches the NZBGeek preset by sortName/name (definitionName is generic)
#      - Resolves a valid appProfileId from /api/v1/appprofile if the schema uses 0
#      - Sets the API key from the NZBGEEK_API_KEY environment variable
#      - Creates the indexer via POST /api/v1/indexer
#   3. Upserts a SABnzbd download client (idempotent):
#      - Creates the client if it does not exist
#      - Updates host, port and apiKey if they changed
#
# All steps are idempotent: re-running on a subsequent restart is safe.

import json
import os
import sys
import time
import urllib.request

PROWLARR_URL = "http://localhost:9696"
PREFIX = "[prowlarr-init]"


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def normalize_name(value):
    return str(value or "").strip().lower()


def to_positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def api_get(path, api_key):
    req = urllib.request.Request(
        f"{PROWLARR_URL}{path}",
        headers={"X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_post(path, payload, api_key):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{PROWLARR_URL}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_put(path, payload, api_key):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{PROWLARR_URL}{path}",
        data=data,
        method="PUT",
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def wait_for_prowlarr(api_key):
    log("Waiting for Prowlarr API to be ready...")
    while True:
        try:
            api_get("/api/v1/health", api_key)
            break
        except Exception:
            time.sleep(5)
    log("Prowlarr API is up.")


def resolve_app_profile_id(api_key):
    log("Resolving app profile...")
    try:
        profiles = api_get("/api/v1/appprofile", api_key)
    except Exception:
        log("WARNING: Could not fetch app profiles.")
        return 0

    for profile in profiles:
        profile_id = to_positive_int(profile.get("id"))
        if profile_id and normalize_name(profile.get("name")) == "standard":
            return profile_id

    for profile in profiles:
        profile_id = to_positive_int(profile.get("id"))
        if profile_id:
            return profile_id

    log("WARNING: No valid app profiles found. Please configure at least one app profile in Prowlarr.")
    return 0


def add_nzbgeek_indexer(prowlarr_api_key, nzbgeek_api_key):
    log("Checking existing indexers...")
    try:
        indexers = api_get("/api/v1/indexer", prowlarr_api_key)
    except Exception:
        log("WARNING: Could not fetch indexers.")
        return

    existing_names = {i["name"].lower() for i in indexers}
    if "nzbgeek" in existing_names:
        log("NZBGeek indexer already exists, skipping.")
        return

    log("Fetching NZBGeek indexer schema...")
    try:
        schemas = api_get("/api/v1/indexer/schema", prowlarr_api_key)
    except Exception:
        log("WARNING: Could not fetch indexer schemas.")
        return

    nzbgeek_schema = None
    for schema in schemas:
        if normalize_name(schema.get("sortName")) == "nzbgeek":
            nzbgeek_schema = schema
            break
        if normalize_name(schema.get("name")) == "nzbgeek":
            nzbgeek_schema = schema
            break

    if nzbgeek_schema is None:
        log("WARNING: NZBGeek schema not found in available indexer schemas.")
        return

    for field in nzbgeek_schema.get("fields", []):
        if field.get("name") == "apiKey":
            field["value"] = nzbgeek_api_key
            break

    if not to_positive_int(nzbgeek_schema.get("appProfileId")):
        app_profile_id = resolve_app_profile_id(prowlarr_api_key)
        if not app_profile_id:
            log("ERROR: Cannot create NZBGeek indexer without a valid app profile.")
            return
        nzbgeek_schema["appProfileId"] = app_profile_id

    nzbgeek_schema["name"] = "NZBGeek"
    nzbgeek_schema["enable"] = True

    log("Adding NZBGeek indexer...")
    try:
        api_post("/api/v1/indexer", nzbgeek_schema, prowlarr_api_key)
        log("NZBGeek indexer added.")
    except Exception:
        log("WARNING: Could not add NZBGeek indexer.")


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


def upsert_sabnzbd_download_client(prowlarr_api_key, sabnzbd_api_key, sabnzbd_host, sabnzbd_port):
    log("Checking existing download clients...")
    try:
        clients = api_get("/api/v1/downloadclient", prowlarr_api_key)
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

    if existing is None:
        log("Fetching SABnzbd download client schema...")
        try:
            schemas = api_get("/api/v1/downloadclient/schema", prowlarr_api_key)
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

        sabnzbd_schema["name"] = "SABnzbd"
        sabnzbd_schema["enable"] = True

        log("Adding SABnzbd download client...")
        try:
            api_post("/api/v1/downloadclient", sabnzbd_schema, prowlarr_api_key)
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

    if not needs_update:
        log("SABnzbd download client already configured, skipping.")
        return

    existing_id = existing.get("id")
    if not existing_id:
        log("WARNING: Existing SABnzbd download client has no id; cannot update.")
        return

    log("Updating SABnzbd download client...")
    try:
        api_put(f"/api/v1/downloadclient/{existing_id}", existing, prowlarr_api_key)
        log("SABnzbd download client updated.")
    except Exception:
        log("WARNING: Could not update SABnzbd download client.")


def main():
    prowlarr_api_key = os.environ.get("PROWLARR__AUTH__APIKEY", "")
    if not prowlarr_api_key:
        log("ERROR: PROWLARR__AUTH__APIKEY is not set. Aborting.")
        sys.exit(1)

    nzbgeek_api_key = os.environ.get("NZBGEEK_API_KEY", "")
    if not nzbgeek_api_key:
        log("ERROR: NZBGEEK_API_KEY is not set. Aborting.")
        sys.exit(1)

    sabnzbd_api_key = os.environ.get("SABNZBD_API_KEY", "")
    if not sabnzbd_api_key:
        log("ERROR: SABNZBD_API_KEY is not set. Aborting.")
        sys.exit(1)

    sabnzbd_host = os.environ.get("SABNZBD_HOST", "sabnzbd")
    sabnzbd_port = os.environ.get("SABNZBD_PORT", "8080")

    wait_for_prowlarr(prowlarr_api_key)
    add_nzbgeek_indexer(prowlarr_api_key, nzbgeek_api_key)
    upsert_sabnzbd_download_client(prowlarr_api_key, sabnzbd_api_key, sabnzbd_host, sabnzbd_port)
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
