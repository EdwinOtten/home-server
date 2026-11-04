import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MEDIA_SERVER = Path(__file__).parent


def load_config(name):
    spec = importlib.util.spec_from_file_location(
        name, MEDIA_SERVER / name / "init-config.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JellyfinNotificationTests(unittest.TestCase):
    def test_radarr_notification_matches_issue_settings(self):
        self.assert_notification_settings(
            load_config("radarr"),
            {
                "onGrab": True,
                "onDownload": True,
                "onUpgrade": True,
                "onRename": True,
                "onMovieAdded": False,
                "onMovieDelete": True,
                "onMovieFileDelete": True,
                "onMovieFileDeleteForUpgrade": True,
                "onHealthIssue": False,
                "onHealthRestored": False,
                "onApplicationUpdate": True,
                "onManualInteractionRequired": False,
            },
        )

    def test_sonarr_notification_matches_issue_settings(self):
        self.assert_notification_settings(
            load_config("sonarr"),
            {
                "onGrab": True,
                "onDownload": True,
                "onUpgrade": True,
                "onImportComplete": True,
                "onRename": True,
                "onSeriesAdd": False,
                "onSeriesDelete": True,
                "onEpisodeFileDelete": True,
                "onEpisodeFileDeleteForUpgrade": True,
                "onHealthIssue": False,
                "onHealthRestored": False,
                "onApplicationUpdate": True,
                "onManualInteractionRequired": False,
            },
        )

    def test_notification_update_failures_are_propagated(self):
        for service in ("sonarr", "radarr"):
            with self.subTest(service=service):
                module = load_config(service)
                existing = {
                    "id": 1,
                    "implementation": "Emby",
                    "name": "Jellyfin",
                    "fields": [
                        {"name": "host", "value": "jellyfin"},
                        {"name": "port", "value": "8096"},
                        {"name": "apiKey", "value": "old-key"},
                        {"name": "useSsl", "value": False},
                        {"name": "updateLibrary", "value": True},
                    ],
                    "onGrab": True,
                }
                with patch.object(module, "api_get", return_value=[existing]), patch.object(
                    module, "api_put", side_effect=OSError("API unavailable")
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "Could not update Jellyfin notification"
                    ):
                        module.upsert_jellyfin_notification(
                            "arr-key", "new-key", "jellyfin", "8096"
                        )

    def assert_notification_settings(self, module, expected_settings):
        schema = {
            "implementation": "Emby",
            "name": "Jellyfin",
            "fields": [
                {"name": "host", "value": "jellyfin"},
                {"name": "port", "value": "8096"},
                {"name": "apiKey", "value": "jellyfin-key"},
                {"name": "useSsl", "value": False},
                {"name": "updateLibrary", "value": True},
            ],
        }
        with patch.object(module, "api_get", side_effect=[[], [schema]]), patch.object(
            module, "api_post"
        ) as api_post:
            module.upsert_jellyfin_notification(
                "arr-key", "jellyfin-key", "jellyfin", "8096"
            )

        payload = api_post.call_args.args[1]
        self.assertEqual(payload["name"], "Jellyfin")
        for setting, value in expected_settings.items():
            self.assertEqual(payload[setting], value)

    def test_main_retry_mechanism_retries_and_succeeds(self):
        for service in ("sonarr", "radarr"):
            with self.subTest(service=service):
                module = load_config(service)
                calls = 0

                def mock_run_init():
                    nonlocal calls
                    calls += 1
                    if calls < 3:
                        raise RuntimeError(f"Simulated failure on attempt {calls}")

                with patch.object(module, "run_init", side_effect=mock_run_init), patch.dict(
                    "os.environ", {"INIT_CONFIG_RETRIES": "4", "INIT_CONFIG_RETRY_DELAY": "0"}
                ), patch("time.sleep") as mock_sleep, patch.object(module, "log") as mock_log:
                    module.main()
                    self.assertEqual(calls, 3)
                    self.assertEqual(mock_sleep.call_count, 2)
                    logged_messages = [call.args[0] for call in mock_log.call_args_list]
                    self.assertTrue(
                        any("attempt 1/4" in msg.lower() for msg in logged_messages)
                    )
                    self.assertTrue(
                        any("attempt 2/4" in msg.lower() for msg in logged_messages)
                    )
                    self.assertTrue(
                        any("attempt 3/4" in msg.lower() for msg in logged_messages)
                    )

    def test_main_retry_mechanism_fails_when_exhausted(self):
        for service in ("sonarr", "radarr"):
            with self.subTest(service=service):
                module = load_config(service)
                with patch.object(
                    module, "run_init", side_effect=RuntimeError("Persistent failure")
                ), patch.dict(
                    "os.environ", {"INIT_CONFIG_RETRIES": "3", "INIT_CONFIG_RETRY_DELAY": "0"}
                ), patch("time.sleep") as mock_sleep, patch.object(module, "log") as mock_log:
                    with self.assertRaises(SystemExit) as cm:
                        module.main()
                    self.assertEqual(cm.exception.code, 1)
                    self.assertEqual(mock_sleep.call_count, 2)
                    logged_messages = [call.args[0] for call in mock_log.call_args_list]
                    self.assertTrue(
                        any("failed after 3 attempts" in msg.lower() for msg in logged_messages)
                    )


if __name__ == "__main__":
    unittest.main()
