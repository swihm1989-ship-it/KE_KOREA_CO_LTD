"""Guard the live mailbox -> AI intake -> reply outbox handoff.

Synthetic mail, mock persistence, no real user data, AI provider or SMTP.
A previously hard-coded v2 revision in the intake page blocked v3 before
the database draft was queued.
"""
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailMessage
from Quotation_KEKOREA.orchestration.tests.test_whois_mail import CONFIG
from Quotation_KEKOREA.orchestration.workflows import email_reply_runtime


ORCH = Path(__file__).resolve().parents[1]
PAGE = ORCH / "ui" / "streamlit_page.py"


class MasterReplyRevisionSyncTests(unittest.TestCase):
    def test_ui_reply_expected_revisions_match_deployed_runtime(self):
        expected = email_reply_runtime.REPLY_RUNTIME_REVISION
        for path in (ORCH / "ui" / "ai_intake_page.py",
                     ORCH / "ui" / "streamlit_page.py"):
            with self.subTest(file=path.name):
                source = path.read_text(encoding="utf-8")
                versions = re.findall(r'_expected_reply_revision\s*=\s*"([^"]+)"', source)
                self.assertEqual(versions, [expected],
                                 "Every UI route must accept the same reply runtime revision")
        from Quotation_KEKOREA.orchestration.workflows import (
            email_reply_handoff, email_reply_drafts,
        )
        from Quotation_KEKOREA.orchestration.ui import email_outbox_page
        for module in (email_reply_drafts, email_reply_handoff, email_outbox_page):
            self.assertEqual(module.REPLY_RUNTIME_REVISION, expected)

    def test_mail_without_documents_is_queued_by_explicit_ui_click(self):
        """Click actual AI 업무 요청 button, not just a helper unit test."""
        mail = MailMessage(
            uid="synthetic-mail-no-docs", sender="Jane Doe <jane@example.test>",
            subject="Quick scheduling question",
            body="Could you confirm whether a call next week is possible?",
        )
        saved = {"id":"d2a41c7f-2a0a-46e4-8401-85aa6efac019",
                 "status":"draft", "candidate_bodies":[],
                 "source_subject":mail.subject,"source_body":mail.body}
        with (
            patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                  return_value="owner@example.test"),
            patch("Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
                  return_value=([], None)),
            patch("Quotation_KEKOREA.orchestration.ui.mailbox_page._settings",
                  return_value=CONFIG),
            patch("Quotation_KEKOREA.orchestration.ui.mailbox_page.fetch_messages",
                  return_value=(mail,)),
            patch.object(email_reply_runtime, "prepare_email_handoff",
                         return_value=(saved, None)) as handoff,
            patch("Quotation_KEKOREA.orchestration.ui.email_outbox_page.render_email_outbox"),
            patch("Quotation_KEKOREA.orchestration.ui.pdf_archive_page.render_pdf_archive"),
        ):
            app = AppTest.from_file(str(PAGE), default_timeout=35).run()
            app.radio(key="master_page").set_value("메일함").run()
            # The real mailbox intentionally requires an explicit first
            # POP refresh before a selected message/action is rendered.
            app.button(key="whois_refresh").click().run()
            app.button(key="whois_ai_synthetic-mail-no-docs").click().run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertFalse(app.checkbox(key="ai_mail_reply_consent").value)
            self.assertTrue(app.button(key="ai_mail_reply_queue").disabled)
            handoff.assert_not_called()
            app.checkbox(key="ai_mail_reply_consent").check().run()
            self.assertFalse(app.button(key="ai_mail_reply_queue").disabled)
            app.button(key="ai_mail_reply_queue").click().run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertFalse(any("런타임 버전" in str(x.message) for x in app.error))
            self.assertEqual(app.session_state["master_page"], "발송 대기")
            self.assertEqual(app.session_state["master_reply_selected"], saved["id"])
            handoff.assert_called_once()
            self.assertEqual(handoff.call_args.kwargs["ai_consented"], True)
            self.assertEqual(handoff.call_args.args[2]["body"], mail.body)


if __name__ == "__main__":
    unittest.main()
