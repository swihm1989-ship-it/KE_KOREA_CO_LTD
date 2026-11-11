"""Tests specify non-final previews from the unchanged validation engines."""
import copy
import unittest

from Quotation_KEKOREA.orchestration.workflows.document_preview import build_preview


class DocumentPreviewTests(unittest.TestCase):
    def test_trade_preview_calculates_with_existing_engine_and_keeps_input(self):
        data = {
            "document_type": "PI",
            "product_family": "solar_cell",
            "currency": "USD",
            "document_number": "DRAFT",
            "buyer": {"legal_name": "Demo Buyer LLC", "address": "Example Street"},
            "seller": {"legal_name": "KE KOREA CO. LTD", "address": "Example Street"},
            "incoterms": "EXW Seoul",
            "payment_terms": "T/T",
            "items": [{
                "product_name": "M10 test cell", "quantity": "100", "unit": "PCS",
                "unit_price": "0.20", "price_basis": "PCS", "price_source": "manual verified"
            }],
        }
        saved = copy.deepcopy(data)
        preview = build_preview("PI", data)
        self.assertEqual(data, saved)
        self.assertEqual(preview.kind, "PI")
        self.assertEqual(preview.total, "20.00")
        self.assertEqual(preview.items[0]["line_total"], "20.00")
        self.assertFalse(preview.final)
        self.assertTrue(preview.watermark)

    def test_trade_missing_conditions_still_show_draft_blockers(self):
        preview = build_preview("PO", {"document_type": "PO", "items": []})
        self.assertEqual(preview.kind, "PO")
        self.assertTrue(preview.blockers)
        self.assertEqual(preview.status, "needs_input")
        self.assertFalse(preview.final)

    def test_kind_cannot_override_requested_document(self):
        with self.assertRaises(ValueError):
            build_preview("PI", {"document_type": "CI"})

    def test_contract_requires_authored_clauses_not_ai_invention(self):
        from Quotation_KEKOREA.contracts.models import new_snapshot
        source = new_snapshot("DRAFT-1", "sale", "ko")
        source["clauses"] = [{"id": "c1", "order": 1, "title": "제1조", "sentences": [
            {"id": "s1", "text": "테스트용 조항입니다.", "status": "suggested"}
        ]}]
        copy_original = copy.deepcopy(source)
        preview = build_preview("CONTRACT", source)
        self.assertEqual(source, copy_original)
        self.assertEqual(preview.clauses[0]["sentences"], ["테스트용 조항입니다."])
        self.assertTrue(preview.blockers)
        self.assertFalse(preview.final)

    def test_blank_contract_has_no_invented_clauses(self):
        from Quotation_KEKOREA.contracts.models import new_snapshot
        source = new_snapshot("DRAFT-2", "sale", "en")
        preview = build_preview("CONTRACT", source)
        self.assertEqual(preview.clauses, ())
        self.assertTrue(preview.blockers)

    def test_unsupported_kind_rejected(self):
        with self.assertRaises(ValueError):
            build_preview("EMAIL", {})


if __name__ == "__main__":
    unittest.main()
