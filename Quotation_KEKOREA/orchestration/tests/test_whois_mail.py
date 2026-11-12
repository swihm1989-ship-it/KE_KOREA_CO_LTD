import unittest
from email.message import EmailMessage
from unittest.mock import Mock, patch
from Quotation_KEKOREA.orchestration.adapters import whois_mail as mail

CONFIG = {'WHOIS_MAIL_OWNER_EMAILS':'owner@example.com',
          'WHOIS_POP_HOST':'pop.example.com','WHOIS_POP_PORT':'995','WHOIS_POP_SECURITY':'ssl',
          'WHOIS_POP_USERNAME':'sales@example.com','WHOIS_POP_PASSWORD':'private-test-password',
          'WHOIS_SMTP_HOST':'smtp.example.com','WHOIS_SMTP_PORT':'587','WHOIS_SMTP_SECURITY':'starttls',
          'WHOIS_SMTP_USERNAME':'sales@example.com','WHOIS_SMTP_PASSWORD':'private-test-password'}

def message():
    m = EmailMessage()
    m['From']='Buyer <buyer@example.test>'
    m['Subject']='PI request'
    m['Date']='Thu, 12 Nov 2026 14:00:00 +0900'
    m.set_content('Please prepare PI for 100 PCS. 수량 확인')
    m.add_attachment(b'example',maintype='application',subtype='pdf',filename='../../sample.pdf')
    return m.as_bytes()

class WhoisMailTests(unittest.TestCase):
    def test_owner_allowlist_is_separate_and_required(self):
        for principal in ('','other@example.com'):
            with self.assertRaises(PermissionError): mail.mail_config(CONFIG,principal)
        with self.assertRaises(PermissionError): mail.mail_config({},'owner@example.com')
        self.assertTrue(mail.mail_config(CONFIG,'OWNER@example.com').pop)

    def test_missing_pop_credentials_remain_unconfigured_and_not_in_repr(self):
        config=mail.mail_config(CONFIG,'owner@example.com')
        self.assertNotIn('private-test-password',repr(config))
        missing=mail.mail_config({'WHOIS_MAIL_OWNER_EMAILS':'owner@example.com'},'owner@example.com')
        self.assertIsNone(missing.pop)
        for updates in ({'WHOIS_POP_SECURITY':'none'}, {'WHOIS_POP_HOST':'https://bad.example'}, {'WHOIS_POP_PORT':'x'}):
            with self.assertRaises(ValueError): mail.mail_config(CONFIG|updates,'owner@example.com')

    def test_pop_fetch_never_deletes_and_preserves_stable_uid_and_attachments(self):
        config=mail.mail_config(CONFIG,'owner@example.com')
        client=Mock()
        raw=message()
        client.uidl.return_value=(b'+OK',[b'1 uid-one',b'2 uid-two'],0)
        client.list.return_value=(b'+OK',[b'1 300',b'2 600'],0)
        client.retr.return_value=(b'+OK',raw.splitlines(),len(raw))
        with patch.object(mail.poplib,'POP3_SSL',return_value=client):
            messages=mail.fetch_messages(config.pop,limit=1)
        self.assertEqual(len(messages),1)
        self.assertEqual(messages[0].uid,'uid-two')
        self.assertIn('100 PCS',messages[0].body)
        self.assertEqual(messages[0].attachments[0].filename,'sample.pdf')
        self.assertEqual(messages[0].attachments[0].content,b'example')
        client.retr.assert_called_once_with(2)
        client.dele.assert_not_called()
        client.quit.assert_called_once()

    def test_oversized_messages_are_skipped_before_retrieval(self):
        client=Mock(); client.uidl.return_value=(b'+OK',[b'1 uid'],0)
        client.list.return_value=(b'+OK',[b'1 999999999'],0)
        with patch.object(mail.poplib,'POP3_SSL',return_value=client):
            result=mail.fetch_messages(mail.mail_config(CONFIG,'owner@example.com').pop)
        client.retr.assert_not_called()
        self.assertTrue(result[0].notice)
        self.assertEqual(result[0].body,'')

    def test_smtp_probe_uses_starttls_before_login_and_never_sends(self):
        client=Mock()
        with patch.object(mail.smtplib,'SMTP',return_value=client):
            mail.probe_smtp(mail.mail_config(CONFIG,'owner@example.com').smtp)
        names=[c[0] for c in client.method_calls]
        self.assertLess(names.index('starttls'),names.index('login'))
        client.sendmail.assert_not_called();client.send_message.assert_not_called()

    def test_auth_errors_are_redacted_and_pop_starttls_has_no_plaintext_fallback(self):
        client=Mock(); client.stls.side_effect=RuntimeError('private-test-password')
        config=mail.mail_config(CONFIG|{'WHOIS_POP_SECURITY':'starttls','WHOIS_POP_PORT':'110'},'owner@example.com')
        with patch.object(mail.poplib,'POP3',return_value=client):
            with self.assertRaises(mail.MailConnectionError) as error: mail.probe_pop(config.pop)
        self.assertNotIn('private-test-password',str(error.exception))
        client.user.assert_not_called(); client.pass_.assert_not_called()

    def test_html_content_is_inert_and_inline_images_not_downloaded(self):
        m=EmailMessage();m['Subject']='HTML';m.set_content('<script>bad()</script><p>Hello buyer</p>',subtype='html')
        parsed=mail.parse_message('uid',m.as_bytes())
        self.assertIn('Hello buyer',parsed.body)
        self.assertNotIn('bad()',parsed.body)
        self.assertNotIn('<script>',parsed.body)

    def test_password_whitespace_is_preserved_and_cleanup_errors_do_not_leak(self):
        config=mail.mail_config(CONFIG|{'WHOIS_POP_PASSWORD':' secret '},'owner@example.com')
        self.assertEqual(config.pop.password,' secret ')
        client=Mock();client.uidl.side_effect=RuntimeError('private-test-password')
        client.quit.side_effect=RuntimeError('private-test-password')
        client.close.side_effect=RuntimeError('private-test-password')
        with patch.object(mail.poplib,'POP3_SSL',return_value=client):
            with self.assertRaises(mail.MailConnectionError) as error: mail.probe_pop(config.pop)
        self.assertNotIn('private-test-password',str(error.exception))

    def test_invalid_email_charset_is_replaced_instead_of_blocking_the_inbox(self):
        raw=b'Subject: bad charset\r\nContent-Type: text/plain; charset=nonexistent-codec\r\n\r\nHello'
        self.assertIn('Hello',mail.parse_message('uid',raw).body)
