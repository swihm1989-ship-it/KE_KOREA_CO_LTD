"""Legacy engine preflight remains usable internally without a sidebar page."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


class EnginePreflightUITest(unittest.TestCase):
    def test_preflight_page_hidden_but_trade_engine_still_checks_missing_data(self):
        from Quotation_KEKOREA.orchestration.adapters.engine_bridge import evaluate_trade_candidate
        report = evaluate_trade_candidate({"document_type": "PI", "items": []})
        self.assertEqual(report.status, "needs_input")
        self.assertTrue(report.blockers)

    def test_contract_preflight_engine_retained_without_menu(self):
        from Quotation_KEKOREA.orchestration.adapters.engine_bridge import evaluate_contract_candidate
        from Quotation_KEKOREA.contracts.models import new_snapshot
        result = evaluate_contract_candidate(new_snapshot("DEMO-001", "sale", "ko"))
        self.assertEqual(result.status, "needs_input")
        self.assertTrue(result.blockers)

    def test_hidden_menu_not_present(self):
        with patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                   return_value="synthetic@example.test"), patch(
            "Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
            return_value=([], None)
        ):
            app = AppTest.from_file(str(UI)).run()
        self.assertNotIn("엔진 사전검증", list(app.radio[0].options))


if __name__ == "__main__":
    unittest.main()
