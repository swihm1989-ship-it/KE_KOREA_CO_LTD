"""Real Streamlit AppTests for an extracted ECLADO row with no item name.

Regression screenshot: item 2 shows 50ml x 10 PCS but no product name/price.
Missing row controls must be visible directly, not only in collapsed details.
"""
from copy import deepcopy
from unittest.mock import patch
import unittest

from Quotation_KEKOREA.orchestration.tests.test_trade_final_ui import TradeFinalUiTests
from Quotation_KEKOREA.orchestration.tests.test_legacy_catalog_bridge import CATALOG
from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi
from Quotation_KEKOREA.orchestration.ui import ai_intake_page
from Quotation_KEKOREA.orchestration.workflows.document_assets import EXPECTED_PROJECT


def screenshot_candidate():
    doc = complete_pi()
    doc.update(product_family="cosmetics", currency="USD",
               buyer={"legal_name": "DEAR GLOW PTE LTD",
                      "address": "Synthetic Buyer Address"})
    first = dict(doc["items"][0],
                 product_name="Cell Memory Cream", capacity="50g",
                 quantity="10", paid_quantity="10",
                 unit="PCS", price_basis="PCS",
                 unit_price="12.50", master_price=True)
    second = dict(first, product_name="", product_code="",
                  capacity="50ml", unit_price=None,
                  price_source=None, master_price=False)
    doc["items"] = [first, second]
    return doc


class MissingItemEditorTests(unittest.TestCase):
    app = TradeFinalUiTests.app

    def test_second_missing_row_is_editable_without_opening_advanced_expander(self):
        app = self.app(screenshot_candidate(), editor=True)
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertEqual(len(app.dataframe), 1)
        self.assertTrue(any(t.label == "PI · 상품 2 · 상품명"
                            for t in app.text_input))
        self.assertTrue(any(t.label == "PI · 상품 2 · 규격"
                            for t in app.text_input))
        self.assertTrue(any(t.label == "PI · 상품 2 · 단가"
                            for t in app.text_input))
        self.assertEqual(next(t for t in app.text_input
                              if t.label == "PI · 상품 2 · 규격").value, "50ml")
        self.assertTrue(any("상품정보 미입력 2번" in t.value for t in app.info))
        self.assertTrue(any(e.label.startswith("상품별 상세 수정") for e in app.expander))

    def test_item2_manual_name_automatically_rematches_dearglow_usd_price(self):
        doc = screenshot_candidate()
        catalog = deepcopy(CATALOG)
        catalog["products"].append({
            "id": "synthetic-melaser-serum", "brand": "ECLADO",
            "source_code": "TEST-MELASER-SERUM",
            "item_name": "Melaser Whitening Serum", "capacity": "50ml",
        })
        catalog["buyer_prices"].append({
            "product_id": "synthetic-melaser-serum",
            "buyer_key": "DEAR_GLOW", "currency": "USD",
            "unit_price": "7.50", "source_row": 8,
        })
        env = {
            "SUPABASE_URL": "https://" + EXPECTED_PROJECT + ".supabase.co",
            "SUPABASE_SECRET_KEY": "SYNTHETIC_TEST_ONLY",
        }
        with (patch.object(ai_intake_page, "document_export_env", return_value=env),
              patch.object(ai_intake_page, "_cached_master_eclado_catalog",
                           return_value=catalog) as lookup):
            app = self.app(doc, editor=True)
            next(t for t in app.text_input
                 if t.label == "PI · 상품 2 · 상품명").set_value(
                    "Melaser Whitening Serum").run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        result = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual(result["items"][1]["product_name"], "Melaser Whitening Serum")
        self.assertEqual(result["items"][1]["capacity"], "50ml")
        self.assertEqual(result["items"][1]["unit_price"], "7.50")
        self.assertTrue(result["items"][1]["master_price"])
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["items"][0]["product_name"], "Cell Memory Cream")
        self.assertEqual(len(result["items"]), 2)
        self.assertGreaterEqual(lookup.call_count, 1)

    def test_item2_correction_does_not_overwrite_po_item2(self):
        pi = screenshot_candidate()
        po = deepcopy(pi)
        po["document_type"] = "PO"
        po["currency"] = "KRW"
        po["buyer"]["legal_name"] = "KE KOREA CO. LTD"
        po["seller"]["legal_name"] = "ECLADO CO. LTD"
        po["items"][1]["product_name"] = "Different supplier item"
        po["items"][1]["unit_price"] = "1100"
        app = self.app(bundle={"PI": pi, "PO": po}, editor=True)
        next(t for t in app.text_input if t.label == "PI · 상품 2 · 상품명").set_value(
            "Melaser Whitening Serum").run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        bundle = app.session_state["ai_intake_candidates"][1]
        self.assertEqual(bundle["PI"]["items"][1]["product_name"],
                         "Melaser Whitening Serum")
        self.assertEqual(bundle["PO"]["items"][1]["product_name"],
                         "Different supplier item")
        self.assertEqual(bundle["PO"]["items"][1]["unit_price"], "1100")


if __name__ == "__main__":
    unittest.main()
