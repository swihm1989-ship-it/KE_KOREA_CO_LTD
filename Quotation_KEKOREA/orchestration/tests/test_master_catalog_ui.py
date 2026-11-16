"""MASTER Streamlit session uses the legacy ECLADO catalog, with no live network."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.orchestration.ui import ai_intake_page
from Quotation_KEKOREA.orchestration.tests.test_legacy_catalog_bridge import (
    CATALOG, trade,
)

_SOURCE = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _remember_candidate_bundle
if 'ai_intake_candidates' not in st.session_state:
    _remember_candidate_bundle('synthetic-master', DATA, replace_editor=True)
st.write('catalog state:', st.session_state.get('master_eclado_catalog_status'))
""".replace("DATA", "None")


class MasterCatalogUiTests(unittest.TestCase):
    def app(self, doc, env):
        source = _SOURCE.replace("None", repr(doc))
        with (patch.object(ai_intake_page, 'document_export_env', return_value=env),
              patch.object(ai_intake_page, '_cached_master_eclado_catalog', return_value=CATALOG)
              as catalog_loader):
            app = AppTest.from_string(source, default_timeout=25).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app, catalog_loader

    def test_master_applies_legacy_usd_and_krw_prices_before_pdf(self):
        from Quotation_KEKOREA.orchestration.workflows.document_assets import EXPECTED_PROJECT
        env = {"SUPABASE_URL": "https://" + EXPECTED_PROJECT + ".supabase.co",
               "SUPABASE_SECRET_KEY": "TEST-ONLY-SERVER-KEY"}
        data = {
            "PI": trade("PI"),
            "PO": trade("PO", buyer="KE KOREA CO. LTD",
                        seller="ECLADO", price="12.50"),
        }
        app, loader = self.app(data, env)
        loader.assert_called_once()
        result = app.session_state['ai_intake_candidates'][1]
        self.assertEqual(result['PI']['currency'], 'USD')
        self.assertEqual(result['PI']['items'][0]['unit_price'], '12.50')
        self.assertEqual(result['PO']['currency'], 'KRW')
        self.assertEqual(result['PO']['items'][0]['unit_price'], '1000')
        self.assertEqual(app.session_state['master_eclado_catalog_status'], 'connected')

    def test_explicit_po_supplier_and_buyer_in_request_restore_roles_and_krw_price(self):
        """A Dear Glow source image can carry SALES parties while PO intent names BUY parties."""
        from Quotation_KEKOREA.orchestration.workflows.document_assets import EXPECTED_PROJECT
        env = {"SUPABASE_URL": "https://" + EXPECTED_PROJECT + ".supabase.co",
               "SUPABASE_SECRET_KEY": "TEST-ONLY-SERVER-KEY"}
        po = trade("PO", buyer="DEAR GLOW PTE LTD",
                   seller="KE Korea Co. LTD", price=None)
        po["currency"] = "USD"  # Purchase order was generated from a customer PI image.
        source = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _remember_candidate_bundle
st.session_state["ai_intake_instruction"] = INSTRUCTION
if "ai_intake_candidates" not in st.session_state:
    _remember_candidate_bundle("po-roles", {"PO": DATA}, replace_editor=True)
""".replace("INSTRUCTION", repr(
            "Dear Glow 주문 목록 기준 PO 발주서 작성. Buyer는 KE KOREA, Supplier는 ECLADO. "
            "Supabase KRW 매입단가를 적용해줘.")).replace("DATA", repr(po))
        with (patch.object(ai_intake_page, "document_export_env", return_value=env),
              patch.object(ai_intake_page, "_cached_master_eclado_catalog",
                           return_value=CATALOG)):
            app = AppTest.from_string(source, default_timeout=25).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        po = app.session_state["ai_intake_candidates"][1]["PO"]
        self.assertEqual(po["buyer"]["legal_name"], "KE Korea Co. LTD")
        self.assertEqual(po["seller"]["legal_name"], "ECLADO")
        self.assertEqual(po["currency"], "KRW")
        self.assertEqual(po["items"][0]["unit_price"], "1000")
        self.assertTrue(po["items"][0]["master_price"])

    def test_po_only_brand_in_product_text_does_not_invent_supplier(self):
        from Quotation_KEKOREA.orchestration.workflows.document_assets import EXPECTED_PROJECT
        env = {"SUPABASE_URL": "https://" + EXPECTED_PROJECT + ".supabase.co",
               "SUPABASE_SECRET_KEY": "TEST-ONLY-SERVER-KEY"}
        po = trade("PO", buyer="KE KOREA CO. LTD", seller="", price=None)
        source = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _remember_candidate_bundle
st.session_state["ai_intake_instruction"] = "PO 작성: ECLADO Cell Memory Cream 주문"
_remember_candidate_bundle("po-unnamed", {"PO": DATA}, replace_editor=True)
""".replace("DATA", repr(po))
        with (patch.object(ai_intake_page, "document_export_env", return_value=env),
              patch.object(ai_intake_page, "_cached_master_eclado_catalog",
                           return_value=CATALOG)):
            app = AppTest.from_string(source, default_timeout=25).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        po = app.session_state["ai_intake_candidates"][1]["PO"]
        self.assertEqual(po["seller"]["legal_name"], "")
        self.assertIsNone(po["items"][0]["unit_price"])

    def test_existing_po_has_explicit_button_to_refresh_supplier_and_purchase_prices(self):
        """Existing stale Streamlit candidates must not require a second AI extraction."""
        from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi
        from Quotation_KEKOREA.orchestration.workflows.document_assets import EXPECTED_PROJECT
        env = {"SUPABASE_URL": "https://" + EXPECTED_PROJECT + ".supabase.co",
               "SUPABASE_SECRET_KEY": "TEST-ONLY-SERVER-KEY"}
        doc = complete_pi()
        doc["document_type"] = "PO"
        doc["product_family"] = "cosmetics"
        doc["seller"]["legal_name"] = "KE KOREA CO. LTD"  # stale source-PI seller
        doc["buyer"]["legal_name"] = "DEAR GLOW PTE LTD"
        doc["items"][0].update(product_name="Cell Memory Cream (E-165)",
                               capacity="50g", unit_price=None,
                               price_source=None, master_price=False, quantity="10")
        source = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import (
    _remember_candidate_bundle, _render_single_editor)
st.session_state["ai_intake_instruction"] = "Please prepare PO from this customer order"
if "ai_intake_candidates" not in st.session_state:
    _remember_candidate_bundle("po-retry", {"PO": DATA}, replace_editor=True)
_render_single_editor("po-retry", st.session_state["ai_intake_candidates"][1])
""".replace("DATA", repr(doc))
        with (patch.object(ai_intake_page, "document_export_env", return_value=env),
              patch.object(ai_intake_page, "_cached_master_eclado_catalog",
                           return_value=CATALOG)):
            app = AppTest.from_string(source, default_timeout=25).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            button = next(x for x in app.button
                          if x.label == "PO · KE KOREA 매입 / ECLADO 공급처 확인 및 단가 재조회")
            button.click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        po = app.session_state["ai_intake_candidates"][1]["PO"]
        self.assertEqual(po["buyer"]["legal_name"], "KE Korea Co. LTD")
        self.assertEqual(po["seller"]["legal_name"], "ECLADO")
        self.assertEqual(po["currency"], "KRW")
        self.assertEqual(po["items"][0]["unit_price"], "1000")
        self.assertTrue(po["items"][0]["master_price"])

    def test_no_secrets_preserves_user_trade_price_without_network(self):
        app, loader = self.app({"PI": trade("PI", price="19.99")}, {})
        loader.assert_not_called()
        result = app.session_state['ai_intake_candidates'][1]
        self.assertEqual(result['PI']['items'][0]['unit_price'], '19.99')
        self.assertEqual(app.session_state['master_eclado_catalog_status'], 'not_configured')


if __name__ == '__main__':
    unittest.main()
