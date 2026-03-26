#!/bin/bash

# This script is executed by the LinuxServer.io container customization mechanism
# (mounted at /custom-cont-init.d/) before Jellyfin starts.
# It injects the JELLYFIN_API_KEY environment variable into Jellyfin's SQLite database.
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

# Ensure sqlite3 CLI is available (not included in the base LSIO image by default)
if ! command -v sqlite3 &>/dev/null; then
  echo "Installing sqlite3..."
  apt-get update -qq && apt-get install -y -qq sqlite3
fi

echo "Injecting Jellyfin API key..."

# Escape single quotes in the API key to prevent SQL injection
ESCAPED_KEY="${JELLYFIN_API_KEY//\'/\'\'}"

sqlite3 "${DB_PATH}" <<EOF
INSERT OR IGNORE INTO ApiKeys (DateCreated, DateLastActivity, Name, AccessToken)
VALUES (datetime('now'), datetime('now'), 'docker-managed', '${ESCAPED_KEY}');
EOF

echo "Jellyfin API key injection complete."
