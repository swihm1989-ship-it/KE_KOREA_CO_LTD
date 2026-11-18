"""WHOIS transport is selected automatically for the scoped SMTP endpoint.

Synthetic settings only; no SMTP network calls, credentials or email sends.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from Quotation_KEKOREA.orchestration.ui import email_outbox_page
from Quotation_KEKOREA.orchestration.adapters.whois_mail import Endpoint


class AutomaticWhoisTransportTests(TestCase):
    def test_verified_whois_587_starttls_is_automatic(self):
        endpoint=Endpoint("smtp.whoisworks.com",587,"starttls",
                          "demo@example.test","synthetic")
        with patch("Quotation_KEKOREA.orchestration.ui.mailbox_page._settings",
                   return_value={}), patch(
                   "Quotation_KEKOREA.orchestration.adapters.whois_mail.mail_config",
                   return_value=SimpleNamespace(smtp=endpoint)):
            self.assertTrue(email_outbox_page._automatic_whois_tls("demo@example.test"))

    def test_other_endpoints_keep_standard_tls(self):
        for endpoint in (
            Endpoint("unrelated.example.test",587,"starttls","demo@example.test","synthetic"),
            Endpoint("smtp.whoisworks.com",465,"ssl","demo@example.test","synthetic"),
            Endpoint("smtp.whoisworks.com",2525,"starttls","demo@example.test","synthetic"),
        ):
            with self.subTest(host=endpoint.host,port=endpoint.port):
                with patch("Quotation_KEKOREA.orchestration.ui.mailbox_page._settings",
                           return_value={}), patch(
                           "Quotation_KEKOREA.orchestration.adapters.whois_mail.mail_config",
                           return_value=SimpleNamespace(smtp=endpoint)):
                    self.assertFalse(email_outbox_page._automatic_whois_tls("demo@example.test"))

    def test_missing_mail_configuration_does_not_turn_on_weak_tls(self):
        with patch("Quotation_KEKOREA.orchestration.ui.mailbox_page._settings",
                   side_effect=ValueError("No mail config")):
            self.assertFalse(email_outbox_page._automatic_whois_tls("demo@example.test"))
