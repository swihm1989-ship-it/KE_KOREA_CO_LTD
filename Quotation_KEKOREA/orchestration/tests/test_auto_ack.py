"""Safety and transport regression tests for opt-in automated acknowledgements."""
import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from unittest.mock import Mock, patch

from Quotation_KEKOREA.orchestration.adapters.whois_mail import Endpoint, MailConfig, MailMessage, parse_message
from Quotation_KEKOREA.orchestration.mail_worker import auto_ack as ack


class AutomaticAckTests(unittest.TestCase):
    def setUp(self):
        self.smtp = Endpoint("smtp.example.test", 587, "starttls", "sales@example.test", "example-secret")
        self.pop = Endpoint("pop.example.test", 995, "ssl", "sales@example.test", "example-secret")
        self.config = MailConfig(self.pop, self.smtp)
        self.now = datetime.now(timezone.utc)
        self.values = {
            "MAIL_AUTO_ACK_ENABLED": "true", "MAIL_AUTO_ACK_SEND_ENABLED": "true",
            "MAIL_AUTO_ACK_NOT_BEFORE": (self.now - timedelta(minutes=3)).isoformat(),
            "MAIL_AUTO_ACK_ALLOWED_SENDERS": "buyer@example.test",
        }
        self.policy = ack.load_policy(self.values, self.config)
        self.message = MailMessage("uid-1", "Buyer <buyer@example.test>", "Price inquiry",
             "Please confirm receipt. Do not make a price offer.", self.now.strftime("%a, %d %b %Y %H:%M:%S +0000"),
             message_id="<one@example.test>")

    def test_disabled_by_default_and_rejects_partial_opt_in(self):
        self.assertIsNone(ack.load_policy({}, self.config))
        self.assertIsNone(ack.load_policy({**self.values, "MAIL_AUTO_ACK_SEND_ENABLED": "false"}, self.config))
        for change in (
            {"MAIL_AUTO_ACK_ALLOWED_SENDERS": "*@example.test"},
            {"MAIL_AUTO_ACK_ALLOWED_SENDERS": ""},
            {"MAIL_AUTO_ACK_NOT_BEFORE": ""},
            {"MAIL_AUTO_ACK_DAILY_LIMIT": "11"},
        ):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                ack.load_policy(self.values | change, self.config)

    def test_receipt_response_is_fixed_and_never_approves_prices(self):
        reply = ack.make_ack(self.message, self.smtp.username, self.policy, now=self.now)
        self.assertEqual(reply.recipient, "buyer@example.test")
        self.assertEqual(reply.subject, "Re: Price inquiry")
        self.assertEqual(reply.in_reply_to, "<one@example.test>")
        self.assertNotIn("Please confirm receipt", reply.body)
        self.assertIn("not a quotation", reply.body)
        korean = MailMessage("uid-2", self.message.sender, "발주 문의", "안녕하세요.",
            self.message.received_at, message_id="<two@example.test>")
        self.assertIn("자동 접수", ack.make_ack(korean, self.smtp.username, self.policy, now=self.now).body)

    def test_skips_suspicious_or_outdated_messages(self):
        scenarios = [
            {"sender": "Unknown <stranger@example.test>"},
            {"sender": "sales@example.test"},
            {"reply_to": "attacker@example.test"},
            {"message_id": ""},
            {"message_id": "bad-value"},
            {"auto_submitted": "auto-replied"},
            {"list_id": "<list.example.test>"},
            {"precedence": "bulk"},
            {"body": ""},
            {"notice": "unreadable"},
            {"attachments": (Mock(),)},
            {"received_at": (self.now - timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S +0000")},
            {"received_at": "not a valid date"},
            {"subject": "hello\r\nCc: attacker@example.test"},
        ]
        for diff in scenarios:
            data = {name: getattr(self.message, name) for name in self.message.__dataclass_fields__}
            data.update(diff)
            with self.subTest(diff=diff):
                self.assertIsNone(ack.make_ack(MailMessage(**data),self.smtp.username,self.policy,now=self.now))

    def test_parser_keeps_message_id_and_auto_reply_headers(self):
        msg = EmailMessage()
        msg["From"] = "Buyer <buyer@example.test>"
        msg["Message-ID"] = "<source@example.test>"
        msg["Auto-Submitted"] = "auto-generated"
        msg["List-ID"] = "<updates.example.test>"
        msg["Date"] = self.message.received_at
        msg.set_content("hello")
        parsed = parse_message("uid-new", msg.as_bytes())
        self.assertEqual(parsed.message_id, "<source@example.test>")
        self.assertEqual(parsed.auto_submitted, "auto-generated")
        self.assertIsNone(ack.make_ack(parsed,self.smtp.username,self.policy,now=self.now))

    def test_tls_before_auth_and_no_unencrypted_fallback(self):
        client = Mock()
        with patch.object(ack.smtplib, "SMTP", return_value=client):
            reply = ack.make_ack(self.message,self.smtp.username,self.policy,now=self.now)
            ack.send_ack(self.smtp, reply)
        names = [c[0] for c in client.method_calls]
        self.assertLess(names.index("starttls"), names.index("login"))
        self.assertLess(names.index("login"), names.index("send_message"))
        envelope = client.send_message.call_args.args[0]
        self.assertEqual(envelope["Auto-Submitted"], "auto-replied")
        self.assertEqual(envelope["In-Reply-To"], "<one@example.test>")
        self.assertEqual(envelope["To"], "buyer@example.test")

    def test_smtp_error_redacted_and_never_retried(self):
        client = Mock()
        client.send_message.side_effect = OSError("example-secret private result")
        with patch.object(ack.smtplib, "SMTP", return_value=client):
            with self.assertRaisesRegex(Exception,"outcome uncertain") as err:
                ack.send_ack(self.smtp, ack.make_ack(self.message,self.smtp.username,self.policy,now=self.now))
        self.assertNotIn("example-secret",str(err.exception))
        self.assertEqual(client.send_message.call_count,1)

    def test_worker_sql_has_durable_one_shot_claim(self):
        self.assertIn("on conflict(account,uidl) do nothing", ack.ENQUEUE)
        self.assertIn("for update skip locked", ack.CLAIM)
        self.assertIn("status='claimed'", ack.CLAIM)
        from pathlib import Path
        sql = (Path(__file__).resolve().parents[1] / "mail_worker" / "schema.sql").read_text()
        self.assertIn("unique(account,uidl)", sql)
        self.assertIn("send_unknown", sql)
        self.assertIn("enable row level security", sql.lower())


if __name__ == "__main__":
    unittest.main()
