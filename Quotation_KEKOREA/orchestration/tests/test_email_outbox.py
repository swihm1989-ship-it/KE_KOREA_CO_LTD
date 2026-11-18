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
