"""AI intake screen tests with explicit consent and no implicit stored data sharing."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

PAGE = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class AiIntakeUiTests(unittest.TestCase):
    def setUp(self):
        gate = patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                     return_value="owner@example.com")
        gate.start()
        self.addCleanup(gate.stop)

    def test_no_key_shows_configuration_warning_and_no_automatic_request(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""}):
            app = AppTest.from_file(str(PAGE), default_timeout=20).run()
            app.radio[0].set_value("AI 거래조건 추출").run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertTrue(any("AI 모델 연결" in x.value for x in app.warning))
            self.assertTrue(app.button(key="ai_intake_extract").disabled)

    def test_no_consent_means_no_api_call(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake", "OPENAI_MODEL": "fake"}), patch(
            "Quotation_KEKOREA.orchestration.workflows.ai_intake.extract_candidate"
        ) as api:
            app = AppTest.from_file(str(PAGE), default_timeout=20).run()
            app.radio[0].set_value("AI 거래조건 추출").run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertTrue(app.button(key="ai_intake_extract").disabled)
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
