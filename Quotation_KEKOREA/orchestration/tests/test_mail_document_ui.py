import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from Quotation_KEKOREA.orchestration.tests.mail_fixtures import cases
from Quotation_KEKOREA.orchestration.adapters.whois_mail import parse_message
from Quotation_KEKOREA.orchestration.tests.test_whois_mail import CONFIG

PAGE=Path(__file__).resolve().parents[1]/'ui'/'streamlit_page.py'


class MailDocumentUiTests(unittest.TestCase):
    def setUp(self):
        self.case=cases()[0]
        self.mail=parse_message(self.case['id'],self.case['raw'])
        for target,value in [
            ('Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication','owner@example.com'),
            ('Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news',([],None)),
            ('Quotation_KEKOREA.orchestration.ui.mailbox_page._settings',CONFIG),
            ('Quotation_KEKOREA.orchestration.ui.mailbox_page.fetch_messages',(self.mail,)),
            ('Quotation_KEKOREA.orchestration.ui.ai_intake_page._model_config',{'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'}),
        ]:
            mock=patch(target,return_value=value);mock.start();self.addCleanup(mock.stop)

    def ready_result(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_trade_normalization import synchronize_nullable_quantities
        return {'analysis':copy.deepcopy(self.case['analysis']),
                'candidates':{'PI':synchronize_nullable_quantities(copy.deepcopy(self.case['trade']))}}

    def mailbox(self):
        app=AppTest.from_file(str(PAGE),default_timeout=25).run()
        app.radio(key='master_page').set_value('메일함').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        return app

    def begin_mail(self, app):
        app.button(key='whois_ai_'+self.mail.uid).click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.radio(key='master_page').value, 'AI 업무 요청')
        self.assertFalse(app.checkbox(key='ai_intake_consent').value)
        self.assertNotIn('ai_intake_mail_pending', app.session_state)
        return app

    def start_analysis(self, app):
        self.begin_mail(app)
        app.radio(key='ai_intake_mail_processing_mode').set_value('AI 자동 분석').run()
        app.checkbox(key='ai_intake_consent').check().run()
        app.button(key='ai_intake_extract').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_explicit_auto_analysis_then_preserves_multiple_rows(self):
        with patch('Quotation_KEKOREA.orchestration.ui.ai_intake_page.extract_mail_candidates',return_value=self.ready_result()) as extract:
            app=self.mailbox()
            self.start_analysis(app)
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertEqual(app.radio(key='master_page').value,'AI 업무 요청')
            self.assertEqual(app.multiselect(key='ai_intake_mail_kinds').value,['PI'])
            self.assertEqual(len(app.session_state['ai_intake_candidates'][1]['PI']['items']),2)
            extract.assert_called_once()
            app.run()
            self.assertEqual(extract.call_count,1)
            app.button(key='ai_intake_build_candidates').click().run()
            self.assertEqual(len(app.session_state['ai_intake_candidates'][1]['PI']['items']),2)
            next(x for x in app.text_input if x.label=='Buyer · 구매자 법인 주소').set_value(
                'NEW SYNTHETIC ADDRESS').run()
            self.assertEqual(app.session_state['ai_intake_candidates'][1]['PI']['buyer']['address'],'NEW SYNTHETIC ADDRESS')
            self.assertEqual(len(app.session_state['ai_intake_candidates'][1]['PI']['items']),2)

    def test_single_editor_quantity_updates_export_and_keeps_second_row(self):
        from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
        with patch('Quotation_KEKOREA.orchestration.ui.ai_intake_page.extract_mail_candidates',return_value=self.ready_result()):
            app=self.mailbox()
            self.start_analysis(app)
            next(x for x in app.text_input if x.label=='수량').set_value('3000').run()
            self.assertFalse(any(b.label == '필수정보 적용 · PDF 생성 준비' for b in app.button))
            data=app.session_state['ai_intake_candidates'][1]['PI']
            self.assertEqual(validate_and_calculate(data)['items'][0]['quantity'],'3000')
            self.assertEqual(len(data['items']),2)

    def test_failure_is_not_retried_on_rerun(self):
        with patch('Quotation_KEKOREA.orchestration.ui.ai_intake_page.extract_mail_candidates',side_effect=RuntimeError('synthetic failure')) as extract:
            app=self.mailbox()
            self.start_analysis(app)
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertTrue(app.error)
            app.run()
            self.assertEqual(extract.call_count,1)
            self.assertNotIn('ai_intake_mail_pending',app.session_state)

    def test_review_only_button_still_makes_no_ai_call(self):
        with patch('Quotation_KEKOREA.orchestration.ui.ai_intake_page.extract_mail_candidates') as extract:
            app=self.mailbox()
            self.begin_mail(app)
            self.assertEqual(app.radio(key='ai_intake_mail_processing_mode').value,
                             '직접 수정 후 분석')
            self.assertTrue(app.button(key='ai_intake_extract').disabled)
            extract.assert_not_called()

    def test_missing_model_config_blocks_analysis_without_auto_retry(self):
        with patch('Quotation_KEKOREA.orchestration.ui.ai_intake_page._model_config',return_value={}),patch(
                'Quotation_KEKOREA.orchestration.ui.ai_intake_page.extract_mail_candidates') as extract:
            app=self.mailbox()
            self.begin_mail(app)
            app.radio(key='ai_intake_mail_processing_mode').set_value('AI 자동 분석').run()
            app.checkbox(key='ai_intake_consent').check().run()
            self.assertTrue(app.button(key='ai_intake_extract').disabled)
            self.assertFalse(app.exception,[e.message for e in app.exception])
            extract.assert_not_called()
            self.assertNotIn('ai_intake_mail_pending',app.session_state)

    def test_document_selection_changes_invalidate_previous_results(self):
        with patch('Quotation_KEKOREA.orchestration.ui.ai_intake_page.extract_mail_candidates',return_value=self.ready_result()) as extract:
            app=self.mailbox()
            self.start_analysis(app)
            app.multiselect(key='ai_intake_mail_kinds').set_value(['CI','PL']).run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertTrue(any('변경' in e.value for e in app.warning))
            self.assertFalse(any(b.key=='master_legacy_export' for b in app.button))
            self.assertEqual(extract.call_count,1)
