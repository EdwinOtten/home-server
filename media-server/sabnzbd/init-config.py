#!/usr/bin/env python3

# This script is executed indirectly by the LinuxServer.io container customization
# mechanism (mounted at /opt/init-config.py). A small bash wrapper at
# /custom-cont-init.d/init-config.sh calls `exec python3 /opt/init-config.py`
# because LinuxServer runs custom-cont-init.d scripts via /bin/bash, so Python
# scripts cannot be placed in that directory directly.
#
# It manages a sabnzbd.ini configuration file that:
#   1. Marks the setup wizard as completed (wizard_completed = 1).
#   2. Sets the API key and NZB key.
#   3. Configures a Usenet server from environment variables.
#
# Idempotent: on first boot it generates the file from scratch; on subsequent
# boots it updates only the managed keys, preserving any settings that SABnzbd
# itself has written.

import os
import re
import sys

CONFIG_PATH = "/config/sabnzbd.ini"
PREFIX = "[sabnzbd-init]"


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def get_env_config():
    """Read and validate configuration from environment variables.

    Returns (misc_settings, server_name, server_settings, category_name, category_settings).
    """
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

    misc_settings = {
        "api_key": api_key,
        "nzb_key": nzb_key,
        "username": username,
        "password": password,
        "wizard_completed": "1",
        "host": "0.0.0.0",
        "port": "8080",
        "download_dir": "/media/downloads/usenet/incomplete",
        "complete_dir": "/media/downloads/usenet/complete",
    }

    server_name = usenet_host
    server_settings = {
        "name": usenet_host,
        "host": usenet_host,
        "port": usenet_port,
        "username": usenet_user,
        "password": usenet_pass,
        "connections": usenet_conn,
        "ssl": str(ssl),
        "ssl_verify": "2",
        "ssl_ciphers": '""',
        "enable": "1",
        "required": "0",
        "optional": "0",
        "retention": "0",
        "expire_date": '""',
        "quota": '""',
        "priority": "0",
    }

    category_name = "default"
    category_settings = {"name": category_name}

    return misc_settings, server_name, server_settings, category_name, category_settings


def generate_config(config_path, misc_settings, server_name, server_settings, category_name, category_settings):
    """Generate a new sabnzbd.ini from scratch."""
    lines = ["[misc]\n"]
    for k, v in misc_settings.items():
        lines.append(f"{k} = {v}\n")
    lines.append("\n[servers]\n")
    lines.append(f"[[{server_name}]]\n")
    for k, v in server_settings.items():
        lines.append(f"{k} = {v}\n")
    lines.append("\n[categories]\n")
    lines.append(f"[[{category_name}]]\n")
    for k, v in category_settings.items():
        lines.append(f"{k} = {v}\n")

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        f.writelines(lines)


_RE_SUBSECTION = re.compile(r"^\[\[(.+?)\]\]\s*$")
_RE_SECTION = re.compile(r"^\[([^\[\]]+)\]\s*$")


def update_config(config_path, misc_settings, server_name, server_settings, category_name, category_settings):
    """Update managed keys in an existing sabnzbd.ini, preserving all other settings.

    Handles configobj-style ``[[subsection]]`` headers used by SABnzbd.
    """
    with open(config_path, "r") as f:
        lines = f.readlines()

    result = []
    section = None
    subsection = None
    misc_seen = set()
    server_seen = set()
    category_seen = set()
    misc_section_found = False
    servers_section_found = False
    categories_section_found = False
    our_server_found = False
    our_category_found = False

    def flush_missing_misc():
        for k, v in misc_settings.items():
            if k not in misc_seen:
                result.append(f"{k} = {v}\n")
                misc_seen.add(k)

    def flush_missing_server():
        for k, v in server_settings.items():
            if k not in server_seen:
                result.append(f"{k} = {v}\n")
                server_seen.add(k)

    def flush_missing_category():
        for k, v in category_settings.items():
            if k not in category_seen:
                result.append(f"{k} = {v}\n")
                category_seen.add(k)

    for line in lines:
        stripped = line.strip()

        sub_match = _RE_SUBSECTION.match(stripped)
        sec_match = _RE_SECTION.match(stripped) if not sub_match else None

        if sub_match:
            # Leaving a previous subsection — flush any missing managed keys
            if section == "servers" and subsection == server_name:
                flush_missing_server()
            elif section == "categories" and subsection == category_name:
                flush_missing_category()
            subsection = sub_match.group(1).strip()
            if section == "servers" and subsection == server_name:
                our_server_found = True
                server_seen.clear()
            elif section == "categories" and subsection == category_name:
                our_category_found = True
                category_seen.clear()
            result.append(line)

        elif sec_match:
            # Leaving a previous section — flush missing keys / add missing subsections
            if section == "misc":
                flush_missing_misc()
            elif section == "servers":
                if subsection == server_name:
                    flush_missing_server()
                if not our_server_found:
                    result.append(f"[[{server_name}]]\n")
                    for k, v in server_settings.items():
                        result.append(f"{k} = {v}\n")
                    our_server_found = True
            elif section == "categories":
                if subsection == category_name:
                    flush_missing_category()
                if not our_category_found:
                    result.append(f"[[{category_name}]]\n")
                    for k, v in category_settings.items():
                        result.append(f"{k} = {v}\n")
                    our_category_found = True

            section = sec_match.group(1).strip()
            subsection = None
            if section == "misc":
                misc_section_found = True
            elif section == "servers":
                servers_section_found = True
            elif section == "categories":
                categories_section_found = True
            result.append(line)

        elif "=" in stripped and not stripped.startswith("#") and not stripped.startswith(";"):
            key = stripped.split("=", 1)[0].strip()
            if section == "misc" and key in misc_settings:
                result.append(f"{key} = {misc_settings[key]}\n")
                misc_seen.add(key)
            elif section == "servers" and subsection == server_name and key in server_settings:
                result.append(f"{key} = {server_settings[key]}\n")
                server_seen.add(key)
            elif section == "categories" and subsection == category_name and key in category_settings:
                result.append(f"{key} = {category_settings[key]}\n")
                category_seen.add(key)
            else:
                result.append(line)
        else:
            result.append(line)

    # End-of-file: flush remaining managed keys for the last active section
    if section == "misc":
        flush_missing_misc()
    elif section == "servers":
        if subsection == server_name:
            flush_missing_server()
        if not our_server_found:
            result.append(f"[[{server_name}]]\n")
            for k, v in server_settings.items():
                result.append(f"{k} = {v}\n")
            our_server_found = True
    elif section == "categories":
        if subsection == category_name:
            flush_missing_category()
        if not our_category_found:
            result.append(f"[[{category_name}]]\n")
            for k, v in category_settings.items():
                result.append(f"{k} = {v}\n")
            our_category_found = True

    # Add entire sections that were not present in the file at all
    if not misc_section_found:
        result.append("\n[misc]\n")
        for k, v in misc_settings.items():
            result.append(f"{k} = {v}\n")

    if not servers_section_found:
        result.append("\n[servers]\n")
        result.append(f"[[{server_name}]]\n")
        for k, v in server_settings.items():
            result.append(f"{k} = {v}\n")

    if not categories_section_found:
        result.append("\n[categories]\n")
        result.append(f"[[{category_name}]]\n")
        for k, v in category_settings.items():
            result.append(f"{k} = {v}\n")

    with open(config_path, "w") as f:
        f.writelines(result)


def main():
    misc_settings, server_name, server_settings, category_name, category_settings = get_env_config()

    if os.path.exists(CONFIG_PATH):
        log(f"Updating managed settings in {CONFIG_PATH}...")
        update_config(CONFIG_PATH, misc_settings, server_name, server_settings, category_name, category_settings)
        log(f"Updated {CONFIG_PATH}.")
    else:
        log(f"Generating {CONFIG_PATH}...")
        generate_config(CONFIG_PATH, misc_settings, server_name, server_settings, category_name, category_settings)
        log(f"Generated {CONFIG_PATH} with wizard_completed=1 and Usenet server configured.")

    uid = int(os.environ.get("PUID", "1000"))
    gid = int(os.environ.get("PGID", "1000"))
    os.chown(CONFIG_PATH, uid, gid)


if __name__ == "__main__":
    main()
