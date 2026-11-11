"""Connected review screen smoke checks (no external SMTP)."""
import unittest
from unittest.mock import patch
from pathlib import Path
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

PAGE = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"

@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class UnifiedUITests(unittest.TestCase):
    def setUp(self):
        # Only fake UI identity inside tests; never a production auth bypass.
        gate = patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                     return_value="test@example.com")
        gate.start()
        self.addCleanup(gate.stop)

    def test_prepare_review_and_email_review_gates(self):
        app = AppTest.from_file(str(PAGE), default_timeout=25).run()
        app.radio[0].set_value("통합 업무 흐름").run()
        self.assertEqual(len(app.exception), 0, [x.message for x in app.exception])
        app.button(key="unified_prepare").click().run()
        self.assertEqual(len(app.exception), 0, [x.message for x in app.exception])
        run = app.session_state["unified_run"]
        self.assertEqual(run.kinds, ("PI",))
        self.assertIn("docx", run.documents[0].files)
        self.assertFalse(run.documents[0].approved)
        self.assertTrue(app.button(key="unified_email_approve").disabled)
        app.button(key="unified_approve_PI").click().run()
        self.assertTrue(app.session_state["unified_run"].documents[0].approved)
        self.assertTrue(app.button(key="unified_email_approve").disabled)
        buttons = [b for b in app.button if b.label == "이메일 초안 저장"]
        self.assertEqual(len(buttons), 1)
        buttons[0].click().run()
        self.assertFalse(app.button(key="unified_email_approve").disabled)
        app.button(key="unified_email_approve").click().run()
        self.assertTrue(app.session_state["unified_run"].email_approved)
        self.assertFalse(app.session_state["unified_run"].can_send)
        self.assertTrue(app.button(key="unified_email_approve").disabled)
        self.assertEqual(len(app.exception), 0, [x.message for x in app.exception])

    def test_unrecognized_request_is_not_approvable(self):
        app = AppTest.from_file(str(PAGE), default_timeout=25).run()
        app.radio[0].set_value("통합 업무 흐름").run()
        app.text_input(key="unified_instruction").set_value("안녕하세요").run()
        app.button(key="unified_prepare").click().run()
        self.assertFalse(app.session_state["unified_run"].documents)
        self.assertTrue(app.button(key="unified_email_approve").disabled)


if __name__ == "__main__":
    unittest.main()
