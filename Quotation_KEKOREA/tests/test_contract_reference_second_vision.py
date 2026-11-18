"""Synthetic scanned-reference Vision recheck; no real API or contract storage."""
import unittest

import pymupdf

from Quotation_KEKOREA.contracts.references import extract_reference


def scanned_pdf():
    document = pymupdf.open()
    document.new_page()
    payload = document.tobytes()
    document.close()
    return payload


class ScannedContractVisionRecheckTests(unittest.TestCase):
    def test_uncertain_first_vision_gets_exactly_one_more_read(self):
        reads = []
        def vision(image, page):
            reads.append((image, page))
            return (
                "The commission shall be [unclear].\n[Needs manual review: unclear]"
                if len(reads) == 1 else
                "The commission shall be 3 percent."
            )
        result = extract_reference(scanned_pdf(), "synthetic.pdf", vision_client=vision)
        self.assertEqual(len(reads), 2)
        self.assertEqual(reads[0][0], reads[1][0])
        self.assertEqual(result["extraction_status"], "partial")
        self.assertEqual(result["uncertain_pages"], [1])
        self.assertIn("independent Vision reads disagree", result["extracted_text"])

    def test_first_empty_second_read_keeps_manual_confirmation(self):
        calls = []
        def vision(image, page):
            calls.append(page)
            return "" if len(calls) == 1 else "Sample supply contract."
        result = extract_reference(scanned_pdf(), "synthetic.pdf", vision_client=vision)
        self.assertEqual(calls, [1, 1])
        self.assertEqual(result["extraction_status"], "partial")
        self.assertIn("Sample supply contract.", result["extracted_text"])
        self.assertIn("only the second Vision read found text", result["extracted_text"])

    def test_first_clear_scan_uses_one_vision_call_only(self):
        calls = []
        def vision(image, page):
            calls.append(page)
            return "Sample contract term: price to be agreed in writing."
        result = extract_reference(scanned_pdf(), "synthetic.pdf", vision_client=vision)
        self.assertEqual(calls, [1])
        self.assertEqual(result["extraction_status"], "extracted")

    def test_second_vision_failure_keeps_original_and_manual_status(self):
        count = [0]
        def vision(image, page):
            count[0] += 1
            if count[0] == 2:
                raise RuntimeError("synthetic timeout")
            return "Sample [Needs manual review: unclear]"
        result = extract_reference(scanned_pdf(), "synthetic.pdf", vision_client=vision)
        self.assertEqual(count[0], 2)
        self.assertEqual(result["extraction_status"], "partial")
        self.assertIn("Needs manual review", result["extracted_text"])

    def test_no_consent_never_calls_vision(self):
        result = extract_reference(scanned_pdf(), "synthetic.pdf", vision_client=None)
        self.assertEqual(result["extraction_status"], "scanned_requires_ocr")


if __name__ == "__main__":
    unittest.main()
