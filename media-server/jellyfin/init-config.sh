#!/bin/bash

# This script is executed by the LinuxServer.io container customization mechanism
# (mounted at /custom-cont-init.d/) before Jellyfin starts.
#
# It forks a background process that:
#   1. Waits for Jellyfin to become ready (the service starts after this script exits).
#   2. Completes the setup wizard via Jellyfin's Startup API (if not already done):
#      - Sets English locale and metadata language.
#      - Sets the admin username and password from JELLYFIN_ADMIN_USER / JELLYFIN_ADMIN_PASSWORD.
#      - Enables remote access (disables UPnP auto-mapping).
#      - Marks the wizard as complete.
#   3. Injects JELLYFIN_API_KEY into the ApiKeys table via Python 3's built-in sqlite3
#      module. Python 3 is installed automatically if not already present.
#      (The Jellyfin API does not allow specifying a pre-determined key value; it always
#      generates a random one, so the exact key must be written directly to the database.)
#
# All steps are idempotent: re-running on a subsequent restart is safe.

JELLYFIN_URL="http://localhost:8096"
DB_PATH="/config/data/data/jellyfin.db"

(
  echo "[jellyfin-init] Waiting for Jellyfin to be ready..."
  until curl -sf "${JELLYFIN_URL}/health" > /dev/null 2>&1; do
    sleep 5
  done
  echo "[jellyfin-init] Jellyfin is up. Sleeping for 20 seconds..."
  sleep 20

  # Install Python3 if not available
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[jellyfin-init] python3 not found; installing..."
    if apt-get update -q && apt-get install -y -q --no-install-recommends python3; then
      echo "[jellyfin-init] python3 installed."
    else
      echo "[jellyfin-init] ERROR: Failed to install python3; subsequent steps require python. Aborting."
      # Don't continue, because later we call python3 for JSON parsing and DB injection
      exit 1
    fi
  fi

  command -v python3 >/dev/null 2>&1 || { echo "[jellyfin-init] ERROR: python3 still missing"; exit 1; }
  # ── 1. Complete the setup wizard (idempotent) ────────────────────────────────

  WIZARD_COMPLETE=$(curl -sSf "${JELLYFIN_URL}/System/Info/Public" 2>/dev/null | \
    python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('StartupWizardCompleted', False))" 2>/dev/null)

  if [ -z "${WIZARD_COMPLETE}" ]; then
    echo "[jellyfin-init] WARNING: Could not determine wizard status; skipping wizard setup."
    WIZARD_COMPLETE="True"
  fi

  if [ "${WIZARD_COMPLETE}" = "True" ]; then
    echo "[jellyfin-init] Setup wizard already complete, skipping."
  else
    echo "[jellyfin-init] Completing setup wizard..."

    if [ -z "${JELLYFIN_ADMIN_USER}" ] || [ -z "${JELLYFIN_ADMIN_PASSWORD}" ]; then
      echo "[jellyfin-init] ERROR: JELLYFIN_ADMIN_USER and JELLYFIN_ADMIN_PASSWORD must be set to complete the wizard."
      exit 1
    fi

    # Set English locale and metadata language
    if ! curl -sSf -X POST "${JELLYFIN_URL}/Startup/Configuration" \
      -H "Content-Type: application/json" \
      -d '{"ServerName":"jellyfin","UICulture":"en-US","MetadataCountryCode":"US","PreferredMetadataLanguage":"en"}'; then
      echo "[jellyfin-init] ERROR: Failed to set startup configuration."
      exit 1
    fi

    # Set admin username and password (build JSON via Python to safely handle special chars)
    SETUP_USER_PAYLOAD=$(python3 -c "
import json, os
print(json.dumps({
    'Name': os.environ.get('JELLYFIN_ADMIN_USER', ''),
    'Password': os.environ.get('JELLYFIN_ADMIN_PASSWORD', '')
}))")
    echo "[jellyfin-init] Payload to be sent to /Startup/User: ${SETUP_USER_PAYLOAD}" 
    if ! curl -sSf -X POST "${JELLYFIN_URL}/Startup/User" \
      -H "Content-Type: application/json" \
      -d "${SETUP_USER_PAYLOAD}"; then
      echo "[jellyfin-init] ERROR: Failed to set admin user."
      exit 1
    fi

    # Enable remote access, disable UPnP auto-mapping
    if ! curl -sSf -X POST "${JELLYFIN_URL}/Startup/RemoteAccess" \
      -H "Content-Type: application/json" \
      -d '{"EnableRemoteAccess":true,"EnableAutomaticPortMapping":false}'; then
      echo "[jellyfin-init] ERROR: Failed to configure remote access."
      exit 1
    fi

    # Complete the wizard
    if ! curl -sSf -X POST "${JELLYFIN_URL}/Startup/Complete"; then
      echo "[jellyfin-init] ERROR: Failed to complete wizard."
      exit 1
    fi

    echo "[jellyfin-init] Setup wizard complete."
  fi

  # ── 2. Inject the pre-determined API key ─────────────────────────────────────

  if [ -z "${JELLYFIN_API_KEY}" ]; then
    echo "[jellyfin-init] JELLYFIN_API_KEY not set, skipping API key injection"
  else
    # Wait until the database file exists (created by Jellyfin on first run)
    until [ -f "${DB_PATH}" ]; do
      echo "[jellyfin-init] Waiting for Jellyfin database..."
      sleep 5
    done

    echo "[jellyfin-init] Injecting API key..."

    python3 - <<PYEOF
import os
import sqlite3
import sys

db_path = "${DB_PATH}"
api_key = os.environ.get("JELLYFIN_API_KEY", "")

if not api_key:
    print("JELLYFIN_API_KEY is empty, skipping")
    sys.exit(0)

with sqlite3.connect(db_path) as con:
    con.execute(
        "INSERT OR IGNORE INTO ApiKeys (DateCreated, DateLastActivity, Name, AccessToken) "
        "VALUES (datetime('now'), datetime('now'), 'docker-managed', ?)",
        (api_key,)
    )
PYEOF

    echo "[jellyfin-init] API key injection complete."
  fi
) &
