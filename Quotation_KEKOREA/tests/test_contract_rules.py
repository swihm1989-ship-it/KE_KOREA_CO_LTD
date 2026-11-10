import unittest

from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.rules import validate_snapshot, apply_analysis
from Quotation_KEKOREA.contracts.models import validate_snapshot as validate_structure


def complete_commission_snapshot():
    snapshot = new_snapshot("test-contract", "trade_commission", "en")
    snapshot["parties"] = [
        {"id": "client", "legal_name": "Buyer Co", "country": "KR",
         "address": "Seoul", "roles": ["client"], "status": "confirmed"},
        {"id": "intermediary", "legal_name": "KE KOREA", "country": "KR",
         "address": "Seoul", "roles": ["intermediary"], "status": "confirmed"},
        {"id": "payer", "legal_name": "Payer Co", "country": "SG",
         "address": "Singapore", "roles": ["commission_payer"], "status": "confirmed"},
    ]
    values = {
        "contract_date": "2026-11-05", "scope": "Introduce buyer and seller",
        "governing_law": None, "dispute_resolution": None,
        "covered_transaction": "Solar cell sale", "commission_formula": "3%",
        "commission_basis": "Amount received, USD", "currency": "USD",
        "success_trigger": "Receipt of each batch payment", "payment_deadline": "Before pickup",
        "term_or_deal_scope": "Specific transaction completion",
    }
    snapshot["terms"] = [
        {"id": f"term-{key}", "key": key, "value": value,
         "status": "missing" if value is None else "confirmed"}
        for key, value in values.items()
    ]
    return snapshot


class ContractRuleTests(unittest.TestCase):
    def test_multilingual_duplicate_terms_do_not_break_draft_validation(self):
        snapshot = new_snapshot("solar-contract", "sale", "ko")
        analysis = {
            "contract_type": "sale", "parties": [], "issues": [], "questions": [],
            "terms": [
                {"key": "수량", "value": "2324938", "unit": "PCS"},
                {"key": "quantity", "value": "2324938", "unit": "PCS"},
                {"key": "단가", "value": "0.225", "currency": "USD"},
                {"key": "unit price", "value": "0.225", "currency": "USD"},
            ],
        }
        result = apply_analysis(snapshot, analysis)
        self.assertEqual([t["key"] for t in result["terms"]], ["quantity", "unit_price"])
        self.assertTrue(all(t["status"] == "suggested" for t in result["terms"]))
        checked = validate_structure(result)
        self.assertEqual([term["key"] for term in checked["terms"]], ["quantity", "unit_price"])
        self.assertTrue(all(term["source_refs"] == [] for term in checked["terms"]))
        self.assertEqual(result["issues"], [])

    def test_conflicting_duplicate_terms_require_review(self):
        snapshot = new_snapshot("solar-contract", "sale", "ko")
        analysis = {
            "contract_type": "sale", "parties": [], "issues": [], "questions": [],
            "terms": [
                {"key": "quantity", "value": "2324938", "unit": "PCS"},
                {"key": "수량", "value": "2324939", "unit": "PCS"},
            ],
        }
        result = apply_analysis(snapshot, analysis)
        self.assertEqual(len(result["terms"]), 1)
        self.assertEqual(result["terms"][0]["value"], "2324938")
        self.assertEqual(result["terms"][0]["status"], "suggested")
        self.assertTrue(result["clause_extraction_conflicts"])
        self.assertTrue(any(issue["code"] == "contract_term_extraction_conflict" for issue in result["issues"]))
        validate_structure(result)

    def test_missing_governing_law_and_disputes_block_until_explicit_omission(self):
        snapshot = complete_commission_snapshot()
        issues = validate_snapshot(snapshot, for_export=True)
        self.assertEqual({issue["key"] for issue in issues if issue["code"] == "missing_term"},
                         {"governing_law", "dispute_resolution"})
        snapshot["omissions"] = {
            "governing_law": {"reason": "Parties defer selection", "confirmed": True},
            "dispute_resolution": {"reason": "Parties defer selection", "confirmed": True},
        }
        self.assertEqual(validate_snapshot(snapshot, for_export=True), [])

    def test_required_business_terms_cannot_be_na(self):
        snapshot = complete_commission_snapshot()
        term = next(item for item in snapshot["terms"] if item["key"] == "commission_formula")
        term["value"] = "N/A"
        term["status"] = "confirmed"
        issues = validate_snapshot(snapshot)
        self.assertTrue(any(issue["code"] == "required_term_cannot_be_na" for issue in issues))

    def test_suggested_party_and_confirm_issue_block_export(self):
        snapshot = complete_commission_snapshot()
        snapshot["parties"][0]["status"] = "suggested"
        snapshot["issues"] = [{"severity": "confirm", "message": "Confirm transaction scope"}]
        issues = validate_snapshot(snapshot, for_export=True)
        self.assertTrue(any(issue["code"] == "suggested_party" for issue in issues))
        self.assertTrue(any(issue["message"] == "Confirm transaction scope" for issue in issues))

    def test_unrelated_information_notice_does_not_block_export(self):
        snapshot = complete_commission_snapshot()
        snapshot["omissions"] = {
            "governing_law": {"reason": "Deferred", "confirmed": True},
            "dispute_resolution": {"reason": "Deferred", "confirmed": True},
        }
        snapshot["issues"] = [{"severity": "info", "message": "Legal review is recommended."}]
        self.assertEqual(validate_snapshot(snapshot, for_export=True), [])


if __name__ == "__main__":
    unittest.main()
