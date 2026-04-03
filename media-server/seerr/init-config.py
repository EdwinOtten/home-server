#!/usr/bin/env python3

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PREFIX = "[seerr-init]"
SEERR_URL = os.environ.get("SEERR_URL", "http://seerr:5055").rstrip("/")


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def request(method, path, payload=None, headers=None, expected=(200,)):
    url = f"{SEERR_URL}{path}"
    body = None if payload is None else json.dumps(payload).encode()
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode() if response.length != 0 else ""
            if response.status not in expected:
                raise RuntimeError(f"Unexpected status {response.status} for {method} {path}")
            if not data:
                return {}
            return json.loads(data)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(errors="ignore")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {error_body}") from exc


def api_key_headers():
    key = os.environ.get("SEERR_API_KEY", "")
    if not key:
        raise RuntimeError("SEERR_API_KEY must be set.")
    return {"X-Api-Key": key}


def wait_for_seerr():
    log("Waiting for Seerr API...")
    while True:
        try:
            status = request("GET", "/api/v1/status")
            version = status.get("version", "unknown")
            log(f"Seerr is up (version: {version}).")
            return
        except Exception:
            time.sleep(5)


def wait_for_public_settings():
    while True:
        try:
            return request("GET", "/api/v1/settings/public")
        except Exception:
            time.sleep(2)


def authenticate_jellyfin_admin(email):
    admin_user = os.environ.get("JELLYFIN_ADMIN_USER", "")
    admin_password = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "")
    if not admin_user or not admin_password:
        raise RuntimeError("JELLYFIN_ADMIN_USER and JELLYFIN_ADMIN_PASSWORD must be set.")

    log("Authenticating Seerr with Jellyfin admin account...")
    return request(
        "POST",
        "/api/v1/auth/jellyfin",
        payload={
            "username": admin_user,
            "password": admin_password,
            "hostname": "jellyfin",
            "port": 8096,
            "useSsl": False,
            "urlBase": "",
            "email": email,
            "serverType": 2,
        },
        expected=(200,),
    )


def get_cookie_headers(set_cookie_headers):
    cookie_values = []
    for header in set_cookie_headers:
        if header:
            cookie_values.append(header.split(";", 1)[0])
    if not cookie_values:
        raise RuntimeError("No session cookie returned by Seerr auth endpoint.")
    return {"Cookie": "; ".join(cookie_values)}


def authenticate_with_raw_response(email):
    admin_user = os.environ.get("JELLYFIN_ADMIN_USER", "")
    admin_password = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "")
    payload = json.dumps(
        {
            "username": admin_user,
            "password": admin_password,
            "hostname": "jellyfin",
            "port": 8096,
            "useSsl": False,
            "urlBase": "",
            "email": email,
            "serverType": 2,
        }
    ).encode()
    req = urllib.request.Request(
        f"{SEERR_URL}/api/v1/auth/jellyfin",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected status {response.status} for auth")
        response.read()
        set_cookie = response.headers.get_all("Set-Cookie", [])
        return get_cookie_headers(set_cookie)


def configure_jellyfin(api_headers):
    jellyfin_api_key = os.environ.get("JELLYFIN_API_KEY", "")
    if not jellyfin_api_key:
        raise RuntimeError("JELLYFIN_API_KEY must be set.")

    log("Configuring Jellyfin in Seerr settings...")
    request(
        "POST",
        "/api/v1/settings/jellyfin",
        payload={
            "ip": "jellyfin",
            "port": 8096,
            "useSsl": False,
            "urlBase": "",
            "externalHostname": "",
            "jellyfinForgotPasswordUrl": "",
            "apiKey": jellyfin_api_key,
        },
        headers=api_headers,
        expected=(200,),
    )

    log("Syncing and enabling Jellyfin libraries...")
    libraries = request(
        "GET",
        "/api/v1/settings/jellyfin/library?sync=true",
        headers=api_headers,
        expected=(200,),
    )
    library_ids = [lib.get("id") for lib in libraries if lib.get("id")]
    if library_ids:
        enable_query = urllib.parse.quote(",".join(library_ids), safe="")
        request(
            "GET",
            f"/api/v1/settings/jellyfin/library?enable={enable_query}",
            headers=api_headers,
            expected=(200,),
        )


def test_radarr(api_headers):
    radarr_api_key = os.environ.get("RADARR_API_KEY", "")
    if not radarr_api_key:
        raise RuntimeError("RADARR_API_KEY must be set.")
    return request(
        "POST",
        "/api/v1/settings/radarr/test",
        payload={
            "hostname": "radarr",
            "port": 7878,
            "apiKey": radarr_api_key,
            "useSsl": False,
            "baseUrl": "",
        },
        headers=api_headers,
        expected=(200,),
    )


def test_sonarr(api_headers):
    sonarr_api_key = os.environ.get("SONARR_API_KEY", "")
    if not sonarr_api_key:
        raise RuntimeError("SONARR_API_KEY must be set.")
    return request(
        "POST",
        "/api/v1/settings/sonarr/test",
        payload={
            "hostname": "sonarr",
            "port": 8989,
            "apiKey": sonarr_api_key,
            "useSsl": False,
            "baseUrl": "",
        },
        headers=api_headers,
        expected=(200,),
    )


def configure_radarr(api_headers):
    existing = request("GET", "/api/v1/settings/radarr", headers=api_headers, expected=(200,))
    if existing:
        log("Radarr is already configured, skipping.")
        return

    test_data = test_radarr(api_headers)
    profile = (test_data.get("profiles") or [{}])[0]
    root = (test_data.get("rootFolders") or [{}])[0]
    if not profile.get("id") or not root.get("path"):
        raise RuntimeError("Unable to determine Radarr profile/root folder from test endpoint.")

    log("Creating Radarr integration in Seerr...")
    request(
        "POST",
        "/api/v1/settings/radarr",
        payload={
            "name": "Radarr",
            "hostname": "radarr",
            "port": 7878,
            "apiKey": os.environ["RADARR_API_KEY"],
            "useSsl": False,
            "baseUrl": "",
            "activeProfileId": int(profile["id"]),
            "activeProfileName": profile.get("name"),
            "activeDirectory": root.get("path"),
            "is4k": False,
            "minimumAvailability": "released",
            "isDefault": True,
            "externalUrl": "",
            "syncEnabled": False,
            "preventSearch": False,
            "tagRequests": False,
            "tags": [],
        },
        headers=api_headers,
        expected=(201,),
    )


def configure_sonarr(api_headers):
    existing = request("GET", "/api/v1/settings/sonarr", headers=api_headers, expected=(200,))
    if existing:
        log("Sonarr is already configured, skipping.")
        return

    test_data = test_sonarr(api_headers)
    profile = (test_data.get("profiles") or [{}])[0]
    root = (test_data.get("rootFolders") or [{}])[0]
    language_profiles = test_data.get("languageProfiles") or []
    language_id = language_profiles[0]["id"] if language_profiles else None
    if not profile.get("id") or not root.get("path"):
        raise RuntimeError("Unable to determine Sonarr profile/root folder from test endpoint.")

    log("Creating Sonarr integration in Seerr...")
    payload = {
        "name": "Sonarr",
        "hostname": "sonarr",
        "port": 8989,
        "apiKey": os.environ["SONARR_API_KEY"],
        "useSsl": False,
        "baseUrl": "",
        "activeProfileId": int(profile["id"]),
        "activeProfileName": profile.get("name"),
        "activeDirectory": root.get("path"),
        "seriesType": "standard",
        "animeSeriesType": "anime",
        "tags": [],
        "animeTags": [],
        "is4k": False,
        "isDefault": True,
        "enableSeasonFolders": True,
        "externalUrl": "",
        "syncEnabled": False,
        "preventSearch": False,
        "tagRequests": False,
        "monitorNewItems": "all",
    }
    if language_id is not None:
        payload["activeLanguageProfileId"] = int(language_id)

    request(
        "POST",
        "/api/v1/settings/sonarr",
        payload=payload,
        headers=api_headers,
        expected=(201,),
    )


def initialize_setup(api_headers):
    public = request("GET", "/api/v1/settings/public", headers=api_headers, expected=(200,))
    if public.get("initialized"):
        log("Seerr is already initialized, skipping final initialize step.")
        return
    log("Finalizing Seerr setup...")
    request("POST", "/api/v1/settings/initialize", headers=api_headers, expected=(200,))


def main():
    wait_for_seerr()
    public = wait_for_public_settings()
    settings_headers = api_key_headers()
    if public.get("initialized"):
        log("Seerr already initialized; ensuring integrations are present via API key.")
    else:
        log("Seerr is not initialized yet; setup wizard automation will run.")
        email = os.environ.get("SEERR_EMAIL", "info@edwinotten.com")
        authenticate_jellyfin_admin(email)
        settings_headers = authenticate_with_raw_response(email)

    configure_jellyfin(settings_headers)
    configure_radarr(settings_headers)
    configure_sonarr(settings_headers)
    initialize_setup(settings_headers)
    log("Seerr setup automation completed successfully.")


if __name__ == "__main__":
    main()
