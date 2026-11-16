"""Verified catalog list prices remain visible in incomplete FINAL PI exports.

Uses synthetic assets and catalog-sourced flags, never real buyer data or seals.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz

from Quotation_KEKOREA.agent.renderers import render_files
from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi
from Quotation_KEKOREA.orchestration.workflows.trade_export_review import review_trade_document
from Quotation_KEKOREA.tests.test_trade_final_rendering import _synthetic_png, _workbook_rows


class VerifiedCatalogPricePrintingTests(unittest.TestCase):
    def test_unknown_discount_keeps_verified_list_price_but_not_unearned_total(self):
        """A known Dear Glow master price must not disappear with an unknown discount."""
        doc = complete_pi()
        doc.update(product_family="cosmetics", currency="USD")
        doc["buyer"]["legal_name"] = "DEAR GLOW PTE LTD"
        doc["items"][0].update(
            product_name="Melaser Whitening Toner", capacity="150ml",
            quantity="10", paid_quantity="10", unit="PCS", price_basis="PCS",
            unit_price="7.50", master_price=True,
            price_source="Verified ECLADO catalog; source workbook row 7",
            discount_percent=None,
        )
        report = review_trade_document("PI", doc, final=True, allow_incomplete=True)
        self.assertTrue(report["ready"], report["issues"])
        prepared = report["render_data"]
        self.assertEqual(prepared["items"][0]["unit_price"], "7.50")
        self.assertIsNone(prepared["items"][0]["final_unit_price"])
        self.assertIsNone(prepared["items"][0]["line_total"])
        self.assertIsNone(prepared["total"])

        with TemporaryDirectory() as folder:
            directory = Path(folder)
            logo, seal = directory / "synthetic-logo.png", directory / "synthetic-seal.png"
            _synthetic_png(logo, 1480, 765, (20, 70, 130))
            _synthetic_png(seal, 60, 30, (180, 20, 20))
            paths = render_files(
                prepared, directory / "output", bank_details={},
                logo_path=logo, seal_path=seal, final=True,
            )
            with fitz.open(paths["pdf"]) as pdf:
                pdf_text = "\n".join(page.get_text() for page in pdf)
            xlsx_rows = str(_workbook_rows(paths["xlsx"]))
            html = paths["html"].read_text(encoding="utf-8")
            self.assertIn("$7.50", pdf_text)
            self.assertIn("LIST", pdf_text)
            for output in (xlsx_rows, html):
                self.assertIn("$7.50 (LIST)", output)
            for output in (pdf_text, xlsx_rows, html):
                self.assertNotIn("$75.00", output)
                self.assertNotIn("$0.00", output)


if __name__ == "__main__":
    unittest.main()
