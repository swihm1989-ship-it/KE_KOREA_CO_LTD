import unittest
from Auth.session import MAX_AGE_SECONDS, make_token, verify_token, password_matches

KEY = 'a'*48
class AuthSessionTests(unittest.TestCase):
    def test_valid_12_hour_token(self):
        token = make_token('kekorea', KEY, now=100)
        self.assertTrue(verify_token(token,'kekorea',KEY,now=101))
        self.assertTrue(verify_token(token,'kekorea',KEY,now=100+MAX_AGE_SECONDS-1))
        self.assertFalse(verify_token(token,'kekorea',KEY,now=100+MAX_AGE_SECONDS))
        self.assertFalse(verify_token(token,'other',KEY,now=101))
        self.assertFalse(verify_token(token,'kekorea','b'*48,now=101))
    def test_tampered_token_fails(self):
        token = make_token('kekorea',KEY,now=100)
        self.assertFalse(verify_token(token+'x','kekorea',KEY,now=101))
        self.assertFalse(verify_token('bad','kekorea',KEY,now=101))
    def test_login_passwords_require_secret(self):
        self.assertTrue(password_matches('12345','12345'))
        self.assertFalse(password_matches('12345',''))
        self.assertFalse(password_matches('1234','12345'))
