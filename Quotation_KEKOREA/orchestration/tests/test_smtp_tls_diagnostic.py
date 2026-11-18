"""Synthetic SMTP TLS failure diagnostics, no network or live credentials."""
import ssl
import unittest
from unittest.mock import MagicMock, patch

from Quotation_KEKOREA.orchestration.adapters import whois_mail


class SmtpTlsDiagnosticTests(unittest.TestCase):
    def test_starttls_handshake_reports_safe_reason_and_stage(self):
        endpoint=whois_mail.Endpoint(
            host="smtp.example.test",port=587,security="starttls",
            username="owner@example.test",password="SENSITIVE-TEST-PASSWORD")
        client=MagicMock()
        problem=ssl.SSLError(1,"synthetic TLS failure")
        problem.reason="SSLV3_ALERT_HANDSHAKE_FAILURE"
        client.starttls.side_effect=problem
        with patch.object(whois_mail.smtplib,"SMTP",return_value=client):
            with self.assertRaises(whois_mail.MailConnectionError) as ctx:
                whois_mail.probe_smtp(endpoint)
        msg=str(ctx.exception)
        self.assertIn("STARTTLS",msg)
        self.assertIn("starttls",msg)
        self.assertIn("SSLV3_ALERT_HANDSHAKE_FAILURE",msg)
        self.assertNotIn("SENSITIVE-TEST-PASSWORD",msg)
        client.login.assert_not_called()
        client.sendmail.assert_not_called()
        client.send_message.assert_not_called()

    def test_unknown_ssl_reason_is_sanitized(self):
        endpoint=whois_mail.Endpoint(
            host="smtp.example.test",port=587,security="starttls",
            username="owner@example.test",password="SENSITIVE")
        client=MagicMock()
        problem=ssl.SSLError(1,"PRIVATE TLS DETAILS")
        problem.reason="UNKNOWN_PRIVATE_STRING"
        client.starttls.side_effect=problem
        with patch.object(whois_mail.smtplib,"SMTP",return_value=client):
            with self.assertRaises(whois_mail.MailConnectionError) as ctx:
                whois_mail.probe_smtp(endpoint)
        self.assertIn("OTHER_SSL_ERROR",str(ctx.exception))
        self.assertNotIn("PRIVATE TLS DETAILS",str(ctx.exception))
        self.assertNotIn("UNKNOWN_PRIVATE_STRING",str(ctx.exception))
