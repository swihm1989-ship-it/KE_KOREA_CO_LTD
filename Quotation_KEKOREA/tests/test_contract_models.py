import unittest

from Quotation_KEKOREA.contracts.models import new_snapshot, validate_snapshot
from Quotation_KEKOREA.contracts.rules import apply_analysis
from Quotation_KEKOREA.contracts.service import language_conflict


class ContractModelTests(unittest.TestCase):
    def test_contract_type_and_language_are_explicit(self):
        with self.assertRaises(ValueError):
            new_snapshot("test", "bipv", "ko")
        with self.assertRaises(ValueError):
            new_snapshot("test", "sale", "ko-en")

    def test_sentence_ids_must_be_unique(self):
        snapshot = new_snapshot("test", "sale", "ko")
        snapshot["clauses"] = [
            {"title": "제1조", "sentences": [
                {"id": "same", "text": "첫 문장"},
                {"id": "same", "text": "둘째 문장"},
            ]}
        ]
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_snapshot(snapshot)

    def test_party_roles_are_not_forced_to_seller(self):
        snapshot = new_snapshot("test", "trade_commission", "ko")
        analysis = {
            "contract_type": "trade_commission",
            "parties": [{"legal_name": "KE KOREA", "roles": ["intermediary"]}],
            "terms": [], "issues": [], "questions": [],
        }
        updated = apply_analysis(snapshot, analysis)
        self.assertEqual(updated["parties"][0]["roles"], ["intermediary"])
        self.assertNotIn("seller", updated["parties"][0]["roles"])
        self.assertEqual(updated["parties"][0]["status"], "suggested")

    def test_language_request_conflict_requires_confirmation(self):
        self.assertTrue(language_conflict("영어 계약서로 작성", "ko"))
        self.assertTrue(language_conflict("한국어 계약서를 만들어줘", "en"))
        self.assertFalse(language_conflict("거래 조건 정리", "ko"))


if __name__ == "__main__":
    unittest.main()
