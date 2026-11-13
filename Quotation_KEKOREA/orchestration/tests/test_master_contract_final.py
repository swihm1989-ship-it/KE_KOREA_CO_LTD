"""Original KE KOREA FINAL layout parity and security regression tests.

All records and generated seal images are synthetic. No outside mail,
Supabase keys, original private seals or external model requests are used.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch
import struct
import zlib

from Quotation_KEKOREA.contracts.models import validate_snapshot
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.orchestration.workflows.master_contract_final import (
    confirm_contract_record, contract_fingerprint, contract_final_blockers,
    render_original_final,
)


def synthetic_seal():
    """Small VALID PNG for layout tests, never the actual company seal."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    header = struct.pack("!2I5B", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
            chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) +
            chunk(b"IEND", b""))


def confirmed_sale():
    from Quotation_KEKOREA.contracts.models import new_snapshot
    sample = new_snapshot("orchestration-synthetic-contract", "sale", "en")
    sample["title"] = "Synthetic Solar Cell Supply Contract"
    sample["parties"] = [
        {"roles": ["seller"], "status": "confirmed", "legal_name": "KE KOREA CO. LTD",
         "address": "Seoul, South Korea", "country": "South Korea",
         "representative": "Synthetic Signer"},
        {"roles": ["buyer"], "status": "confirmed", "legal_name": "SYNTHETIC BUYER LTD",
         "address": "Wuxi, China", "country": "China",
         "representative": "Synthetic Buyer Signer"},
    ]
    values = {
        "contract_date": "2026-11-13", "scope": "Synthetic solar cell sale",
        "governing_law": "Singapore law", "dispute_resolution": "SIAC arbitration",
        "products": "M10 synthetic solar cells", "quantity": "100",
        "unit": "PCS", "unit_price": "USD 0.20 per PCS",
        "currency": "USD", "payment_trigger": "T/T 100% in advance",
        "payment_deadline": "Before 2026-11-20",
        "delivery": "EXW synthetic Seoul warehouse",
        "inspection_claims": "Inspect within 7 days of receipt",
    }
    sample["terms"] = [
        {"key": key, "value": val, "status": "confirmed"}
        for key, val in values.items()
    ]
    sample["clauses"] = [
        {"title": "Product and Price",
         "sentences": [{"text": "The Seller shall supply 100 synthetic solar cells."}]},
        {"title": "Delivery",
         "sentences": [{"text": "Delivery is EXW synthetic Seoul warehouse."}]},
    ]
    return validate_snapshot(sample)


class MasterContractFinalParityTests(TestCase):
    def test_original_final_engine_output_parity_pdf_and_docx(self):
        import pymupdf
        from docx import Document
        candidate = confirmed_sale()
        self.assertEqual(contract_final_blockers(candidate, {}), [])
        seal = synthetic_seal()
        with patch("Quotation_KEKOREA.contracts.ui._verified_contract_seal",
                   return_value=seal) as verified:
            final = render_original_final(
                candidate, {}, principal="authorized@example.test",
                approved=True, authorized=True,
                expected_fingerprint=contract_fingerprint(candidate))
        verified.assert_called_once()
        legacy = export_contract(candidate, formats=("pdf", "docx"), seal_bytes=seal)
        self.assertEqual(set(final), {"pdf", "docx"})
        for kind, magic in (("pdf", b"%PDF"), ("docx", b"PK")):
            self.assertTrue(final[kind]["content"].startswith(magic))
        with (pymupdf.open(stream=final["pdf"]["content"], filetype="pdf") as left,
              pymupdf.open(stream=legacy["pdf"]["content"], filetype="pdf") as right):
            self.assertEqual(
                "\n".join(page.get_text() for page in left),
                "\n".join(page.get_text() for page in right),
            )
            pdftext = "\n".join(page.get_text() for page in left)
            self.assertIn("Product and Price", pdftext)
            self.assertIn("Signature", pdftext)
            self.assertEqual(len(left), len(right))
        word = Document(BytesIO(final["docx"]["content"]))
        oldword = Document(BytesIO(legacy["docx"]["content"]))
        self.assertEqual([p.text for p in word.paragraphs],
                         [p.text for p in oldword.paragraphs])
        self.assertEqual(len(word.tables), len(oldword.tables))

    def test_no_unapproved_or_uncredentialed_final_render(self):
        candidate = confirmed_sale()
        with patch("Quotation_KEKOREA.contracts.ui._verified_contract_seal") as seal:
            for params in (
                {"principal": "", "approved": True, "authorized": True},
                {"principal": "test@example.test", "approved": False, "authorized": True},
                {"principal": "test@example.test", "approved": True, "authorized": False},
            ):
                with self.subTest(params=params), self.assertRaises(PermissionError):
                    render_original_final(
                        candidate, {}, expected_fingerprint=contract_fingerprint(candidate),
                        **params)
            seal.assert_not_called()

    def test_change_invalidates_old_fingerprint_and_prevents_seal(self):
        source = confirmed_sale()
        prior_fingerprint = contract_fingerprint(source)
        new = deepcopy(source)
        new["clauses"][0]["sentences"][0]["text"] = "CHANGED price terms"
        with patch("Quotation_KEKOREA.contracts.ui._verified_contract_seal") as seal:
            with self.assertRaisesRegex(ValueError, "변경"):
                render_original_final(
                    new, {}, principal="test@example.test", approved=True,
                    authorized=True, expected_fingerprint=prior_fingerprint)
            seal.assert_not_called()

    def test_unconfirmed_ai_conditions_and_missing_signers_block_final(self):
        snapshot = confirmed_sale()
        snapshot["parties"][0]["status"] = "suggested"
        snapshot["terms"][0]["status"] = "suggested"
        errors = contract_final_blockers(snapshot, {})
        self.assertTrue(any("당사자" in line for line in errors))
        self.assertTrue(any("계약조건" in line or "AI 제안" in line for line in errors))
        with patch("Quotation_KEKOREA.contracts.ui._verified_contract_seal") as seal:
            with self.assertRaises(ValueError):
                render_original_final(
                    snapshot, {}, principal="test@example.test", approved=True,
                    authorized=True, expected_fingerprint=contract_fingerprint(snapshot))
            seal.assert_not_called()
        snapshot["parties"] = [snapshot["parties"][1]]
        self.assertTrue(any("직인" in text or "Seller" in text
                            for text in contract_final_blockers(snapshot, {})))

    def test_explicit_record_confirmation_never_auto_approves_a_changed_party(self):
        snapshot = confirmed_sale()
        snapshot["parties"][0]["status"] = "suggested"
        old = deepcopy(snapshot)
        party = snapshot["parties"][0]
        import json
        expected = json.dumps({
            "roles": party.get("roles"), "legal_name": party.get("legal_name"),
            "address": party.get("address"), "country": party.get("country"),
        }, sort_keys=True, ensure_ascii=False)
        result = confirm_contract_record(snapshot, "parties", 0, expected)
        self.assertEqual(result["parties"][0]["status"], "confirmed")
        self.assertEqual(snapshot, old)
        changed = deepcopy(snapshot)
        changed["parties"][0]["address"] = "Other address"
        with self.assertRaisesRegex(ValueError, "변경"):
            confirm_contract_record(changed, "parties", 0, expected)
        term = snapshot["terms"][0]
        confirmed_term = confirm_contract_record(
            {**snapshot, "terms": [{**term, "status": "suggested"}]},
            "terms", 0, str(term["value"]))
        self.assertEqual(confirmed_term["terms"][0]["status"], "confirmed")
        blank = deepcopy(snapshot)
        blank["parties"][0]["country"] = ""
        with self.assertRaises(ValueError):
            confirm_contract_record(blank, "parties", 0, json.dumps({
                "roles": blank["parties"][0]["roles"],
                "legal_name": blank["parties"][0]["legal_name"],
                "address": blank["parties"][0]["address"],
                "country": "",
            }, sort_keys=True, ensure_ascii=False))

    def test_unconfirmed_ai_review_issue_blocks_until_user_action(self):
        from Quotation_KEKOREA.orchestration.workflows.master_contract_final import (
            confirm_contract_issue,
        )
        original = confirmed_sale()
        original["issues"] = [
            {"severity": "confirm", "code": "synthetic-review",
             "message": "Confirm synthetic payment deadline", "confirmed": False},
            {"severity": "block", "code": "synthetic-block",
             "message": "Missing independent approval"},
        ]
        self.assertTrue(any("Confirm synthetic payment deadline" in m
                            for m in contract_final_blockers(original, {})))
        snapshot = deepcopy(original)
        updated = confirm_contract_issue(
            original, 0, "Confirm synthetic payment deadline")
        self.assertTrue(updated["issues"][0]["confirmed"])
        self.assertEqual(original, snapshot)
        self.assertFalse(updated["issues"][1].get("confirmed"))
        self.assertTrue(any("Missing independent approval" in m
                            for m in contract_final_blockers(updated, {})))
        with self.assertRaises(ValueError):
            confirm_contract_issue(updated, 1, "Missing independent approval")
        with self.assertRaises(ValueError):
            confirm_contract_issue(original, 0, "Different old message")

    def test_non_master_contract_never_claims_to_be_new_master_final(self):
        original = confirmed_sale()
        original["contract_id"] = "saved-original-contract-id"
        self.assertTrue(contract_final_blockers(original, {}))
