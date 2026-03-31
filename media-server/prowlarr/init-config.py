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
#      - Sets the API key from the NZBGEEK_API_KEY environment variable
#      - Creates the indexer via POST /api/v1/indexer
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


def wait_for_prowlarr(api_key):
    log("Waiting for Prowlarr API to be ready...")
    while True:
        try:
            api_get("/api/v1/health", api_key)
            break
        except Exception:
            time.sleep(5)
    log("Prowlarr API is up.")


def add_nzbgeek_indexer(prowlarr_api_key, nzbgeek_api_key):
    log("Checking existing indexers...")
    try:
        indexers = api_get("/api/v1/indexer", prowlarr_api_key)
    except Exception as exc:
        log(f"WARNING: Could not fetch indexers: {exc}")
        return

    existing_names = {i["name"].lower() for i in indexers}
    if "nzbgeek" in existing_names:
        log("NZBGeek indexer already exists, skipping.")
        return

    log("Fetching NZBGeek indexer schema...")
    try:
        schemas = api_get("/api/v1/indexer/schema", prowlarr_api_key)
    except Exception as exc:
        log(f"WARNING: Could not fetch indexer schemas: {exc}")
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

    nzbgeek_schema["name"] = "NZBGeek"
    nzbgeek_schema["enable"] = True

    log("Adding NZBGeek indexer...")
    try:
        api_post("/api/v1/indexer", nzbgeek_schema, prowlarr_api_key)
        log("NZBGeek indexer added.")
    except Exception as exc:
        log(f"WARNING: Could not add NZBGeek indexer: {exc}")


def main():
    prowlarr_api_key = os.environ.get("PROWLARR__AUTH__APIKEY", "")
    if not prowlarr_api_key:
        log("ERROR: PROWLARR__AUTH__APIKEY is not set. Aborting.")
        sys.exit(1)

    nzbgeek_api_key = os.environ.get("NZBGEEK_API_KEY", "")
    if not nzbgeek_api_key:
        log("ERROR: NZBGEEK_API_KEY is not set. Aborting.")
        sys.exit(1)

    wait_for_prowlarr(prowlarr_api_key)
    add_nzbgeek_indexer(prowlarr_api_key, nzbgeek_api_key)
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
