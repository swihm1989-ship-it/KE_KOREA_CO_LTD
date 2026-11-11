"""Regression tests for sales scope presentation in draft and final exports."""
import unittest
from io import BytesIO

import fitz
from docx import Document

from Quotation_KEKOREA.contracts.draft_exports import export_draft
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.sale_scope_render import scope_display_items, sales_scope_display_text
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

    def test_scope_rows_have_no_workflow_status_notice(self):
        snap = self.snapshot()
        items = scope_display_items(snap["clauses"][0]["sentences"], "en")
        tables = [value for kind, value in items if kind == "table"]
        self.assertEqual(len(tables), 1)
        values = dict(tables[0])
        self.assertEqual(values["Brand"], "Hanwha")
        self.assertEqual(values["Price"], "USD 0.225/pc")
        paragraphs = [value for kind, value in items if kind == "paragraph"]
        self.assertFalse(any("Pending confirmation" in value for value in paragraphs))
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
            self.assertNotIn("Pending confirmation", body_text)
            self.assertNotIn("확인 필요 (미승인 조건)", body_text)

    def test_draft_and_final_pdf_include_table_values_and_pending_notice(self):
        snap = self.snapshot()
        for exported in (export_draft(snap, formats=("pdf",)),
                         export_contract(snap, formats=("pdf",))):
            with fitz.open(stream=exported["pdf"]["content"], filetype="pdf") as pdf:
                text = "\n".join(page.get_text() for page in pdf)
                self.assertIn("Hanwha", text)
                self.assertIn("0.225", text)
                self.assertNotIn("Pending confirmation", text)
                self.assertNotIn("확인 필요 (미승인 조건)", text)
                self.assertNotIn("Proposed (not agreed)", text)

    def test_suggested_term_status_is_preserved_but_never_printed(self):
        snap = self.snapshot()
        price = next(term for term in snap["terms"] if term["key"] == "unit_price")
        self.assertEqual(price["status"], "suggested")
        sentences = snap["clauses"][0]["sentences"]
        row = next(item for item in sentences if item.get("sale_spec_field") == "unit_price")
        self.assertEqual(row["sale_spec_status"], "suggested")
        for language in ("en", "ko"):
            display = str(scope_display_items(sentences, language))
            self.assertNotIn("Pending confirmation", display)
            self.assertNotIn("확인 필요 (미승인 조건)", display)
            self.assertNotIn("제안(미확정)", display)

    def test_saved_legacy_prefix_is_hidden_but_original_is_unchanged(self):
        snap = self.snapshot()
        rows = snap["clauses"][0]["sentences"]
        row = next(item for item in rows if item.get("sale_spec_field") == "unit_price")
        original = row["text"]
        row["text"] = "Price: Proposed (not agreed): USD 0.225/pc"
        before = row["text"]
        self.assertEqual(sales_scope_display_text(row), "Price: USD 0.225/pc")
        self.assertEqual(row["text"], before)
        items = scope_display_items(rows, "en")
        self.assertEqual(dict(next(data for kind, data in items if kind == "table"))["Price"], "USD 0.225/pc")
        self.assertNotIn("Proposed (not agreed)", str(items))
        self.assertNotEqual(original, before)

    def test_saved_korean_legacy_prefix_only_hidden_in_display(self):
        row = {"id": "sample", "sale_spec_field": "products",
               "text": "제품: 제안(미확정): 태양광 셀 제안(미확정): 2,324,938 장"}
        self.assertEqual(sales_scope_display_text(row), "제품: 태양광 셀 2,324,938 장")
        self.assertIn("제안(미확정)", row["text"])
        unrelated = {"text": "상태: 제안(미확정): 별도 검토 필요"}
        self.assertEqual(sales_scope_display_text(unrelated), unrelated["text"])


if __name__ == "__main__":
    unittest.main()
