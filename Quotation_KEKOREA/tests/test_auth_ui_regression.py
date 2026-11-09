"""Verify compatibility of AI warning schema and test-only auth isolation."""
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.service import _normalize_ai_issues
from Quotation_KEKOREA.tests.auth_test_helpers import isolated_authenticated_ui_tests


class IssueSchemaCompatibilityTests(unittest.TestCase):
    def test_plain_text_warning_is_unconfirmed_and_not_discarded(self):
        result = _normalize_ai_issues(['확인 필요', '다른 확인 필요'], 'error')
        self.assertEqual([v['code'] for v in result], ['ai_review_text', 'ai_review_text_1'])
        self.assertTrue(all(v['severity'] == 'confirm' for v in result))

    def test_unknown_severity_explains_original_value(self):
        result = _normalize_ai_issues([{'severity': 'warning', 'message': 'Confirm delivery.'}], 'error')
        self.assertIn('warning', result[0]['message'])
        self.assertIn('please review and confirm', result[0]['message'])

    def test_unsupported_item_rejected(self):
        with self.assertRaises(ValueError):
            _normalize_ai_issues([['unreadable']], 'error')

    def test_auth_mock_scoped_to_one_test(self):
        # This test is deliberately not decorated: the real production function
        # must remain callable outside UI tests.
        from Auth.gate import require_login
        self.assertTrue(callable(require_login))


@isolated_authenticated_ui_tests
class SampleIsolatedUiTests(unittest.TestCase):
    def test_only_during_this_test(self):
        from Auth.gate import require_login
        self.assertIsNone(require_login(None, None))
