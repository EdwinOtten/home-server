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
#   4. Upserts Radarr and Sonarr applications (idempotent):
#      - Creates each app if it does not exist
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


def has_field(fields, field_name):
    for field in fields:
        if normalize_name(field.get("name")) == normalize_name(field_name):
            return True
    return False


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

    if normalize_name(field_name) == "baseurl":
        return str(current_value).rstrip("/") == str(desired_value).rstrip("/")

    return str(current_value) == str(desired_value)


def build_application_base_url(app_host, app_port):
    host = str(app_host or "").strip()
    if not host:
        return ""

    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")

    port = str(app_port or "").strip()
    if port:
        return f"http://{host}:{port}"
    return f"http://{host}"


def normalize_category_mappings(mappings):
    normalized = []
    if not isinstance(mappings, list):
        return normalized
    for item in mappings:
        if not isinstance(item, dict):
            continue
        client_category = str(item.get("clientCategory", "")).strip().lower()
        categories = item.get("categories", [])
        category_ids = sorted(
            {
                cid
                for cid in (to_positive_int(value) for value in categories)
                if cid
            }
        )
        normalized.append((client_category, tuple(category_ids)))
    return sorted(normalized)


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
    desired_optional = {
        "category": "default",
    }
    desired_category_mappings = [
        {"clientCategory": "movies", "categories": [2000]},
        {"clientCategory": "tv", "categories": [5000]},
    ]

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
        for field_name, field_value in desired_optional.items():
            set_field_value(fields, field_name, field_value)

        sabnzbd_schema["name"] = "SABnzbd"
        sabnzbd_schema["enable"] = True
        sabnzbd_schema["categories"] = desired_category_mappings

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
    for field_name, desired_value in desired_optional.items():
        current_value = get_field_value(fields, field_name)
        if current_value is None or not field_value_matches(field_name, current_value, desired_value):
            if not set_field_value(fields, field_name, desired_value):
                log(f"WARNING: Existing SABnzbd client missing optional field '{field_name}'.")
                continue
            needs_update = True

    current_mappings = existing.get("categories")
    if normalize_category_mappings(current_mappings) != normalize_category_mappings(desired_category_mappings):
        existing["categories"] = desired_category_mappings
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
        api_put(f"/api/v1/downloadclient/{existing_id}", existing, prowlarr_api_key)
        log("SABnzbd download client updated.")
    except Exception:
        log("WARNING: Could not update SABnzbd download client.")


def upsert_application(prowlarr_api_key, implementation, application_name, app_api_key, app_host, app_port):
    log(f"Checking existing {application_name} application...")
    try:
        applications = api_get("/api/v1/applications", prowlarr_api_key)
    except Exception:
        log("WARNING: Could not fetch applications.")
        return

    existing = None
    target_name = normalize_name(application_name)
    target_implementation = normalize_name(implementation)
    for application in applications:
        if (
            normalize_name(application.get("implementation")) == target_implementation
            or normalize_name(application.get("name")) == target_name
        ):
            existing = application
            break

    desired_api_key = app_api_key
    desired_host = app_host
    desired_port = str(app_port)
    desired_base_url = build_application_base_url(app_host, app_port)

    if existing is None:
        log(f"Fetching {application_name} application schema...")
        try:
            schemas = api_get("/api/v1/applications/schema", prowlarr_api_key)
        except Exception:
            log("WARNING: Could not fetch application schemas.")
            return

        app_schema = None
        for schema in schemas:
            if (
                normalize_name(schema.get("implementation")) == target_implementation
                or normalize_name(schema.get("name")) == target_name
                or normalize_name(schema.get("sortName")) == target_name
            ):
                app_schema = schema
                break

        if app_schema is None:
            log(f"WARNING: {application_name} schema not found in available application schemas.")
            return

        fields = app_schema.get("fields", [])

        if not set_field_value(fields, "apiKey", desired_api_key):
            log(f"WARNING: {application_name} schema missing expected field 'apiKey'.")
            return

        has_host_field = False
        if has_field(fields, "host"):
            has_host_field = set_field_value(fields, "host", desired_host)
        elif has_field(fields, "hostname"):
            has_host_field = set_field_value(fields, "hostname", desired_host)

        has_port_field = set_field_value(fields, "port", desired_port) if has_field(fields, "port") else False
        has_base_url_field = (
            set_field_value(fields, "baseUrl", desired_base_url) if has_field(fields, "baseUrl") else False
        )

        if not (has_base_url_field or has_host_field):
            log(f"WARNING: {application_name} schema missing expected connection field ('baseUrl' or 'host').")
            return

        if has_host_field and not has_port_field:
            log(f"WARNING: {application_name} schema missing expected field 'port'.")
            return

        app_schema["name"] = application_name

        log(f"Adding {application_name} application...")
        try:
            api_post("/api/v1/applications", app_schema, prowlarr_api_key)
            log(f"{application_name} application added.")
        except Exception:
            log(f"WARNING: Could not add {application_name} application.")
        return

    fields = existing.get("fields", [])
    needs_update = False
    current_api_key = get_field_value(fields, "apiKey")
    if not field_value_matches("apiKey", current_api_key, desired_api_key):
        needs_update = True
        if not set_field_value(fields, "apiKey", desired_api_key):
            log(f"WARNING: Existing {application_name} application missing expected field 'apiKey'.")
            return

    current_host_value = get_field_value(fields, "host")
    current_hostname_value = get_field_value(fields, "hostname")
    current_port = get_field_value(fields, "port")
    current_base_url = get_field_value(fields, "baseUrl")

    has_host_field = current_host_value is not None or current_hostname_value is not None
    has_port_field = current_port is not None
    has_base_url_field = current_base_url is not None

    if has_host_field:
        current_host = current_host_value
        host_field_name = "host"
        if current_host is None:
            current_host = current_hostname_value
            host_field_name = "hostname"
        if not field_value_matches(host_field_name, current_host, desired_host):
            needs_update = True
            if not set_field_value(fields, host_field_name, desired_host):
                log(f"WARNING: Existing {application_name} application missing expected field '{host_field_name}'.")
                return

    if has_port_field:
        if not field_value_matches("port", current_port, desired_port):
            needs_update = True
            if not set_field_value(fields, "port", desired_port):
                log(f"WARNING: Existing {application_name} application missing expected field 'port'.")
                return

    if has_base_url_field:
        if not field_value_matches("baseUrl", current_base_url, desired_base_url):
            needs_update = True
            if not set_field_value(fields, "baseUrl", desired_base_url):
                log(f"WARNING: Existing {application_name} application missing expected field 'baseUrl'.")
                return

    if not (has_base_url_field or has_host_field):
        log(f"WARNING: Existing {application_name} application missing expected connection field ('baseUrl' or 'host').")
        return

    if not needs_update:
        log(f"{application_name} application already configured, skipping.")
        return

    existing_id = existing.get("id")
    if not existing_id:
        log(f"WARNING: Existing {application_name} application has no id; cannot update.")
        return

    log(f"Updating {application_name} application...")
    try:
        api_put(f"/api/v1/applications/{existing_id}", existing, prowlarr_api_key)
        log(f"{application_name} application updated.")
    except Exception:
        log(f"WARNING: Could not update {application_name} application.")


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

    radarr_api_key = os.environ.get("RADARR_API_KEY", "")
    if not radarr_api_key:
        log("ERROR: RADARR_API_KEY is not set. Aborting.")
        sys.exit(1)

    sonarr_api_key = os.environ.get("SONARR_API_KEY", "")
    if not sonarr_api_key:
        log("ERROR: SONARR_API_KEY is not set. Aborting.")
        sys.exit(1)

    sabnzbd_host = os.environ.get("SABNZBD_HOST", "sabnzbd")
    sabnzbd_port = os.environ.get("SABNZBD_PORT", "8080")
    radarr_host = os.environ.get("RADARR_HOST", "radarr")
    radarr_port = os.environ.get("RADARR_PORT", "7878")
    sonarr_host = os.environ.get("SONARR_HOST", "sonarr")
    sonarr_port = os.environ.get("SONARR_PORT", "8989")

    wait_for_prowlarr(prowlarr_api_key)
    add_nzbgeek_indexer(prowlarr_api_key, nzbgeek_api_key)
    upsert_sabnzbd_download_client(prowlarr_api_key, sabnzbd_api_key, sabnzbd_host, sabnzbd_port)
    upsert_application(prowlarr_api_key, "radarr", "Radarr", radarr_api_key, radarr_host, radarr_port)
    upsert_application(prowlarr_api_key, "sonarr", "Sonarr", sonarr_api_key, sonarr_host, sonarr_port)
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
