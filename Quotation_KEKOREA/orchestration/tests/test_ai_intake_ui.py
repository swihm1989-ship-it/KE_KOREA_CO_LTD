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


    def test_advanced_json_draft_button_normalizes_existing_raw_price(self):
        import hashlib
        from Quotation_KEKOREA.orchestration.tests.test_draft_files import trade_fixture
        instruction = "PI 작성"
        digest = hashlib.sha256((instruction + "|한국어|solar_cell").encode()).hexdigest()
        pi = trade_fixture()
        pi['currency'] = ''
        pi['items'][0].update(quantity='2325860', unit='', unit_price='$0.2/pc', price_basis='', price_source='')
        app = AppTest.from_file(str(PAGE), default_timeout=25).run()
        app.radio[0].set_value("AI 업무 요청").run()
        app.text_area(key="ai_intake_instruction").set_value(instruction).run()
        app.session_state['ai_intake_candidates'] = (digest, {'PI': pi})
        app.session_state['ai_intake_result'] = (digest, {'parties': [], 'terms': []})
        app.run()
        app.button(key='ai_intake_prepare').click().run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        run = app.session_state['ai_intake_drafts'][1]
        self.assertEqual(run.documents[0].blockers, ())
        self.assertTrue(run.documents[0].files['docx']['content'].startswith(b'PK'))

    def test_bare_quantity_exposes_blank_unit_and_no_mandatory_price_source(self):
        import hashlib
        instruction = "PI와 영문 계약서 작성"
        digest = hashlib.sha256((instruction + "|한국어|solar_cell").encode()).hexdigest()
        candidate = {"PI": {"document_type": "PI", "product_family": "solar_cell",
                     "currency": "USD", "items": [{"product_name": "Hanwha Solar Cell",
                     "quantity": "2325860", "unit_price": "0.2", "unit": "", "price_basis": ""}]}}
        app = AppTest.from_file(str(PAGE), default_timeout=25).run()
        app.radio[0].set_value("AI 업무 요청").run()
        app.text_area(key="ai_intake_instruction").set_value(instruction).run()
        app.session_state["ai_intake_candidates"] = (digest, candidate)
        app.session_state["ai_intake_result"] = (digest, {"parties": [], "terms": []})
        app.run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertEqual(next(x for x in app.text_input if x.label == "수량 단위").value, "")
        self.assertEqual(len([x for x in app.text_input if x.label == "수량 단위"]), 1)
        self.assertFalse(any(x.key and x.key.startswith("master_pdf_") for x in app.text_input))

    def test_formal_pdf_error_explains_bank_seal_and_legacy_ai_notices(self):
        from Quotation_KEKOREA.orchestration.ui.ai_intake_page import (
            _formal_pdf_hold_reason,
        )
        self.assertIn("6/6", _formal_pdf_hold_reason(
            "PI", ValueError("기존 업무 에이전트와 동일하게 PI 은행정보 6개 항목이 모두 필요합니다."), {}))
        complete_bank = {("KEKOREA_USD_" + field): "set-in-test-only"
                         for field in ("BENEFICIARY", "BANK_NAME", "BRANCH",
                                       "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")}
        self.assertIn("0/6", _formal_pdf_hold_reason(
            "PI", ValueError("PI 은행정보 6개 항목이 필요합니다"), complete_bank))
        self.assertIn("회사 직인", _formal_pdf_hold_reason(
            "PI", ValueError("검증된 KE KOREA 회사 직인이 필요합니다"), complete_bank))
        self.assertIn("이전 AI", _formal_pdf_hold_reason(
            "PI", ValueError("거래조건을 먼저 보완하세요: Resolve conflicting information"), complete_bank))
        unknown = _formal_pdf_hold_reason(
            "PI", ValueError("SECRET INTERNAL SERVER RESPONSE"), complete_bank)
        self.assertNotIn("SECRET", unknown)
        self.assertIn("렌더러", unknown)

    def test_one_editor_resolves_only_user_acknowledged_historical_ai_notes(self):
        import hashlib
        instruction = "Synthetic PI request with confirmed details"
        digest = hashlib.sha256((instruction + "|한국어|solar_cell").encode()).hexdigest()
        candidate = {"document_type": "PI", "product_family": "solar_cell",
                     "document_number": "DRAFT",
                     "buyer": {"legal_name": "SYNTHETIC BUYER LTD",
                               "address": "Seoul, South Korea"},
                     "seller": {"legal_name": "KE KOREA CO. LTD",
                                "address": "Seoul, South Korea"},
                     "currency": "USD", "incoterms": "EXW Seoul",
                     "payment_terms": "T/T in advance",
                     "items": [{"product_name": "M10 test cell", "quantity": "100",
                                "unit": "PCS", "unit_price": "0.20",
                                "price_basis": "PCS"}],
                     "missing_fields": ["Confirm buyer and seller official names"],
                     "conflicts": ["Confirm payment date from original email"]}
        app = AppTest.from_file(str(PAGE), default_timeout=25).run()
        app.radio[0].set_value("AI 업무 요청").run()
        app.text_area(key="ai_intake_instruction").set_value(instruction).run()
        app.session_state["ai_intake_candidates"] = (digest, {"PI": candidate})
        app.session_state["ai_intake_result"] = (
            digest, {"parties": [], "terms": [], "issues": [], "questions": []}
        )
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(any("이전 AI 확인 기록" in x.message for x in app.warning))
        self.assertEqual(len([x for x in app.button if x.label == "해소 확인"]), 2)
        next(x for x in app.button if x.label == "해소 확인").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        data = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual(len(data["missing_fields"]) + len(data["conflicts"]), 1)
        next(x for x in app.button if x.label == "해소 확인").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        data = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual(data["missing_fields"], [])
        self.assertEqual(data["conflicts"], [])
        self.assertEqual(data["buyer"]["legal_name"], "SYNTHETIC BUYER LTD")
        self.assertEqual(data["seller"]["legal_name"], "KE KOREA CO. LTD")

    def test_historical_session_with_string_seller_renders_and_exports_review_pdf(self):
        import hashlib
        instruction = "Synthetic PI request"
        digest = hashlib.sha256((instruction + "|한국어|solar_cell").encode()).hexdigest()
        app = AppTest.from_file(str(PAGE), default_timeout=25).run()
        app.radio[0].set_value("AI 업무 요청").run()
        app.text_area(key="ai_intake_instruction").set_value(instruction).run()
        app.session_state["ai_intake_candidates"] = (digest, {
            "PI": {"document_type": "PI", "product_family": "solar_cell",
                   "buyer": "Smart Solar Systems Co. Ltd",
                   "seller": "KE KOREA CO. LTD", "currency": "USD",
                   "items": [{"product_name": "Synthetic Solar Cell",
                              "quantity": "100", "unit": "PCS",
                              "unit_price": "0.2", "price_basis": "PCS"}]},
            "PO": {"document_type": "PO", "product_family": "solar_cell",
                   "buyer": {"legal_name": "KE KOREA CO. LTD",
                             "address": "Test Seoul"},
                   "seller": None, "currency": "USD", "items": []},
        })
        app.session_state["ai_intake_result"] = (digest, {
            "parties": [], "terms": [], "issues": [], "questions": []})
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        candidates = app.session_state["ai_intake_candidates"][1]
        self.assertEqual(candidates["PI"]["seller"]["legal_name"],
                         "KE KOREA CO. LTD")
        self.assertEqual(candidates["PI"]["buyer"]["legal_name"],
                         "Smart Solar Systems Co. Ltd")
        self.assertEqual(candidates["PO"]["seller"]["legal_name"], "")
        self.assertEqual(next(i for i in app.text_input
                              if i.label == "Seller · 판매자 법인명").value,
                         "KE KOREA CO. LTD")
        next(i for i in app.text_input
             if i.label == "Seller · 판매자 법인 주소").set_value(
                 "Synthetic corrected company address").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state["ai_intake_candidates"][1]
                         ["PI"]["seller"]["address"],
                         "Synthetic corrected company address")
        app.button(key="master_legacy_export").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        pdf = app.session_state["master_legacy_files"][1]["PI"]["pdf"]
        self.assertTrue(pdf["content"].startswith(b"%PDF"))
        self.assertTrue(pdf["review_only"])
        self.assertFalse(pdf["final"])
        self.assertFalse(pdf["sendable"])

    def test_stale_cached_ai_page_is_reloaded_before_render(self):
        from Quotation_KEKOREA.orchestration.ui import ai_intake_page
        # Simulates a Streamlit process that still holds the old Python
        # module after the entrypoint source has been deployed.
        with (patch.object(ai_intake_page, "AI_INTAKE_REVISION", "prior-release"),
              patch.object(ai_intake_page, "render_ai_intake",
                           side_effect=AssertionError("stale code executed"))):
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
            app.radio[0].set_value("AI 업무 요청").run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertFalse(any("최신 버전으로" in e.message for e in app.error))
            self.assertIsNotNone(app.button(key="ai_intake_extract"))

    def test_cached_legacy_apply_answer_reloads_and_preserves_user_edit(self):
        from Quotation_KEKOREA.orchestration.ui import ai_intake_page
        from Quotation_KEKOREA.orchestration.workflows import intake_followups

        # This is the old cached function signature reported in production.
        def legacy_apply_answer(candidates, key, value):
            raise AssertionError("stale function must never be called")

        digest = "synthetic-legacy-digest"
        widget = "synthetic-buyer-name"
        state = {
            "ai_intake_candidates": (digest, {
                "PI": {"document_type": "PI", "product_family": "solar_cell",
                       "buyer": {"legal_name": "", "address": ""},
                       "seller": {"legal_name": "KE KOREA CO. LTD", "address": ""},
                       "items": [{"product_name": "Synthetic Cell",
                                  "quantity": "10", "unit_price": "0.2"}]}}),
            widget: "New Synthetic Buyer Co. Ltd",
        }
        with (patch.object(intake_followups, "apply_answer", legacy_apply_answer),
              patch.object(ai_intake_page.st, "session_state", state)):
            ai_intake_page._apply_shared_input(
                digest, "buyer.legal_name", widget)
            self.assertNotIn("ai_intake_followup_error", state)
            self.assertEqual(state["ai_intake_candidates"][1]["PI"]
                             ["buyer"]["legal_name"],
                             "New Synthetic Buyer Co. Ltd")
            state[widget] = ""
            ai_intake_page._apply_shared_input(
                digest, "buyer.legal_name", widget)
            self.assertEqual(state["ai_intake_candidates"][1]["PI"]
                             ["buyer"]["legal_name"], "")
            self.assertNotIn("ai_intake_followup_error", state)

    def test_cached_pdf_module_without_review_function_is_reloaded(self):
        from Quotation_KEKOREA.orchestration.ui import ai_intake_page
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports

        with patch.object(legacy_document_exports, "render_incomplete_trade_pdf", None):
            old_renderer, review_renderer = (
                ai_intake_page._current_pdf_export_renderers())
            self.assertTrue(callable(old_renderer))
            self.assertTrue(callable(review_renderer))
            document = review_renderer("PI", {
                "document_type": "PI", "product_family": "solar_cell",
                "buyer": {"legal_name": "Synthetic Buyer Ltd"},
                "seller": {"legal_name": "KE KOREA CO. LTD"},
                "items": [{"product_name": "Synthetic Cells", "quantity": ""}],
            })
            self.assertTrue(document["pdf"]["content"].startswith(b"%PDF"))
            self.assertFalse(document["pdf"]["final"])
            self.assertFalse(document["pdf"]["sendable"])

    def test_broken_reload_returns_safe_message_without_original_data(self):
        from Quotation_KEKOREA.orchestration.ui import ai_intake_page
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports
        with (patch.object(legacy_document_exports, "render_incomplete_trade_pdf", None),
              patch.object(ai_intake_page.importlib, "reload",
                           side_effect=ImportError("SECRET private-message-content"))):
            with self.assertRaises(RuntimeError) as exc:
                ai_intake_page._current_pdf_export_renderers()
        self.assertIn("앱을 재시작", str(exc.exception))
        self.assertNotIn("SECRET", str(exc.exception))

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
            self.assertEqual(len([x for x in app.text_input if x.label == "Buyer · 구매자 법인명"]), 1)
            self.assertEqual(len([x for x in app.text_input if x.label == "Seller · 판매자 법인명"]), 1)
            next(x for x in app.text_input if x.label == "Buyer · 구매자 법인명").set_value(
                "TENGYAO TECHNOLOGY CO. LTD").run()
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
