import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "jellyfin_init_config", Path(__file__).with_name("init-config.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegularUsersFromEnvTests(unittest.TestCase):
    def test_parses_comma_separated_usernames_and_passwords(self):
        with patch.dict(
            os.environ,
            {
                "JELLYFIN_REGULAR_USERS": "Kiki, Nala, Obi-Wan",
                "JELLYFIN_REGULAR_USER_PASSWORDS": "Kiki,Nala,Obi-Wan",
            },
            clear=False,
        ):
            self.assertEqual(
                MODULE.regular_users_from_env(),
                [("Kiki", "Kiki"), ("Nala", "Nala"), ("Obi-Wan", "Obi-Wan")],
            )

    def test_rejects_mismatched_usernames_and_passwords(self):
        with patch.dict(
            os.environ,
            {
                "JELLYFIN_REGULAR_USERS": "Kiki,Nala",
                "JELLYFIN_REGULAR_USER_PASSWORDS": "Kiki",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "same number"):
                MODULE.regular_users_from_env()

    def test_sets_required_regular_user_permissions(self):
        policy = MODULE.regular_user_policy(
            {
                "AuthenticationProviderId": "Default",
                "PasswordResetProviderId": "Default",
                "EnableContentDownloading": True,
            }
        )

        self.assertEqual(
            policy,
            {
                "AuthenticationProviderId": "Default",
                "PasswordResetProviderId": "Default",
                "EnableContentDownloading": True,
                "IsAdministrator": False,
                "IsHidden": False,
                "EnableRemoteAccess": True,
                "EnableSharedDeviceControl": True,
                "EnableMediaPlayback": True,
                "EnableAudioPlaybackTranscoding": True,
                "EnableVideoPlaybackTranscoding": True,
                "EnablePlaybackRemuxing": True,
                "EnableContentDeletion": False,
                "EnableContentDeletionFromFolders": [],
                "EnableAllFolders": True,
            },
        )


class LibraryScanStartupTriggerTests(unittest.TestCase):
    def test_adds_startup_trigger_without_removing_existing_triggers(self):
        tasks = [{
            "Id": "library-scan",
            "Key": "RefreshLibrary",
            "Triggers": [{"Type": "IntervalTrigger", "IntervalTicks": 432000000000}],
        }]

        with patch.object(MODULE, "api_request", side_effect=[tasks, None]) as request:
            MODULE.configure_library_scan_on_startup("MediaBrowser Token=\"token\"")

        self.assertEqual(
            request.call_args_list[1].kwargs["payload"],
            [
                {"Type": "IntervalTrigger", "IntervalTicks": 432000000000},
                {"Type": "StartupTrigger"},
            ],
        )

    def test_does_not_update_task_when_startup_trigger_exists(self):
        tasks = [{
            "Id": "library-scan",
            "Name": "Scan Media Library",
            "Triggers": [{"Type": "StartupTrigger"}],
        }]

        with patch.object(MODULE, "api_request", return_value=tasks) as request:
            MODULE.configure_library_scan_on_startup("MediaBrowser Token=\"token\"")

        request.assert_called_once_with("/ScheduledTasks", "MediaBrowser Token=\"token\"")


class AdminAuthenticationTests(unittest.TestCase):
    def test_authentication_header_is_reused_by_setup_functions(self):
        auth_header = "MediaBrowser Token=\"token\""
        with patch.object(MODULE, "get_admin_auth_header", return_value=auth_header) as authenticate, \
             patch.object(MODULE, "add_media_libraries") as add_libraries, \
             patch.object(MODULE, "configure_library_scan_on_startup") as configure_scan, \
             patch.object(MODULE, "provision_regular_users") as provision_users, \
             patch.object(MODULE, "wait_for_jellyfin"), \
             patch.object(MODULE, "complete_wizard_if_needed"), \
             patch.object(MODULE, "inject_api_key"):
            MODULE.main()

        authenticate.assert_called_once_with()
        add_libraries.assert_called_once_with(auth_header)
        configure_scan.assert_called_once_with(auth_header)
        provision_users.assert_called_once_with(auth_header)


class ApiKeyInjectionTests(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.NamedTemporaryFile()
        self.addCleanup(self.db.close)
        self.addCleanup(os.unlink, self.db.name)
        with sqlite3.connect(self.db.name) as con:
            con.execute(
                "CREATE TABLE ApiKeys (DateCreated TEXT, DateLastActivity TEXT, "
                "Name TEXT UNIQUE, AccessToken TEXT UNIQUE)"
            )

    def test_updates_existing_managed_key(self):
        with sqlite3.connect(self.db.name) as con:
            con.execute(
                "INSERT INTO ApiKeys VALUES ('created', 'last-used', 'docker-managed', 'old-key')"
            )

        with patch.object(MODULE, "DB_PATH", self.db.name), patch.dict(
            os.environ, {"JELLYFIN_API_KEY": "configured-key"}
        ):
            MODULE.inject_api_key()

        with sqlite3.connect(self.db.name) as con:
            self.assertEqual(
                con.execute(
                    "SELECT Name, AccessToken FROM ApiKeys"
                ).fetchall(),
                [("docker-managed", "configured-key")],
            )

    def test_inserts_managed_key_when_missing(self):
        with patch.object(MODULE, "DB_PATH", self.db.name), patch.dict(
            os.environ, {"JELLYFIN_API_KEY": "configured-key"}
        ):
            MODULE.inject_api_key()

        with sqlite3.connect(self.db.name) as con:
            self.assertEqual(
                con.execute(
                    "SELECT Name, AccessToken FROM ApiKeys"
                ).fetchall(),
                [("docker-managed", "configured-key")],
            )


if __name__ == "__main__":
    unittest.main()
