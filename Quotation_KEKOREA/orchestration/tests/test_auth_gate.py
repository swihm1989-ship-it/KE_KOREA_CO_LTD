"""OIDC authorization must fail closed, including absent config and unverified email."""
import unittest

from Quotation_KEKOREA.orchestration.security.auth_gate import authorized_email


class AuthGateTests(unittest.TestCase):
    def test_matching_verified_oidc_email_is_allowed(self):
        user = {"is_logged_in": True, "email": "OWNER@example.com", "email_verified": True, "exp": 4102444800}
        self.assertEqual(authorized_email(user, "owner@example.com"), "owner@example.com")

    def test_absent_allowlist_denies_even_logged_in_user(self):
        self.assertIsNone(authorized_email({"is_logged_in": True, "email": "a@example.com", "email_verified": True}, ""))

    def test_unverified_email_denied(self):
        self.assertIsNone(authorized_email({"is_logged_in": True, "email": "a@example.com", "email_verified": False, "exp": 4102444800}, "a@example.com"))
        self.assertIsNone(authorized_email({"is_logged_in": True, "email": "a@example.com"}, "a@example.com"))

    def test_anonymous_and_unlisted_emails_denied(self):
        self.assertIsNone(authorized_email({"is_logged_in": False, "email": "owner@example.com", "email_verified": True}, "owner@example.com"))
        self.assertIsNone(authorized_email({"is_logged_in": True, "email": "other@example.com", "email_verified": True}, "owner@example.com"))

    def test_no_wildcard_or_domain_implicit_access(self):
        self.assertIsNone(authorized_email({"is_logged_in": True, "email": "a@corp.com", "email_verified": True}, "*@corp.com"))
        self.assertIsNone(authorized_email({"is_logged_in": True, "email": "a@corp.com", "email_verified": True}, "*"))

    def test_expired_or_missing_oidc_token_is_denied(self):
        base = {"is_logged_in": True, "email": "owner@example.com", "email_verified": True}
        self.assertIsNone(authorized_email(base, "owner@example.com"))
        self.assertIsNone(authorized_email({**base, "exp": 1000}, "owner@example.com"))
        self.assertIsNone(authorized_email({**base, "exp": "not-a-timestamp"}, "owner@example.com"))

    def test_multiple_explicit_allowed_addresses(self):
        self.assertEqual(authorized_email({"is_logged_in": True, "email": "B@example.com", "email_verified": True},
                                          "a@example.com, b@example.com"), "b@example.com")


if __name__ == "__main__":
    unittest.main()
