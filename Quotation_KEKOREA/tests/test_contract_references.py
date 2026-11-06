import unittest
from io import BytesIO

import fitz
from docx import Document

from Quotation_KEKOREA.contracts.references import (
    candidate_clauses, extract_reference,
)


class ContractReferenceTests(unittest.TestCase):
    def test_text_pdf_has_page_source_locations_and_hash(self):
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Payment: Buyer shall pay each invoice within 15 days.")
        data = document.tobytes()
        result = extract_reference(data, "example.pdf")
        self.assertEqual(result["extraction_status"], "extracted")
        self.assertIn("[page 1]", result["extracted_text"])
        self.assertEqual(len(result["content_hash"]), 64)

    def test_docx_preserves_paragraph_locations(self):
        document = Document()
        document.add_paragraph("Commission is 3 percent of funds actually received.")
        output = BytesIO()
        document.save(output)
        result = extract_reference(output.getvalue(), "example.docx")
        self.assertEqual(result["source_locations"][0]["locator"], "paragraph 1")
        self.assertEqual(len(candidate_clauses(result)), 1)

    def test_encrypted_or_unsupported_documents_are_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, 'HWP5'):
            extract_reference(b'not a compound document', 'example.hwp')
        with self.assertRaisesRegex(ValueError, "PDF or DOCX"):
            extract_reference(b"anything", "example.doc")
        with self.assertRaisesRegex(ValueError, "damaged"):
            extract_reference(b"not a pdf", "example.pdf")

    def test_scan_pages_are_flagged_without_external_ocr_consent(self):
        document = fitz.open()
        document.new_page()
        result = extract_reference(document.tobytes(), "scan.pdf")
        self.assertEqual(result["extraction_status"], "scanned_requires_ocr")
        self.assertEqual(result["scanned_pages"], [1])


if __name__ == "__main__":
    unittest.main()
