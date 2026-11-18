"""Numeric AI extraction types: preserve terms without bypassing legacy guardrails."""
import copy
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.service import analyze_trade
from Quotation_KEKOREA.orchestration.workflows.ai_intake import extract_candidate, make_trade_candidate


def analysis():
    return {
        "contract_type": "sale",
        "parties": [
            {"roles": ["buyer"], "legal_name": "TEST BUYER", "source_refs": []},
            {"roles": ["seller"], "legal_name": "TEST SELLER", "source_refs": []},
        ],
        "terms": [
            {"key": "products", "value": "Solar Cell M10", "status": "suggested", "source_refs": []},
            {"key": "quantity", "value": 2500000, "status": "suggested", "source_refs": []},
            {"key": "unit", "value": "PCS", "status": "suggested", "source_refs": []},
            {"key": "unit_price", "value": 0.225, "status": "suggested", "source_refs": []},
            {"key": "currency", "value": "USD", "status": "suggested", "source_refs": []},
        ],
        "questions": [],
        "issues": [],
    }


class NumericTermRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.messages = [{"role": "user", "content": "태양광 M10 250만장 USD 0.225/장 PI"}]
        self.snapshot = {"language": "ko"}
        self.env = {"OPENAI_API_KEY": "synthetic", "OPENAI_MODEL": "synthetic"}

    def test_legacy_guard_still_rejects_unexpected_numeric_types(self):
        with patch("Quotation_KEKOREA.contracts.service._call", return_value=analysis()):
            with self.assertRaisesRegex(ValueError, "term values as text"):
                analyze_trade(self.messages, self.snapshot, [], env=self.env)

    def test_opt_in_recovers_finite_numbers_once_and_preserves_proposals(self):
        original = analysis()
        with patch("Quotation_KEKOREA.contracts.service._call", return_value=copy.deepcopy(original)):
            output = analyze_trade(self.messages, self.snapshot, [], env=self.env,
                                   allow_numeric_terms=True)
        self.assertEqual(output["terms"][1]["value"], "2500000")
        self.assertEqual(output["terms"][3]["value"], "0.225")
        self.assertEqual(output["terms"][3]["status"], "suggested")
        self.assertEqual([i["code"] for i in output["issues"]],
                         ["ai_numeric_term_needs_review"])
        self.assertEqual(original["terms"][1]["value"], 2500000)
        self.assertEqual(make_trade_candidate("PI", output)["items"][0]["unit_price"], "0.225")

    def test_master_explicitly_opts_into_safe_recovery(self):
        with patch("Quotation_KEKOREA.contracts.service.analyze_trade",
                   return_value=analysis()) as mocked:
            extract_candidate("Make PI", self.env, consent=True)
        self.assertIs(mocked.call_args.kwargs["allow_numeric_terms"], True)

    def test_reject_boolean_nan_and_nested_arrays(self):
        for value in [True, float("inf"), float("nan"), [], {"value": "100"}]:
            with self.subTest(value=str(value)):
                data = analysis()
                data["terms"][1]["value"] = value
                with patch("Quotation_KEKOREA.contracts.service._call",
                           return_value=data):
                    with self.assertRaises(ValueError):
                        analyze_trade(self.messages, self.snapshot, [], env=self.env,
                                      allow_numeric_terms=True)

    def test_numeric_unit_and_currency_still_rejected(self):
        for key in ["unit", "currency"]:
            with self.subTest(key=key):
                data = analysis()
                next(t for t in data["terms"] if t["key"] == key)["value"] = 7
                with patch("Quotation_KEKOREA.contracts.service._call",
                           return_value=data):
                    with self.assertRaises(ValueError):
                        analyze_trade(self.messages, self.snapshot, [], env=self.env,
                                      allow_numeric_terms=True)


if __name__ == "__main__":
    unittest.main()
