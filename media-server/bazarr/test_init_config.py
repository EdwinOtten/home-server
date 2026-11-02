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
        MODULE.configure_jellyfin("bazarr-key", "jellyfin-key", "jellyfin", "8096")

        api_request.assert_called_once_with(
            "/api/system/settings",
            "bazarr-key",
            {
                "settings-general-use_jellyfin": "true",
                "settings-jellyfin-url": "http://jellyfin:8096",
                "settings-jellyfin-apikey": "jellyfin-key",
                "settings-jellyfin-refresh_method": "immediate",
                "settings-jellyfin-movie_library": ["Movies"],
                "settings-jellyfin-series_library": ["Series"],
                "settings-jellyfin-update_movie_library": "true",
                "settings-jellyfin-update_series_library": "true",
            },
        )


if __name__ == "__main__":
    unittest.main()
