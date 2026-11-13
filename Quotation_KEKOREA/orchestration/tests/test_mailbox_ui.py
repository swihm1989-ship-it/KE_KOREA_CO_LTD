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

    def test_stale_smtp_module_is_reloaded_and_ui_callable_rebound(self):
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        from Quotation_KEKOREA.orchestration.adapters import whois_mail
        with (patch.object(whois_mail, "SMTP_DIAGNOSTIC_REVISION", "old-version"),
              patch.object(mailbox_page.st, "session_state", {})):
            self.assertTrue(mailbox_page._ensure_smtp_adapter_current())
            revision, fingerprint, current = mailbox_page._smtp_runtime_diagnostics()
            self.assertEqual(revision, "smtp-starttls-20261112-v3")
            self.assertTrue(current)
            self.assertEqual(len(fingerprint), 12)
            self.assertFalse(mailbox_page._ensure_smtp_adapter_current())

    def test_stale_pop_diagnostic_revision_triggers_reload(self):
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        from Quotation_KEKOREA.orchestration.adapters import whois_mail
        with (patch.object(whois_mail, "POP_DIAGNOSTIC_REVISION", "stale-pop-version"),
              patch.object(mailbox_page.st, "session_state", {})):
            self.assertTrue(mailbox_page._ensure_smtp_adapter_current())
            self.assertEqual(whois_mail.POP_DIAGNOSTIC_REVISION,
                             "pop-health-20261113-v4")
            self.assertTrue(callable(whois_mail.probe_pop_diagnostics))
            self.assertFalse(mailbox_page._ensure_smtp_adapter_current())

    def test_stale_pop_fetch_revision_triggers_reload_and_rebind(self):
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        from Quotation_KEKOREA.orchestration.adapters import whois_mail
        with (patch.object(whois_mail, "POP_FETCH_REVISION", "legacy-before-older-mail-recovery"),
              patch.object(mailbox_page.st, "session_state", {})):
            self.assertTrue(mailbox_page._ensure_smtp_adapter_current())
            self.assertEqual(whois_mail.POP_FETCH_REVISION,
                             "pop-fetch-older-fallback-20261113-v1")
            self.assertIs(mailbox_page.fetch_messages, whois_mail.fetch_messages)
            self.assertFalse(mailbox_page._ensure_smtp_adapter_current())

    def test_missing_pop_diagnostic_symbol_triggers_reload(self):
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        from Quotation_KEKOREA.orchestration.adapters import whois_mail
        with (patch.object(whois_mail, "probe_pop_diagnostics", None),
              patch.object(mailbox_page.st, "session_state", {})):
            self.assertTrue(mailbox_page._ensure_smtp_adapter_current())
            self.assertTrue(callable(whois_mail.probe_pop_diagnostics))

    def test_smtp_runtime_diagnostic_reports_loaded_callable_without_secrets(self):
        from Quotation_KEKOREA.orchestration.ui.mailbox_page import _smtp_runtime_diagnostics
        revision, fingerprint, current = _smtp_runtime_diagnostics()
        self.assertEqual(revision, "smtp-starttls-20261112-v3")
        self.assertEqual(len(fingerprint), 12)
        self.assertTrue(current)
        self.assertNotIn("private-test-password", fingerprint)
        with patch('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',return_value=CONFIG):
            app=AppTest.from_file(str(PAGE),default_timeout=25).run()
            app.radio[0].set_value('메일함').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertTrue(any('smtp-starttls-20261112-v3' in x.value for x in app.text))

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

    def test_app_boot_with_cached_legacy_navigation_symbol(self):
        # Streamlit hot-reloads entrypoint source, not necessarily imports.
        # A missing new workflow symbol must NEVER take the whole Master down.
        from Quotation_KEKOREA.orchestration.workflows import mail_intake
        with patch.object(mail_intake, "consume_mail_navigation", None):
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            app.session_state['master_mail_navigation_pending'] = True
            app.run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertEqual(app.radio(key='master_page').value, 'AI 업무 요청')
            self.assertNotIn('master_mail_navigation_pending', app.session_state)

    def test_mail_handoff_reloads_cached_legacy_queue_signature(self):
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        from Quotation_KEKOREA.orchestration.workflows import mail_intake
        mail = parse_message('synthetic-pi-uid', message())
        def legacy_queue(state, msg, *, extract=False, attachments=(), requested=None):
            raise AssertionError('legacy handler must never be invoked')
        with (patch.object(mail_intake, 'queue_handoff', legacy_queue),
              patch.object(mailbox_page.st, 'session_state', {})):
            self.assertTrue(mailbox_page._use_for_ai(
                mail, extract=True, requested=['PI']))
            self.assertTrue(mailbox_page.st.session_state['master_mail_navigation_pending'])
            self.assertEqual(mailbox_page.st.session_state['ai_intake_mail_source']['kinds'], ['PI'])
            self.assertEqual(mailbox_page.st.session_state['master_page']
                             if 'master_page' in mailbox_page.st.session_state
                             else '메일함', '메일함')
            self.assertTrue(mailbox_page.st.session_state['ai_intake_consent'])

    def test_unified_button_handoff_requires_new_consent_and_preserves_choice(self):
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        mail = parse_message('synthetic-pi-uid', message())
        with (patch.object(mailbox_page, '_settings', return_value=CONFIG),
              patch.object(mailbox_page, 'fetch_messages', return_value=(mail,))):
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
            app.radio(key='master_page').set_value('메일함').run()
            action = app.button(key='whois_ai_synthetic-pi-uid')
            self.assertEqual(action.label, 'AI 업무 요청으로 이동')
            self.assertFalse(action.disabled)
            self.assertFalse(any(b.key == 'whois_ai_extract_synthetic-pi-uid' for b in app.button))
            action.click().run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertEqual(app.radio(key='master_page').value, 'AI 업무 요청')
            self.assertIn('100 PCS', app.text_area(key='ai_intake_instruction').value)
            self.assertEqual(app.session_state['ai_intake_mail_source']['kinds'], ['PI'])
            self.assertFalse(app.checkbox(key='ai_intake_consent').value)
            self.assertEqual(app.radio(key='ai_intake_mail_processing_mode').value,
                             '직접 수정 후 분석')
            self.assertEqual(app.button(key='ai_intake_extract').label,
                             '수정한 내용으로 AI 분석')
            self.assertTrue(app.button(key='ai_intake_extract').disabled)
            self.assertNotIn('master_mail_navigation_pending', app.session_state)
            self.assertNotIn('ai_intake_mail_pending', app.session_state)

    def test_unified_auto_mode_never_calls_provider_without_explicit_run(self):
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        from Quotation_KEKOREA.orchestration.ui import ai_intake_page
        mail = parse_message('synthetic-pi-uid', message())
        synthetic_analysis = {'parties': [], 'terms': [], 'questions': [], 'issues': []}
        with (patch.object(mailbox_page, '_settings', return_value=CONFIG),
              patch.object(mailbox_page, 'fetch_messages', return_value=(mail,)),
              patch.object(ai_intake_page, '_model_config',
                           return_value={'OPENAI_API_KEY': 'synthetic-only', 'OPENAI_MODEL': 'mock'}),
              patch.object(ai_intake_page, 'extract_mail_candidates',
                           return_value={'analysis': synthetic_analysis, 'candidates': {}}) as provider):
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
            app.radio(key='master_page').set_value('메일함').run()
            app.button(key='whois_ai_synthetic-pi-uid').click().run()
            provider.assert_not_called()
            app.radio(key='ai_intake_mail_processing_mode').set_value('AI 자동 분석').run()
            provider.assert_not_called()
            self.assertTrue(app.text_area(key='ai_intake_instruction').disabled)
            self.assertEqual(app.button(key='ai_intake_extract').label, 'AI 자동 분석 실행')
            self.assertTrue(app.button(key='ai_intake_extract').disabled)
            app.checkbox(key='ai_intake_consent').check().run()
            provider.assert_not_called()
            self.assertFalse(app.button(key='ai_intake_extract').disabled)
            app.button(key='ai_intake_extract').click().run()
            provider.assert_called_once()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertEqual(app.session_state['ai_intake_result'][1], synthetic_analysis)
            self.assertFalse(app.session_state.get('ai_intake_mail_pending'))

    def test_unified_mou_handoff_keeps_contract_and_edit_mode(self):
        from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailMessage
        from Quotation_KEKOREA.orchestration.ui import mailbox_page
        synthetic_mou = MailMessage(
            'synthetic-mou-uid', sender='Sender <synthetic@example.test>',
            subject='BIPV MoU 요청',
            body='BIPV 설치 관련 MoU 작성 수정안 부탁드립니다.',
        )
        with (patch.object(mailbox_page, '_settings', return_value=CONFIG),
              patch.object(mailbox_page, 'fetch_messages', return_value=(synthetic_mou,))):
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
            app.radio(key='master_page').set_value('메일함').run()
            app.button(key='whois_ai_synthetic-mou-uid').click().run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertEqual(app.session_state['ai_intake_mail_source']['kinds'],
                             ['CONTRACT'])
            self.assertEqual(app.radio(key='ai_intake_mail_processing_mode').value,
                             '직접 수정 후 분석')
            self.assertFalse(app.checkbox(key='ai_intake_consent').value)
            self.assertIn('MoU', app.text_area(key='ai_intake_instruction').value)
            app.text_area(key='ai_intake_instruction').set_value(
                'BIPV 설치 MoU 수정 요청. 계약 당사자 확인 필요').run()
            self.assertFalse(app.exception, [x.message for x in app.exception])
            self.assertEqual(app.button(key='ai_intake_extract').label,
                             '수정한 내용으로 AI 분석')

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

    def test_retr_placeholders_never_displace_previous_good_mail(self):
        from Quotation_KEKOREA.orchestration.ui.mailbox_page import _merge_messages
        from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailMessage
        good = parse_message('uid1', message())
        placeholder = MailMessage('uid1', notice='이 메일의 POP3 본문(RETR) 조회에 실패했습니다.')
        orphan = MailMessage('uid2', notice='이 메일의 POP3 본문(RETR) 조회에 실패했습니다.')
        merged = _merge_messages((good, orphan), (placeholder, orphan))
        self.assertEqual([m.uid for m in merged], ['uid1'])
        self.assertIn('100 PCS', merged[0].body)

    def test_non_owner_cannot_display_previous_mail_session(self):
        config=CONFIG|{'WHOIS_MAIL_OWNER_EMAILS':'another@example.com'}
        with patch('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',return_value=config):
            app=AppTest.from_file(str(PAGE),default_timeout=20).run()
            app.session_state['whois_mail_bundle']=('old',(parse_message('uid1',message()),),'today')
            app.radio[0].set_value('메일함').run()
            self.assertFalse(app.exception)
            self.assertNotIn('whois_mail_bundle',app.session_state)
            self.assertFalse(any('PI request' in x.value for x in app.text))
