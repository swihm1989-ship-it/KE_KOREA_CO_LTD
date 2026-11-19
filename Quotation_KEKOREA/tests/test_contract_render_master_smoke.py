"""Synthetic Render MASTER smoke tests: no real recipients, network or database writes.

Purpose: verify actual PDF bytes for PI/PO/CI/PL review exports and
actual PDF/DOCX bytes for contract exports on GitHub CI.
All candidates are fictional. No emails are sent.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import unittest

import fitz
from docx import Document

from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import (
    render_incomplete_trade_pdf, render_master_trade_final,
)
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.models import new_snapshot


class RenderMasterDocumentSmokeTests(unittest.TestCase):
    def _source(self, kind):
        return {
            "document_type": kind,
            "product_family": "solar_cell",
            "document_number": "SYNTHETIC-20261119",
            "seller": {"legal_name": "KE KOREA CO. LTD", "address": "Example Seoul"},
            "buyer": {"legal_name": "Fictional Solar Customer LTD", "address": "Example Overseas"},
            "currency": "USD",
            "incoterms": "EXW Seoul",
            "payment_terms": "30% deposit and 70% balance",
            "items": [
                {
                    "product_name": "Synthetic M10 PERC Solar Cell",
                    "quantity": "1000",
                    "unit": "PCS",
                    "unit_price": "0.20",
                    "price_basis": "PCS",
                    "package_count": "10",
                    "net_weight_kg": "10",
                    "gross_weight_kg": "12",
                }
            ],
        }

    def test_four_trade_pdf_types_generate_real_valid_review_pdfs(self):
        for kind in ("PI", "PO", "CI", "PL"):
            with self.subTest(kind=kind):
                generated = render_incomplete_trade_pdf(kind, self._source(kind))
                self.assertEqual(list(generated), ["pdf"])
                record = generated["pdf"]
                payload = record["content"]
                self.assertTrue(payload.startswith(b"%PDF"))
                self.assertEqual(record["sha256"], sha256(payload).hexdigest())
                self.assertEqual(record["mime"], "application/pdf")
                self.assertFalse(record["final"])
                self.assertFalse(record["sendable"])
                self.assertTrue(record["review_only"])
                with fitz.open(stream=payload, filetype="pdf") as pdf:
                    self.assertGreaterEqual(pdf.page_count, 1)
                    extracted = "\n".join(page.get_text() for page in pdf)
                    self.assertIn(kind + " - DRAFT", extracted)
                    self.assertIn("Synthetic M10 PERC Solar Cell", extracted)
                    self.assertIn("Fictional Solar Customer LTD", extracted)
                    self.assertIn("NOT FOR ISSUE", extracted)

    def test_review_pdf_does_not_guess_unknown_amounts(self):
        source = self._source("PI")
        source["items"][0]["unit_price"] = None
        record = render_incomplete_trade_pdf("PI", source)["pdf"]
        with fitz.open(stream=record["content"], filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
        self.assertIn("TOTAL: NOT PROVIDED", text)
        self.assertNotIn("INDICATIVE TOTAL: USD", text)

    def test_final_trade_pdf_cannot_bypass_approval(self):
        with self.assertRaisesRegex(ValueError, "승인"):
            render_master_trade_final("PI", self._source("PI"), {}, approved=False)

    def test_contract_pdf_docx_generate_with_real_bytes(self):
        contract = new_snapshot("synthetic-id", "trade_commission", "en")
        contract.update(title="Synthetic Commercial Commission Agreement", revision=1)
        contract["parties"] = [
            {"legal_name": "KE KOREA CO. LTD", "roles": ["intermediary"]},
            {"legal_name": "Fictional Counterparty LTD", "roles": ["payer"]},
        ]
        contract["clauses"] = [
            {"id": "c1", "title": "Commission", "order": 1, "sentences": [
                {"id": "s1", "text": "Commission equals 3 percent of collected equity.",
                 "term_ids": [], "source_refs": []}
            ]}
        ]
        exported = export_contract(contract, formats=("pdf", "docx"))
        pdf = exported["pdf"]["content"]
        docx = exported["docx"]["content"]
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertTrue(docx.startswith(b"PK"))
        with fitz.open(stream=pdf, filetype="pdf") as file:
            text = "\n".join(page.get_text() for page in file)
        self.assertIn("Synthetic Commercial Commission Agreement", text)
        self.assertIn("Commission equals 3 percent", text)
        document = Document(BytesIO(docx))
        body = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("Synthetic Commercial Commission Agreement", body)
        self.assertIn("Commission equals 3 percent", body)


if __name__ == "__main__":
    unittest.main()
