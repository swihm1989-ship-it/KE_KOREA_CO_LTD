"""Explicit final rendering with synthetic brand assets and extracted PDF text."""
from copy import deepcopy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree
import zipfile
import zlib

import pymupdf as fitz

from Quotation_KEKOREA.agent.pi_pdf import render_charcoal_gold_pi, render_trade_document
from Quotation_KEKOREA.agent.renderers import document_lines, render_files


def _synthetic_png(path, width, height, color):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload)))

    scanlines = (b"\x00" + bytes(color) * width) * height
    path.write_bytes(b"\x89PNG\r\n\x1a\n" +
                     chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def _trade(document_type="PI", item_count=1):
    return {
        "document_type": document_type, "status": "DRAFT_READY_FOR_REVIEW",
        "document_number": f"{document_type}-2026-001", "issue_date": "2026-01-01",
        "product_family": "cosmetics", "currency": "USD", "total": str(item_count * 10),
        "seller": {"legal_name": "KE KOREA CO. LTD", "address": "1 Test Road",
                   "contact": "Test Seller", "phone": "N/A", "email": "N/A"},
        "buyer": {"legal_name": "Example Buyer Ltd", "address": "2 Test Road",
                  "contact": "Test Buyer", "phone": "N/A", "email": "N/A"},
        "ship_to": "Example Warehouse", "incoterms": "FOB Busan",
        "payment_terms": "T/T in advance", "country_of_origin": "Republic of Korea",
        "shipment_reference": "N/A",
        "remarks": "Synthetic transaction for rendering tests.", "blocking_issues": [],
        "container_count": "1", "actual_package_count": str(item_count), "hs_code": "3304.99",
        "items": [{"product_name": f"Product-{index:02}", "capacity": "100 ml",
                   "quantity": "10", "unit": "PCS", "final_unit_price": "1",
                   "discount_percent": "0", "line_total": "10", "package_count": "1",
                   "package_type": "CTN", "net_weight_kg": "1", "gross_weight_kg": "2",
                   "volume_cbm": "0.01", "hs_code": "3304.99"}
                  for index in range(item_count)],
    }


def _incomplete_trade(document_type="PI"):
    doc = _trade(document_type)
    for key in ("document_number", "currency", "ship_to", "incoterms", "payment_terms",
                "country_of_origin", "shipment_reference", "remarks", "container_count",
                "actual_package_count", "hs_code", "total"):
        doc[key] = None
    doc["seller"] = {}
    doc["buyer"] = {}
    item = doc["items"][0]
    for key in ("capacity", "quantity", "display_quantity", "paid_quantity", "shipped_quantity",
                "free_quantity", "unit", "unit_price", "final_unit_price", "line_total",
                "discount_percent", "package_type", "package_count", "net_weight_kg",
                "gross_weight_kg", "volume_cbm", "hs_code"):
        item[key] = None
    return doc


def _workbook_rows(path):
    with zipfile.ZipFile(path) as workbook:
        root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [["".join(cell.itertext()) for cell in row.findall("s:c", ns)]
            for row in root.findall("s:sheetData/s:row", ns)]


class TradeFinalRenderingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.logo = self.root / "synthetic-logo.png"
        self.seal = self.root / "synthetic-seal.png"
        # Match the original logo crop bounds; never use production brand assets.
        _synthetic_png(self.logo, 1480, 765, (20, 70, 130))
        _synthetic_png(self.seal, 60, 30, (180, 20, 20))
        self.bank = {key: f"TEST_{key}" for key in (
            "BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")}

    def render_pdf(self, doc, **kwargs):
        return render_trade_document(doc, self.bank, logo_path=self.logo,
                                     seal_path=self.seal, **kwargs)

    def test_final_files_use_final_names_status_and_document_headers_for_every_trade_type(self):
        for dtype in ("PI", "PO", "CI", "PL"):
            with self.subTest(document_type=dtype):
                doc = _trade(dtype)
                original = deepcopy(doc)
                paths = render_files(doc, self.root / dtype, bank_details=self.bank,
                                     logo_path=self.logo, seal_path=self.seal, final=True)
                for path in paths.values():
                    self.assertIn("_FINAL_", path.name)
                    self.assertNotIn("DRAFT", path.name)
                html = paths["html"].read_text(encoding="utf-8")
                self.assertIn("<title>Trade Document Final</title>", html)
                self.assertIn("<h2>FINAL</h2>", html)
                self.assertNotIn("DRAFT", html.upper())
                self.assertNotIn("NOT FOR ISSUE", html)
                with zipfile.ZipFile(paths["xlsx"]) as workbook:
                    sheet = workbook.read("xl/worksheets/sheet1.xml").decode()
                    self.assertIn(">FINAL</t>", sheet)
                    self.assertNotIn("DRAFT", sheet)
                    self.assertNotIn("Draft", workbook.read("xl/workbook.xml").decode())
                with fitz.open(paths["pdf"]) as pdf:
                    text = "\n".join(page.get_text() for page in pdf)
                    self.assertIn("FINAL  |  PAGE 1 OF", text)
                    self.assertNotIn("DRAFT", text)
                    self.assertNotIn("NOT FOR ISSUE", text)
                self.assertEqual(doc, original)

    def test_document_lines_require_explicit_final_flag(self):
        doc = _trade()
        doc["status"] = "FINAL"
        self.assertIn("DRAFT", document_lines(doc, self.bank)[0])
        lines = document_lines(doc, self.bank, final=True)
        self.assertEqual(lines[0], "FINAL")
        self.assertIn("KE KOREA CO. LTD", lines)
        self.assertNotIn("DRAFT", "\n".join(lines))

    def test_final_pdf_leaves_unknown_fields_blank_in_original_trade_layouts(self):
        for dtype in ("PI", "PO", "CI", "PL"):
            with self.subTest(document_type=dtype):
                doc = _incomplete_trade(dtype)
                original = deepcopy(doc)
                data = render_trade_document(doc, {}, logo_path=self.logo,
                                             seal_path=self.seal, final=True)
                with fitz.open(stream=data, filetype="pdf") as pdf:
                    text = "\n".join(page.get_text() for page in pdf)
                    self.assertIn("Product-00", text)
                    self.assertIn("FINAL  |  PAGE 1 OF", text)
                    self.assertIn("SELLER / SUPPLIER", text)
                    self.assertIn("BUYER / CUSTOMER", text)
                    self.assertIn("AUTHORIZED REPRESENTATIVE", text)
                    self.assertEqual(len(pdf[-1].get_images()), 2)
                    for placeholder in ("TBD", "TO CONFIRM", "TO BE CONFIRMED", "Not provided",
                                        "N/A", "BANK DETAIL REQUIRED", "$0.00", "0 PCS"):
                        self.assertNotIn(placeholder, text)
                    summary = next(line for line in text.splitlines()
                                   if line.startswith("TOTAL QUANTITY:"))
                    self.assertEqual(summary.strip(), "TOTAL QUANTITY:")
                self.assertEqual(doc, original)

    def test_final_files_accept_none_totals_and_leave_unknown_cells_blank(self):
        for dtype in ("PI", "PO", "CI", "PL"):
            with self.subTest(document_type=dtype):
                doc = _incomplete_trade(dtype)
                paths = render_files(doc, self.root / (dtype + "-incomplete"), bank_details={},
                                     logo_path=self.logo, seal_path=self.seal, final=True)
                html = paths["html"].read_text(encoding="utf-8")
                rows = _workbook_rows(paths["xlsx"])
                for output in (html, str(rows)):
                    self.assertIn("Product-00", output)
                    for placeholder in ("TBD", "TO CONFIRM", "TO BE CONFIRMED", "Not provided",
                                        "N/A", "BANK DETAIL REQUIRED", "REVIEW REQUIRED", "$0.00"):
                        self.assertNotIn(placeholder, output)
                if dtype != "PL":
                    self.assertIn("TOTAL: \nAMOUNT IN WORDS: ", html)
                    self.assertEqual(next(row for row in rows if "TOTAL" in row), ["TOTAL"])

    def test_final_zero_quantity_and_amount_remain_explicit_zero(self):
        for zero in (0, "0"):
            with self.subTest(zero=zero):
                doc = _trade()
                doc["total"] = zero
                doc["items"][0].update({
                    "quantity": zero, "display_quantity": zero, "paid_quantity": zero,
                    "shipped_quantity": zero, "free_quantity": zero,
                    "final_unit_price": "1.25", "line_total": zero, "discount_percent": zero,
                })
                paths = render_files(doc, self.root / f"zero-{type(zero).__name__}",
                                     bank_details=self.bank, logo_path=self.logo,
                                     seal_path=self.seal, final=True)
                with fitz.open(paths["pdf"]) as pdf:
                    text = "\n".join(page.get_text() for page in pdf)
                    self.assertIn("0 PCS", text)
                    self.assertIn("TOTAL QUANTITY: 0 PCS", text)
                    self.assertIn("$0.00", text)
                    self.assertNotIn("- PCS", text)
                item_row = next(row for row in _workbook_rows(paths["xlsx"]) if "Product-00" in row)
                self.assertEqual(item_row, ["1", "Product-00", "100 ml", "0", "PCS", "$1.25", "0%", "$0.00"])

    def test_final_unknown_derived_values_do_not_restore_stale_source_numbers(self):
        doc = _trade()
        doc["total"] = None
        doc["items"][0].update({
            "quantity": "98765", "unit_price": "43210", "display_quantity": None,
            "paid_quantity": None, "shipped_quantity": None, "free_quantity": None,
            "final_unit_price": None, "line_total": None, "discount_percent": None,
        })
        paths = render_files(doc, self.root / "unknown-derived", bank_details=self.bank,
                             logo_path=self.logo, seal_path=self.seal, final=True)
        with fitz.open(paths["pdf"]) as pdf:
            pdf_text = "\n".join(page.get_text() for page in pdf)
        for output in (pdf_text, paths["html"].read_text(encoding="utf-8"), str(_workbook_rows(paths["xlsx"]))):
            self.assertNotIn("98,765", output)
            self.assertNotIn("98765", output)
            self.assertNotIn("43,210", output)
            self.assertNotIn("43210", output)
            self.assertNotIn("$0.00", output)
        self.assertIn("PCS", pdf_text)
        self.assertIn("TOTAL QUANTITY:\n", pdf_text)

    def test_final_quantity_summary_does_not_report_a_partial_sum(self):
        doc = _trade(item_count=2)
        doc["items"][1].update({"quantity": None, "display_quantity": None,
                                "paid_quantity": None, "shipped_quantity": None})
        with fitz.open(stream=self.render_pdf(doc, final=True), filetype="pdf") as pdf:
            summary = next(line for page in pdf for line in page.get_text().splitlines()
                           if line.startswith("TOTAL QUANTITY:"))
        self.assertEqual(summary.strip(), "TOTAL QUANTITY:")

    def test_final_packing_totals_override_is_authoritative_even_when_unknown(self):
        doc = _trade("PL")
        doc.update({"actual_package_count": "4567", "declared_net_weight_kg": "5678",
                    "declared_gross_weight_kg": "6789", "declared_volume_cbm": "7890"})
        doc["_final_packing_totals"] = {
            "package_count": None, "net_weight_kg": None, "gross_weight_kg": None,
            "volume_cbm": None, "quantities": None,
        }
        paths = render_files(doc, self.root / "packing-unknown", bank_details=self.bank,
                             logo_path=self.logo, seal_path=self.seal, final=True)
        with fitz.open(paths["pdf"]) as pdf:
            text = "\n".join(page.get_text() for page in pdf)
        self.assertNotIn("TOTAL PACKAGES: 1", text)
        self.assertIn("NET WEIGHT:  KG  |  GROSS WEIGHT:  KG", text)
        self.assertIn("TOTAL VOLUME:  CBM", text)
        self.assertIn("TOTAL QUANTITY:\n", text)
        rows = _workbook_rows(paths["xlsx"])
        for label in ("Total packages", "Total net weight (kg)", "Total gross weight (kg)",
                      "Total volume (CBM)"):
            self.assertEqual(next(row for row in rows if row and row[0] == label), [label])
        for output in (text, paths["html"].read_text(encoding="utf-8"), str(rows)):
            for stale in ("4567", "5678", "6789", "7890"):
                self.assertNotIn(stale, output)

    def test_packing_totals_override_preserves_known_zero_and_is_ignored_for_drafts(self):
        doc = _trade("PL")
        original_draft = self.render_pdf(doc)
        doc["_final_packing_totals"] = {
            "package_count": 0, "net_weight_kg": "0", "gross_weight_kg": 0,
            "volume_cbm": "0", "quantities": {"PCS": "0", "KG": "2.5"},
        }
        self.assertEqual(self.render_pdf(doc), original_draft)
        with fitz.open(stream=self.render_pdf(doc, final=True), filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
        self.assertIn("TOTAL PACKAGES: 0", text)
        self.assertIn("NET WEIGHT: 0 KG  |  GROSS WEIGHT: 0 KG", text)
        self.assertIn("TOTAL VOLUME: 0 CBM", text)
        self.assertIn("TOTAL QUANTITY: 0 PCS | 2.5 KG", text)

    def test_final_pdf_keeps_products_and_entire_bank_seal_group_on_original_pages(self):
        doc = _trade(item_count=20)
        with fitz.open(stream=self.render_pdf(doc, final=True), filetype="pdf") as pdf:
            self.assertEqual(len(pdf), 2)
            texts = [page.get_text() for page in pdf]
            self.assertIn("Product-19", texts[0])
            self.assertNotIn("Product-19", texts[1])
            self.assertNotIn("PRODUCT & PRICING", texts[1])
            for label in ("BENEFICIARY", "BANK NAME", "BRANCH NAME", "SWIFT CODE",
                          "ACCOUNT NUMBER", "BANK ADDRESS", "AUTHORIZED REPRESENTATIVE"):
                self.assertNotIn(label, texts[0])
                self.assertIn(label, texts[1])
            for value in self.bank.values():
                self.assertIn(value, texts[1])
            self.assertEqual([len(page.get_images()) for page in pdf], [1, 2])
            for index, text in enumerate(texts, 1):
                self.assertIn(f"FINAL  |  PAGE {index} OF 2", text)
                self.assertNotIn("DRAFT", text)
                self.assertNotIn("NOT FOR ISSUE", text)

    def test_default_multipage_pdf_and_explicit_false_are_identical_even_for_final_candidate(self):
        doc = _trade(item_count=20)
        doc["status"] = "FINAL"
        default = self.render_pdf(doc)
        self.assertEqual(default, self.render_pdf(doc, final=False))
        with fitz.open(stream=default, filetype="pdf") as pdf:
            self.assertEqual(len(pdf), 2)
            for index, page in enumerate(pdf, 1):
                self.assertIn(f"DRAFT - NOT FOR ISSUE  |  PAGE {index} OF 2", page.get_text())

    def test_final_changes_only_pdf_footer_and_preserves_layout_and_assets(self):
        doc = _trade(item_count=20)
        with (fitz.open(stream=self.render_pdf(doc), filetype="pdf") as draft,
              fitz.open(stream=self.render_pdf(doc, final=True), filetype="pdf") as final):
            self.assertEqual(len(draft), len(final))
            for draft_page, final_page in zip(draft, final):
                draft_body = [word for word in draft_page.get_text("words") if word[1] < 778]
                final_body = [word for word in final_page.get_text("words") if word[1] < 778]
                self.assertEqual(draft_body, final_body)
                self.assertEqual(draft_page.get_drawings(), final_page.get_drawings())
                self.assertEqual(draft_page.get_image_info(hashes=True), final_page.get_image_info(hashes=True))

    def test_default_files_and_legacy_pi_alias_remain_draft(self):
        doc = _trade()
        paths = render_files(doc, self.root / "default", bank_details=self.bank,
                             logo_path=self.logo, seal_path=self.seal)
        for path in paths.values():
            self.assertIn("_DRAFT_", path.name)
        html = paths["html"].read_text(encoding="utf-8")
        self.assertIn("<title>Trade Document Draft</title>", html)
        self.assertIn("<h2>DRAFT_READY_FOR_REVIEW</h2>", html)
        self.assertIn("KE KOREA CO. LTD - REVIEW DRAFT", html)
        doc["status"] = "FINAL"
        paths = render_files(doc, self.root / "candidate-final", bank_details=self.bank,
                             logo_path=self.logo, seal_path=self.seal)
        self.assertIn("<h2>DRAFT</h2>", paths["html"].read_text(encoding="utf-8"))
        alias_pdf = render_charcoal_gold_pi(doc, self.bank, logo_path=self.logo, seal_path=self.seal)
        with fitz.open(stream=alias_pdf, filetype="pdf") as pdf:
            self.assertIn("DRAFT - NOT FOR ISSUE", pdf[0].get_text())


if __name__ == "__main__":
    unittest.main()
