"""Synthetic source-mapping tests. No real company prices are committed."""
import importlib.util
import json
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_eclado_seed.py"


def main_row(code="A01", name="Example Toner", capacity="100ml", purchase=1000, sale=10):
    row = [None] * 19
    row[1:4] = [code, name, capacity]
    row[13] = purchase
    row[15] = sale
    row[16] = sale * .9 if sale is not None else None
    return row


def buyer_row(source):
    row = source[:16]
    row[13] = source[15]
    row[14] = source[16]
    return row


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE_PATH.exists(), "Read-only ECLADO importer is not implemented")
        spec = importlib.util.spec_from_file_location("eclado_import", MODULE_PATH)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def catalog(self, rows=None, samples=None, sample_sales=None):
        rows = rows if rows is not None else [main_row()]
        return self.module.build_catalog(rows, [buyer_row(r) for r in rows],
                                         samples or [], sample_sales or [])

    def test_shared_code_does_not_merge_different_products(self):
        catalog = self.catalog([main_row("73568", "Example Toner", "500ml"),
                                main_row("73568", "Example Cream", "50g")])
        self.assertEqual(len(catalog["products"]), 2)
        self.assertEqual(len({p["id"] for p in catalog["products"]}), 2)
        self.assertIn("duplicate_code", {i["type"] for i in catalog["issues"]})

    def test_sample_currency_and_unknown_capacity(self):
        catalog = self.catalog(samples=[["S1", "Example Toner", 100]],
                               sample_sales=[["S1", "Example Toner", 150]])
        sample = next(p for p in catalog["products"] if p["kind"] == "sample")
        self.assertIsNone(sample["capacity"])
        sales = next(p for p in catalog["buyer_prices"] if p["product_id"] == sample["id"])
        self.assertEqual(sales["currency"], "KRW")
        self.assertEqual(sales["unit_price"], "150")
        self.assertIsNone(sales["reference_discount_percent"])

    def test_discount_uses_base_price_without_float_noise(self):
        price = self.catalog([main_row(sale=8.3)])["buyer_prices"][0]
        self.assertEqual(price["unit_price"], "8.3")
        self.assertEqual(price["reference_discounted_price"], "7.47")
        self.assertEqual(price["reference_discount_percent"], "10")

    def test_missing_purchase_price_fails(self):
        with self.assertRaisesRegex(ValueError, "purchase price"):
            self.catalog([main_row(purchase=None)])

    def test_missing_sale_price_fails(self):
        with self.assertRaisesRegex(ValueError, "sale price"):
            self.catalog([main_row(sale=None)])

    def test_source_identity_mismatch_fails(self):
        purchase = main_row()
        other = buyer_row(main_row(name="Different Item"))
        with self.assertRaisesRegex(ValueError, "identity"):
            self.module.build_catalog([purchase], [other], [], [])

    def test_source_sale_price_mismatch_fails(self):
        purchase = main_row()
        other = buyer_row(purchase)
        other[13] = 12
        with self.assertRaisesRegex(ValueError, "sale price mismatch"):
            self.module.build_catalog([purchase], [other], [], [])

    def test_exact_duplicate_product_fails(self):
        with self.assertRaisesRegex(ValueError, "Duplicate product identity"):
            self.catalog([main_row(), main_row()])

    def test_wrong_reference_discount_fails(self):
        purchase = main_row()
        other = buyer_row(purchase)
        other[14] = 1
        with self.assertRaisesRegex(ValueError, "discount"):
            self.module.build_catalog([purchase], [other], [], [])

    def test_missing_capacity_is_not_invented(self):
        product = self.catalog([main_row(capacity=None)])["products"][0]
        self.assertIsNone(product["capacity"])

    def test_seed_json_round_trip_preserves_apostrophes(self):
        catalog = self.catalog([main_row(name="Maker's Toner")])
        sources = [{"file_name": "source.xlsx", "sha256": "a" * 64}]
        sql, report = self.module.make_seed(catalog, sources)
        payload = sql.split("$kekorea_seed$", 2)[1]
        data = json.loads(payload)
        self.assertEqual(data["products"][0]["item_name"], "Maker's Toner")
        self.assertEqual(report["counts"]["products"], 1)
        self.assertTrue(sql.startswith("-- Confidential"))
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertEqual(self.module.make_seed(catalog, sources)[1]["import_id"], report["import_id"])

    def test_changed_payload_is_detectable_for_same_source_manifest(self):
        sources = [{"file_name": "source.xlsx", "sha256": "a" * 64}]
        _, original = self.module.make_seed(self.catalog(), sources)
        _, changed = self.module.make_seed(self.catalog([main_row(purchase=2000)]), sources)
        self.assertIn("payload_sha256", original, "A source manifest alone cannot detect extraction corrections")
        self.assertEqual(original["import_id"], changed["import_id"])
        self.assertNotEqual(original["payload_sha256"], changed["payload_sha256"])

    def test_purchase_header_cannot_silently_label_usd_as_krw(self):
        self.assertTrue(hasattr(self.module, "validate_price_header"), "Currency header guard is missing")
        with self.assertRaisesRegex(ValueError, "currency"):
            self.module.validate_price_header("UNIT Price (USD)", "purchase")
        self.assertEqual(self.module.validate_price_header("UNIT Price (\\)", "purchase"), "KRW")

    def test_truncated_snapshot_is_rejected_before_export(self):
        self.assertTrue(hasattr(self.module, "validate_counts"), "Expected snapshot count guard is missing")
        with self.assertRaisesRegex(ValueError, "count"):
            self.module.validate_counts(self.catalog(), 131, 26)
        self.module.validate_counts(self.catalog(), 1, 0)


if __name__ == "__main__":
    unittest.main()
