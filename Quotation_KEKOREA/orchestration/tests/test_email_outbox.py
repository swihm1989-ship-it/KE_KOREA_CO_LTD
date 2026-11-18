import unittest
from unittest.mock import Mock,patch
from uuid import uuid4
from pathlib import Path

from Quotation_KEKOREA.orchestration.adapters.whois_mail import Endpoint,MailConfig,MailMessage
from Quotation_KEKOREA.orchestration.workflows import email_outbox as outbox
from Quotation_KEKOREA.orchestration.workflows.mail_intake import queue_handoff

class MemoryRepo:
    def __init__(self,row=None):
        self.row=row
        self.events=[]
    def request(self,method,table,*,payload=None,query=None,headers=None):
        self.events.append((method,table,payload,query))
        params=dict(query or [])
        if method=="GET":
            return [self.row] if self.row and params.get("owner_email")=="eq."+self.row["owner_email"] else []
        if method=="PATCH":
            if self.row is None or params.get("status")!="eq."+self.row["status"]:
                return []
            self.row.update(payload)
            return [dict(self.row)]
        if method=="POST":
            if self.row is None:
                self.row={**payload,"id":str(uuid4()),"candidate_bodies":[],"status":"draft"}
            return []
        raise AssertionError((method,table))

class EmailOutboxTests(unittest.TestCase):
    def setUp(self):
        self.owner="owner@example.test"
        self.pop=Endpoint("pop.example.test",995,"ssl","owner@example.test","secret")
        self.smtp=Endpoint("smtp.example.test",587,"starttls","owner@example.test","secret")
        self.config=MailConfig(self.pop,self.smtp)
        self.row={
            "id":str(uuid4()),"owner_email":self.owner,
            "mailbox_hash":self.pop.account_id,"mail_uid":"u1",
            "source_hash":"a"*64,"status":"draft",
            "candidate_bodies":["Candidate 1 text","Candidate 2 text","Candidate 3 text"],
            "message_id":"<parent@example.test>"
        }
    def test_owner_and_confirmation_gate(self):
        db=MemoryRepo(dict(self.row));transport=Mock()
        with patch.object(outbox,"_repo",return_value=db),patch.object(outbox,"mail_config",return_value=self.config):
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},"buyer@example.test","Re: Hello",
                                     "Test message",confirmed=False,transport=transport)
            self.assertFalse(any(e[0]=="PATCH" for e in db.events))
            transport.assert_not_called()
            result=outbox.send_approved({},self.owner,self.row["id"],{},"buyer@example.test","Re: Hello",
                                         "Test message",confirmed=True,transport=transport)
            self.assertEqual(result["status"],"sent")
            transport.assert_called_once()
            self.assertEqual(db.row["status"],"sent")
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},"buyer@example.test","Re: Hello",
                                     "Test message",confirmed=True,transport=transport)
            transport.assert_called_once()

    def test_manual_reply_allowed_when_ai_is_unavailable(self):
        # AI model errors must not prevent a fully human-written, explicitly
        # approved reply, and must never trigger an automatic SMTP call.
        row=dict(self.row)
        row["candidate_bodies"]=[]
        db=MemoryRepo(row)
        transport=Mock()
        from Quotation_KEKOREA.orchestration.workflows.email_reply_drafts import default_signature
        signature=default_signature("ko")
        composed="문의 확인 후 회신드리겠습니다.\n\n"+signature
        with patch.object(outbox,"_repo",return_value=db), \
             patch.object(outbox,"mail_config",return_value=self.config):
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},
                    "buyer@example.test","Re: 문의",composed,confirmed=False,
                    signature_text=signature,language="ko",transport=transport)
            transport.assert_not_called()
            result=outbox.send_approved({},self.owner,self.row["id"],{},
                "buyer@example.test","Re: 문의",composed,confirmed=True,
                signature_text=signature,language="ko",transport=transport)
        self.assertEqual(result["status"],"sent")
        self.assertEqual(db.row["status"],"sent")
        self.assertEqual(transport.call_count,1)

    def test_ambiguous_smtp_result_does_not_retry(self):
        db=MemoryRepo(dict(self.row))
        sender=Mock(side_effect=OSError("provider may have accepted"))
        with patch.object(outbox,"_repo",return_value=db),patch.object(outbox,"mail_config",return_value=self.config):
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},"buyer@example.test","Re: Hello",
                                     "Test message",confirmed=True,transport=sender)
            self.assertEqual(db.row["status"],"send_unknown")
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},"buyer@example.test","Re: Hello",
                                     "Test message",confirmed=True,transport=sender)
            sender.assert_called_once()

    def test_html_signature_is_only_built_after_explicit_send_approval(self):
        from Quotation_KEKOREA.orchestration.workflows.email_reply_drafts import default_signature
        db = MemoryRepo(dict(self.row))
        transport = Mock()
        signature = default_signature("ko")
        complete = "안녕하세요. 확인하겠습니다.\n\n" + signature
        with patch.object(outbox, "_repo", return_value=db), \
             patch.object(outbox, "mail_config", return_value=self.config):
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({}, self.owner, self.row["id"], {},
                    "buyer@example.test", "Re: Hello", complete,
                    confirmed=False, signature_text=signature, language="ko",
                    transport=transport)
            transport.assert_not_called()
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({}, self.owner, self.row["id"], {},
                    "buyer@example.test", "Re: Hello", "Other text",
                    confirmed=True, signature_text=signature, language="ko",
                    transport=transport)
            transport.assert_not_called()
            self.assertEqual(db.row["status"], "draft")
            response = outbox.send_approved({}, self.owner, self.row["id"], {},
                "buyer@example.test", "Re: Hello", complete,
                confirmed=True, signature_text=signature, language="ko",
                transport=transport)
            self.assertEqual(response["status"], "sent")
        transport.assert_called_once()
        self.assertIn("html_body", transport.call_args.kwargs)
        self.assertIn("cid:ke-korea-signature-logo",
                      transport.call_args.kwargs["html_body"])
        self.assertTrue(transport.call_args.kwargs["logo_bytes"].startswith(b"\x89PNG"))
        self.assertIn("www.ke-korea.co.kr", transport.call_args.args[3])
        self.assertEqual(db.row["approved_body"], complete)

    def test_tls_smtp_and_threading(self):
        client=Mock()
        with patch.object(outbox.smtplib,"SMTP",return_value=client):
            outbox.send_smtp(self.config,"buyer@example.test","Re: Inquiry","Hello",
                             "<parent@example.test>")
        methods=[entry[0] for entry in client.method_calls]
        self.assertLess(methods.index("starttls"),methods.index("login"))
        self.assertLess(methods.index("login"),methods.index("send_message"))
        msg=client.send_message.call_args.args[0]
        self.assertEqual(msg["In-Reply-To"],"<parent@example.test>")
        self.assertEqual(msg["To"],"buyer@example.test")


    def test_smtp_connect_error_is_certainly_before_data(self):
        with patch.object(outbox.smtplib,"SMTP",
                          side_effect=ConnectionRefusedError("fake-private-host")):
            with self.assertRaises(outbox.SMTPBeforeDataError) as error:
                outbox.send_smtp(self.config,"buyer@example.test",
                                 "Re: Test","Test")
        self.assertEqual(error.exception.stage,"connect")
        self.assertIn("메일은 전송되지 않았습니다",str(error.exception))
        self.assertNotIn("fake-private-host",str(error.exception))

    def test_smtp_login_rejection_restores_draft_without_duplicate_send(self):
        import smtplib
        db=MemoryRepo(dict(self.row))
        client=Mock()
        client.login.side_effect=smtplib.SMTPAuthenticationError(
            535,b"synthetic-private-user")
        with patch.object(outbox,"_repo",return_value=db), \
             patch.object(outbox,"mail_config",return_value=self.config), \
             patch.object(outbox.smtplib,"SMTP",return_value=client):
            with self.assertRaises(outbox.SMTPBeforeDataError) as error:
                outbox.send_approved({},self.owner,self.row["id"],{},
                    "buyer@example.test","Re: Hello","Test message",
                    confirmed=True,transport=outbox.send_smtp)
        self.assertIn("SMTP 인증 실패",str(error.exception))
        self.assertIn("535",str(error.exception))
        self.assertNotIn("synthetic-private-user",str(error.exception))
        self.assertEqual(db.row["status"],"draft")
        self.assertIsNone(db.row["send_started_at"])
        self.assertIsNone(db.row["approved_sha256"])
        self.assertIsNone(db.row["approved_body"])
        client.send_message.assert_not_called()

    def test_tls_failure_keeps_editable_draft(self):
        db=MemoryRepo(dict(self.row))
        client=Mock()
        client.starttls.side_effect=OSError("private-route")
        with patch.object(outbox,"_repo",return_value=db), \
             patch.object(outbox,"mail_config",return_value=self.config), \
             patch.object(outbox.smtplib,"SMTP",return_value=client):
            with self.assertRaises(outbox.SMTPBeforeDataError) as error:
                outbox.send_approved({},self.owner,self.row["id"],{},
                    "buyer@example.test","Re: Hello","Test message",
                    confirmed=True,transport=outbox.send_smtp)
        self.assertEqual(db.row["status"],"draft")
        self.assertIn("starttls",str(error.exception))
        self.assertNotIn("private-route",str(error.exception))
        client.login.assert_not_called()
        client.send_message.assert_not_called()

    def test_timeout_inside_send_message_remains_unknown_and_locked(self):
        db=MemoryRepo(dict(self.row))
        client=Mock()
        client.send_message.side_effect=TimeoutError("server may have accepted")
        with patch.object(outbox,"_repo",return_value=db), \
             patch.object(outbox,"mail_config",return_value=self.config), \
             patch.object(outbox.smtplib,"SMTP",return_value=client):
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},
                    "buyer@example.test","Re: Hello","Test message",
                    confirmed=True,transport=outbox.send_smtp)
            self.assertEqual(db.row["status"],"send_unknown")
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},
                    "buyer@example.test","Re: Hello","Test message",
                    confirmed=True,transport=outbox.send_smtp)
        client.send_message.assert_called_once()
        self.assertIsNotNone(db.row["send_started_at"])

    def test_older_unknown_record_is_never_reset_by_predata_fix(self):
        row=dict(self.row,status="send_unknown",send_started_at="2026-11-18T07:16:08Z")
        db=MemoryRepo(row)
        sender=Mock()
        with patch.object(outbox,"_repo",return_value=db), \
             patch.object(outbox,"mail_config",return_value=self.config):
            with self.assertRaises(outbox.OutboxError):
                outbox.send_approved({},self.owner,self.row["id"],{},
                    "buyer@example.test","Re: Hello","Test message",
                    confirmed=True,transport=sender)
        self.assertEqual(db.row["status"],"send_unknown")
        sender.assert_not_called()

    def test_no_header_injection(self):
        for input_ in ("person@example.com\r\nBcc:bad@example.com","two@example.com,other@example.com","bad"):
            with self.subTest(input_=input_),self.assertRaises(ValueError):
                outbox.email_address(input_)
        self.assertEqual(outbox.email_address("Someone <buyer@example.test>"),"buyer@example.test")

    def test_queue_without_documents_keeps_mail_metadata(self):
        source=MailMessage("unique-mail","Person <buyer@example.test>","Meeting",
                           "Thank you. Please reply.",message_id="<message@example.test>")
        state={}
        queue_handoff(state,source,requested=(),navigate=True)
        item=state["ai_intake_mail_source"]
        self.assertEqual(item["kinds"],[])
        self.assertEqual(item["uid"],"unique-mail")
        self.assertEqual(item["message_id"],"<message@example.test>")
        self.assertIn("Please reply",item["body"])

    def test_sql_has_no_automatic_send_or_public_read(self):
        sql=(Path(__file__).resolve().parents[1]/"sql"/"master_mail_outbox.sql").read_text()
        self.assertIn("enable row level security",sql.lower())
        self.assertIn("revoke all",sql.lower())
        self.assertNotIn("create trigger",sql.lower())
        self.assertNotIn("create function",sql.lower())
        self.assertNotIn("cron.schedule",sql.lower())

if __name__=="__main__":
    unittest.main()
