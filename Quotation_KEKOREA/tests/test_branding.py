"""Seal selection must not silently use an older cloud image."""
import base64
import hashlib
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from Quotation_KEKOREA.agent.branding import resolve_company_seal


class CompanySealTests(TestCase):
    def test_local_requested_image_takes_priority_over_old_secret(self):
        with patch.object(Path, "is_file", return_value=True):
            path, data, error = resolve_company_seal("root", {"KEKOREA_COMPANY_SEAL_BASE64": "old"})
        self.assertEqual(path.name, "image.png")
        self.assertIsNone(data)
        self.assertIsNone(error)

    def test_cloud_secret_must_match_requested_image(self):
        data = b"\x89PNG\r\n\x1a\nexample"
        encoded = base64.b64encode(data).decode("ascii")
        expected = hashlib.sha256(data).hexdigest()
        with patch.object(Path, "is_file", return_value=False):
            _, actual, error = resolve_company_seal("root", {"KEKOREA_COMPANY_SEAL_BASE64": encoded}, expected_sha256=expected)
            self.assertEqual(actual, data)
            self.assertIsNone(error)
            _, actual, error = resolve_company_seal("root", {"KEKOREA_COMPANY_SEAL_BASE64": encoded}, expected_sha256="0" * 64)
            self.assertIsNone(actual)
            self.assertIn("does not match", error)

    def test_missing_or_invalid_cloud_secret_reports_setup_error(self):
        with patch.object(Path, "is_file", return_value=False):
            self.assertIn("missing", resolve_company_seal("root", {})[2])
            self.assertIn("Base64", resolve_company_seal("root", {"KEKOREA_COMPANY_SEAL_BASE64": "!"})[2])
