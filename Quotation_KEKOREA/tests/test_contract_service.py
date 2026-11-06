import json
import unittest
from io import BytesIO
import urllib.error

from Quotation_KEKOREA.contracts.editing import RevisionConflict
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.service import (
    analyze_trade, generate_draft, propose_revision,
)


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return json.dumps({"status": "completed", "output": [{
            "content": [{"type": "output_text", "text": json.dumps(self.value)}],
        }]}).encode()


class ContractServiceTests(unittest.TestCase):
    def test_drafting_keeps_user_title_even_when_ai_returns_another_title(self):
        snapshot = new_snapshot('contract-1', 'investment_commission', 'en')
        snapshot['title'] = 'Example FI Agreement'
        response = {'title': 'Investment Commission Agreement', 'issues': [],
                    'clauses': [{'id': 'c1', 'title': 'Scope', 'order': 1,
                                 'sentences': [{'id': 's1', 'text': 'The parties agree to the stated scope.',
                                                'term_ids': [], 'source_refs': []}]}]}
        result = generate_draft(snapshot, [], env={'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'},
                                client=self.opener_for(response))
        self.assertEqual(result['title'], 'Example FI Agreement')

    def opener_for(self, value, captured=None):
        def opener(request, timeout):
            if captured is not None:
                captured["request"] = request
                captured["timeout"] = timeout
            return FakeResponse(value)
        return opener

    def test_analysis_preserves_currency_units_and_commission_payer_role(self):
        captured = {}
        response = {
            "contract_type": "trade_commission",
            "parties": [{"legal_name": "KE KOREA", "country": "KR", "address": "Seoul",
                         "representative": None, "roles": ["intermediary"]},
                        {"legal_name": "Example Co", "country": "SG", "address": "Singapore",
                         "representative": None, "roles": ["commission_payer"]}],
            "terms": [{"key": "commission_formula", "value": "3%", "unit": None,
                       "currency": None, "status": "suggested", "source_refs": []},
                      {"key": "quantity", "value": "5,000,000", "unit": "PCS",
                       "currency": None, "status": "suggested", "source_refs": []},
                      {"key": "commission_basis", "value": "USD 1.25", "unit": "PCS",
                       "currency": "USD", "status": "suggested", "source_refs": []}],
            "questions": ["Who pays the commission?"],
            "issues": [],
        }
        result = analyze_trade([{"role": "user", "content": "3% of USD/PCS"}],
                               {"revision": 1}, [], env={"OPENAI_API_KEY": "test",
                               "OPENAI_MODEL": "test"}, client=self.opener_for(response, captured))
        self.assertEqual(result["terms"][1]["value"], "5,000,000")
        self.assertEqual(result["terms"][1]["unit"], "PCS")
        self.assertEqual(result["terms"][2]["currency"], "USD")
        self.assertIn("commission_payer", result["parties"][1]["roles"])
        self.assertIn("Bearer test", captured["request"].get_header("Authorization"))

    def test_missing_terms_are_not_invented_by_service_validation(self):
        response = {
            "contract_type": "sale", "parties": [], "terms": [],
            "questions": ["Which governing law applies?"], "issues": [],
        }
        result = analyze_trade([], {"contract_type": "sale"}, [], env={
            "OPENAI_API_KEY": "test", "OPENAI_MODEL": "test",
        }, client=self.opener_for(response))
        self.assertEqual(result["terms"], [])
        self.assertEqual(result["questions"], ["Which governing law applies?"])

    def test_analysis_accepts_only_verifiable_reference_quotes(self):
        response = {
            "contract_type": "sale", "parties": [],
            "terms": [{"key": "payment_trigger", "value": "Upon delivery",
                       "unit": None, "currency": None, "status": "suggested",
                       "source_refs": [{"kind": "reference", "document_id": "ref-1",
                                        "quote": "Payment is due upon delivery."}]}],
            "questions": [], "issues": [],
        }
        source = [{"id": "ref-1", "extracted_text": "Payment is due upon delivery."}]
        env = {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test"}
        result = analyze_trade([{"role": "user", "content": "Use the reference."}],
                               {"revision": 1}, source, env=env,
                               client=self.opener_for(response))
        self.assertEqual(result["terms"][0]["value"], "Upon delivery")

        response["terms"][0]["source_refs"][0]["quote"] = "Payment is due in advance."
        with self.assertRaisesRegex(ValueError, "not found"):
            analyze_trade([{"role": "user", "content": "Use the reference."}],
                          {"revision": 1}, source, env=env,
                          client=self.opener_for(response))

    def test_korean_input_can_generate_english_only_and_preserve_ids(self):
        snapshot = new_snapshot("contract-1", "sale", "en")
        sentence = {"id": "sentence-1", "text": "The price is USD 4 per PCS.",
                    "term_ids": ["unit-price"], "source_refs": []}
        response = {"title": "Solar Cell Sale Agreement", "issues": [],
                    "clauses": [{"id": "clause-1", "title": "Price", "order": 1,
                                 "sentences": [sentence]}]}
        result = generate_draft(snapshot, [], env={"OPENAI_API_KEY": "test",
                                "OPENAI_MODEL": "test"}, client=self.opener_for(response))
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["clauses"][0]["sentences"][0]["id"], "sentence-1")

    def test_korean_contract_rejects_english_only_body(self):
        snapshot = new_snapshot("contract-1", "sale", "ko")
        response = {"title": "Sale Agreement", "issues": [],
                    "clauses": [{"id": "c1", "title": "Price", "order": 1,
                                 "sentences": [{"id": "s1", "text": "The price is USD 4.",
                                                "term_ids": [], "source_refs": []}]}]}
        with self.assertRaisesRegex(ValueError, "substantial English prose"):
            generate_draft(snapshot, [], env={"OPENAI_API_KEY": "test",
                                "OPENAI_MODEL": "test"}, client=self.opener_for(response))

    def test_draft_rejects_unverified_reference_citations(self):
        snapshot = new_snapshot("contract-1", "sale", "en")
        response = {"title": "Sale Agreement", "issues": [],
                    "clauses": [{"id": "c1", "title": "Payment", "order": 1,
                                 "sentences": [{
                                     "id": "s1", "text": "Payment is due on delivery.",
                                     "term_ids": [],
                                     "source_refs": [{
                                         "kind": "reference", "document_id": "ref-1",
                                         "quote": "Payment is due on delivery.",
                                     }],
                                 }]}]}
        env = {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test"}
        with self.assertRaisesRegex(ValueError, "not found"):
            generate_draft(snapshot, [], env=env, client=self.opener_for(response))
        result = generate_draft(
            snapshot, [], env=env,
            reference_context=[{
                "id": "ref-1", "extracted_text": "Payment is due on delivery.",
            }],
            client=self.opener_for(response),
        )
        self.assertEqual(result["clauses"][0]["sentences"][0]["source_refs"][0]["document_id"],
                         "ref-1")

    def test_ai_failure_does_not_mutate_existing_draft(self):
        snapshot = new_snapshot("contract-1", "trade_commission", "en")
        snapshot["clauses"] = [{"id": "c1", "title": "Fee", "order": 1,
                                "sentences": [{"id": "s1", "text": "Original sentence.",
                                               "term_ids": [], "source_refs": []}]}]
        original = json.dumps(snapshot, sort_keys=True)
        def failing_opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 500, "failure", {}, BytesIO())
        with self.assertRaises(RuntimeError):
            propose_revision(snapshot, "s1", "change it",
                             env={"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test"},
                             client=failing_opener)
        self.assertEqual(json.dumps(snapshot, sort_keys=True), original)


if __name__ == "__main__":
    unittest.main()
