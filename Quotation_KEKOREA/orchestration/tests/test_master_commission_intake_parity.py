"""Regression: MASTER must retain the party roles used by legacy commission contracts."""
import unittest

from Quotation_KEKOREA.contracts.models import validate_snapshot
from Quotation_KEKOREA.orchestration.workflows.ai_intake import make_contract_candidate


def analysis(contract_type, roles):
    return {
        "contract_type": contract_type,
        "parties": [
            {"roles": [role], "legal_name": f"TEST {role.upper()} LTD",
             "address": "Synthetic office, Seoul", "country": "South Korea",
             "representative": "Synthetic Signatory", "source_refs": []}
            for role in roles
        ],
        "terms": [
            {"key": "scope", "value": "Synthetic brokerage agreement",
             "status": "suggested", "source_refs": []},
            {"key": "commission_formula", "value": "3% of agreed basis",
             "status": "suggested", "source_refs": []},
        ],
        "questions": [], "issues": [],
    }


class MasterCommissionIntakeParityTests(unittest.TestCase):
    def test_trade_commission_keeps_all_legacy_roles(self):
        roles = ["client", "intermediary", "commission_payer"]
        source = analysis("trade_commission", roles)
        result = make_contract_candidate(source, "en")
        self.assertEqual(result["contract_type"], "trade_commission")
        self.assertEqual([row["roles"][0] for row in result["parties"]], roles)
        self.assertEqual([row["status"] for row in result["parties"]],
                         ["suggested"] * 3)
        self.assertEqual(result["terms"][1]["value"], "3% of agreed basis")
        self.assertTrue(result["contract_id"].startswith("orchestration-"))
        self.assertEqual(validate_snapshot(result), result)

    def test_investment_commission_keeps_payer_fundraiser_investor(self):
        roles = ["client", "fundraiser", "commission_payer", "investor"]
        source = analysis("investment_commission", roles)
        result = make_contract_candidate(source, "ko")
        self.assertEqual([row["roles"][0] for row in result["parties"]], roles)
        self.assertEqual(result["contract_type"], "investment_commission")

    def test_contract_types_do_not_autoconfirm_extracted_roles(self):
        candidate = make_contract_candidate(
            analysis("trade_commission", ["client", "intermediary",
                                          "commission_payer"]), "en")
        self.assertTrue(all(p["status"] != "confirmed"
                            for p in candidate["parties"]))
        self.assertTrue(all(t["status"] != "confirmed"
                            for t in candidate["terms"]))

    def test_unknown_roles_do_not_enter_signed_legal_candidates(self):
        source = analysis("trade_commission", ["client", "intermediary",
                                                "commission_payer"])
        source["parties"].append({
            "roles": ["untrusted_new_role"], "legal_name": "Untrusted role",
            "address": "", "country": "", "source_refs": []})
        result = make_contract_candidate(source, "en")
        self.assertEqual(result["parties"][-1]["roles"], [])


if __name__ == "__main__":
    unittest.main()
