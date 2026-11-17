"""Regression for a 49-product laptop PI in the KE KOREA MASTER UI.

Synthetic customer data only. Tests original KE KOREA extraction handoff,
the retained Master candidate, one-click unit confirmation, and the separation
between payment instalments and merchandise discounts. No network or mail send.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
from Quotation_KEKOREA.orchestration.ui import ai_intake_page
from Quotation_KEKOREA.orchestration.workflows.mail_intake import extract_mail_candidates
from Quotation_KEKOREA.orchestration.tests.test_mail_document_intake import response
from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi

INSTRUCTION = (
    "Prepare PI from the attached laptop order. Unit prices are USD per item. "
    "추가 할인율은 0%입니다. 결제조건: T/T 계약금 30%, 잔금 70% 선적 전 지급. "
    "모델 변경 및 대체품은 사전 협의합니다."
)
SOURCE = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import (
    _remember_candidate_bundle, _render_single_editor)
st.session_state["ai_intake_instruction"] = INSTRUCTION
if "ai_intake_candidates" not in st.session_state:
    _remember_candidate_bundle("synthetic-49-unit", DATA,
                               replace_editor=True,
                               source_extraction=FRESH)
_render_single_editor("synthetic-49-unit",
                      st.session_state["ai_intake_candidates"][1])
"""


def laptop_pi(*, discount="70", unit=None, price_basis=None):
    doc = complete_pi()
    doc.update(product_family="other", document_type="PI", currency="USD",
               incoterms="CIF Singapore Port", payment_terms="T/T 30% deposit; 70% balance")
    doc["items"] = [
        {"product_name": f"Synthetic Laptop Model {i:02d}",
         "product_code": f"SKU-{i:02d}", "capacity": None,
         "quantity": str(90 + i), "paid_quantity": str(90 + i),
         "shipped_quantity": str(90 + i), "free_quantity": "0",
         "unit": unit, "unit_price": "1270", "price_basis": price_basis,
         "discount_percent": discount, "price_source": "Synthetic order unit price",
         "source": f"Synthetic Laptop Model {i:02d} Qty {90+i} USD 1270"}
        for i in range(1, 50)
    ]
    return doc


def master_ui(candidate, *, fresh=True, instruction=INSTRUCTION):
    source = (SOURCE.replace("INSTRUCTION", repr(instruction))
              .replace("DATA", repr(candidate))
              .replace("FRESH", str(bool(fresh))))
    with patch.object(ai_intake_page, "document_export_env", return_value={}):
        app = AppTest.from_string(source, default_timeout=35).run()
    if app.exception:
        raise AssertionError([e.message for e in app.exception])
    return app


class MasterPaymentUnitHandoffRegression(unittest.TestCase):
    def test_original_agent_49_row_mail_pipeline_rejects_payment_70_as_discount(self):
        """A simulated AI response wrongly says 70%, source explicitly says 0%."""
        raw = laptop_pi()
        before = deepcopy(raw)
        with patch("Quotation_KEKOREA.agent.document_engine.verify_item_quotes",
                   side_effect=lambda d, prompt, image_context=False: d):
            result = extract_mail_candidates(
                INSTRUCTION, ("PI",),
                {"OPENAI_API_KEY": "SYNTHETIC", "OPENAI_MODEL": "test-only"},
                consent=True, family="other",
                trade_opener=lambda *a, **kw: response(raw))
        actual = result["candidates"]["PI"]
        self.assertEqual(raw, before)
        self.assertEqual(len(actual["items"]), 49)
        self.assertTrue(all(row["discount_percent"] == "0" for row in actual["items"]))
        self.assertTrue(all(row["unit_price"] == "1270" for row in actual["items"]))
        self.assertEqual(actual["payment_terms"], "T/T 30% deposit; 70% balance")
        # Missing units are not filled by guessing merely because qty is numeric.
        self.assertTrue(all(not row.get("unit") for row in actual["items"]))

    def test_master_initial_store_restores_source_zero_for_bad_provider_70(self):
        app = master_ui({"PI": laptop_pi()}, fresh=True)
        rows = app.session_state["ai_intake_candidates"][1]["PI"]["items"]
        self.assertEqual([row["discount_percent"] for row in rows], ["0"] * 49)
        self.assertTrue(all(row["unit_price"] == "1270" for row in rows))

    def test_49_rows_show_one_bulk_unit_action_not_49_product_cards(self):
        app = master_ui({"PI": laptop_pi()}, fresh=True)
        self.assertTrue(any("수량은 인식됐지만 단위가 미확정인 품목 49개"
                            in text.value for text in app.info))
        self.assertFalse(any(entry.label == "PI · 상품 28 · 단위"
                             for entry in app.text_input))
        self.assertFalse(any(entry.label == "PI · 상품 29 · 규격"
                             for entry in app.text_input))
        self.assertEqual(len([x for x in app.selectbox
                              if x.label == "PI · 미확정 품목 수량 단위"]), 1)
        self.assertTrue(any("품목별 할인·행사 (49개)" in x.label for x in app.expander))
        next(btn for btn in app.button if btn.label == "PI · 빈 단위 49개 일괄 적용").click().run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        rows = app.session_state["ai_intake_candidates"][1]["PI"]["items"]
        self.assertEqual(len(rows), 49)
        self.assertTrue(all(x["unit"] == "PCS" and x["price_basis"] == "PCS" for x in rows))
        self.assertEqual([x["unit_price"] for x in rows], ["1270"] * 49)
        self.assertEqual([x["discount_percent"] for x in rows], ["0"] * 49)
        self.assertEqual([x["paid_quantity"] for x in rows], [str(90 + i) for i in range(1, 50)])
        report = validate_and_calculate(app.session_state["ai_intake_candidates"][1]["PI"])
        self.assertEqual(report["items"][0]["line_total"], "115570.00")
        self.assertEqual(app.session_state.get("master_trade_final_files"), None)

    def test_bulk_units_change_only_the_current_kind_and_leave_real_kg_alone(self):
        pi = laptop_pi(discount="5")
        pi["items"][3]["unit"] = "KG"
        po = laptop_pi(discount="10", unit="KG", price_basis="KG")
        po.update(document_type="PO", currency="KRW")
        po["buyer"]["legal_name"] = "KE KOREA CO. LTD"
        po["seller"]["legal_name"] = "SYNTHETIC SUPPLIER"
        app = master_ui({"PI": pi, "PO": po}, fresh=False,
                        instruction="Prepare two documents from synthetic order")
        next(b for b in app.button if b.label.startswith("PI · 빈 단위 ")).click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        docs = app.session_state["ai_intake_candidates"][1]
        self.assertEqual(docs["PI"]["items"][3]["unit"], "KG")
        self.assertEqual(docs["PI"]["items"][0]["unit"], "PCS")
        self.assertEqual(docs["PI"]["items"][0]["discount_percent"], "5")
        self.assertEqual(docs["PO"]["items"][0]["unit"], "KG")
        self.assertEqual(docs["PO"]["items"][0]["discount_percent"], "10")
        self.assertEqual(docs["PO"]["currency"], "KRW")

    def test_bulk_unit_does_not_fill_unidentified_products_outside_button_count(self):
        pi = laptop_pi(discount="0")
        pi["items"][1]["product_name"] = None
        app = master_ui({"PI": pi}, fresh=False,
                        instruction="Synthetic PI line list for user verification")
        self.assertTrue(any(b.label == "PI · 빈 단위 48개 일괄 적용"
                            for b in app.button))
        next(b for b in app.button
             if b.label == "PI · 빈 단위 48개 일괄 적용").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        rows = app.session_state["ai_intake_candidates"][1]["PI"]["items"]
        self.assertEqual(rows[0]["unit"], "PCS")
        self.assertIsNone(rows[1]["unit"])  # Product name requires separate evidence

    def test_stale_70_only_restored_after_click_and_user_discount_stays_editable(self):
        app = master_ui({"PI": laptop_pi(unit="PCS", price_basis="PCS")}, fresh=False)
        rows = app.session_state["ai_intake_candidates"][1]["PI"]["items"]
        self.assertEqual(rows[0]["discount_percent"], "70")  # no silent mutation
        self.assertTrue(any("원문 할인율 0%" in x.value for x in app.warning))
        next(b for b in app.button if b.label == "PI · 원문 할인율 0% 복원").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        rows = app.session_state["ai_intake_candidates"][1]["PI"]["items"]
        self.assertTrue(all(x["discount_percent"] == "0" for x in rows))
        next(x for x in app.selectbox if x.label == "PI · 상품 1 · 할인율").set_value("5%").run()
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["PI"]["items"][0]["discount_percent"], "5")

    def test_real_discount_five_is_not_treated_as_payment_balance(self):
        app = master_ui({"PI": laptop_pi()}, fresh=True,
                        instruction="Discount 5%. T/T 30% deposit and 70% balance before shipment.")
        rows = app.session_state["ai_intake_candidates"][1]["PI"]["items"]
        self.assertTrue(all(row["discount_percent"] == "5" for row in rows))


if __name__ == "__main__":
    unittest.main()
