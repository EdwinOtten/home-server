import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "bazarr_init_config", Path(__file__).with_name("init-config.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class JellyfinConfigurationTests(unittest.TestCase):
    @patch.object(MODULE, "api_request")
    def test_configures_jellyfin_integration(self, api_request):
        api_request.return_value = {
            "data": [
                {"id": "movie-library-id", "name": "Movies", "type": "movies"},
                {"id": "series-library-id", "name": "Series", "type": "tvshows"},
            ]
        }

        MODULE.configure_jellyfin("bazarr-key", "jellyfin-key", "jellyfin", "8096")

        self.assertEqual(
            api_request.call_args_list[0].args,
            (
                "/api/jellyfin/libraries?url=http%3A%2F%2Fjellyfin%3A8096&apikey=jellyfin-key",
                "bazarr-key",
            ),
        )
        self.assertEqual(
            api_request.call_args_list[1].args,
            (
                "/api/system/settings",
                "bazarr-key",
                {
                    "settings-general-use_jellyfin": "true",
                    "settings-jellyfin-url": "http://jellyfin:8096",
                    "settings-jellyfin-apikey": "jellyfin-key",
                    "settings-jellyfin-refresh_method": "immediate",
                    "settings-jellyfin-movie_library": ["Movies"],
                    "settings-jellyfin-movie_library_ids": ["movie-library-id"],
                    "settings-jellyfin-series_library": ["Series"],
                    "settings-jellyfin-series_library_ids": ["series-library-id"],
                    "settings-jellyfin-update_movie_library": "true",
                    "settings-jellyfin-update_series_library": "true",
                },
            ),
        )

    @patch.object(MODULE.time, "sleep")
    @patch.object(MODULE, "api_request")
    def test_retries_until_libraries_available(self, api_request, sleep):
        api_request.side_effect = [
            Exception("not ready"),
            {"data": []},
            {"data": [
                {"id": "m", "name": "Movies", "type": "movies"},
                {"id": "s", "name": "Series", "type": "tvshows"},
            ]},
            None,
        ]

        MODULE.configure_jellyfin("bazarr-key", "jellyfin-key", "jellyfin", "8096")

        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(30)

    @patch.object(MODULE.time, "sleep")
    @patch.object(MODULE, "api_request", side_effect=Exception("down"))
    def test_gives_up_after_five_retries(self, api_request, sleep):
        with self.assertRaises(RuntimeError):
            MODULE.configure_jellyfin("bazarr-key", "jellyfin-key", "jellyfin", "8096")

        self.assertEqual(api_request.call_count, 6)
        self.assertEqual(sleep.call_count, 5)


if __name__ == "__main__":
    unittest.main()
