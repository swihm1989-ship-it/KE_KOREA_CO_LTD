"""Rename in saved-contract list updates both metadata and actual PDF/DOCX title."""
from copy import deepcopy
from io import BytesIO
import unittest
from unittest.mock import patch

import fitz
from docx import Document
from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.contracts.draft_exports import export_draft
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.ui import _rename_saved_contract
from Quotation_KEKOREA.tests.test_contract_workspace_ui import MemoryContracts
from Quotation_KEKOREA.contracts.models import new_snapshot


class ContractListRenameTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryContracts()
        snapshot = dict(new_snapshot("rename-example", "sale", "en"),
                        title="Old Contract Title")
        snapshot["clauses"] = [{
            "id": "scope", "title": "Scope", "order": 1,
            "sentences": [{"id": "sentence1", "text": "Goods are supplied."}],
        }]
        self.repo.create_contract({
            "title": "Old Contract Title", "contract_type": "sale", "language": "en"
        }, snapshot)
        p = patch("Quotation_KEKOREA.contracts.ui._repository", return_value=self.repo)
        p.start()
        self.addCleanup(p.stop)
        self.at = AppTest.from_string(
            "from Quotation_KEKOREA.contracts.ui import render_contract_page\n"
            "render_contract_page('계약서 만들기', {})")

    def run_app(self):
        self.at.run(timeout=20)
        self.assertFalse(self.at.exception)

    def test_rename_button_changes_saved_list_and_document_snapshot(self):
        original = deepcopy(self.repo.revisions["rename-example"][0]["snapshot"])
        self.run_app()
        self.at.button(key="contract_rename_rename-example").click()
        self.run_app()
        self.at.text_input(key="contract_rename_input_rename-example").set_value(
            "Solar Cell Supply Agreement")
        next(x for x in self.at.button if x.label == "이름 변경 저장").click()
        self.run_app()
        self.assertEqual(self.repo.records["rename-example"]["title"],
                         "Solar Cell Supply Agreement")
        self.assertEqual(self.repo.records["rename-example"]["current_revision"], 2)
        latest = self.repo.revisions["rename-example"][-1]["snapshot"]
        self.assertEqual(latest["title"], "Solar Cell Supply Agreement")
        self.assertEqual(latest["clauses"], original["clauses"])
        self.assertEqual(latest["terms"], original["terms"])
        self.assertEqual(self.repo.revisions["rename-example"][0]["snapshot"], original)
        self.assertIn("Solar Cell Supply Agreement [EN]",
                      [b.label for b in self.at.button])

    def test_cancel_does_not_rename(self):
        self.run_app()
        self.at.button(key="contract_rename_rename-example").click()
        self.run_app()
        self.at.text_input(key="contract_rename_input_rename-example").set_value("Ignored")
        next(x for x in self.at.button if x.label == "취소").click()
        self.run_app()
        self.assertEqual(self.repo.records["rename-example"]["title"], "Old Contract Title")
        self.assertEqual(self.repo.records["rename-example"]["current_revision"], 1)

    def test_empty_title_does_not_commit(self):
        with self.assertRaisesRegex(ValueError, "새 계약 제목"):
            _rename_saved_contract(self.repo, "rename-example", "  ")
        self.assertEqual(self.repo.records["rename-example"]["current_revision"], 1)

    def test_new_pdf_docx_have_updated_document_title(self):
        updated = _rename_saved_contract(self.repo, "rename-example",
                                          "Solar Cell Supply Agreement")
        for result in (export_draft(updated, formats=("docx", "pdf")),
                       export_contract(updated, formats=("docx", "pdf"))):
            doc = Document(BytesIO(result["docx"]["content"]))
            text = " ".join(p.text for p in doc.paragraphs)
            self.assertIn("Solar Cell Supply Agreement", text)
            with fitz.open(stream=result["pdf"]["content"], filetype="pdf") as pdf:
                all_text = "\n".join(page.get_text() for page in pdf)
            self.assertIn("Solar Cell Supply Agreement", all_text)


if __name__ == "__main__":
    unittest.main()
