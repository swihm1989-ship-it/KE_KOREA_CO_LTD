"""OIDC Render startup must not generate settings without all secrets."""
import tempfile
import unittest
from pathlib import Path

from Quotation_KEKOREA.orchestration.ui.secure_launch import (
    build_oidc_secrets, configure_runtime,
)


class SecureLaunchTests(unittest.TestCase):
    def test_missing_oidc_values_create_no_secrets_file(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(configure_runtime({}, Path(folder)))
            self.assertFalse((Path(folder) / ".streamlit" / "secrets.toml").exists())

    def test_invalid_redirect_url_is_rejected(self):
        values = {"ORCHESTRATION_OIDC_CLIENT_ID": "a",
                  "ORCHESTRATION_OIDC_CLIENT_SECRET": "b",
                  "ORCHESTRATION_OIDC_METADATA_URL": "https://accounts.google.com/.well-known/openid-configuration",
                  "ORCHESTRATION_OIDC_REDIRECT_URI": "http://example.com/oauth2callback",
                  "ORCHESTRATION_OIDC_COOKIE_SECRET": "x" * 40}
        with self.assertRaises(ValueError):
            build_oidc_secrets(values)

    def test_valid_oidc_values_generate_private_toml(self):
        env = {"ORCHESTRATION_OIDC_CLIENT_ID": "app",
               "ORCHESTRATION_OIDC_CLIENT_SECRET": "secret-example",
               "ORCHESTRATION_OIDC_METADATA_URL": "https://accounts.google.com/.well-known/openid-configuration",
               "ORCHESTRATION_OIDC_REDIRECT_URI": "https://demo.onrender.com/oauth2callback",
               "ORCHESTRATION_OIDC_COOKIE_SECRET": "x" * 40}
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(configure_runtime(env, Path(folder)))
            text = (Path(folder) / ".streamlit" / "secrets.toml").read_text(encoding="utf-8")
            self.assertIn("[auth]", text)
            self.assertIn("secret-example", text)
            self.assertNotIn("ORCHESTRATION_OIDC_CLIENT_SECRET", text)


if __name__ == "__main__":
    unittest.main()
