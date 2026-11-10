"""Regression tests for sales scope presentation in draft and final exports."""
import unittest
from io import BytesIO

import fitz
from docx import Document

from Quotation_KEKOREA.contracts.draft_exports import export_draft
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.sale_scope_render import scope_display_items
from Quotation_KEKOREA.contracts.sale_scope_template import apply_sale_scope_template
from Quotation_KEKOREA.tests.test_contract_sale_scope_template import fixture


class SaleScopeExportPresentationTests(unittest.TestCase):
    def snapshot(self):
        snapshot = fixture()
        snapshot["language"] = "en"
        snapshot["title"] = "Test Solar Cell Contract"
        snapshot["terms"][0]["value"] = "Hanwha"
        snapshot["terms"][1]["value"] = "Solar Cell"
        snapshot["terms"][2]["unit"] = "pcs"
        snapshot["terms"][3]["unit"] = "pc"
        snapshot["terms"][4]["value"] = "EXW Jincheon"
        snapshot["terms"][5]["value"] = "100% TT in Advance"
        snapshot["terms"][3]["status"] = "suggested"
        return apply_sale_scope_template(snapshot)

    def test_scope_rows_display_once_with_separate_unconfirmed_notice(self):
        snap = self.snapshot()
        items = scope_display_items(snap["clauses"][0]["sentences"], "en")
        tables = [value for kind, value in items if kind == "table"]
        self.assertEqual(len(tables), 1)
        values = dict(tables[0])
        self.assertEqual(values["Brand"], "Hanwha")
        self.assertEqual(values["Price"], "USD 0.225/pc")
        paragraphs = [value for kind, value in items if kind == "paragraph"]
        self.assertTrue(any("Pending confirmation" in value and "Price" in value
                            for value in paragraphs))
        self.assertNotIn("Proposed (not agreed)", str(items))

    def test_draft_and_final_docx_have_real_specification_tables(self):
        snap = self.snapshot()
        for exported in (export_draft(snap, formats=("docx",)),
                         export_contract(snap, formats=("docx",))):
            document = Document(BytesIO(exported["docx"]["content"]))
            tables = [table for table in document.tables
                      if any("Hanwha" in cell.text for row in table.rows for cell in row.cells)]
            self.assertEqual(len(tables), 1)
            rows = {row.cells[0].text: row.cells[1].text for row in tables[0].rows}
            self.assertEqual(rows["Price"], "USD 0.225/pc")
            self.assertNotIn("Proposed (not agreed)", str(rows))
            body_text = " ".join(paragraph.text for paragraph in document.paragraphs)
            self.assertIn("Pending confirmation", body_text)

    def test_draft_and_final_pdf_include_table_values_and_pending_notice(self):
        snap = self.snapshot()
        for exported in (export_draft(snap, formats=("pdf",)),
                         export_contract(snap, formats=("pdf",))):
            with fitz.open(stream=exported["pdf"]["content"], filetype="pdf") as pdf:
                text = "\n".join(page.get_text() for page in pdf)
                self.assertIn("Hanwha", text)
                self.assertIn("0.225", text)
                self.assertIn("Pending confirmation", text)
                self.assertNotIn("Proposed (not agreed)", text)


if __name__ == "__main__":
    unittest.main()
