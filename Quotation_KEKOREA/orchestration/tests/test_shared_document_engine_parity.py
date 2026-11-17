"""Regression: KE KOREA UI and MASTER use one extraction postprocessor."""
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from Quotation_KEKOREA.agent import document_engine
from Quotation_KEKOREA.orchestration.workflows.mail_intake import _safe_trade


EMPTY_CATALOG = {"products": [], "buyer_prices": [], "purchase_prices": []}
REQUEST = (
    "Please provide PI for ECLADO Cell Memory Cream (E-165). "
    "Quantity: 10 PCS. Buyer: Dear Glow. Seller: KE KOREA. "
    "Payment terms: T/T in advance. No discount."
)


def trade_source(kind="PI"):
    return {
        "document_type": kind, "product_family": "cosmetics",
        "document_number": None, "buyer": {
            "legal_name": "Dear Glow", "address": "Synthetic Buyer Address"},
        "seller": {"legal_name": None, "address": None},
        "currency": "USD", "incoterms": "EXW Seoul",
        "payment_terms": "T/T in advance",
        "remarks": None, "ship_to": None,
        "missing_fields": [], "conflicts": [], "source_notes": [],
        "items": [{
            "product_name": "Cell Memory Cream", "product_code": "E-165",
            "quantity": "10", "unit": "PCS", "capacity": "50 g",
            "price_basis": "PCS", "unit_price": None,
            "source": "Quantity: 10 PCS",
            "discount_percent": None,
        }],
    }


class SharedDocumentEngineParity(unittest.TestCase):
    def test_original_app_entrypoint_is_shared_import_not_fork(self):
        root = Path(__file__).resolve().parents[2]
        app_source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("from Quotation_KEKOREA.agent.document_engine import", app_source)
        self.assertNotIn("def _extract_draft(", app_source)
        self.assertIn("finalize_extracted_trade", document_engine.__dict__)
        self.assertEqual(document_engine.SHARED_TRADE_ENGINE_REVISION,
                         "master-payment-discount-shared-20261117-v2")

    def test_master_mail_and_original_app_share_source_for_pi(self):
        raw = trade_source("PI")
        candidate = deepcopy(raw)
        original = deepcopy(raw)
        master = _safe_trade(candidate, "PI", REQUEST, "cosmetics", ())
        legacy = document_engine.finalize_extracted_trade(
            original, REQUEST, "PI", (), EMPTY_CATALOG, family="cosmetics")
        self.assertEqual(candidate, raw)  # MASTER cannot mutate the model source
        for key in ("seller", "buyer", "document_type", "currency",
                    "issue_date", "product_family", "remarks"):
            self.assertEqual(master[key], legacy[key], key)
        for key in ("quantity", "paid_quantity", "shipped_quantity", "unit",
                    "unit_price", "discount_percent"):
            self.assertEqual(master["items"][0].get(key), legacy["items"][0].get(key), key)
        self.assertEqual(master["seller"]["legal_name"], "KE Korea Co. LTD")

    def test_original_entrypoint_delegates_to_same_postprocessor(self):
        raw = trade_source("PI")
        with patch.object(document_engine, "extract_trade_data",
                          return_value=deepcopy(raw)) as extract:
            data = document_engine._extract_draft(
                REQUEST, "Proforma Invoice", "PI", (), {}, EMPTY_CATALOG)
        extract.assert_called_once()
        self.assertEqual(data["document_type"], "PI")
        self.assertEqual(data["seller"]["legal_name"], "KE Korea Co. LTD")
        self.assertEqual(data["items"][0]["quantity"], "10")

    def test_po_uses_exact_same_buy_side_company_defaults(self):
        raw = trade_source("PO")
        raw["buyer"] = {"legal_name": None, "address": None}
        raw["seller"] = {"legal_name": "ECLADO", "address": "Synthetic address"}
        master = _safe_trade(deepcopy(raw), "PO", REQUEST, "cosmetics", ())
        legacy = document_engine.finalize_extracted_trade(
            deepcopy(raw), REQUEST, "PO", (), EMPTY_CATALOG, family="cosmetics")
        self.assertEqual(master["buyer"], legacy["buyer"])
        self.assertEqual(master["buyer"]["legal_name"], "KE Korea Co. LTD")
        self.assertEqual(master["currency"], legacy["currency"])


    def test_unrelated_po_keeps_original_foreign_currency(self):
        raw = trade_source("PO")
        raw["buyer"] = {"legal_name": "KE KOREA CO. LTD", "address": "Synthetic"}
        raw["seller"] = {"legal_name": "UNRELATED SUPPLIER LTD",
                         "address": "Synthetic"}
        raw["currency"] = "EUR"
        for pipeline in (
            lambda: _safe_trade(deepcopy(raw), "PO", REQUEST, "cosmetics", ()),
            lambda: document_engine.finalize_extracted_trade(
                deepcopy(raw), REQUEST, "PO", (), EMPTY_CATALOG,
                family="cosmetics"),
        ):
            with self.subTest(pipeline=pipeline):
                output = pipeline()
                self.assertEqual(output["currency"], "EUR")
                self.assertEqual(output["seller"]["legal_name"],
                                 "UNRELATED SUPPLIER LTD")



if __name__ == "__main__":
    unittest.main()
