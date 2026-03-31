#!/usr/bin/env python3

# This script is executed indirectly by the LinuxServer.io container customization
# mechanism (mounted at /opt/init-config.py). A small bash wrapper at
# /custom-cont-init.d/init-config.sh calls `exec python3 /opt/init-config.py`
# because LinuxServer runs custom-cont-init.d scripts via /bin/bash, so Python
# scripts cannot be placed in that directory directly.
#
# It generates a sabnzbd.ini configuration file that:
#   1. Marks the setup wizard as completed (wizard_completed = 1).
#   2. Sets the API key and NZB key.
#   3. Configures a Usenet server from environment variables.
#
# The config is only generated when /config/sabnzbd.ini does not yet exist,
# making subsequent container restarts safe (idempotent).

import os
import sys

CONFIG_PATH = "/config/sabnzbd.ini"
PREFIX = "[sabnzbd-init]"


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def main():
    if os.path.exists(CONFIG_PATH):
        log(f"{CONFIG_PATH} already exists, skipping generation.")
        return

    api_key = os.environ.get("SABNZBD_API_KEY", "")
    nzb_key = os.environ.get("SABNZBD_NZB_KEY", "")
    username = os.environ.get("SABNZBD_USER", "")
    password = os.environ.get("SABNZBD_PASSWORD", "")
    usenet_host = os.environ.get("USENET_SECRET_SERVER", "")
    usenet_user = os.environ.get("USENET_SECRET_USER", "")
    usenet_pass = os.environ.get("USENET_PASSWORD", "")
    usenet_port = os.environ.get("USENET_PORT", "563")
    usenet_conn = os.environ.get("USENET_CONNECTIONS", "50")

    required = {
        "SABNZBD_API_KEY": api_key,
        "SABNZBD_NZB_KEY": nzb_key,
        "USENET_SECRET_SERVER": usenet_host,
        "USENET_SECRET_USER": usenet_user,
        "USENET_PASSWORD": usenet_pass,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        log(f"ERROR: Missing required environment variables: {', '.join(missing)}. Aborting.")
        sys.exit(1)

    # Enable SSL for well-known secure Usenet ports
    ssl = 1 if usenet_port in ("563", "443") else 0

    config = (
        "[misc]\n"
        f"api_key = {api_key}\n"
        f"nzb_key = {nzb_key}\n"
        f"username = {username}\n"
        f"password = {password}\n"
        "wizard_completed = 1\n"
        "host = 0.0.0.0\n"
        "port = 8080\n"
        "download_dir = /data/incomplete\n"
        "complete_dir = /data\n"
        "\n"
        "[servers]\n"
        f"[[{usenet_host}]]\n"
        f"name = {usenet_host}\n"
        f"host = {usenet_host}\n"
        f"port = {usenet_port}\n"
        f"username = {usenet_user}\n"
        f"password = {usenet_pass}\n"
        f"connections = {usenet_conn}\n"
        f"ssl = {ssl}\n"
        "ssl_verify = 2\n"
        "ssl_ciphers = \"\"\n"
        "enable = 1\n"
        "required = 0\n"
        "optional = 0\n"
        "retention = 0\n"
        "expire_date = \"\"\n"
        "quota = \"\"\n"
        "priority = 0\n"
    )

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write(config)

    uid = int(os.environ.get("PUID", "1000"))
    gid = int(os.environ.get("PGID", "1000"))
    os.chown(CONFIG_PATH, uid, gid)

    log(f"Generated {CONFIG_PATH} with wizard_completed=1 and Usenet server configured.")


if __name__ == "__main__":
    main()
