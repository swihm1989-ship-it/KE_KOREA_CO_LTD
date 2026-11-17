"""Master must delegate PI/PO extraction and family rules to KE KOREA agent.

Regression for live Master screenshot: family=other is visible, but a
pre-deployment mail_intake module rejects it as "상품군을 확인해 주세요."
All examples are synthetic; no live provider requests or private customer data.
"""
import unittest
from unittest.mock import patch
from pathlib import Path

from Quotation_KEKOREA.agent import trade_documents
from Quotation_KEKOREA.orchestration.workflows import mail_intake, ai_intake
from Quotation_KEKOREA.orchestration.ui import ai_intake_page
from Quotation_KEKOREA.orchestration.tests.mail_fixtures import cases
from Quotation_KEKOREA.orchestration.tests.test_mail_document_intake import response


class SharedProductFamilyHandoffTests(unittest.TestCase):
    def test_master_mail_families_are_exactly_original_ke_korea_agent_families(self):
        self.assertIs(getattr(mail_intake, "FAMILIES", None), trade_documents.FAMILIES)
        self.assertIn("other", mail_intake.FAMILIES)

    def test_master_text_families_are_same_original_ke_korea_agent_families(self):
        self.assertIs(ai_intake._FAMILIES, trade_documents.FAMILIES)
        self.assertIn("other", ai_intake._FAMILIES)

    def test_stale_mail_module_is_reloaded_before_ai_is_called(self):
        # The UI reloads on a Streamlit deploy but the imported workflow module
        # does not. Simulate a cached pre-PR #121 function refusing "other".
        with (patch.object(mail_intake, "MAIL_INTAKE_REVISION",
                           "pre-other-family", create=True),
              patch.object(mail_intake, "extract_mail_candidates",
                           side_effect=ValueError("상품군을 확인해 주세요."))):
            module = ai_intake_page._current_mail_intake()
            self.assertEqual(module.MAIL_INTAKE_REVISION,
                             "shared-ke-korea-family-20261117-v1")
            self.assertIn("other", module.FAMILIES)
            self.assertTrue(callable(module.extract_mail_candidates))
            self.assertNotIn("mock", module.extract_mail_candidates.__module__)
            self.assertIs(module.FAMILIES, trade_documents.FAMILIES)

    def test_stale_generic_text_workflow_reloads_even_if_old_revision_matches(self):
        # PR #121 extended the _FAMILIES set but did not bump its revision.
        # A revision-only check silently retains the old set.
        with patch.object(ai_intake, "_FAMILIES", {"cosmetics"}):
            module = ai_intake_page._current_ai_workflow()
            self.assertIn("other", module._FAMILIES)
            self.assertIs(module._FAMILIES, trade_documents.FAMILIES)

    def test_original_ke_korea_trade_agent_returns_generic_multi_item_pi(self):
        fixture = cases()[3]
        raw = fixture["trade"]
        result = mail_intake.extract_mail_candidates(
            fixture["body"], ("PI",),
            {"OPENAI_API_KEY": "SYNTHETIC", "OPENAI_MODEL": "test"},
            consent=True, family="other",
            trade_opener=lambda *a, **kw: response(raw))
        pi = result["candidates"]["PI"]
        self.assertEqual(pi["product_family"], "other")
        self.assertEqual(len(pi["items"]), 2)
        self.assertEqual(pi["items"][0]["unit_price"], raw["items"][0]["unit_price"])
        self.assertEqual(pi["items"][1]["unit_price"], raw["items"][1]["unit_price"])


try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

PAGE = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class MasterOtherFamilyMailUiTests(unittest.TestCase):
    def test_other_pi_from_mail_survives_old_cached_workflow(self):
        fixture = cases()[3]
        with (patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                    return_value="synthetic@example.test"),
              patch("Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
                    return_value=([], None)),
              patch.object(ai_intake_page, "_model_config",
                           return_value={"OPENAI_API_KEY": "SYNTHETIC", "OPENAI_MODEL": "test"}),
              patch("Quotation_KEKOREA.agent.extractor.extract_trade_data",
                    return_value=fixture["trade"])):
            app = AppTest.from_file(str(PAGE), default_timeout=35).run()
            app.radio(key="master_page").set_value("AI 업무 요청").run()
            app.session_state["ai_intake_instruction"] = fixture["body"]
            app.session_state["ai_intake_mail_source"] = {"kinds": ["PI"]}
            app.session_state["ai_intake_mail_attachments"] = []
            app.run()
            app.selectbox(key="ai_intake_family").set_value("other").run()
            app.checkbox(key="ai_intake_consent").check().run()
            with (patch.object(mail_intake, "MAIL_INTAKE_REVISION", "pre-other", create=True),
                  patch.object(mail_intake, "extract_mail_candidates",
                               side_effect=ValueError("상품군을 확인해 주세요."))):
                app.button(key="ai_intake_extract").click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertFalse(any("상품군을 확인해 주세요" in x.value for x in app.error))
            pi = app.session_state["ai_intake_candidates"][1]["PI"]
            self.assertEqual(pi["product_family"], "other")
            self.assertEqual(len(pi["items"]), 2)
            self.assertEqual(pi["items"][0]["unit_price"],
                             fixture["trade"]["items"][0]["unit_price"])


if __name__ == "__main__":
    unittest.main()
