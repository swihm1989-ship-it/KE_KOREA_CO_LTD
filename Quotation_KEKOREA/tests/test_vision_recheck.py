"""Synthetic-only verification of conditional OCR/Vision second-pass handling.

These tests make NO live API calls and never send mail or approve documents.
"""
import json
import unittest

import pymupdf

from Quotation_KEKOREA.agent import extractor
from Quotation_KEKOREA.agent.vision_recheck import (
    _same, recheck_reasons, MAX_IMAGES,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.body, ensure_ascii=False).encode("utf-8")


def result(data):
    return {"output": [{"content": [
        {"type": "output_text", "text": json.dumps(data, ensure_ascii=False)}
    ]}]}


def item(quantity="2", unit_price="5.00",
         source="00229 Suncream 2 PCS USD 5.00"):
    return {
        "product_code": "00229",
        "product_name": "Suncream",
        "capacity": None,
        "quantity": quantity,
        "unit": "PCS",
        "unit_price": unit_price,
        "source": source,
    }


def audit_item(quantity="2", unit_price="5.00"):
    return {
        "product_code": "00229",
        "product_name": "Suncream",
        "capacity": None,
        "quantity": quantity,
        "unit": "PCS",
        "unit_price": unit_price,
        "source_line_total": None,
        "package_count": None,
        "net_weight_kg": None,
        "gross_weight_kg": None,
        "volume_cbm": None,
        "source": "00229 Suncream 2 PCS USD 5.00",
    }


def first(items, **extra):
    return {"document_type": "PO", "currency": "USD",
            "items": items, "conflicts": [], "missing_fields": [], **extra}


def second(rows=None, uncertain=None, source_total=None, currency="USD"):
    return {"items": [audit_item()] if rows is None else rows,
            "uncertain": uncertain or [], "source_total": source_total,
            "currency": currency}


class VisionRecheckTests(unittest.TestCase):
    def run_extract(self, primary, audit=None, *, attachments=None):
        requests = []
        replies = [result(primary)]
        if audit is not None:
            replies.append(result(audit))

        def opener(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            if len(requests) > len(replies):
                raise AssertionError("Unexpected third AI call")
            return FakeResponse(replies[len(requests) - 1])

        outcome = extractor.extract_trade_data(
            "Make a draft PO from attached source.", images=attachments,
            requested_document_type="PO",
            env={"OPENAI_API_KEY": "synthetic", "OPENAI_MODEL": "synthetic-model"},
            opener=opener)
        return outcome, requests

    def test_clean_attached_image_uses_only_first_pass(self):
        out, requests = self.run_extract(
            first([item()]),
            attachments=[{"mime_type": "image/png", "name": "clean.png", "data": b"fake-image"}])
        self.assertEqual(len(requests), 1)
        self.assertEqual(out["items"][0]["unit_price"], "5.00")
        self.assertEqual(out["conflicts"], [])

    def test_text_only_request_never_calls_vision_even_if_missing_price(self):
        out, requests = self.run_extract(first([item(unit_price=None)]))
        self.assertEqual(len(requests), 1)
        self.assertIsNone(out["items"][0]["unit_price"])

    def test_mismatched_price_is_2nd_read_and_human_review_not_auto_correct(self):
        out, requests = self.run_extract(
            first([item(unit_price="50.00")]), second([audit_item(unit_price="5.00")]),
            attachments=[{"mime_type": "image/jpeg", "name": "blurry.jpg", "data": b"jpeg"}])
        self.assertEqual(len(requests), 2)
        self.assertEqual(out["items"][0]["unit_price"], "50.00")
        self.assertTrue(any("단가" in x and "5.00" in x for x in out["conflicts"]))
        image_blocks = requests[1]["input"][0]["content"]
        self.assertTrue(any(x["type"] == "input_image" for x in image_blocks))
        self.assertEqual(requests[1]["text"]["format"]["name"], "vision_trade_audit")
        self.assertNotIn("50.00", requests[1]["instructions"])
        self.assertNotIn("50.00", image_blocks[0]["text"])

    def test_missing_first_source_with_agreeing_secondary_is_not_overwritten(self):
        out, requests = self.run_extract(
            first([item(source=None)]), second([audit_item()]),
            attachments=[{"mime_type": "image/png", "name": "order.png", "data": b"png"}])
        self.assertEqual(len(requests), 2)
        self.assertEqual(out["conflicts"], [])
        self.assertIsNone(out["items"][0]["source"])

    def test_vision_unreadable_remains_manual_review(self):
        out, requests = self.run_extract(
            first([item(quantity=None)]),
            second([audit_item(quantity=None)], uncertain=["row 1 quantity unreadable"]),
            attachments=[{"mime_type": "image/png", "name": "unclear.png", "data": b"image"}])
        self.assertEqual(len(requests), 2)
        self.assertIsNone(out["items"][0]["quantity"])
        self.assertTrue(any("읽기 어려운" in text for text in out["conflicts"]))

    def test_vision_api_invalid_response_does_not_lose_original_candidate(self):
        out, requests = self.run_extract(
            first([item(quantity=None)]),
            {},
            attachments=[{"mime_type": "image/png", "name": "order.png", "data": b"png"}])
        self.assertEqual(len(requests), 2)
        self.assertTrue(any("Vision 2차 확인을 완료하지" in x for x in out["conflicts"]))
        self.assertEqual(out["items"][0]["unit_price"], "5.00")

    def test_independent_second_pass_counts_potential_missing_item(self):
        other = dict(audit_item())
        other["product_code"] = "SKU-002"
        other["product_name"] = "Keyboard"
        out, _ = self.run_extract(
            first([item(source=None)]), second([audit_item(), other]),
            attachments=[{"mime_type": "image/png", "name": "order.png", "data": b"image"}])
        self.assertEqual(len(out["items"]), 1)
        self.assertTrue(any("1차 1품목 / 2차 2품목" in x for x in out["conflicts"]))

    def test_printed_total_mismatch_remains_blocking_after_agreement(self):
        primary = first([dict(item(), source_line_total="10.00")],
                        source_total="9.00")
        self.assertIn("invoice_total_inconsistent", recheck_reasons(primary))
        out, requests = self.run_extract(
            primary, second([dict(audit_item(), source_line_total="10.00")],
                            source_total="9.00"),
            attachments=[{"mime_type": "image/png", "name": "invoice.png", "data": b"image"}])
        self.assertEqual(len(requests), 2)
        self.assertTrue(any("전체 합계" in x for x in out["conflicts"]))

    def test_pl_missing_prices_does_not_trigger_extra_vision(self):
        draft = first([item(unit_price=None)])
        draft["document_type"] = "PL"
        self.assertEqual(recheck_reasons(draft), [])

    def test_numeric_and_unit_normalization_does_not_raise_false_discrepancy(self):
        self.assertTrue(_same("5.00", "5", "unit_price"))
        self.assertTrue(_same("1,000", "1000.0", "quantity"))
        self.assertTrue(_same("PCS", "EA", "unit"))
        self.assertFalse(_same("00229", "229", "product_code"))

    def test_pdf_source_rerendered_to_original_page_pixels(self):
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((75, 100), "00229 Suncream Qty 2 Unit Price USD 5.00")
        pdf_bytes = pdf.tobytes()
        pdf.close()
        out, requests = self.run_extract(
            first([item(unit_price=None)]), second([audit_item()]),
            attachments=[{"mime_type": "application/pdf", "name": "order.pdf",
                          "data": pdf_bytes}])
        self.assertEqual(len(requests), 2)
        first_blocks = requests[0]["input"][0]["content"]
        self.assertTrue(any(x["type"] == "input_file" for x in first_blocks))
        second_blocks = requests[1]["input"][0]["content"]
        images = [x for x in second_blocks if x["type"] == "input_image"]
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(any("단가" in x for x in out["conflicts"]))

    def test_partial_image_limit_reports_manual_review(self):
        pdf = pymupdf.open()
        for i in range(MAX_IMAGES + 1):
            page = pdf.new_page()
            page.insert_text((75, 100), f"Page {i + 1} Item Qty 10")
        data = pdf.tobytes()
        pdf.close()
        out, requests = self.run_extract(
            first([item(quantity=None)]), second([audit_item()]),
            attachments=[{"mime_type": "application/pdf", "name": "multi.pdf", "data": data}])
        self.assertEqual(len(requests), 2)
        self.assertTrue(any("일부 페이지만" in s for s in out["conflicts"]))
        blocks = requests[1]["input"][0]["content"]
        self.assertEqual(len([x for x in blocks if x["type"] == "input_image"]), MAX_IMAGES)


if __name__ == "__main__":
    unittest.main()
