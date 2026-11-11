"""Read-only legacy engine bridge: no saved revisions, exports, or SMTP."""
import copy
import unittest

from Quotation_KEKOREA.orchestration.adapters.engine_bridge import (
    evaluate_trade_candidate, evaluate_contract_candidate,
)


class TradeEngineTests(unittest.TestCase):
    def test_missing_data_returns_blockers_without_creating_document(self):
        source = {"document_type": "PI", "product_family": "solar_cell", "items": []}
        original = copy.deepcopy(source)
        report = evaluate_trade_candidate(source)
        self.assertEqual(report.kind, "PI")
        self.assertEqual(report.status, "needs_input")
        self.assertTrue(report.blockers)
        self.assertEqual(source, original)
        self.assertFalse(report.can_send)

    def test_invalid_trade_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_trade_candidate({"document_type": "CONTRACT"})

    def test_does_not_trust_client_ready_flag(self):
        report = evaluate_trade_candidate({"document_type": "PO", "ready_for_issue": True})
        self.assertFalse(report.ready_for_user_confirmation)
        self.assertFalse(report.can_send)


class ContractEngineTests(unittest.TestCase):
    def test_missing_contract_terms_block_export(self):
        from Quotation_KEKOREA.contracts.models import new_snapshot
        source = new_snapshot("test-001", "sale", "ko")
        original = copy.deepcopy(source)
        report = evaluate_contract_candidate(source)
        self.assertEqual(report.kind, "CONTRACT")
        self.assertEqual(report.status, "needs_input")
        self.assertTrue(report.blockers)
        self.assertFalse(report.can_send)
        self.assertEqual(source, original)

    def test_invalid_contract_shape_raises_validation_error(self):
        with self.assertRaises(ValueError):
            evaluate_contract_candidate({"contract_type": "sale"})

    def test_does_not_mutate_or_export(self):
        from Quotation_KEKOREA.contracts.models import new_snapshot
        source = new_snapshot("test-002", "sale", "en")
        source["issues"].append({"severity": "block", "code": "test", "message": "Needs manual review"})
        report = evaluate_contract_candidate(source)
        self.assertTrue(any("manual review" in b.lower() for b in report.blockers))
        self.assertEqual(source["issues"][0]["code"], "test")
        self.assertFalse(report.can_send)


if __name__ == "__main__":
    unittest.main()
