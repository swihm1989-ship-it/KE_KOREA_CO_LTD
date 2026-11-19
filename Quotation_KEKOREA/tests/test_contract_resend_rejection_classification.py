"""Definitive Resend HTTP rejection cannot be marked as ambiguous sent mail."""
import io
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from Quotation_KEKOREA.orchestration.workflows.email_outbox import (
    SMTPBeforeDataError, send_resend_https,
)


class ResendKnownRejectionTests(unittest.TestCase):
    def test_all_known_http_rejections_cannot_be_accepted(self):
        for code in (400, 401, 403, 404, 422, 429):
            with self.subTest(status=code):
                def reject(req, timeout):
                    raise HTTPError(req.full_url, code, "rejected", {}, io.BytesIO(b"{}"))
                with patch.dict(os.environ, {
                    "RESEND_API_KEY": "re_dummy_offline_no_send",
                    "RESEND_FROM_EMAIL": "david.ihm@ke-korea.com",
                }):
                    with self.assertRaises(SMTPBeforeDataError) as caught:
                        send_resend_https(
                            None, "swihm1989@gmail.com", "Synthetic test",
                            "Testing only", opener=reject,
                        )
                self.assertEqual(caught.exception.stage, "https_rejected")

    def test_resend_acceptance_returns_provider_id(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"id":"synthetic-provider-id"}'
        with patch.dict(os.environ, {
            "RESEND_API_KEY": "re_dummy_offline_no_send",
            "RESEND_FROM_EMAIL": "david.ihm@ke-korea.com",
        }):
            provider_id = send_resend_https(
                None, "swihm1989@gmail.com", "Synthetic test", "Testing only",
                opener=lambda req, timeout: FakeResponse(),
            )
        self.assertEqual(provider_id, "synthetic-provider-id")


if __name__ == "__main__":
    unittest.main()
