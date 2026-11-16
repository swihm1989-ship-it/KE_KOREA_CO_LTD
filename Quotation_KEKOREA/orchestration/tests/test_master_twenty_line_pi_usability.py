"""MASTER video regression: 20 ECLADO rows, one review, and compact inputs.

Only synthetic prices are used. Original ECLADO TEST.png is evidence for the
names/sizes/quantities; no private customer data or real invoice is generated.
"""
from copy import deepcopy
import unittest

from Quotation_KEKOREA.orchestration.tests.test_trade_final_ui import TradeFinalUiTests
from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi


NAMES = [
    "Melaser Whitening Toner", "Melaser Whitening Serum",
    "Melaser Turn Over Cream", "Melaser Radiance Cream",
    "Exo Clinica Toner", "Exo Clinica Gel", "Exo Clinica Cream",
    "Exo Clinica UV Suncream", "Cell Memory Cream",
    "Golden Sandalwood Gua Sha", "Rescuer Cica Balm",
    "Enhancer Mild Cleanser", "Purifying Cleanser",
    "Enzyme Deep Cleanser Pure Powder", "Perfect Cleansing Smoothie Balm",
    "Rejuven Fiber&Ampoule System", "Oxygen Bubble Pack",
    "Whitening Enhancer Sun Blemish Balm", "Shining V-C Serum",
    "Revitalizing Elastin & Collagen Serum",
]


def twenty_item_pi():
    doc = complete_pi()
    doc.update(document_type="PI", product_family="cosmetics",
               document_number="DRAFT", source_image_attached=True,
               incoterms="", payment_terms="")
    item = deepcopy(doc["items"][0])
    doc["items"] = [
        {**deepcopy(item), "product_name": name,
         "quantity": str(15 if idx == 7 else 5 if idx == 15 else 10),
         "paid_quantity": str(15 if idx == 7 else 5 if idx == 15 else 10),
         "unit": "PCS", "price_basis": "PCS", "unit_price": "10.00",
         "master_price": True, "discount_percent": None}
        for idx, name in enumerate(NAMES)]
    doc["missing_fields"] = [
        "Confirm discount percentage including whether no discount applies"
        for _ in range(20)]
    doc["conflicts"] = [
        "Order details were extracted from an image; visually confirm "
        "product names, sizes, and quantities",
        "Item 2 has no verifiable exact quote from the prompt; confirm its extracted facts",
    ]
    return doc


class MasterTwentyLinePiUxTests(unittest.TestCase):
    app = TradeFinalUiTests.app
    seal = TradeFinalUiTests.seal
    approve = TradeFinalUiTests.approve
    export = TradeFinalUiTests.export

    def test_twenty_products_use_a_single_compact_editor_and_one_final_report(self):
        doc = twenty_item_pi()
        app = self.app(doc, editor=True)
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertEqual(len([e for e in app.expander
                              if e.label.startswith("상품별 상세 수정")]), 1)
        self.assertFalse(any(e.label == "현재 입력 확인사항 · 누락·오류 상세"
                             for e in app.expander))
        self.assertEqual(len([x for x in app.selectbox if "· 할인율" in x.label]), 20)
        self.assertEqual(len([x for x in app.selectbox if "· 증정행사" in x.label]), 20)
        self.assertFalse(any("미입력 할인율" in x.label for x in app.button))
        self.assertTrue(all(item["discount_percent"] == "0"
                            for item in app.session_state["ai_intake_candidates"][1]["PI"]["items"]))
        self.assertEqual(len(app.dataframe), 1)
        # Every line-item discount exists in the collapsed advanced editor,
        # not as a repeated warning/comment 20 times.
        self.assertLessEqual(len(app.warning), 1)
        self.assertFalse(next(c for c in app.checkbox
                              if c.label.startswith("PI · 최종 출력")).disabled)

    def test_default_list_discount_preserves_explicit_item_rate(self):
        doc = twenty_item_pi()
        doc["items"][0]["discount_percent"] = "5"
        app = self.app(doc, editor=True)
        self.assertFalse(app.exception, [e.message for e in app.exception])
        result = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual(len(result["items"]), 20)
        self.assertEqual(result["items"][0]["discount_percent"], "5")
        self.assertTrue(all(row["discount_percent"] == "0"
                            for row in result["items"][1:]))
        self.assertFalse(any(b.label.startswith("PI · 미입력 할인율")
                             for b in app.button))
        self.assertFalse(next(c for c in app.checkbox
                              if c.label.startswith("PI · 최종 출력")).disabled)

    def test_user_can_export_real_legacy_pi_without_bulk_discount_action(self):
        with self.seal():
            app = self.app(twenty_item_pi(), editor=True)
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.approve(app)
            self.export(app)
            pdf = app.session_state["master_trade_final_files"]["PI"]["files"]["pdf"]
            self.assertTrue(pdf["content"].startswith(b"%PDF"))
            self.assertTrue(pdf["final"])

    def test_corrected_image_item_final_pdf_without_source_flag(self):
        doc = twenty_item_pi()
        doc.pop("source_image_attached", None)
        for item in doc["items"]:
            item["discount_percent"] = "0"
        doc["items"][1].update(product_name="Melaser Whitening Serum",
                               capacity="50ml", unit_price="7.50",
                               master_price=True)
        with self.seal():
            app = self.app(doc, editor=True)
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertFalse(next(c for c in app.checkbox
                                  if c.label.startswith("PI · 최종 출력")).disabled)
            self.approve(app)
            self.export(app)
            self.assertTrue(app.session_state["master_trade_final_files"]["PI"]
                            ["files"]["pdf"]["content"].startswith(b"%PDF"))

    def test_discount_edits_are_scoped_and_do_not_edit_other_documents(self):
        doc = twenty_item_pi()
        po = deepcopy(doc)
        po["document_type"] = "PO"
        po["buyer"] = {"legal_name": "KE KOREA CO. LTD",
                       "address": "Synthetic address"}
        po["seller"] = {"legal_name": "ECLADO CO. LTD",
                        "address": "Synthetic address"}
        po["currency"] = "KRW"
        po["conflicts"] = []
        app = self.app(bundle={"PI": doc, "PO": po}, editor=True)
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["PI"]["items"][0]["discount_percent"], "0")
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["PO"]["items"][0]["discount_percent"], "0")
        next(x for x in app.selectbox if x.label == "PI · 상품 1 · 할인율").set_value("5%").run()
        candidate = app.session_state["ai_intake_candidates"][1]
        self.assertEqual(candidate["PI"]["items"][0]["discount_percent"], "5")
        self.assertEqual(candidate["PO"]["items"][0]["discount_percent"], "0")


if __name__ == "__main__":
    unittest.main()
