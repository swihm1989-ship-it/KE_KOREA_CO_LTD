"""AI audit hallucinated citations cannot lose the draft or silently approve it."""
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts import drafting
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.rules import validate_snapshot as validate_rules


class AuditCitationFallbackTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = new_snapshot("audit-fallback", "sale", "ko")
        self.snapshot["clauses"] = [
            {"id": "cl_scope_01", "title": "Scope", "order": 1,
             "sentences": [{"id": "sn_payment_03", "text": "결제금액은 계약에 따릅니다."}]}
        ]
        self.plan = {"topics": [{"key": "scope", "elements": {"goods": "Goods"}}]}

    def test_second_mismatch_preserves_audit_unverified_not_complete(self):
        attempts = []
        def fake_audit(*args, **kwargs):
            attempts.append(kwargs.get("strict_quotes", False))
            raise drafting.AuditCitationMismatch(
                "Clause audit citation mismatch: clause_id=cl_scope_01, sentence_id=sn_payment_03")
        with patch.object(drafting, "_audit_once", side_effect=fake_audit):
            result = drafting._audit(self.snapshot, self.plan, [], env={}, client=None, timeout=60)
        self.assertEqual(attempts, [False, True])
        self.assertTrue(result.citation_unverified)
        self.assertTrue(all(row["status"] != "complete" for row in result))
        self.assertTrue(all(not row["evidence"] for row in result))

    def test_verifiable_audit_is_unchanged(self):
        original = [{"topic": "scope", "status": "complete", "clause_ids": ["cl_scope_01"],
                     "missing_elements": [], "evidence": []}]
        with patch.object(drafting, "_audit_once", return_value=original) as audit:
            result = drafting._audit(self.snapshot, self.plan, [], env={}, client=None, timeout=60)
        self.assertIs(result, original)
        audit.assert_called_once()

    def test_conservative_issue_blocks_final(self):
        snap = new_snapshot("audit-blocker", "sale", "ko")
        snap["issues"] = [{
            "id": "draft_audit_citation_unverified",
            "code": "draft_audit_citation_unverified",
            "severity": "block", "confirmed": False,
            "message": "AI 인용 검증 실패"
        }]
        problems = validate_rules(snap, for_export=True)
        self.assertTrue(any(p.get("code") == "draft_audit_citation_unverified"
                            for p in problems))


if __name__ == "__main__":
    unittest.main()
