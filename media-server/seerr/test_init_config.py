import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "seerr_init_config", Path(__file__).with_name("init-config.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DefaultPermissionsTests(TestCase):
    @patch.object(MODULE, "request")
    def test_enables_non_4k_requests_and_auto_approval(self, request):
        request.return_value = {"defaultPermissions": 0}
        headers = {"X-Api-Key": "test-key"}

        MODULE.configure_default_permissions(headers)

        request.assert_any_call("GET", "/api/v1/settings/main", headers=headers, expected=(200,))
        request.assert_any_call(
            "POST",
            "/api/v1/settings/main",
            payload={"defaultPermissions": 160},
            headers=headers,
            expected=(200,),
        )

    @patch.object(MODULE, "request")
    def test_preserves_existing_default_permissions(self, request):
        request.return_value = {"defaultPermissions": 160}

        MODULE.configure_default_permissions({"X-Api-Key": "test-key"})

        request.assert_called_once_with(
            "GET", "/api/v1/settings/main", headers={"X-Api-Key": "test-key"}, expected=(200,)
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
