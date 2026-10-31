import importlib.util
import os
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


if __name__ == "__main__":
    unittest.main()
