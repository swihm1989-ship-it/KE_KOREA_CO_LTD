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
        news = patch("Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
                     return_value=([], None))
        news.start()
        self.addCleanup(news.stop)

    def test_no_key_shows_configuration_warning_and_no_automatic_request(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""}):
            app = AppTest.from_file(str(PAGE), default_timeout=20).run()
            app.radio[0].set_value("AI 업무 요청").run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertTrue(any("AI 모델 연결" in x.value for x in app.warning))
            self.assertTrue(app.button(key="ai_intake_extract").disabled)

    def test_no_consent_means_no_api_call(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake", "OPENAI_MODEL": "fake"}), patch(
            "Quotation_KEKOREA.orchestration.workflows.ai_intake.extract_candidate"
        ) as api:
            app = AppTest.from_file(str(PAGE), default_timeout=20).run()
            app.radio[0].set_value("AI 업무 요청").run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertTrue(app.button(key="ai_intake_extract").disabled)
            api.assert_not_called()


    def test_real_ai_request_shows_fillable_buyer_and_seller_and_syncs_both(self):
        analysis = {
            "contract_type": "sale", "parties": [], "questions": [],
            "issues": [], "terms": [
                {"key": "products", "value": "Hanwha M10 PERC", "status": "suggested", "source_refs": []},
                {"key": "quantity", "value": "1000000", "status": "suggested", "source_refs": []},
                {"key": "unit", "value": "PCS", "status": "suggested", "source_refs": []},
                {"key": "unit_price", "value": "0.225", "status": "suggested", "source_refs": []},
                {"key": "currency", "value": "USD", "status": "suggested", "source_refs": []},
                {"key": "delivery", "value": "EXW Jincheon", "status": "suggested", "source_refs": []},
                {"key": "payment_trigger", "value": "10% deposit, 90% balance", "status": "suggested", "source_refs": []},
            ],
        }
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake", "OPENAI_MODEL": "fake"}), patch(
            "Quotation_KEKOREA.orchestration.ui.ai_intake_page.extract_candidate",
            return_value=analysis,
        ) as api:
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
            app.radio[0].set_value("AI 업무 요청").run()
            app.text_area(key="ai_intake_instruction").set_value(
                "한화 M10 PERC 태양광 셀 100만 장 장당 USD 0.225, EXW 진천공장, PI와 영문 계약서 작성",
            ).run()
            app.checkbox(key="ai_intake_consent").check().run()
            app.button(key="ai_intake_extract").click().run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            api.assert_called_once()
            self.assertIn("CONTRACT", app.session_state["ai_intake_candidates"][1])
            self.assertIn("PI", app.session_state["ai_intake_candidates"][1])
            self.assertTrue(app.text_input(key="ai_intake_answer_buyer_legal_name"))
            self.assertTrue(app.text_input(key="ai_intake_answer_seller_legal_name"))
            self.assertTrue(any(x.label == "Buyer · 구매자 법인명" for x in app.text_input))
            app.text_input(key="ai_intake_answer_buyer_legal_name").set_value("TENGYAO TECHNOLOGY CO. LTD").run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            result = app.session_state["ai_intake_candidates"][1]
            self.assertEqual(result["PI"]["buyer"]["legal_name"], "TENGYAO TECHNOLOGY CO. LTD")
            party = next(p for p in result["CONTRACT"]["parties"] if "buyer" in p["roles"])
            self.assertEqual(party["legal_name"], "TENGYAO TECHNOLOGY CO. LTD")
            self.assertEqual(party["status"], "suggested")
            self.assertNotIn("ai_intake_drafts", app.session_state)
            self.assertFalse(any(b.label == "샘플 업무 생성" for b in app.button))


if __name__ == "__main__":
    unittest.main()
