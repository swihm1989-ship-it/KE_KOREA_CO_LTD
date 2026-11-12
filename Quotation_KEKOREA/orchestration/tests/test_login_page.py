import os
from pathlib import Path
from unittest.mock import patch
import unittest
from streamlit.testing.v1 import AppTest

PAGE=Path(__file__).resolve().parents[1]/'ui'/'streamlit_page.py'
class LoginPageTests(unittest.TestCase):
    @patch.dict(os.environ,{'ORCHESTRATION_ALLOWED_EMAILS':'owner@example.com'})
    def test_branded_login_keeps_private_workspace_locked(self):
        app=AppTest.from_file(str(PAGE),default_timeout=20).run()
        self.assertFalse(app.exception)
        html='\n'.join(x.value for x in app.markdown)
        self.assertIn('ke-login-hero',html)
        self.assertIn('업무는 한눈에',html)
        self.assertIn('alt="KE KOREA',html)
        self.assertIn('data:image/png;base64,',html)
        self.assertEqual(app.button(key='master_auth_login').label,'Google 계정으로 계속하기')
        self.assertFalse(app.radio)
        self.assertFalse(app.selectbox)
        self.assertFalse(any('시안 둘러보기' in b.label for b in app.button))

    @patch.dict(os.environ,{'ORCHESTRATION_ALLOWED_EMAILS':'owner@example.com'})
    def test_login_button_calls_existing_oidc_login(self):
        with patch('streamlit.login') as login:
            app=AppTest.from_file(str(PAGE),default_timeout=20).run()
            app.button(key='master_auth_login').click().run()
        login.assert_called_once_with()

    @patch.dict(os.environ,{'ORCHESTRATION_ALLOWED_EMAILS':''})
    def test_missing_allowlist_has_no_login_or_mail_access(self):
        with patch('Quotation_KEKOREA.orchestration.adapters.whois_mail._pop') as connect:
            app=AppTest.from_file(str(PAGE),default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertFalse(any(b.key=='master_auth_login' for b in app.button))
        connect.assert_not_called()
        self.assertFalse(app.radio)
