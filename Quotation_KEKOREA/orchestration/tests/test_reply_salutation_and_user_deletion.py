"""Synthetic regression for recipient greetings, opt-in duplicate sends and deletion.

No production data, real email, SMTP, AI API calls, or Storage operations.
"""
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from Quotation_KEKOREA.orchestration.workflows import email_reply_drafts as reply
from Quotation_KEKOREA.orchestration.workflows import email_outbox as outbox
from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailConfig, Endpoint


class RecipientGreetingTests(TestCase):
    def test_korean_surname_and_explicit_role(self):
        email={"sender": '"김철수 대표" <ceo@example.test>',
               "body": "안녕하세요.\n계약서 부탁드립니다."}
        self.assertEqual(reply.recipient_salutation(email,"ko"),"김철수 대표님께")
        self.assertEqual(reply.with_recipient_salutation(
            "안녕하세요.\n\n계약서 확인했습니다.",email,"ko"),
            "김철수 대표님께\n\n계약서 확인했습니다.")

    def test_korean_sender_with_pro_title_and_honorific(self):
        a={"sender": "박진우 프로님 <pro@example.test>", "body": "자료 부탁해요."}
        self.assertEqual(reply.recipient_salutation(a,"ko"),"박진우 프로님께")
        b={"sender": "박진우님 <pro@example.test>", "body": "자료 부탁해요."}
        self.assertEqual(reply.recipient_salutation(b,"ko"),"박진우님께")

    def test_english_named_reply_with_no_fabricated_title(self):
        a={"sender": "John Smith <john@example.test>", "body": "Please send the PI."}
        self.assertEqual(reply.recipient_salutation(a,"en"),"Dear John Smith,")
        self.assertEqual(reply.with_recipient_salutation(
            "Hello,\n\nThanks for your inquiry.",a,"en"),
            "Dear John Smith,\n\nThanks for your inquiry.")

    def test_explicit_mr_preserved(self):
        self.assertEqual(reply.recipient_salutation(
            {"sender": "Mr. David Lee <david@example.test>"},"en"
        ),"Dear Mr. David Lee,")

    def test_company_or_bare_mailbox_is_not_guessed_as_person(self):
        self.assertEqual(reply.recipient_salutation(
            {"sender": "ECLADO Sales <sales@example.test>"},"ko"),"안녕하세요.")
        self.assertEqual(reply.recipient_salutation(
            {"sender": "sales@example.test"},"en"),"Hello,")

    def test_named_signature_used_only_when_from_is_generic(self):
        a={"sender": "Company Sales <team@example.test>",
           "body": "Please advise.\n\nBest regards,\nJane Smith\nAccount Manager"}
        self.assertEqual(reply.recipient_salutation(a,"en"),"Dear Jane Smith,")
        # A different closing signature cannot override a named From header.
        a["sender"]="John Lee <john@example.test>"
        self.assertEqual(reply.recipient_salutation(a,"en"),"Dear John Lee,")

    def test_reapplying_does_not_duplicate_greeting(self):
        a={"sender": "Jane Doe <jane@example.test>"}
        first=reply.with_recipient_salutation("Thanks for your note.",a,"en")
        self.assertEqual(reply.with_recipient_salutation(first,a,"en"),first)

    def test_invalid_language(self):
        with self.assertRaises(ValueError):
            reply.recipient_salutation({"sender":"Jane Doe"},"invalid")


class UserOwnedOutboxOperations(TestCase):
    def setUp(self):
        self.owner="owner@example.test"
        self.identifier=str(uuid4())
        self.pop=Endpoint("pop.example.test",995,"ssl",self.owner,"private")
        self.smtp=Endpoint("smtp.example.test",587,"starttls",self.owner,"private")
        self.config=MailConfig(self.pop,self.smtp)
        self.original={
            "id":self.identifier,"owner_email":self.owner,
            "mailbox_hash":self.pop.account_id,"mail_uid":"mail1",
            "sender_header":"Jane Doe <jane@example.test>",
            "recipient_email":"jane@example.test",
            "source_subject":"Order question","source_body":"Hello, about our order.",
            "source_hash":"a"*64,"message_id":"<original@example.test>",
            "language":"en","status":"sent","approved_subject":"Re: Order question",
            "approved_body":"Dear Jane Doe,\n\nWe will check.\n\n"
                            +reply.default_signature("en"),
            "approved_sha256":"s"*64,"candidate_bodies":["one","two","three"],
        }

    def test_manual_repeat_creates_new_unapproved_draft_and_never_sends(self):
        repo=Mock()
        repo.request.side_effect=lambda method, table, **kw: [
            {**kw["payload"],"id":str(uuid4())}
        ] if method=="POST" else None
        with patch.object(outbox,"get_reply",return_value=self.original), \
             patch.object(outbox,"_repo",return_value=repo), \
             patch.object(outbox,"mail_config",return_value=self.config), \
             patch.object(outbox,"send_smtp") as send:
            draft=outbox.requeue_reply({},self.owner,self.identifier,{})
        self.assertEqual(draft["status"],"draft")
        self.assertIsNone(draft["approved_sha256"])
        self.assertEqual(draft["approved_body"],self.original["approved_body"])
        self.assertEqual(draft["approved_subject"],self.original["approved_subject"])
        self.assertNotEqual(draft["mail_uid"],self.original["mail_uid"])
        self.assertEqual(draft["owner_email"],self.owner)
        self.assertEqual(self.original["status"],"sent")
        send.assert_not_called()

    def test_user_can_deliberately_repeat_an_unknown_delivery(self):
        original=dict(self.original,status="send_unknown")
        repo=Mock()
        repo.request.return_value=[{**original,"id":str(uuid4()),
                                    "mail_uid":"manual-repeat-test","status":"draft"}]
        with patch.object(outbox,"get_reply",return_value=original), \
             patch.object(outbox,"_repo",return_value=repo), \
             patch.object(outbox,"mail_config",return_value=self.config):
            new=outbox.requeue_reply({},self.owner,self.identifier,{})
        self.assertEqual(new["status"],"draft")
        self.assertEqual(original["status"],"send_unknown")
        repo.request.assert_called_once()
        self.assertEqual(repo.request.call_args.args[:2],("POST",outbox.TABLE))

    def test_not_automatic_retry_and_cannot_copy_inflight(self):
        old=dict(self.original,status="sending")
        with patch.object(outbox,"get_reply",return_value=old), \
             patch.object(outbox,"_repo") as repo:
            with self.assertRaises(outbox.OutboxError):
                outbox.requeue_reply({},self.owner,self.identifier,{})
            repo.assert_not_called()

    def test_deletion_of_owned_sent_or_draft_record_is_explicit_and_scoped(self):
        for status in ("draft","sent","send_unknown"):
            with self.subTest(status=status):
                repo=Mock()
                repo.request.return_value=[dict(self.original,status=status)]
                with patch.object(outbox,"get_reply",return_value=dict(self.original,status=status)), \
                     patch.object(outbox,"_repo",return_value=repo):
                    outbox.delete_reply({},self.owner,self.identifier)
                kw=repo.request.call_args.kwargs
                self.assertEqual(repo.request.call_args.args[:2],("DELETE",outbox.TABLE))
                filters=dict(kw["query"])
                self.assertEqual(filters["owner_email"],"eq."+self.owner)
                self.assertEqual(filters["id"],"eq."+self.identifier)
                self.assertEqual(filters["status"],"eq."+status)

    def test_deleting_sending_is_rejected_without_mutation(self):
        repo=Mock()
        with patch.object(outbox,"get_reply",return_value=dict(self.original,status="sending")), \
             patch.object(outbox,"_repo",return_value=repo):
            with self.assertRaises(outbox.OutboxError):
                outbox.delete_reply({},self.owner,self.identifier)
        repo.assert_not_called()

    def test_deleting_wrong_owner_never_mutates(self):
        with patch.object(outbox,"get_reply",side_effect=outbox.OutboxError("not found")), \
             patch.object(outbox,"_repo") as repo:
            with self.assertRaises(outbox.OutboxError):
                outbox.delete_reply({},self.owner,self.identifier)
            repo.assert_not_called()


if __name__=="__main__":
    import unittest
    unittest.main()
