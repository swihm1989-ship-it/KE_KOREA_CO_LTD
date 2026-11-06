import unittest
from io import BytesIO

import fitz
from docx import Document

from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.models import new_snapshot


class ContractExportTests(unittest.TestCase):
    def snapshot(self, language):
        snapshot = new_snapshot("contract-1", "trade_commission", language)
        snapshot.update(title="Commission Agreement", revision=3)
        snapshot["parties"] = [{"legal_name": "KE KOREA", "roles": ["intermediary"]}]
        sentence = ("수수료는 실제 수령한 금액의 3%로 한다."
                    if language == "ko" else
                    "The commission is 3% of the amount actually received.")
        snapshot["clauses"] = [{"id": "c1", "title": "Commission", "order": 1,
                                "sentences": [{"id": "s1", "text": sentence,
                                               "term_ids": [], "source_refs": []}]}]
        snapshot["annotations"] = [{"instruction": "secret note"}]
        snapshot["issues"] = [{"message": "review note"}]
        return snapshot

    def test_docx_contains_current_snapshot_only(self):
        outputs = export_contract(self.snapshot("en"), formats=("docx",))
        document = Document(BytesIO(outputs["docx"]["content"]))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("3% of the amount actually received", text)
        self.assertNotIn("secret note", text)
        self.assertNotIn("review note", text)
        self.assertIn("-r3.docx", outputs["docx"]["filename"])

    def test_korean_pdf_renders_unicode_text_and_signature_page(self):
        outputs = export_contract(self.snapshot("ko"), formats=("pdf",))
        pdf = fitz.open(stream=outputs["pdf"]["content"], filetype="pdf")
        text = "\n".join(page.get_text() for page in pdf)
        self.assertIn("수수료는 실제 수령한 금액의 3%로 한다.", text)
        self.assertIn("서명", text)
        self.assertNotIn("secret note", text)


if __name__ == "__main__":
    unittest.main()
