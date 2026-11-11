"""UI smoke tests run against an isolated Streamlit AppTest session."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

UI_FILE = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class StreamlitMockUiTests(unittest.TestCase):
    def setUp(self):
        # Only fake UI identity inside tests; never a production auth bypass.
        gate = patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                     return_value="test@example.com")
        gate.start()
        self.addCleanup(gate.stop)

    def _app(self):
        app = AppTest.from_file(str(UI_FILE), default_timeout=15).run()
        self.assertEqual(len(app.exception), 0, [str(x.message) for x in app.exception])
        return app

    def test_dashboard_renders_without_mail_connection(self):
        app = self._app()
        self.assertTrue(any("Trade operations" in x.value for x in app.title))
        self.assertEqual(len([b for b in app.button if b.key and b.key.startswith("start-demo-")]), 3)
        self.assertEqual(len(app.exception), 0)

    def test_sample_mail_to_review_navigation(self):
        app = self._app()
        app.button(key="start-demo-001").click().run()
        self.assertEqual(len(app.exception), 0, [str(x.message) for x in app.exception])
        self.assertIn("demo-001", app.session_state["mock_runs"])
        app.radio[0].set_value("문서 검토").run()
        self.assertEqual(len(app.exception), 0, [str(x.message) for x in app.exception])
        self.assertTrue(any("초안별 검토" in x.value for x in app.subheader))

    def test_send_control_unavailable_even_after_mock_approval(self):
        app = self._app()
        app.button(key="start-demo-002").click().run()
        run = app.session_state["mock_runs"]["demo-002"]
        from Quotation_KEKOREA.orchestration.workflows.mock_workflow import approve_mock_document, approve_mock_email
        run = approve_mock_email(approve_mock_document(run, "CONTRACT"))
        app.session_state["mock_runs"]["demo-002"] = run
        app.radio[0].set_value("발송 대기").run()
        self.assertEqual(len(app.exception), 0, [str(x.message) for x in app.exception])
        controls = [b for b in app.button if "실제 메일 발송" in b.label]
        self.assertEqual(len(controls), 1)
        self.assertTrue(controls[0].disabled)


if __name__ == "__main__":
    unittest.main()
