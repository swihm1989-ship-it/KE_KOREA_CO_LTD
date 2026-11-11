"""Non-final document download tests. Existing branded trade PDF policy remains intact."""
import copy
import io
import unittest
import zipfile
from Quotation_KEKOREA.orchestration.workflows.draft_files import create_review_files


def trade_fixture():
    return {
        "document_type": "PI", "product_family": "solar_cell", "currency": "USD",
        "document_number": "DRAFT", "seller": {"legal_name": "KE KOREA CO. LTD", "address": "Example Street"},
        "buyer": {"legal_name": "Demo Buyer LLC", "address": "Example Street"},
        "incoterms": "EXW Seoul", "payment_terms": "T/T",
        "items": [{"product_name": "M10 test cell", "quantity": "100", "unit": "PCS",
                   "unit_price": "0.20", "price_basis": "PCS", "price_source": "demo"}]
    }


class DraftFileTests(unittest.TestCase):
    def test_trade_produces_only_unbranded_draft_docx_using_verified_calculations(self):
        from docx import Document
        data = trade_fixture()
        before = copy.deepcopy(data)
        result = create_review_files("PI", data)
        self.assertEqual(data, before)
        self.assertEqual(set(result), {"docx"})
        asset = result["docx"]
        self.assertEqual(asset["mime"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertTrue(asset["content"].startswith(b"PK"))
        doc = Document(io.BytesIO(asset["content"]))
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("DRAFT", text)
        self.assertIn("20.00", text)
        self.assertIn("M10 test cell", "\\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells))
        self.assertNotIn("AUTHORIZED REPRESENTATIVE", text)
        self.assertEqual(len(asset["sha256"]), 64)

    def test_trade_does_not_create_file_with_unresolved_blockers(self):
        with self.assertRaises(ValueError):
            create_review_files("PO", {"document_type": "PO", "items": []})

    def test_trade_kind_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            create_review_files("CI", trade_fixture())

    def test_existing_contract_draft_export_produces_pdf_and_docx(self):
        from Quotation_KEKOREA.contracts.models import new_snapshot
        source = new_snapshot("sample", "sale", "en")
        source["title"] = "Demo Contract"
        source["clauses"] = [{"id": "cl1", "order": 1, "title": "Scope",
                              "sentences": [{"id": "s1", "text": "This is a demo clause."}]}]
        before = copy.deepcopy(source)
        result = create_review_files("CONTRACT", source)
        self.assertEqual(before, source)
        self.assertEqual(set(result), {"pdf", "docx"})
        self.assertTrue(result["pdf"]["content"].startswith(b"%PDF"))
        self.assertTrue(result["docx"]["content"].startswith(b"PK"))
        self.assertIn("DRAFT", result["pdf"]["filename"].upper())
        self.assertEqual(len(result["pdf"]["sha256"]), 64)

    def test_empty_contract_does_not_export_blank_file(self):
        from Quotation_KEKOREA.contracts.models import new_snapshot
        with self.assertRaises(ValueError):
            create_review_files("CONTRACT", new_snapshot("sample", "sale", "ko"))

    def test_no_final_artifact_or_sending_flags(self):
        result = create_review_files("PI", trade_fixture())
        for asset in result.values():
            self.assertFalse(asset["final"])
            self.assertFalse(asset["sendable"])
            self.assertTrue(asset["filename"].endswith("-DRAFT.docx"))


if __name__ == "__main__":
    unittest.main()
