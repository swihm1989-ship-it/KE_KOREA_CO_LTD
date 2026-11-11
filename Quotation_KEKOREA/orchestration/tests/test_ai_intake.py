"""AI intake must preserve suggested status, source and explicit review gates."""
import copy
import unittest
from unittest.mock import patch, Mock

from Quotation_KEKOREA.orchestration.workflows.ai_intake import (
    extract_candidate, make_contract_candidate, make_trade_candidate,
    selected_contract_reference, generate_contract_draft,
)


class AiIntakeTests(unittest.TestCase):
    def setUp(self):
        self.instruction = "PI 계약서: seller KE KOREA CO. LTD, 100 PCS, USD 0.20/pc"
        self.ai = {
            "contract_type": "sale",
            "parties": [{"roles": ["seller"], "legal_name": "KE KOREA CO. LTD",
                         "country": "", "address": "", "source_refs": []},
                        {"roles": ["buyer"], "legal_name": "Demo Buyer Ltd",
                         "country": "", "address": "", "source_refs": []}],
            "terms": [
                {"key": "products", "value": "M10 PERC", "status": "suggested", "source_refs": []},
                {"key": "quantity", "value": "100", "status": "suggested", "source_refs": []},
                {"key": "unit", "value": "PCS", "status": "suggested", "source_refs": []},
                {"key": "unit_price", "value": "0.20", "status": "suggested", "source_refs": []},
                {"key": "currency", "value": "USD", "status": "suggested", "source_refs": []},
                {"key": "delivery", "value": "EXW Seoul", "status": "suggested", "source_refs": []},
                {"key": "payment_trigger", "value": "T/T", "status": "suggested", "source_refs": []},
            ],
            "questions": ["구매자의 정확한 주소는 무엇인가요?"],
            "issues": [],
        }

    def test_explicit_opt_in_required_before_external_ai_call(self):
        with patch("Quotation_KEKOREA.contracts.service.analyze_trade") as api:
            with self.assertRaises(PermissionError):
                extract_candidate(self.instruction, {}, consent=False)
            api.assert_not_called()

    def test_no_model_config_stops_before_ai_call(self):
        with patch("Quotation_KEKOREA.contracts.service.analyze_trade") as api:
            with self.assertRaises(ValueError):
                extract_candidate(self.instruction, {}, consent=True)
            api.assert_not_called()

    def test_reuses_existing_verified_contract_extractor_without_reference_transfer(self):
        with patch("Quotation_KEKOREA.contracts.service.analyze_trade", return_value=copy.deepcopy(self.ai)) as api:
            result = extract_candidate(self.instruction,
                {"OPENAI_API_KEY": "fake", "OPENAI_MODEL": "fake-model"}, consent=True)
            self.assertEqual(result["terms"][0]["status"], "suggested")
            self.assertEqual(result["questions"][0], self.ai["questions"][0])
            self.assertEqual(api.call_args.args[2], [])
            self.assertEqual(api.call_args.args[0], [{"role": "user", "content": self.instruction}])

    def test_contract_candidate_is_new_draft_never_copies_old_clauses(self):
        src = {"contract_id": "old-id", "contract_type": "sale", "language": "ko",
               "revision": 5, "clauses": [{"title": "Old Clause", "sentences": [{"text": "old secret"}]}],
               "parties": [], "terms": []}
        original = copy.deepcopy(src)
        candidate = make_contract_candidate(self.ai, "ko", reference=src)
        self.assertEqual(src, original)
        self.assertNotEqual(candidate["contract_id"], src["contract_id"])
        self.assertEqual(candidate["clauses"], [])
        self.assertFalse(any(p.get("status") == "confirmed" for p in candidate["parties"]))
        self.assertTrue(all(t["status"] != "confirmed" for t in candidate["terms"]))
        self.assertNotIn("old secret", str(candidate))

    def test_trade_candidate_prefills_without_inventing_address_or_approvals(self):
        pi = make_trade_candidate("PI", self.ai)
        self.assertEqual(pi["items"][0]["quantity"], "100")
        self.assertEqual(pi["items"][0]["unit_price"], "0.20")
        self.assertFalse(pi.get("ready_for_issue", False))
        self.assertEqual(pi["buyer"].get("address", ""), "")
        self.assertEqual(pi["items"][0]["price_source"], "")  # verified provenance must be user-supplied
        self.assertNotIn("price_override_confirmed", pi["items"][0])

    def test_prior_contract_reference_is_immutable_and_never_autofilled(self):
        repo = Mock()
        reference = {"contract_id": "c-1", "revision": 2, "contract_type": "sale",
                     "language": "ko", "parties": [], "terms": [],
                     "clauses": [{"title": "Terms", "sentences": [{"text": "Private clause"}]}]}
        repo.list_contracts.return_value = [{"id": "c-1", "title": "Old Contract", "language": "ko"}]
        repo.load_contract.return_value = [{"revision": 2, "snapshot": reference}]
        copied = copy.deepcopy(reference)
        result = selected_contract_reference(repo, "c-1", 2)
        self.assertEqual(result["clauses"], reference["clauses"])
        self.assertEqual(copied, reference)
        repo.commit_revision.assert_not_called()
        repo.save_export.assert_not_called()

    def test_contract_drafting_is_opt_in_and_never_saves_to_existing_repo(self):
        candidate = make_contract_candidate(self.ai, "ko")
        with patch("Quotation_KEKOREA.contracts.ai_graph.generate_contract_draft_graph") as draft:
            with self.assertRaises(PermissionError):
                generate_contract_draft(candidate, {}, consent=False)
            draft.assert_not_called()
            fake = copy.deepcopy(candidate)
            fake["clauses"] = [{"title": "DRAFT", "sentences": [{"text": "review only"}]}]
            draft.return_value = fake
            result = generate_contract_draft(
                candidate, {"OPENAI_API_KEY": "fake", "OPENAI_MODEL": "test"}, consent=True)
            self.assertEqual(result["clauses"][0]["sentences"][0]["text"], "review only")
            self.assertTrue(draft.call_args.kwargs["use_library"] is False)
            self.assertIsNone(draft.call_args.kwargs["repo"])

    def test_recovery_does_not_change_strict_ai_confirmation_guard(self):
        bad = copy.deepcopy(self.ai)
        bad["terms"][0]["status"] = "confirmed"
        with self.assertRaises(ValueError):
            make_trade_candidate("PI", bad)

    def test_ai_terms_must_be_suggested_even_if_model_claims_confirmed(self):
        bad = copy.deepcopy(self.ai)
        bad["terms"][0]["status"] = "confirmed"
        with self.assertRaises(ValueError):
            make_contract_candidate(bad, "ko")


if __name__ == "__main__":
    unittest.main()
