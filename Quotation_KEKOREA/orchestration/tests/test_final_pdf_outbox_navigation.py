"""Synthetic final-PDF -> outbox navigation checks; never sends SMTP."""
from hashlib import sha256
from unittest import TestCase
from unittest.mock import patch

from Quotation_KEKOREA.orchestration.ui import ai_intake_page as intake


class FinalPdfOutboxNavigationTests(TestCase):
    def setUp(self):
        self.data=b"%PDF-1.4\nsynthetic"
        self.files={"pdf":{"filename":"PI_KE-KOREA.pdf","content":self.data}}
        self.id="00000000-0000-4000-8000-000000000001"

    def test_click_navigates_only_to_matching_draft_without_sending(self):
        state={"master_final_pdf_outbox_handoff":{"PI":{
            "reply_id":self.id,
            "sha256":sha256(self.data).hexdigest(),
        }}}
        with patch.object(intake.st,"session_state",state), \
             patch.object(intake.st,"button",return_value=True) as button, \
             patch.object(intake.st,"rerun") as rerun:
            intake._show_final_pdf_outbox_button("PI",self.files,"source-1")
        self.assertEqual(state["master_reply_selected"],self.id)
        self.assertEqual(state["master_reply_select_pending"],self.id)
        self.assertTrue(state["master_reply_navigation_pending"])
        button.assert_called_once()
        rerun.assert_called_once()

    def test_no_source_mail_or_stale_pdf_never_exposes_button(self):
        for handoff in ({}, {"PI":{"reply_id":self.id,"sha256":"0"*64}}):
            with self.subTest(handoff=handoff), \
                 patch.object(intake.st,"session_state",
                              {"master_final_pdf_outbox_handoff":handoff}), \
                 patch.object(intake.st,"button") as button, \
                 patch.object(intake.st,"rerun") as rerun:
                intake._show_final_pdf_outbox_button("PI",self.files,"source-1")
                button.assert_not_called()
                rerun.assert_not_called()

    def test_contract_and_trade_share_same_navigation_control(self):
        for kind in ("PI","PO","CI","PL","CONTRACT"):
            state={"master_final_pdf_outbox_handoff":{kind:{
                "reply_id":self.id,"sha256":sha256(self.data).hexdigest()}}}
            with patch.object(intake.st,"session_state",state), \
                 patch.object(intake.st,"button",return_value=False) as button:
                intake._show_final_pdf_outbox_button(kind,self.files,kind)
                self.assertIn("발송 대기",button.call_args.args[0])
