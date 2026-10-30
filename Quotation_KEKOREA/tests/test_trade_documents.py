"""Synthetic checks for English trade document drafts and safe calculations."""
import importlib.util
from decimal import Decimal
from pathlib import Path
import zipfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("trade_documents", ROOT / "agent" / "trade_documents.py")
trade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trade)
from Quotation_KEKOREA.agent.pricing import apply_verified_eclado_prices, load_local_seed, match_eclado_product, resolve_price
from Quotation_KEKOREA.agent.renderers import amount_in_english, render_files


def sample_trade(**updates):
    data = {
        "document_type": "PI", "product_family": "cosmetics", "currency": "USD",
        "buyer": {"legal_name": "Example Buyer Ltd", "address": "1 Sample Road, Seoul", "contact": None, "phone": None, "email": None},
        "seller": {"legal_name": "KE KOREA CO. LTD", "address": None, "contact": None, "phone": None, "email": None},
        "items": [{"product_name": "Example Toner", "capacity": "100 ml", "quantity": "10", "unit": "PCS", "unit_price": "12.50", "price_basis": "per PCS", "discount_percent": "10", "paid_quantity": "10", "free_quantity": "0", "shipped_quantity": "10", "source": "synthetic test"}],
        "incoterms": None, "payment_terms": None, "remarks": None, "document_number": None,
        "issue_date": "2026-10-30", "ship_to": None, "bill_to": None,
        "missing_fields": [], "conflicts": [], "source_notes": ["synthetic test"],
    }
    data.update(updates)
    return data


class TradeDocumentTests(unittest.TestCase):
    def test_decimal_discount_is_applied_once_to_final_unit_price(self):
        result = trade.validate_and_calculate(sample_trade())
        item = result["items"][0]
        self.assertEqual(item["final_unit_price"], "11.25")
        self.assertEqual(item["line_total"], "112.50")
        self.assertEqual(result["total"], "112.50")

    def test_missing_transaction_terms_block_document_render(self):
        result = trade.validate_and_calculate(sample_trade())
        self.assertIn("Incoterms and named place", result["blocking_issues"])
        self.assertFalse(result["ready_for_issue"])

    def test_conflicting_or_unknown_price_basis_blocks_document(self):
        data = sample_trade(product_family="solar")
        data["items"][0]["price_basis"] = None
        result = trade.validate_and_calculate(data)
        self.assertIn("Price basis for Example Toner", result["blocking_issues"])

    def test_promotion_separates_paid_free_and_shipped_quantities(self):
        item = trade.apply_promotion("5", "2+1")
        self.assertEqual(item, {"paid_quantity": "5", "free_quantity": "2", "shipped_quantity": "7"})

    def test_free_items_are_not_charged(self):
        data = sample_trade()
        data["items"][0].update({"quantity": "5", "paid_quantity": "5", "free_quantity": "2", "shipped_quantity": "7"})
        result = trade.validate_and_calculate(data)
        self.assertEqual(result["items"][0]["line_total"], "56.25")

    def test_non_english_document_fields_are_rejected(self):
        data = sample_trade()
        data["buyer"]["legal_name"] = "가상의 구매자"
        result = trade.validate_and_calculate(data)
        self.assertIn("Buyer legal name must be English", result["blocking_issues"])

    def test_po_and_pi_party_roles_are_checked(self):
        data = sample_trade(document_type="PO")
        self.assertIn("PO seller must be the supplier and buyer must be KE KOREA", trade.validate_and_calculate(data)["blocking_issues"])

    def test_unconfirmed_packing_cannot_be_finalized(self):
        data = sample_trade(document_type="PL")
        data["packages"] = []
        self.assertIn("Actual package count and weights", trade.validate_and_calculate(data)["blocking_issues"])

    def test_eclado_local_seed_has_separate_purchase_and_buyer_price_tables(self):
        seed = load_local_seed()
        self.assertEqual(len(seed["products"]), 157)
        product = seed["products"][0]
        self.assertEqual(match_eclado_product(product["item_name"], product.get("capacity"), seed["products"])["status"], "matched")
        role = "purchase" if product["kind"] == "sample" else "sale"
        currency = "KRW" if role == "purchase" or product["kind"] == "sample" else "USD"
        self.assertIsNotNone(resolve_price(product["id"], seed, role, currency))

    def test_dear_glow_price_is_not_applied_to_an_unregistered_buyer(self):
        seed = load_local_seed()
        product = next(p for p in seed["products"] if p["kind"] == "standard")
        draft = {"document_type": "PI", "product_family": "cosmetics", "currency": "USD",
                 "buyer": {"legal_name": "Different Buyer Ltd"}, "items": [{
                     "product_name": product["item_name"], "capacity": product["capacity"],
                     "unit_price": None, "source": None}]}
        apply_verified_eclado_prices(draft, seed)
        self.assertIsNot(draft["items"][0].get("master_price"), True)
        self.assertTrue(any("local catalog price is only for DEAR GLOW" in issue for issue in draft["missing_fields"]))

    def test_purchase_and_sale_prices_are_selected_by_document_direction(self):
        seed = load_local_seed()
        product = next(p for p in seed["products"] if p["kind"] == "standard")
        item = {"product_name": product["item_name"], "capacity": product["capacity"],
                "unit_price": None, "source": None}
        pi = {"document_type": "PI", "product_family": "cosmetics", "currency": "USD",
              "buyer": {"legal_name": "Dear Glow"}, "items": [dict(item)]}
        po = {"document_type": "PO", "product_family": "cosmetics", "currency": "KRW",
              "seller": {"legal_name": "Eclado Co., Ltd."}, "items": [dict(item)]}
        apply_verified_eclado_prices(pi, seed)
        apply_verified_eclado_prices(po, seed)
        self.assertEqual(pi["items"][0]["price_source"].split(";")[0], "Verified local ECLADO catalog")
        self.assertEqual(po["items"][0]["price_source"].split(";")[0], "Verified local ECLADO catalog")
        self.assertEqual(pi["currency"], "USD")
        self.assertEqual(po["currency"], "KRW")

    def test_amount_words(self):
        self.assertEqual(amount_in_english("112.50", "USD"), "ONE HUNDRED TWELVE US DOLLARS AND FIFTY CENTS ONLY")

    def test_generated_review_files_are_readable_containers(self):
        data = trade.validate_and_calculate(sample_trade())
        temp = ROOT / "private" / "eclado" / "test-output"
        temp.mkdir(parents=True, exist_ok=True)
        paths = render_files(data, temp)
        try:
            self.assertTrue(paths["pdf"].read_bytes().startswith(b"%PDF-1.4"))
            with zipfile.ZipFile(paths["xlsx"]) as workbook:
                self.assertIn("xl/worksheets/sheet1.xml", workbook.namelist())
                sheet = workbook.read("xl/worksheets/sheet1.xml").decode()
                self.assertIn("112.50", sheet)
            self.assertIn("AMOUNT IN WORDS", paths["html"].read_text(encoding="utf-8"))
        finally:
            for path in paths.values():
                path.unlink(missing_ok=True)
            temp.rmdir()

    def test_renderer_rejects_non_english_document_text_instead_of_corrupting_it(self):
        data = trade.validate_and_calculate(sample_trade())
        data["buyer"]["legal_name"] = "구매자"
        with self.assertRaisesRegex(ValueError, "English or Latin-1"):
            from Quotation_KEKOREA.agent.renderers import document_lines
            document_lines(data)


if __name__ == "__main__":
    unittest.main()
