import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from Quotation_KEKOREA.orchestration.tests.test_whois_mail import CONFIG, message
from Quotation_KEKOREA.orchestration.adapters.whois_mail import parse_message

PAGE=Path(__file__).resolve().parents[1]/'ui'/'streamlit_page.py'
class MailboxUiTests(unittest.TestCase):
    def setUp(self):
        for target,value in [('Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication','owner@example.com'),
                             ('Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news',([],None))]:
            p=patch(target,return_value=value);p.start();self.addCleanup(p.stop)

    def test_whois_settings_inside_auth_table_are_read_without_bypassing_owner(self):
        from Quotation_KEKOREA.orchestration.ui.mailbox_page import _settings
        nested = {
            'auth': {
                'WHOIS_MAIL_OWNER_EMAILS': 'owner@example.com',
                'WHOIS_POP_USERNAME': 'david.ihm@ke-korea.com',
            },
        }
        with patch('Quotation_KEKOREA.orchestration.ui.mailbox_page.st.secrets', nested):
            settings = _settings()
        self.assertEqual(settings['WHOIS_MAIL_OWNER_EMAILS'], 'owner@example.com')
        self.assertEqual(settings['WHOIS_POP_USERNAME'], 'david.ihm@ke-korea.com')

    def test_mail_page_without_settings_does_not_connect(self):
        with patch('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',return_value={}),patch('Quotation_KEKOREA.orchestration.ui.mailbox_page.fetch_messages') as fetch:
            app=AppTest.from_file(str(PAGE),default_timeout=20).run()
            app.radio[0].set_value('메일함').run()
        self.assertFalse(app.exception)
        fetch.assert_not_called()
        self.assertTrue(any('WHOIS_MAIL_OWNER_EMAILS' in x.value for x in app.code))
        self.assertFalse(any(b.label=='업무 시작' for b in app.button))

    def test_refresh_and_handoff_require_no_implicit_ai_consent(self):
        with patch('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',return_value=CONFIG),patch('Quotation_KEKOREA.orchestration.ui.mailbox_page.fetch_messages',return_value=(parse_message('uid1',message()),)) as fetch:
            app=AppTest.from_file(str(PAGE),default_timeout=20).run()
            app.radio[0].set_value('메일함').run()
            fetch.assert_called_once()  # Auto-sync immediately when mailbox opens.
            app.button(key='whois_refresh').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('PI request' in x.value for x in app.text))
            app.session_state['ai_intake_consent']=True
            app.session_state['ai_intake_result']=('old',{})
            app.session_state['master_pdf_quantity']='OLD QUANTITY'
            app.session_state['ai_intake_contract_consent']=True
            app.button(key='whois_ai_uid1').click().run()
            self.assertFalse(app.exception,[x.message for x in app.exception])
            self.assertEqual(app.radio(key='master_page').value,'AI 업무 요청')
            self.assertIn('100 PCS',app.text_area(key='ai_intake_instruction').value)
            self.assertFalse(app.checkbox(key='ai_intake_consent').value)
            self.assertNotIn('ai_intake_result',app.session_state)
            self.assertNotIn('master_pdf_quantity',app.session_state)
            self.assertNotIn('ai_intake_contract_consent',app.session_state)

    def test_inbox_list_selection_search_and_selected_mail_ai_handoff(self):
        from email.message import EmailMessage
        second = EmailMessage()
        second['From'] = 'Supplier <supplier@example.test>'
        second['Subject'] = 'Solar cell pricing'
        second['Date'] = 'Thu, 12 Nov 2026 16:00:00 +0900'
        second.set_content('Need 500 PCS with USD 0.20 per piece')
        mails = (parse_message('uid1',message()),
                 parse_message('uid2',second.as_bytes()))
        with (patch('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',return_value=CONFIG),
              patch('Quotation_KEKOREA.orchestration.ui.mailbox_page.fetch_messages',return_value=mails)):
            app=AppTest.from_file(str(PAGE),default_timeout=25).run()
            app.radio[0].set_value('메일함').run()
            app.button(key='whois_refresh').click().run()
            self.assertFalse(app.exception,[x.message for x in app.exception])
            self.assertTrue(any('2건' in x.value for x in app.caption))
            self.assertTrue(any('PI request' in x.value for x in app.text))
            app.button(key='whois_select_1_uid2').click().run()
            self.assertFalse(app.exception,[x.message for x in app.exception])
            self.assertEqual(app.session_state['whois_selected_uid'],'uid2')
            self.assertIn('uid2',app.session_state['whois_opened_uids'])
            self.assertTrue(any('Solar cell pricing' in x.value for x in app.text))
            app.text_input(key='whois_mail_search').set_value('Supplier').run()
            self.assertFalse(app.exception,[x.message for x in app.exception])
            self.assertTrue(any('1건' in x.value for x in app.caption))
            app.button(key='whois_ai_uid2').click().run()
            self.assertFalse(app.exception,[x.message for x in app.exception])
            self.assertIn('500 PCS',app.text_area(key='ai_intake_instruction').value)
            self.assertFalse(app.checkbox(key='ai_intake_consent').value)

    def test_auto_poll_fetches_without_click_and_preserves_uidl_unique_messages(self):
        from Quotation_KEKOREA.orchestration.ui.mailbox_page import _merge_messages
        first = parse_message('uid1',message())
        second = parse_message('uid2',message())
        self.assertEqual([m.uid for m in _merge_messages((first,), (second, first))],
                         ['uid2', 'uid1'])
        with patch('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',return_value=CONFIG), \
             patch('Quotation_KEKOREA.orchestration.ui.mailbox_page.fetch_messages',return_value=(first,)) as fetch:
            app=AppTest.from_file(str(PAGE),default_timeout=25).run()
            fetch.assert_not_called()
            app.radio[0].set_value('메일함').run()
            self.assertFalse(app.exception,[x.message for x in app.exception])
            fetch.assert_called_once()
            self.assertEqual(fetch.call_args.kwargs['limit'],5)
            self.assertTrue(any('PI request' in x.value for x in app.text))
            app.run()
            fetch.assert_called_once()

    def test_non_owner_cannot_display_previous_mail_session(self):
        config=CONFIG|{'WHOIS_MAIL_OWNER_EMAILS':'another@example.com'}
        with patch('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',return_value=config):
            app=AppTest.from_file(str(PAGE),default_timeout=20).run()
            app.session_state['whois_mail_bundle']=('old',(parse_message('uid1',message()),),'today')
            app.radio[0].set_value('메일함').run()
            self.assertFalse(app.exception)
            self.assertNotIn('whois_mail_bundle',app.session_state)
            self.assertFalse(any('PI request' in x.value for x in app.text))
