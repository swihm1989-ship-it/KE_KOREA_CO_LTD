import unittest
from Quotation_KEKOREA.orchestration.security.auth_gate import authentication_issue, authorized_email

class AuthDiagnosticsTests(unittest.TestCase):
    def test_distinguishes_wrong_account_from_expiration_without_weakening_checks(self):
        valid={'is_logged_in':True,'email_verified':True,'email':'owner@example.com','exp':4102444800}
        self.assertEqual(authentication_issue(valid,'owner@example.com'),'')
        self.assertEqual(authentication_issue(valid,'other@example.com'),'not_allowlisted')
        self.assertEqual(authentication_issue(valid|{'exp':100},'owner@example.com'),'expired')
        missing=dict(valid);missing.pop('exp')
        self.assertEqual(authentication_issue(missing,'owner@example.com'),'missing_expiration')
        self.assertIsNone(authorized_email(missing,'owner@example.com'))
        self.assertIsNone(authorized_email(valid|{'exp':100},'owner@example.com'))
        self.assertEqual(authentication_issue(valid|{'email_verified':False},'owner@example.com'),'unverified_email')
        self.assertEqual(authentication_issue({},''),'not_logged_in')
