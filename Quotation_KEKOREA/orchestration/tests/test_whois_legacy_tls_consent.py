"""WHOIS 1024-bit DHE compatibility must require explicit user consent.

Only synthetic local tests; no SMTP credentials or messages are transmitted.
"""
import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from Quotation_KEKOREA.orchestration.adapters import whois_mail
from Quotation_KEKOREA.orchestration.workflows import email_outbox


class WhoisLegacyTlsConsentTests(unittest.TestCase):
    def setUp(self):
        self.endpoint=whois_mail.Endpoint(
            host="smtp.whoisworks.com",port=587,security="starttls",
            username="synthetic@example.test",password="SYNTHETIC-NOT-A-SECRET")

    def test_legacy_context_is_tls12_cert_verified_and_cipher_restricted(self):
        ctx=whois_mail._whois_legacy_dh_context(self.endpoint)
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(ctx.maximum_version, ssl.TLSVersion.TLSv1_2)
        self.assertIn("DHE-RSA-AES256-GCM-SHA384",
                      [row["name"] for row in ctx.get_ciphers()])

    def test_scope_only_verified_whois_endpoint(self):
        for host,port,mode in [
            ("attacker.example",587,"starttls"),
            ("mail.w.ke-korea.com",587,"starttls"),
            ("smtp.whoisworks.com",465,"ssl"),
            ("smtp.whoisworks.com",25,"starttls"),
        ]:
            with self.subTest(host=host,port=port,mode=mode):
                endpoint=whois_mail.Endpoint(host,port,mode,
                                             "user@example.test","dummy")
                with self.assertRaises(whois_mail.MailConnectionError):
                    whois_mail._whois_legacy_dh_context(endpoint)

    def test_probe_never_sends_with_consent(self):
        client=MagicMock()
        with patch.object(whois_mail.smtplib,"SMTP",return_value=client):
            whois_mail.probe_smtp(self.endpoint,allow_legacy_dh=True)
        self.assertTrue(client.starttls.called)
        ctx=client.starttls.call_args.kwargs["context"]
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode,ssl.CERT_REQUIRED)
        client.login.assert_called_once()
        client.send_message.assert_not_called()
        client.sendmail.assert_not_called()

    def test_send_uses_strict_default_and_weak_only_when_explicit(self):
        cfg=SimpleNamespace(smtp=self.endpoint)
        def send(opted_in):
            client=MagicMock()
            with patch.object(email_outbox.smtplib,"SMTP",return_value=client):
                email_outbox.send_smtp(
                    cfg,"buyer@example.test","Synthetic PDF","This is a test",
                    allow_legacy_dh=opted_in)
            tls_ctx=client.starttls.call_args.kwargs["context"]
            client.send_message.assert_called_once()
            return tls_ctx
        strict=send(False)
        opt_in=send(True)
        self.assertGreaterEqual(strict.security_level,2)
        self.assertEqual(opt_in.security_level,1)
        self.assertTrue(opt_in.check_hostname)
        self.assertEqual(opt_in.verify_mode,ssl.CERT_REQUIRED)


if __name__=="__main__":
    unittest.main()
