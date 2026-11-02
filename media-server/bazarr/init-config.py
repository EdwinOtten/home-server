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
JELLYFIN_MOVIE_LIBRARY = "Movies"
JELLYFIN_SERIES_LIBRARY = "Series"


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


def configure_jellyfin(api_key, jellyfin_api_key, jellyfin_host, jellyfin_port):
    jellyfin_url = f"http://{jellyfin_host}:{jellyfin_port}"
    libraries = []
    try:
        response = api_request(
            f"/api/jellyfin/libraries?{urllib.parse.urlencode({'url': jellyfin_url, 'apikey': jellyfin_api_key})}",
            api_key,
        )
        libraries = (response or {}).get("data", [])
    except Exception as error:
        log(f"WARNING: Could not retrieve Jellyfin libraries: {error}")

    movie_library_ids = [
        library["id"]
        for library in libraries
        if library.get("name") == JELLYFIN_MOVIE_LIBRARY and library.get("type") == "movies"
    ]
    series_library_ids = [
        library["id"]
        for library in libraries
        if library.get("name") == JELLYFIN_SERIES_LIBRARY and library.get("type") == "tvshows"
    ]
    api_request(
        "/api/system/settings",
        api_key,
        {
            "settings-general-use_jellyfin": "true",
            "settings-jellyfin-url": jellyfin_url,
            "settings-jellyfin-apikey": jellyfin_api_key,
            "settings-jellyfin-refresh_method": "immediate",
            "settings-jellyfin-movie_library": [JELLYFIN_MOVIE_LIBRARY],
            "settings-jellyfin-movie_library_ids": movie_library_ids,
            "settings-jellyfin-series_library": [JELLYFIN_SERIES_LIBRARY],
            "settings-jellyfin-series_library_ids": series_library_ids,
            "settings-jellyfin-update_movie_library": "true",
            "settings-jellyfin-update_series_library": "true",
        },
    )
    log("Configured Jellyfin integration for Movies and Series.")


def main():
    api_key = os.environ.get("BAZARR_API_KEY", "")
    if not api_key:
        log("ERROR: BAZARR_API_KEY is not set. Aborting.")
        sys.exit(1)

    jellyfin_api_key = os.environ.get("JELLYFIN_API_KEY", "")
    if not jellyfin_api_key:
        log("ERROR: JELLYFIN_API_KEY is not set. Aborting.")
        sys.exit(1)
    jellyfin_host = os.environ.get("JELLYFIN_HOST", "jellyfin")
    jellyfin_port = os.environ.get("JELLYFIN_PORT", "8096")

    wait_for_bazarr(api_key)
    configure_bazarr(api_key)
    configure_jellyfin(api_key, jellyfin_api_key, jellyfin_host, jellyfin_port)
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
