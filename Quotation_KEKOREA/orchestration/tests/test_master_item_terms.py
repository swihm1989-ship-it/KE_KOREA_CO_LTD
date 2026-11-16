"""Each MASTER PI/PO line independently controls discounts and free-goods promotions.

This uses synthetic prices and buyers; no live network or API credentials.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.orchestration.ui import ai_intake_page
from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi
from Quotation_KEKOREA.orchestration.workflows.trade_export_review import review_trade_document


DIGEST = "synthetic-item-terms"
_SOURCE = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import (
    _remember_candidate_bundle, _render_single_editor)
if 'ai_intake_candidates' not in st.session_state:
    _remember_candidate_bundle('synthetic-item-terms', DATA, replace_editor=True)
_render_single_editor('synthetic-item-terms', st.session_state['ai_intake_candidates'][1])
""".replace("DATA", "None")


def document(kind="PI"):
    doc = complete_pi()
    doc.update(document_type=kind, product_family="cosmetics", currency="USD")
    doc["buyer"]["legal_name"] = "DEAR GLOW PTE LTD" if kind == "PI" else "KE KOREA CO. LTD"
    doc["seller"]["legal_name"] = "KE KOREA CO. LTD" if kind == "PI" else "ECLADO"
    doc["items"] = [
        dict(product_name="Synthetic Toner", capacity="150ml", quantity="10",
             paid_quantity="10", free_quantity="0", shipped_quantity="10",
             unit="PCS", price_basis="PCS", unit_price="7.50",
             discount_percent=None, price_source="Verified ECLADO catalog; source workbook row 1",
             master_price=True),
        dict(product_name="Synthetic Serum", capacity="50ml", quantity="10",
             paid_quantity="10", free_quantity="0", shipped_quantity="10",
             unit="PCS", price_basis="PCS", unit_price="9.40",
             discount_percent=None, price_source="Verified ECLADO catalog; source workbook row 2",
             master_price=True),
    ]
    return doc


def ui(data):
    with patch.object(ai_intake_page, "document_export_env", return_value={}):
        app = AppTest.from_string(_SOURCE.replace("None", repr(data)), default_timeout=30).run()
    if app.exception:
        raise AssertionError([e.message for e in app.exception])
    return app


class MasterItemTermsTests(unittest.TestCase):
    def test_unselected_discount_defaults_to_actual_list_price_and_total(self):
        app = ui({"PI": document()})
        pi = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual([line["discount_percent"] for line in pi["items"]], ["0", "0"])
        self.assertEqual([line["unit_price"] for line in pi["items"]], ["7.50", "9.40"])
        report = review_trade_document("PI", pi, final=True, allow_incomplete=True)
        self.assertTrue(report["ready"], report["issues"])
        self.assertEqual([line["final_unit_price"] for line in report["render_data"]["items"]],
                         ["7.5", "9.4"])
        self.assertEqual(report["render_data"]["total"], "169.00")

    def test_existing_special_discount_is_not_reset_and_unknown_price_is_not_invented(self):
        pi = document()
        pi["items"][0]["discount_percent"] = "7.5"
        pi["items"][1]["unit_price"] = None
        pi["items"][1]["master_price"] = False
        app = ui({"PI": pi})
        rows = app.session_state["ai_intake_candidates"][1]["PI"]["items"]
        self.assertEqual(rows[0]["discount_percent"], "7.5")
        self.assertEqual(rows[1]["discount_percent"], "0")
        self.assertIsNone(rows[1]["unit_price"])
        report = review_trade_document("PI", app.session_state["ai_intake_candidates"][1]["PI"],
                                       final=True, allow_incomplete=True)
        self.assertIsNone(report["render_data"]["total"])

    def test_per_product_discount_and_promotion_are_independent(self):
        app = ui({"PI": document()})
        self.assertTrue(any(x.label == "PI · 상품 1 · 할인율" for x in app.selectbox))
        self.assertTrue(any(x.label == "PI · 상품 2 · 증정행사" for x in app.selectbox))
        app.selectbox(key="master_item_terms_PI_0_discount").set_value("5%").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.selectbox(key="master_item_terms_PI_1_promotion").set_value("2+1").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        pi = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual([item["discount_percent"] for item in pi["items"]], ["5", "0"])
        self.assertEqual([item.get("promotion") for item in pi["items"]], [None, "2+1"])
        self.assertEqual(pi["items"][1]["free_quantity"], "5")
        self.assertEqual(pi["items"][1]["shipped_quantity"], "15")
        self.assertEqual(pi["items"][0]["shipped_quantity"], "10")
        reviewed = review_trade_document("PI", pi, final=True, allow_incomplete=True)
        self.assertTrue(reviewed["ready"], reviewed["issues"])
        self.assertEqual(reviewed["render_data"]["total"], "165.25")
        self.assertEqual(reviewed["render_data"]["items"][1]["free_quantity"], "5")

        app.selectbox(key="master_item_terms_PI_1_promotion").set_value("행사 없음").run()
        pi = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertFalse(pi["items"][1].get("promotion"))
        self.assertEqual(pi["items"][1]["free_quantity"], "0")
        self.assertEqual(pi["items"][1]["shipped_quantity"], "10")

    def test_custom_discount_and_custom_promotion_are_per_line(self):
        app = ui({"PI": document()})
        app.selectbox(key="master_item_terms_PI_0_discount").set_value("직접 입력").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.text_input(key="master_item_terms_PI_0_custom_discount").set_value("7.5").run()
        app.selectbox(key="master_item_terms_PI_0_promotion").set_value("직접 입력").run()
        app.text_input(key="master_item_terms_PI_0_custom_promotion").set_value("5+2").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        pi = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual(pi["items"][0]["discount_percent"], "7.5")
        self.assertEqual(pi["items"][0]["promotion"], "5+2")
        self.assertEqual(pi["items"][0]["free_quantity"], "4")
        self.assertEqual(pi["items"][0]["shipped_quantity"], "14")
        self.assertEqual(pi["items"][1]["discount_percent"], "0")
        self.assertFalse(pi["items"][1].get("promotion"))

    def test_pi_discount_edit_cannot_change_po_price_or_discount(self):
        po = document("PO")
        po["currency"] = "KRW"
        po["items"][0]["unit_price"] = "1000"
        data = {"PI": document(), "PO": po}
        original_po = deepcopy(po)
        app = ui(data)
        app.selectbox(key="master_item_terms_PI_0_discount").set_value("10%").run()
        bundle = app.session_state["ai_intake_candidates"][1]
        self.assertEqual(bundle["PI"]["items"][0]["discount_percent"], "10")
        self.assertEqual(bundle["PO"]["items"][0]["discount_percent"], "0")
        self.assertEqual(bundle["PO"]["items"][0]["unit_price"], original_po["items"][0]["unit_price"])
        self.assertFalse(any(item.get("promotion") for item in bundle["PO"]["items"]))

    def test_ci_source_discounts_remain_untouched_by_pi_po_default(self):
        ci = document("PI")
        ci["document_type"] = "CI"
        ci["items"][0]["discount_percent"] = None
        app = ui({"CI": ci})
        result = app.session_state["ai_intake_candidates"][1]["CI"]
        self.assertIsNone(result["items"][0]["discount_percent"])


if __name__ == "__main__":
    unittest.main()
