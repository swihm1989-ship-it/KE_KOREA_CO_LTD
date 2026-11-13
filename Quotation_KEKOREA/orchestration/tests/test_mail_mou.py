"""Synthetic-only regression cases for MoU routing and manual overrides."""
import unittest
from types import SimpleNamespace

from Quotation_KEKOREA.orchestration.router import classify
from Quotation_KEKOREA.orchestration.workflows.mail_intake import (
    prepare_mail_request, queue_handoff, consume_pending,
)


class MoUMailRoutingTests(unittest.TestCase):
    def test_mou_aliases_and_exact_request(self):
        for expression in (
            "MoU", "MOU", "M.O.U.", "Memorandum of Understanding",
            "양해각서", "양해 각서", "M.\nO.\nU.",
            "Memorandum\nof\nUnderstanding", "양해\n각서",
        ):
            with self.subTest(expression=expression):
                self.assertEqual(classify("", expression), ["CONTRACT"])
                request = prepare_mail_request("", expression + " 작성 부탁드립니다")
                self.assertEqual(request.kinds, ("CONTRACT",))
                self.assertIn(expression, request.instruction)

    def test_realistic_bipv_request(self):
        request = prepare_mail_request(
            "BIPV 설치 관련", "BIPV 설치 관련 MoU 작성 수정안 부탁드립니다"
        )
        self.assertEqual(request.kinds, ("CONTRACT",))

    def test_final_period_does_not_suppress_other_document(self):
        request = prepare_mail_request(
            "", "Please prepare M.O.U. No need for PI. Please prepare PO."
        )
        self.assertEqual(request.kinds, ("PO", "CONTRACT"))

    def test_mou_negation_and_history(self):
        request = prepare_mail_request(
            "Re: BIPV", "M.O.U.는 필요 없습니다. 발주서만 작성해 주세요."
        )
        self.assertEqual(request.kinds, ("PO",))

    def test_manual_override_handoff_and_no_auto_approval(self):
        message = SimpleNamespace(subject="BIPV project", body="Please revise the project document")
        self.assertFalse(prepare_mail_request(message.subject, message.body).kinds)
        state = {"ai_intake_candidates": "stale", "master_legacy_files": "old"}
        queue_handoff(state, message, extract=True, requested=["CONTRACT"])
        self.assertEqual(state["ai_intake_mail_source"]["kinds"], ["CONTRACT"])
        self.assertEqual(state["master_page"], "AI 업무 요청")
        self.assertTrue(state["ai_intake_consent"])
        self.assertNotIn("master_legacy_files", state)
        self.assertTrue(consume_pending(state, state["ai_intake_instruction"]))
        self.assertFalse(consume_pending(state, state["ai_intake_instruction"]))

    def test_override_cannot_select_unsupported_kind(self):
        state = {}
        message = SimpleNamespace(subject="Test", body="Synthetic test body")
        queue_handoff(state, message, extract=True, requested=["MOU"])
        self.assertFalse(state["ai_intake_consent"])
        self.assertNotIn("ai_intake_mail_pending", state)

    def test_original_newlines_preserved_in_ai_instruction(self):
        body = "BIPV 설치\nMemorandum\nof\nUnderstanding\n수정 요청"
        req = prepare_mail_request("", body)
        self.assertIn(body, req.instruction)
        self.assertEqual(req.kinds, ("CONTRACT",))


if __name__ == "__main__":
    unittest.main()
