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

    def test_upstream_missing_terms_reach_trade_candidate_as_empty_fields(self):
        for absent in (None, ""):
            with self.subTest(value=absent):
                analysis = copy.deepcopy(self.ai)
                analysis["terms"][1].update(value=absent, status="missing")
                analysis["terms"][6].update(value=absent, status="missing")
                # Exercise the real contract-service response validator; only
                # its external model call is replaced with synthetic JSON.
                with patch("Quotation_KEKOREA.contracts.service._call",
                           return_value=analysis):
                    extracted = extract_candidate(self.instruction,
                        {"OPENAI_API_KEY": "fake", "OPENAI_MODEL": "fake-model"}, consent=True)
                before = copy.deepcopy(extracted)
                pi = make_trade_candidate("PI", extracted)
                self.assertEqual(pi["items"][0]["quantity"], "")
                self.assertEqual(pi["payment_terms"], "")
                self.assertEqual(pi["items"][0]["unit_price"], "0.20")
                self.assertEqual(extracted, before)
                self.assertFalse(pi.get("ready_for_issue", False))

    def test_empty_missing_contract_terms_remain_unresolved(self):
        for absent in (None, "", "   "):
            with self.subTest(value=absent):
                analysis = copy.deepcopy(self.ai)
                analysis["terms"][1].update(value=absent, status="missing")
                before = copy.deepcopy(analysis)
                contract = make_contract_candidate(analysis, "ko")
                quantity = next(t for t in contract["terms"] if t["key"] == "quantity")
                self.assertEqual(quantity["value"], absent)
                self.assertEqual(quantity["status"], "missing")
                self.assertEqual(contract["clauses"], [])
                self.assertFalse(any(t["status"] == "confirmed" for t in contract["terms"]))
                self.assertEqual(analysis, before)

    def test_nonempty_missing_term_is_only_a_suggestion_like_mail_intake(self):
        analysis = copy.deepcopy(self.ai)
        analysis["terms"][1].update(value="2500", status="missing")
        with patch("Quotation_KEKOREA.contracts.service._call", return_value=analysis):
            extracted = extract_candidate(self.instruction,
                {"OPENAI_API_KEY": "fake", "OPENAI_MODEL": "fake-model"}, consent=True)
        self.assertEqual(extracted["terms"][1]["status"], "missing")
        contract = make_contract_candidate(extracted, "ko")
        quantity = next(t for t in contract["terms"] if t["key"] == "quantity")
        self.assertEqual(quantity["value"], "2500")
        self.assertEqual(quantity["status"], "suggested")
        self.assertEqual(make_trade_candidate("PI", extracted)["items"][0]["quantity"], "2500")
        self.assertEqual(extracted["terms"][1]["status"], "missing")
        self.assertFalse(any(t["status"] == "confirmed" for t in contract["terms"]))

    def test_invalid_term_statuses_stay_blocked_in_both_candidate_builders(self):
        for status in ("confirmed", "approved", "", None, 1, ["suggested"]):
            for kind in ("PI", "CONTRACT"):
                with self.subTest(status=status, kind=kind):
                    analysis = copy.deepcopy(self.ai)
                    analysis["terms"][1]["status"] = status
                    with self.assertRaises(ValueError):
                        if kind == "PI":
                            make_trade_candidate("PI", analysis)
                        else:
                            make_contract_candidate(analysis, "ko")

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

    def test_integrated_draft_retrieves_approved_shared_guidance_only_when_opted_in(self):
        candidate = make_contract_candidate(self.ai, "ko")
        fake = copy.deepcopy(candidate)
        fake["clauses"] = [{"title": "DRAFT", "sentences": [{"text": "review only"}]}]
        env = {
            "OPENAI_API_KEY": "fake", "OPENAI_MODEL": "test",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "test-private",
        }
        with (patch("Quotation_KEKOREA.contracts.repository.ContractRepository") as repository,
              patch("Quotation_KEKOREA.contracts.ai_graph.generate_contract_draft_graph",
                    return_value=fake) as draft):
            result = generate_contract_draft(candidate, env, consent=True, use_library=True)
            repository.assert_called_once_with(env)
            self.assertIs(draft.call_args.kwargs["repo"], repository.return_value)
            self.assertTrue(draft.call_args.kwargs["use_library"])
            self.assertEqual(draft.call_args.kwargs["reference_context"], [])
            self.assertEqual(result["clauses"][0]["title"], "DRAFT")
            repository.return_value.commit_revision.assert_not_called()
            repository.return_value.save_reference.assert_not_called()

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
