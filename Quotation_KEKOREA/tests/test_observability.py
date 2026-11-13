"""Privacy and failure-isolation contracts for metadata-only monitoring."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        from Quotation_KEKOREA.observability import core
        self.core = core
        self.events = []
        self.previous = core.set_recorder(self.events.append)

    def tearDown(self):
        self.core.set_recorder(self.previous)

    def test_json_spans_have_correlated_ids_and_monotonic_duration(self):
        with self.core.operation('contract.analyze'):
            with self.core.operation('ai.request', model='gpt-6-luna') as ai:
                ai.usage({'usage': {'input_tokens': 1000, 'output_tokens': 200,
                                   'input_tokens_details': {'cached_tokens': 100}}})
        outer, inner, inner_end, outer_end = self.events
        self.assertEqual({e['run_id'] for e in self.events}, {outer['run_id']})
        self.assertEqual(inner['parent_span_id'], outer['span_id'])
        self.assertEqual(inner_end['status'], 'success')
        self.assertGreaterEqual(inner_end['duration_ms'], 0)
        self.assertIsNotNone(inner_end['ended_at'])
        self.assertIsNone(inner['ended_at'])
        self.assertEqual(inner_end['input_tokens'], 1000)
        self.assertAlmostEqual(inner_end['estimated_cost_usd'], 0.000191)
        self.assertEqual(json.loads(json.dumps(outer_end)), outer_end)

    def test_errors_are_fixed_categories_without_message_or_class_name(self):
        secret = 'password=never-log sk-secret private@example.com contract-body'
        class PrivateNameError(Exception):
            pass
        with self.assertRaises(PrivateNameError):
            with self.core.operation('mail.collect'):
                raise PrivateNameError(secret)
        encoded = json.dumps(self.events)
        for value in (secret, 'PrivateNameError', 'private@example.com', 'sk-secret'):
            self.assertNotIn(value, encoded)
        self.assertEqual(self.events[-1]['error_type'], 'unexpected')
        self.assertEqual(self.events[-1]['status'], 'failure')

    def test_http_rate_limit_is_classified_without_reading_response(self):
        err = HTTPError('https://secret-url', 429, 'private', {}, io.BytesIO(b'secret'))
        with self.core.operation('ai.request', model='gpt-6-luna') as ai:
            ai.failure(err)
        self.assertEqual(self.events[-1]['error_type'], 'rate_limit')
        self.assertEqual(self.events[-1]['http_status'], 429)
        self.assertNotIn('secret', json.dumps(self.events))

    def test_missing_usage_and_unknown_prices_stay_unknown(self):
        with self.core.operation('ai.request', model='gpt-5.4') as ai:
            ai.usage({'usage': {'input_tokens': 10, 'output_tokens': 20}})
        self.assertIsNone(self.events[-1]['estimated_cost_usd'])
        self.assertEqual(self.events[-1]['pricing_status'], 'unknown_model')
        with self.core.operation('ai.request', model='gpt-6-luna'):
            pass
        self.assertIsNone(self.events[-1]['input_tokens'])
        self.assertEqual(self.events[-1]['pricing_status'], 'missing_usage')

    def test_provider_content_and_untrusted_model_names_are_never_recorded(self):
        with self.core.operation('ai.request', model='sk-key private@example.com') as ai:
            ai.usage({'model': 'private-company', 'output': [{'text': 'PRIVATE'}],
                      'usage': {'input_tokens': 1, 'output_tokens': 2, 'email': 'PRIVATE'}})
        self.assertEqual(self.events[-1]['model'], 'other')
        self.assertNotIn('PRIVATE', json.dumps(self.events))
        self.assertNotIn('private', json.dumps(self.events))

    def test_storage_failure_does_not_change_return_or_exception(self):
        def broken(event):
            raise RuntimeError('secret storage failure')
        self.core.set_recorder(broken)
        @self.core.traced('contract.analyze')
        def good():
            return object_value
        object_value = object()
        self.assertIs(good(), object_value)
        err = ValueError('private validation')
        with self.assertRaises(ValueError) as caught:
            with self.core.operation('contract.analyze'):
                raise err
        self.assertIs(caught.exception, err)

    def test_invalid_usage_and_cache_write_or_nonstandard_tier_not_underpriced(self):
        for usage in ({'input_tokens': -2, 'output_tokens': 2},
                      {'input_tokens': True, 'output_tokens': 2},
                      {'input_tokens': 2, 'output_tokens': '2'}):
            with self.core.operation('ai.request', model='gpt-6-luna') as ai:
                ai.usage({'usage': usage})
            self.assertIsNone(self.events[-1]['estimated_cost_usd'])
        for response in (
            {'usage': {'input_tokens': 100, 'output_tokens': 2,
                       'input_tokens_details': {'cache_write_tokens': 50}}},
            {'service_tier': 'priority', 'usage': {'input_tokens': 100, 'output_tokens': 2}},
        ):
            with self.core.operation('ai.request', model='gpt-6-luna') as ai:
                ai.usage(response)
            self.assertIsNone(self.events[-1]['estimated_cost_usd'])

    def test_retry_is_explicit_and_does_not_add_calls(self):
        with self.core.operation('contract.generate'):
            with self.core.retry_attempt(1):
                with self.core.operation('ai.request', model='gpt-6-luna'):
                    pass
        self.assertEqual([e['retry_count'] for e in self.events if e['task'] == 'ai.request'], [1, 1])

    def test_invalid_task_is_not_copied_into_events(self):
        with self.core.operation('private@example.com'):
            pass
        self.assertEqual(self.events[-1]['task'], 'other')
        self.assertNotIn('private@', json.dumps(self.events))

    def test_incomplete_provider_result_records_usage_and_failure(self):
        with self.core.operation('ai.request', model='gpt-6-luna') as ai:
            ai.usage({'status': 'incomplete', 'usage': {'input_tokens': 100, 'output_tokens': 10},
                      'incomplete_details': {'reason': 'private-text'}})
        self.assertEqual(self.events[-1]['status'], 'failure')
        self.assertEqual(self.events[-1]['error_type'], 'incomplete_response')
        self.assertEqual(self.events[-1]['output_tokens'], 10)

    def test_malformed_provider_metadata_cannot_change_business_success(self):
        from Quotation_KEKOREA.contracts.service import _call
        for status in ([], {}, 3):
            def opener(*args, **kwargs):
                return io.BytesIO(json.dumps({'status': status, 'usage': [],
                    'output': [{'content': [{'type':'output_text','text':'{"ok":true}'}]}]}).encode())
            result = _call('test',{},env={'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},opener=opener)
            self.assertEqual(result,{'ok':True})

    def test_fallback_p95_matches_database_percentile_cont(self):
        from Quotation_KEKOREA.observability.reporting import metrics
        rows=[{'status':'success','duration_ms':100,'input_tokens':None,'output_tokens':None},
              {'status':'success','duration_ms':1000,'input_tokens':None,'output_tokens':None}]
        self.assertEqual(metrics(rows)['p95_duration_ms'],955)


if __name__ == '__main__':
    unittest.main()
