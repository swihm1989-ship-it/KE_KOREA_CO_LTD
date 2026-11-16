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
        next(x for x in app.selectbox if x.label == "PI · 상품 1 · 할인율").set_value("5%").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        next(x for x in app.selectbox if x.label == "PI · 상품 2 · 증정행사").set_value("2+1").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        pi = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual([item["discount_percent"] for item in pi["items"]], ["5", "0"])
        self.assertEqual([item.get("promotion") for item in pi["items"]], [None, "2+1"])
        self.assertEqual(pi["items"][1]["free_quantity"], "5")
        self.assertEqual(pi["items"][1]["shipped_quantity"], "15")
        self.assertEqual(pi["items"][0]["shipped_quantity"], "10")
        reviewed = review_trade_document("PI", pi, final=True, allow_incomplete=True)
        self.assertTrue(reviewed["ready"], reviewed["issues"])
        self.assertEqual(reviewed["render_data"]["total"], "165.30")
        self.assertEqual(reviewed["render_data"]["items"][1]["free_quantity"], "5")

        next(x for x in app.selectbox if x.label == "PI · 상품 2 · 증정행사").set_value("행사 없음").run()
        pi = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertFalse(pi["items"][1].get("promotion"))
        self.assertEqual(pi["items"][1]["free_quantity"], "0")
        self.assertEqual(pi["items"][1]["shipped_quantity"], "10")

    def test_custom_discount_and_custom_promotion_are_per_line(self):
        app = ui({"PI": document()})
        next(x for x in app.selectbox if x.label == "PI · 상품 1 · 할인율").set_value("직접 입력").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        next(x for x in app.text_input if x.label == "PI · 상품 1 · 직접 할인율 (%)").set_value("7.5").run()
        next(x for x in app.selectbox if x.label == "PI · 상품 1 · 증정행사").set_value("직접 입력").run()
        next(x for x in app.text_input if x.label == "PI · 상품 1 · 직접 증정행사 (예: 5+2)").set_value("5+2").run()
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
        next(x for x in app.selectbox if x.label == "PI · 상품 1 · 할인율").set_value("10%").run()
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


    def test_bulk_preset_buttons_overwrite_each_discount_and_restore_full_list_price(self):
        pi = document()
        pi["items"][0]["discount_percent"] = "10"
        pi["items"][1]["discount_percent"] = "2.5"
        app = ui({"PI": pi})
        for label, rate, total in [
            ("PI · 전체 5%", "5", "160.60"),
            ("PI · 전체 10%", "10", "152.10"),
            ("PI · 전체 0%", "0", "169.00"),
        ]:
            next(b for b in app.button if b.label == label).click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            current = app.session_state["ai_intake_candidates"][1]["PI"]
            self.assertEqual([row["discount_percent"] for row in current["items"]], [rate, rate])
            self.assertEqual([row["unit_price"] for row in current["items"]], ["7.50", "9.40"])
            review = review_trade_document("PI", current, final=True, allow_incomplete=True)
            self.assertTrue(review["ready"], review["issues"])
            self.assertEqual(review["render_data"]["total"], total)

    def test_bulk_discount_preserves_gifts_and_other_document_prices(self):
        pi = document()
        pi["items"][1]["promotion"] = "2+1"
        pi["items"][1]["free_quantity"] = "5"
        pi["items"][1]["shipped_quantity"] = "15"
        po = document("PO")
        po["items"][0]["discount_percent"] = "10"
        po["items"][0]["unit_price"] = "1000"
        po["currency"] = "KRW"
        ci = document()
        ci["document_type"] = "CI"
        ci["items"][0]["discount_percent"] = "7.5"
        app = ui({"PI": pi, "PO": po, "CI": ci})
        next(b for b in app.button if b.label == "PI · 전체 5%").click().run()
        data = app.session_state["ai_intake_candidates"][1]
        self.assertEqual([x["discount_percent"] for x in data["PI"]["items"]], ["5", "5"])
        self.assertEqual(data["PI"]["items"][1]["promotion"], "2+1")
        self.assertEqual(data["PI"]["items"][1]["free_quantity"], "5")
        self.assertEqual(data["PI"]["items"][1]["shipped_quantity"], "15")
        self.assertEqual(data["PO"]["items"][0]["discount_percent"], "10")
        self.assertEqual(data["PO"]["items"][0]["unit_price"], "1000")
        self.assertEqual(data["CI"]["items"][0]["discount_percent"], "7.5")
        next(x for x in app.selectbox if x.label == "PI · 상품 1 · 할인율").set_value("10%").run()
        data = app.session_state["ai_intake_candidates"][1]
        self.assertEqual([x["discount_percent"] for x in data["PI"]["items"]], ["10", "5"])

    def test_custom_bulk_discount_and_invalid_value_do_not_reprice_items(self):
        app = ui({"PI": document()})
        entry = next(x for x in app.text_input if x.label == "PI · 할인율 직접 입력 (%)")
        entry.set_value("7.5").run()
        next(x for x in app.button if x.label == "PI · 입력 할인율 전체 적용").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        current = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual([x["discount_percent"] for x in current["items"]], ["7.5", "7.5"])
        self.assertEqual([x["unit_price"] for x in current["items"]], ["7.50", "9.40"])
        next(x for x in app.text_input if x.label == "PI · 할인율 직접 입력 (%)").set_value("101").run()
        next(x for x in app.button if x.label == "PI · 입력 할인율 전체 적용").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        current = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual([x["discount_percent"] for x in current["items"]], ["7.5", "7.5"])
        self.assertTrue(any("0~100" in x.message for x in app.error))

    def test_bulk_discount_actions_not_offered_for_ci(self):
        ci = document()
        ci["document_type"] = "CI"
        app = ui({"CI": ci})
        self.assertFalse(any("전체 5%" in button.label for button in app.button))


if __name__ == "__main__":
    unittest.main()
