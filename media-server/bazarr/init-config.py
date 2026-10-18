#!/usr/bin/env python3

import json
import os
import sys
import time
import urllib.parse
import urllib.request

BAZARR_URL = "http://localhost:6767"
PREFIX = "[bazarr-init]"
PROFILE_NAME = "Dutch and English"


def log(message):
    print(f"{PREFIX} {message}", flush=True)


def api_request(path, api_key, payload=None):
    data = None
    headers = {"X-Api-Key": api_key}
    method = "GET"
    if payload is not None:
        data = urllib.parse.urlencode(payload, doseq=True).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        method = "POST"

    request = urllib.request.Request(
        f"{BAZARR_URL}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else None


def wait_for_bazarr(api_key):
    log("Waiting for Bazarr API to be ready...")
    while True:
        try:
            api_request("/api/system/status", api_key)
            log("Bazarr API is up.")
            return
        except Exception:
            time.sleep(5)


def profile_id(profiles):
    for profile in profiles:
        if str(profile.get("name", "")).strip().casefold() == PROFILE_NAME.casefold():
            return int(profile["profileId"])
    return max((int(profile.get("profileId", 0)) for profile in profiles), default=0) + 1


def configure_bazarr(api_key):
    profiles = api_request("/api/system/languages/profiles", api_key) or []
    selected_profile_id = profile_id(profiles)
    profile = {
        "profileId": selected_profile_id,
        "name": PROFILE_NAME,
        "tag": None,
        "items": [
            {
                "id": 1,
                "language": "nl",
                "audio_exclude": "False",
                "audio_only_include": "False",
                "forced": "False",
                "hi": "False",
            },
            {
                "id": 2,
                "language": "en",
                "audio_exclude": "False",
                "audio_only_include": "False",
                "forced": "False",
                "hi": "False",
            },
        ],
        "cutoff": None,
        "mustContain": [],
        "mustNotContain": [],
        "originalFormat": False,
    }
    profiles = [
        existing
        for existing in profiles
        if str(existing.get("name", "")).strip().casefold() != PROFILE_NAME.casefold()
    ]
    profiles.append(profile)

    api_request(
        "/api/system/settings",
        api_key,
        {
            "languages-enabled": ["nl", "en"],
            "languages-profiles": json.dumps(profiles),
            "settings-general-serie_default_enabled": "true",
            "settings-general-serie_default_profile": str(selected_profile_id),
            "settings-general-movie_default_enabled": "true",
            "settings-general-movie_default_profile": str(selected_profile_id),
            "settings-general-path_mappings": "/media/series,/media/series",
            "settings-general-path_mappings_movie": "/media/movies,/media/movies",
        },
    )
    log(f"Configured Dutch and English profile {selected_profile_id} for movies and series.")


def main():
    api_key = os.environ.get("BAZARR_API_KEY", "")
    if not api_key:
        log("ERROR: BAZARR_API_KEY is not set. Aborting.")
        sys.exit(1)

    wait_for_bazarr(api_key)
    configure_bazarr(api_key)
    log("Init complete.")


if __name__ == "__main__":
    if os.fork() == 0:
        try:
            main()
        except Exception as error:
            log(f"ERROR: Bazarr setup failed: {error}")
            sys.exit(1)
    else:
        sys.exit(0)
