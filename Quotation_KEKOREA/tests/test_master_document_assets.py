"""Tests for server-only seal resolution and safe configuration diagnostics."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Quotation_KEKOREA.orchestration.workflows.document_assets import (
    document_export_env, seal_health,
)


class DocumentAssetTests(unittest.TestCase):
    def test_streamlit_secrets_override_stale_environment(self):
        secrets = {
            "SUPABASE_URL": "https://jusozufdsnpdxezxptfp.supabase.co",
            "SUPABASE_SECRET_KEY": "new-private-key",
        }
        env = {"SUPABASE_URL": "https://wrong.supabase.co",
               "SUPABASE_SECRET_KEY": "old-private-key"}
        values = document_export_env(secrets, env)
        self.assertEqual(values["SUPABASE_URL"], secrets["SUPABASE_URL"])
        self.assertEqual(values["SUPABASE_SECRET_KEY"], secrets["SUPABASE_SECRET_KEY"])

    def test_nested_auth_legacy_setting_still_supported(self):
        values = document_export_env({"auth": {
            "SUPABASE_URL": "https://jusozufdsnpdxezxptfp.supabase.co",
            "SUPABASE_SECRET_KEY": "private-key",
        }}, {})
        self.assertEqual(values["SUPABASE_SECRET_KEY"], "private-key")

    def test_existing_seal_is_validated_without_exposing_secret(self):
        with TemporaryDirectory() as folder:
            def success(root, env):
                return Path(root) / "assets" / "image.png", b"PNG-private-data", None
            state, info = seal_health({
                "SUPABASE_URL": "https://jusozufdsnpdxezxptfp.supabase.co",
                "SUPABASE_SECRET_KEY": "private-test-secret",
            }, root=folder, resolver=success)
            self.assertEqual(state, "ready")
            self.assertNotIn("private-test-secret", info)
            self.assertNotIn("PNG-private-data", info)

    def test_wrong_project_and_missing_key_distinct(self):
        with TemporaryDirectory() as folder:
            state, info = seal_health({"SUPABASE_URL": "https://wrong.supabase.co",
                                       "SUPABASE_SECRET_KEY": "private-test-secret"},
                                      root=folder)
            self.assertEqual(state, "wrong_project")
            self.assertNotIn("private-test-secret", info)
            state, info = seal_health({}, root=folder)
            self.assertEqual(state, "not_configured")

    def test_remote_storage_error_is_redacted(self):
        with TemporaryDirectory() as folder:
            def failed(root, env):
                return Path(root) / "assets" / "image.png", None, "HTTP 403 private-secret"
            state, info = seal_health({
                "SUPABASE_URL": "https://jusozufdsnpdxezxptfp.supabase.co",
                "SUPABASE_SECRET_KEY": "private-secret",
            }, root=folder, resolver=failed)
            self.assertEqual(state, "access_denied")
            self.assertNotIn("private-secret", info)
