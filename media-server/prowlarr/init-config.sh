#!/bin/bash
# Trampoline: LinuxServer's custom-cont-init.d runs scripts via /bin/bash,
# so Python scripts cannot be placed there directly.
# This wrapper installs python3 if needed, then delegates to /opt/prowlarr-init-config.py.

if ! command -v python3 >/dev/null 2>&1; then
    echo "[prowlarr-init] python3 not found; installing..."
    if apk add --no-cache python3; then
        echo "[prowlarr-init] python3 installed."
    else
        echo "[prowlarr-init] ERROR: Failed to install python3. Aborting."
        exit 1
    fi
fi

exec python3 /opt/prowlarr-init-config.py
