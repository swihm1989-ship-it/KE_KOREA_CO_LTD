"""Corporate HTML signature regressions; no network or SMTP calls."""
import unittest
from email.message import EmailMessage
from unittest.mock import Mock, patch

from Quotation_KEKOREA.orchestration.workflows import (
    email_signature_design as design,
    email_reply_drafts as drafts,
    email_outbox as outbox,
)
from Quotation_KEKOREA.orchestration.adapters.whois_mail import Endpoint, MailConfig


class EmailSignatureDesignTests(unittest.TestCase):
    def test_korean_defaults_and_website(self):
        sig = drafts.default_signature("ko")
        self.assertEqual(sig, (
            "임석원 (David Seokwon Ihm)\n"
            "대표이사 (Managing Director)\n"
            "(주)케이이코리아\n"
            "서울특별시 영등포구 양평로 157, 1510호\n"
            "www.ke-korea.co.kr"
        ))
        html = design.signature_html("안녕하세요.\n확인하겠습니다.", sig,
                                     logo_src="cid:" + design.LOGO_CID)
        self.assertIn("임석원", html)
        self.assertIn("(주)케이이코리아", html)
        self.assertIn("border-top:1px solid", html)
        self.assertIn('src="cid:ke-korea-signature-logo"', html)
        self.assertIn('href="https://www.ke-korea.co.kr"', html)
        self.assertLess(html.index("(주)케이이코리아"), html.index("www.ke-korea.co.kr"))

    def test_english_signature_has_same_company_brand_and_site(self):
        sig = drafts.default_signature("en")
        html = design.signature_html("Hello.", sig, logo_src="cid:" + design.LOGO_CID)
        self.assertIn("David Seokwon Ihm", html)
        self.assertIn("Managing Director", html)
        self.assertIn("#1510, 157 Yangpyung Ro", html)
        self.assertIn("www.ke-korea.co.kr", html)
        self.assertNotIn("(주)케이이코리아", html)

    def test_dynamic_html_is_escaped(self):
        sig = "Test <b> person\nDirector\nCompany & Sons\nStreet <script>hack()</script>\nwww.ke-korea.co.kr"
        html = design.signature_html("<script>attack()</script>", sig,
                                     logo_src="cid:" + design.LOGO_CID)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp; Sons", html)

    def test_packaged_logo_is_valid_compact_png(self):
        data = design.optimized_logo()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertLessEqual(len(data), 300000)
        self.assertTrue(design.LOGO_PATH.is_file())

    def test_smtp_produces_plain_text_html_and_inline_logo(self):
        pop = Endpoint("pop.example.test",995,"ssl","owner@example.test","test-only")
        smtp = Endpoint("smtp.example.test",587,"starttls","owner@example.test","test-only")
        conf = MailConfig(pop,smtp)
        logo = design.optimized_logo()
        sig = drafts.default_signature("ko")
        html = design.delivery_signature_html("안녕하세요",sig)
        client = Mock()
        with patch.object(outbox.smtplib, "SMTP", return_value=client):
            outbox.send_smtp(conf,"buyer@example.test","Re: Hello",
                             "안녕하세요\n\n"+sig,"<parent@example.test>",
                             html_body=html,logo_bytes=logo)
        message = client.send_message.call_args.args[0]
        self.assertTrue(message.is_multipart())
        self.assertEqual(message.get_body(preferencelist=("plain",)).get_content(),
                         "안녕하세요\n\n"+sig+"\n")
        actual_html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn('cid:ke-korea-signature-logo', actual_html)
        self.assertIn('href="https://www.ke-korea.co.kr"', actual_html)
        image_parts = [m for m in message.walk() if m.get_content_type()=="image/png"]
        self.assertEqual(len(image_parts),1)
        self.assertEqual(image_parts[0]["Content-ID"],"<ke-korea-signature-logo>")
        self.assertEqual(image_parts[0].get_content_disposition(),"inline")
        self.assertEqual(image_parts[0].get_payload(decode=True),logo)
        self.assertEqual(client.send_message.call_count,1)

    def test_bad_logo_fails_before_any_smtp_connection(self):
        pop = Endpoint("pop.example.test",995,"ssl","owner@example.test","test-only")
        smtp = Endpoint("smtp.example.test",587,"starttls","owner@example.test","test-only")
        conf = MailConfig(pop,smtp)
        client = Mock()
        with patch.object(outbox.smtplib,"SMTP",return_value=client),self.assertRaises(outbox.OutboxError):
            outbox.send_smtp(conf,"buyer@example.test","Re: Hello","Text",
                             html_body=design.delivery_signature_html("Text",drafts.default_signature("ko")),
                             logo_bytes=b"not-an-image")
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
