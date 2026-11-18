"""Regression: AI outages must not prevent mailbox -> draft-outbox routing."""
import unittest
from unittest.mock import Mock

from Quotation_KEKOREA.orchestration.workflows.email_reply_handoff import (
    prepare_email_handoff,
)


class EmailReplyHandoffTests(unittest.TestCase):
    def setUp(self):
        self.saved={"id":"8ca113cc-971d-4e74-b2a9-7a9dd101c2f8","status":"draft","candidate_bodies":[]}
        self.queue=Mock(return_value=self.saved)
        self.save=Mock()
        self.source={"subject":"문의","sender":"Buyer <buyer@example.test>","body":"반갑습니다."}
        self.model={"OPENAI_API_KEY":"fake-key","CONTRACT_OPENAI_MODEL":"test-model"}

    def prepare(self, *, consent, generate=None, queue=None):
        return prepare_email_handoff(
            {}, "owner@example.test", self.source, {}, self.model, "ko",
            ai_consented=consent, queue=queue or self.queue,
            generate=generate or Mock(return_value=[
                "안녕하세요. 문의 감사합니다.",
                "안녕하세요. 검토하겠습니다.",
                "안녕하세요. 자세히 확인하겠습니다.",
            ]),
            save=self.save,
        )

    def test_ai_auth_failure_does_not_erase_queued_draft(self):
        generator=Mock(side_effect=RuntimeError(
            "AI 회신 API 오류 (HTTP 401): 서버의 OpenAI API 키가 유효하지 않습니다."
        ))
        row, warning=self.prepare(consent=True, generate=generator)
        self.assertIs(row,self.saved)
        self.assertIn("HTTP 401",warning)
        self.queue.assert_called_once()
        self.save.assert_not_called()

    def test_ai_rate_limit_does_not_block_handoff(self):
        row, warning=self.prepare(consent=True,generate=Mock(
            side_effect=RuntimeError("AI 회신 API 오류 (HTTP 429): 사용량 제한")))
        self.assertEqual(row["status"],"draft")
        self.assertIn("HTTP 429",warning)

    def test_no_consent_skips_provider(self):
        generator=Mock()
        row,warning=self.prepare(consent=False,generate=generator)
        self.assertIs(row,self.saved)
        self.assertIsNone(warning)
        generator.assert_not_called()
        self.save.assert_not_called()

    def test_existing_candidates_are_never_overwritten(self):
        self.saved["candidate_bodies"]=["original 1","original 2","original 3"]
        generator=Mock()
        self.prepare(consent=True,generate=generator)
        generator.assert_not_called()
        self.save.assert_not_called()

    def test_success_saves_candidates_after_durable_queue(self):
        generator=Mock(return_value=["draft one","draft two","draft three"])
        row,warning=self.prepare(consent=True,generate=generator)
        self.assertIs(row,self.saved)
        self.assertIsNone(warning)
        self.save.assert_called_once_with(
            {}, "owner@example.test", self.saved["id"],
            ["draft one","draft two","draft three"], "ko")

    def test_candidate_persistence_failure_retains_queued_draft(self):
        self.save.side_effect=RuntimeError("candidate storage temporarily unavailable")
        row,warning=self.prepare(consent=True)
        self.assertIs(row,self.saved)
        self.assertIn("candidate storage",warning)

    def test_actual_queue_failure_is_not_misreported_as_saved(self):
        queue=Mock(side_effect=RuntimeError("database unavailable"))
        with self.assertRaisesRegex(RuntimeError,"database unavailable"):
            self.prepare(consent=True,queue=queue)
        self.save.assert_not_called()

if __name__=="__main__":
    unittest.main()
