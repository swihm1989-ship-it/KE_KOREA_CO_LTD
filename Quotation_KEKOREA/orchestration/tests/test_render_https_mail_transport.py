"""Offline tests for the free-Render HTTPS sending adapter. No real emails."""
import base64
import io
import json
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.orchestration.workflows.email_outbox import (
    send_resend_https, SMTPBeforeDataError,
)
from Quotation_KEKOREA.orchestration.workflows.email_signature_design import LOGO_CID


class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return b'{"id":"test-provider-confirmation"}'


class HttpsTransportTests(unittest.TestCase):
    def test_missing_key_fails_without_network(self):
        with patch.dict("os.environ", {
            "RESEND_API_KEY": "",
            "RESEND_FROM_EMAIL": "david.ihm@ke-korea.com",
        }):
            with self.assertRaises(SMTPBeforeDataError):
                send_resend_https(None, "recipient@example.com", "Subject", "Body",
                                  opener=lambda *a, **kw: self.fail("No network allowed"))

    def test_approved_payload_carries_pdf_logo_and_threading(self):
        sent = []
        def opener(req, timeout):
            sent.append(req)
            return FakeResponse()
        logo = b"\x89PNG\r\n\x1a\n" + b"test-logo"
        pdf = b"%PDF-1.4\nmock-pdf-data"
        with patch.dict("os.environ", {
            "RESEND_API_KEY": "re_synthetic_test_only",
            "RESEND_FROM_EMAIL": "david.ihm@ke-korea.com",
        }):
            send_resend_https(
                None, "recipient@example.com", "Re: Subject", "Hello",
                "<original@example.com>", html_body='<img src="cid:' + LOGO_CID + '">',
                logo_bytes=logo, attachments=[{"filename": "final.pdf", "data": pdf}],
                opener=opener,
            )
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].full_url, "https://api.resend.com/emails")
        payload = json.loads(sent[0].data)
        self.assertEqual(payload["from"], "david.ihm@ke-korea.com")
        self.assertEqual(payload["to"], ["recipient@example.com"])
        self.assertEqual(payload["headers"]["In-Reply-To"], "<original@example.com>")
        self.assertEqual(len(payload["attachments"]), 2)
        self.assertEqual(payload["attachments"][0]["content_id"], LOGO_CID)
        self.assertEqual(base64.b64decode(payload["attachments"][1]["content"]), pdf)


if __name__ == "__main__":
    unittest.main()
