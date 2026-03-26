#!/bin/bash

# This script is executed by the LinuxServer.io container customization mechanism
# (mounted at /custom-cont-init.d/) before Jellyfin starts.
# It injects the JELLYFIN_API_KEY environment variable into Jellyfin's SQLite database
# using Python 3's built-in sqlite3 module (available in the Ubuntu Noble base image,
# no additional packages required).
#
# Note: On the very first startup the database does not yet exist.
# In that case this script exits gracefully; the key will be injected on the next restart
# (after Jellyfin has completed its initial setup wizard and created the database).

DB_PATH="/config/data/jellyfin.db"

if [ -z "${JELLYFIN_API_KEY}" ]; then
  echo "JELLYFIN_API_KEY not set, skipping API key injection"
  exit 0
fi

if [ ! -f "${DB_PATH}" ]; then
  echo "Jellyfin database not found at ${DB_PATH}, skipping API key injection"
  echo "(This is expected on first startup. The key will be injected on the next restart.)"
  exit 0
fi

echo "Injecting Jellyfin API key..."

python3 - <<EOF
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
EOF

echo "Jellyfin API key injection complete."
