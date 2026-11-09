"""Unit-level sanity checks of the delivered login and AI review repair."""
import unittest
from unittest.mock import patch
from copy import deepcopy
from Auth.session import create_token, validate_token, MAX_AGE_SECONDS
from Quotation_KEKOREA.contracts.service import _normalize_ai_issues


class LoginAndReviewTests(unittest.TestCase):
    def test_signed_refresh_token_expires_after_twelve_hours(self):
        secret = 's' * 48
        token = create_token('kekorea', 'example-private-password', secret, now=1000)
        self.assertTrue(validate_token(token, 'kekorea', 'example-private-password', secret, now=1000))
        self.assertTrue(validate_token(token, 'kekorea', 'example-private-password', secret, now=1000 + MAX_AGE_SECONDS - 1))
        self.assertFalse(validate_token(token, 'kekorea', 'example-private-password', secret, now=1000 + MAX_AGE_SECONDS))
        self.assertFalse(validate_token(token+'x', 'kekorea', 'example-private-password', secret, now=1000))
        self.assertFalse(validate_token(token, 'another', 'example-private-password', secret, now=1000))
        self.assertFalse(validate_token(token, 'kekorea', 'changed', secret, now=1000))

    def test_review_messages_keep_user_warning(self):
        result = _normalize_ai_issues(['확인이 필요합니다.', {'description':'장소 재확인', 'severity':'warning'}], 'bad issue')
        self.assertEqual([i['severity'] for i in result], ['confirm','confirm'])
        self.assertIn('확인이 필요합니다.', result[0]['message'])
        self.assertIn('장소 재확인', result[1]['message'])

    def test_bad_issue_still_fails_without_dropping_warning(self):
        with self.assertRaises(ValueError):
            _normalize_ai_issues([{'unrelated': 42}], 'bad issue')
        with self.assertRaises(ValueError):
            _normalize_ai_issues([['bad']], 'bad issue')


if __name__ == '__main__':
    unittest.main()
