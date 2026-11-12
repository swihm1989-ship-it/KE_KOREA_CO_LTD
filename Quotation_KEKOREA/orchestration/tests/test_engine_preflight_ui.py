"""Smoke-test the separate read-only legacy-engine validation UI."""
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

UI = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class EnginePreflightUITest(unittest.TestCase):
    def setUp(self):
        # Only fake UI identity inside tests; never a production auth bypass.
        gate = patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                     return_value="test@example.com")
        gate.start()
        self.addCleanup(gate.stop)
        news = patch("Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
                     return_value=([], None))
        news.start()
        self.addCleanup(news.stop)

    def test_missing_pi_data_displays_blockers(self):
        app = AppTest.from_file(str(UI), default_timeout=15).run()
        app.radio[0].set_value("엔진 사전검증").run()
        self.assertEqual(len(app.exception), 0, [str(e.message) for e in app.exception])
        app.button(key="validate_existing_engine").click().run()
        self.assertEqual(len(app.exception), 0, [str(e.message) for e in app.exception])
        self.assertTrue(any("needs_input" in x.value for x in app.markdown))
        self.assertFalse(any("발송 완료" in str(x) for x in app.success))

    def test_missing_contract_terms_display_blockers(self):
        app = AppTest.from_file(str(UI), default_timeout=15).run()
        app.radio[0].set_value("엔진 사전검증").run()
        app.selectbox[0].set_value("CONTRACT").run()
        app.button(key="validate_existing_engine").click().run()
        self.assertEqual(len(app.exception), 0, [str(e.message) for e in app.exception])
        self.assertTrue(any("needs_input" in x.value for x in app.markdown))


if __name__ == "__main__":
    unittest.main()
