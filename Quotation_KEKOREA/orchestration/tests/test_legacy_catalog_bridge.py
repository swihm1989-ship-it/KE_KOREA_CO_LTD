"""Synthetic MASTER/legacy pricing parity. No real prices or Supabase traffic."""
import unittest
from copy import deepcopy

from Quotation_KEKOREA.orchestration.workflows.legacy_catalog_bridge import (
    requires_eclado_catalog, reuse_legacy_catalog,
)


CATALOG = {
    "products": [{"id": "synthetic-p1", "brand": "ECLADO",
                  "source_code": "E-165", "item_name": "Cell Memory Cream",
                  "capacity": "50g"}],
    "purchase_prices": [{"product_id": "synthetic-p1", "supplier_key": "ECLADO",
                         "currency": "KRW", "unit_price": "1000",
                         "source_row": 4}],
    "buyer_prices": [{"product_id": "synthetic-p1", "buyer_key": "DEAR_GLOW",
                      "currency": "USD", "unit_price": "12.50",
                      "source_row": 4}],
}


def trade(kind, buyer="Dear Glow", seller="KE KOREA CO. LTD", price=None):
    return {
        "document_type": kind, "product_family": "cosmetics",
        "document_number": "DRAFT", "currency": "USD" if kind != "PO" else "KRW",
        "buyer": {"legal_name": buyer, "address": "Synthetic buyer address"},
        "seller": {"legal_name": seller, "address": "Synthetic seller address"},
        "incoterms": "EXW Seoul", "payment_terms": "T/T in advance",
        "missing_fields": [], "conflicts": [],
        "items": [{"product_name": "Cell Memory Cream (E-165)",
                   "capacity": "50 g", "quantity": "10", "unit": "PCS",
                   "price_basis": "PCS", "discount_percent": "0",
                   "unit_price": price}],
    }


class MasterLegacyCatalogParityTests(unittest.TestCase):
    def test_pi_dear_glow_receives_exact_usd_sale_price(self):
        doc = trade("PI")
        original = deepcopy(doc)
        updated = reuse_legacy_catalog({"PI": doc}, CATALOG)["PI"]
        self.assertEqual(doc, original)
        self.assertEqual(updated["items"][0]["unit_price"], "12.50")
        self.assertTrue(updated["items"][0]["master_price"])
        self.assertEqual(updated["currency"], "USD")

    def test_po_eclado_uses_purchase_krw_not_pi_sale_usd(self):
        po = trade("PO", buyer="KE KOREA CO. LTD", seller="ECLADO", price="12.50")
        pi = trade("PI")
        updated = reuse_legacy_catalog({"PO": po, "PI": pi}, CATALOG)
        self.assertEqual(updated["PO"]["items"][0]["unit_price"], "1000")
        self.assertEqual(updated["PO"]["currency"], "KRW")
        self.assertEqual(updated["PI"]["items"][0]["unit_price"], "12.50")
        self.assertEqual(updated["PI"]["currency"], "USD")

    def test_unsupported_buyer_never_inherits_dear_glow_sale_price(self):
        pi = trade("PI", buyer="Another buyer", price="19.99")
        result = reuse_legacy_catalog({"PI": pi}, CATALOG)["PI"]
        self.assertEqual(result["items"][0]["unit_price"], "19.99")
        self.assertFalse(result["items"][0].get("master_price", False))
        self.assertNotIn("12.50", str(result))

    def test_ci_pl_original_prices_not_replaced_by_catalog(self):
        ci = trade("CI", price="19.99")
        pl = trade("PL", price=None)
        result = reuse_legacy_catalog({"CI": ci, "PL": pl}, CATALOG)
        self.assertEqual(result["CI"]["items"][0]["unit_price"], "19.99")
        self.assertIsNone(result["PL"]["items"][0]["unit_price"])

    def test_explicit_pi_price_differs_and_is_never_silently_overwritten(self):
        pi = trade("PI", price="15.00")
        first = reuse_legacy_catalog({"PI": pi}, CATALOG)
        self.assertEqual(first["PI"]["items"][0]["unit_price"], "15.00")
        conflicts = [x for x in first["PI"]["conflicts"]
                     if "stated price differs" in x]
        self.assertEqual(len(conflicts), 1)
        repeated = reuse_legacy_catalog(first, CATALOG)
        self.assertEqual(len([x for x in repeated["PI"]["conflicts"]
                              if "stated price differs" in x]), 1)
        repeated["PI"]["items"][0]["unit_price"] = "12.50"
        fixed = reuse_legacy_catalog(repeated, CATALOG)
        self.assertEqual(fixed["PI"]["items"][0]["unit_price"], "12.50")
        self.assertFalse(any("stated price differs" in x
                             for x in fixed["PI"]["conflicts"]))

    def test_po_switching_supplier_clears_only_verified_eclado_purchase_price(self):
        """The former supplier's private KRW cost must not survive a PO supplier change."""
        original = trade("PO", buyer="KE KOREA CO. LTD", seller="ECLADO", price=None)
        priced = reuse_legacy_catalog({"PO": original}, CATALOG)
        self.assertEqual(priced["PO"]["items"][0]["unit_price"], "1000")
        priced["PO"]["seller"]["legal_name"] = "UNRELATED SUPPLIER LTD"
        revised = reuse_legacy_catalog(priced, CATALOG)["PO"]
        self.assertIsNone(revised["items"][0]["unit_price"])
        self.assertFalse(revised["items"][0].get("master_price", False))

    def test_pi_switching_buyer_does_not_leak_dear_glow_catalog_price(self):
        original = trade("PI", price=None)
        priced = reuse_legacy_catalog({"PI": original}, CATALOG)
        self.assertEqual(priced["PI"]["items"][0]["unit_price"], "12.50")
        priced["PI"]["buyer"]["legal_name"] = "OTHER BUYER LTD"
        revised = reuse_legacy_catalog(priced, CATALOG)["PI"]
        self.assertIsNone(revised["items"][0]["unit_price"])
        self.assertFalse(revised["items"][0].get("master_price", False))

    def test_unrelated_solar_transaction_skips_catalog(self):
        source = {"PI": {"document_type": "PI",
                         "product_family": "solar_cell",
                         "buyer": {"legal_name": "Unrelated"},
                         "seller": {"legal_name": "KE KOREA CO. LTD"},
                         "items": [{"product_name": "Solar cell", "unit_price": "0.2"}]}}
        self.assertFalse(requires_eclado_catalog(source))

    def test_missing_catalog_fails_closed_and_does_not_mutate(self):
        pi = trade("PI")
        before = deepcopy(pi)
        with self.assertRaises(ValueError):
            reuse_legacy_catalog({"PI": pi}, {"products": []})
        self.assertEqual(pi, before)


if __name__ == "__main__":
    unittest.main()
