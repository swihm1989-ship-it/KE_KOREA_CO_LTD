"""FINAL PDF mail attachment regression tests; synthetic data only."""
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from Quotation_KEKOREA.orchestration.workflows import (
    email_outbox as outbox,
    mail_pdf_attachments as attachments,
)
from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailConfig, PopConfig, SmtpConfig


class MailPdfAttachmentTests(TestCase):
    def setUp(self):
        self.owner = "owner@example.test"
        self.outbox_id = str(uuid4())
        self.pdf_id = str(uuid4())

    def test_link_requires_current_owner_draft_and_final(self):
        reply = {"id": self.outbox_id, "status": "draft"}
        repo = Mock()
        repo.request.side_effect = [
            [{"id": self.pdf_id, "status": "final"}],
            None,
        ]
        with patch.object(attachments, "get_reply", return_value=reply), \
             patch.object(attachments, "_repo", return_value=repo):
            attachments.link_final_pdf({}, self.owner, self.outbox_id, self.pdf_id)
        self.assertEqual(repo.request.call_args.args[:2], ("POST", attachments.TABLE))
        self.assertEqual(repo.request.call_args.kwargs["payload"]["owner_email"], self.owner)

        with patch.object(attachments, "get_reply",
                          return_value={"status": "sent"}), \
             patch.object(attachments, "_repo") as db:
            with self.assertRaises(outbox.OutboxError):
                attachments.link_final_pdf({}, self.owner, self.outbox_id, self.pdf_id)
            db.assert_not_called()

    def test_verified_bytes_and_digest_invalidate_after_change(self):
        doc = {"id": self.pdf_id, "filename": "PI-FINAL.pdf",
               "kind": "PI", "status": "final", "content_sha256": "a"*64}
        stamp = attachments.attachment_digest([doc])
        with patch.object(attachments, "list_attachments", return_value=[doc]), \
             patch.object(attachments.pdf_archive, "load_pdf",
                          return_value=({**doc}, b"%PDF-1.4\nexample")):
            loaded = attachments.load_approved_attachments(
                {}, self.owner, self.outbox_id, stamp)
        self.assertEqual(loaded[0]["filename"], "PI-FINAL.pdf")
        self.assertTrue(loaded[0]["data"].startswith(b"%PDF"))
        with patch.object(attachments, "list_attachments", return_value=[]):
            with self.assertRaises(outbox.OutboxError):
                attachments.load_approved_attachments(
                    {}, self.owner, self.outbox_id, stamp)

    def test_smtp_mime_contains_actual_pdf_attachment(self):
        from types import SimpleNamespace
        smtp = SimpleNamespace(host="smtp.example.test", port=587,
                               security="starttls", username="owner@example.test",
                               password="dummy")
        config = SimpleNamespace(smtp=smtp)
        client = Mock()
        with patch.object(outbox.smtplib, "SMTP", return_value=client):
            outbox.send_smtp(
                config, "buyer@example.test", "Re: PI", "Attached.",
                attachments=[{"filename": "PI-FINAL.pdf", "data": b"%PDF-1.4\nsynthetic"}])
        client.send_message.assert_called_once()
        message = client.send_message.call_args.args[0]
        pdfs = [part for part in message.iter_attachments()
                if part.get_content_type() == "application/pdf"]
        self.assertEqual(len(pdfs), 1)
        self.assertEqual(pdfs[0].get_filename(), "PI-FINAL.pdf")
        self.assertEqual(pdfs[0].get_payload(decode=True), b"%PDF-1.4\nsynthetic")

    def test_wrong_attachment_digest_blocks_before_claim_and_smtp(self):
        reply = {
            "id": self.outbox_id, "owner_email": self.owner,
            "status": "draft", "mailbox_hash": "synthetic-account",
            "candidate_bodies": [], "message_id": "",
        }
        config = SimpleNamespace(
            pop=SimpleNamespace(account_id="synthetic-account"),
            smtp=SimpleNamespace(username=self.owner))
        with patch.object(outbox, "get_reply", return_value=reply), \
             patch.object(outbox, "mail_config", return_value=config), \
             patch.object(attachments, "load_approved_attachments",
                          side_effect=outbox.OutboxError("changed")), \
             patch.object(outbox, "_repo") as db:
            transport = Mock()
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({}, self.owner, self.outbox_id, {},
                                     "buyer@example.test", "Re: PI", "Reply",
                                     confirmed=True, expected_attachment_digest="stale",
                                     transport=transport)
            transport.assert_not_called()
            db.assert_not_called()
