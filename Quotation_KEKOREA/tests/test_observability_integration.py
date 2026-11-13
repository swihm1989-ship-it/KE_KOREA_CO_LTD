"""Real operation boundaries with synthetic provider/mail data only."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from Quotation_KEKOREA.observability import core


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.old = core.set_recorder(self.events.append)

    def tearDown(self):
        core.set_recorder(self.old)

    def opener(self, request, **kwargs):
        return io.BytesIO(json.dumps({'status': 'completed',
            'usage': {'input_tokens': 100, 'output_tokens': 10},
            'output': [{'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}]}).encode())

    def test_contract_provider_usage_does_not_change_original_result(self):
        from Quotation_KEKOREA.contracts.service import _call
        self.assertEqual(_call('test', {}, env={'OPENAI_API_KEY': 'SYNTHETIC',
                                              'OPENAI_MODEL': 'gpt-6-luna'}, opener=self.opener), {'ok': True})
        finished = [e for e in self.events if e['task']=='ai.request' and e['event_type']=='finish']
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]['input_tokens'], 100)
        self.assertEqual(finished[0]['status'], 'success')
        self.assertNotIn('SYNTHETIC', json.dumps(self.events))

    def test_provider_http_error_preserves_ui_error_and_safe_cause(self):
        from Quotation_KEKOREA.contracts.service import _call
        def failed(*a, **kw):
            raise HTTPError('https://api.openai.com/v1/responses',429,'test',{},io.BytesIO(b'{}'))
        with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
            _call('test', {}, env={'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},opener=failed)
        self.assertEqual(self.events[-1]['error_type'], 'rate_limit')

    def test_mail_collect_does_not_log_mail_or_credentials(self):
        from Quotation_KEKOREA.orchestration.adapters.whois_mail import fetch_messages
        with patch('Quotation_KEKOREA.orchestration.adapters.whois_mail._pop', side_effect=RuntimeError('PRIVATE MAIL PASSWORD')):
            with self.assertRaises(RuntimeError):
                fetch_messages(None)
        self.assertEqual(self.events[-1]['task'], 'mail.collect')
        self.assertNotIn('PRIVATE',json.dumps(self.events))

    def test_trade_export_failure_is_observed_without_source_content(self):
        from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_master_trade_draft
        with self.assertRaises(ValueError):
            render_master_trade_draft('PI',{'private': 'PRIVATE CONTRACT'}, {})
        self.assertEqual(self.events[-1]['task'],'document.generate')
        self.assertEqual(self.events[-1]['document_kind'],'PI')
        self.assertNotIn('PRIVATE',json.dumps(self.events))

    def test_contract_analysis_validation_failure_is_recorded(self):
        from Quotation_KEKOREA.orchestration.workflows.ai_intake import extract_candidate
        with self.assertRaises(PermissionError):
            extract_candidate('PRIVATE',{},consent=False)
        self.assertEqual(self.events[-1]['task'],'contract.analyze')
        self.assertEqual(self.events[-1]['error_type'],'permission')

    def test_legacy_trade_extraction_uses_same_api_payload_and_tracks_usage(self):
        from Quotation_KEKOREA.agent.extractor import extract_trade_data
        result = extract_trade_data('test synthetic', env={'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},opener=self.opener)
        self.assertTrue(result['ok'])
        ai = [e for e in self.events if e['task']=='ai.request' and e['event_type']=='finish']
        self.assertEqual(len(ai),1)
        self.assertEqual(ai[0]['output_tokens'],10)
