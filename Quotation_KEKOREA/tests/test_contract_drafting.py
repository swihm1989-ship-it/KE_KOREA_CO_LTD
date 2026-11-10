"""Quality drafting exercises the service boundary with synthetic API responses."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.tests.test_contract_service import FakeResponse
from Quotation_KEKOREA.contracts.drafting import (
    build_drafting_plan, select_topic_references, generate_reviewed_draft,
)


ENV = {'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'}


def clause(cid, title, text):
    return {'id': cid, 'title': title, 'order': 1,
            'sentences': [{'id': cid + '_s1', 'text': text, 'term_ids': [], 'source_refs': []}]}


class DraftingTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = dict(new_snapshot('sample', 'sale', 'en'), title='User title')
        self.snapshot['terms'] = [{'id': 't1', 'key': 'quantity', 'value': '0', 'status': 'confirmed', 'source_refs': []},
                                  {'id': 't2', 'key': 'payment_deadline', 'value': None, 'status': 'missing', 'source_refs': []}]
        self.fm = clause('fm', 'Force Majeure', 'A party is excused by events beyond its control.')
        self.scope = clause('scope', 'Scope', 'The agreed goods are supplied.')
        self.calls = []

    def opener(self, *, repair=False, residual=False, fail_audit=False, alter_scope=False,
               omit_clause_review=False, complete=False):
        def call(request, timeout):
            data = json.loads(json.loads(request.data)['input'][0]['content'])
            self.calls.append(data)
            if data.get('drafting_task') == 'audit':
                if fail_audit:
                    raise TimeoutError()
                checks = []
                for topic in data['drafting_plan']['topics']:
                    missing = not complete and topic['key'] == 'force_majeure' and (len(self.calls) == 2 or residual)
                    checks.append({'topic': topic['key'], 'status': 'missing' if missing else 'complete',
                                   'clause_ids': ['fm'], 'missing_elements': ['notice'] if missing else [],
                                   'reason': 'Missing notice.' if missing else 'Covered.',
                                   'evidence': [] if missing else [
                                       {'element': element, 'sentence_id': 'fm_s1',
                                        'quote': data['snapshot']['clauses'][1]['sentences'][0]['text']}
                                       for element in topic['elements']]})
                clause_checks = [
                    {'clause_id': c['id'], 'status': 'complete', 'reason': 'No conflict in the test fixture.',
                     'evidence': [{'sentence_id': c['sentences'][0]['id'], 'quote': c['sentences'][0]['text']}]}
                    for c in data['snapshot']['clauses']]
                return FakeResponse({'checks': checks, 'clause_checks': [] if omit_clause_review else clause_checks})
            clauses = [deepcopy(self.scope), deepcopy(self.fm)]
            if data.get('drafting_task') == 'repair':
                clauses[1]['sentences'][0]['text'] += ' Give prompt notice, mitigate effects and resume performance.'
                if alter_scope:
                    clauses[0]['sentences'][0]['text'] = 'Changed unrelated scope.'
            return FakeResponse({'title': 'AI renamed title', 'clauses': clauses, 'issues': []})
        return call

    def test_plan_preserves_zero_and_requires_operational_force_majeure_elements(self):
        plan = build_drafting_plan(self.snapshot)
        fm = next(t for t in plan['topics'] if t['key'] == 'force_majeure')
        self.assertTrue({'events', 'notice', 'mitigation', 'resumption'} <= set(fm['elements']))
        self.assertEqual(plan['confirmed_terms'][0]['value'], '0')
        self.assertEqual(plan['unresolved_terms'][0]['status'], 'missing')

    def test_topic_retrieval_reaches_tail_and_retains_source_id(self):
        source = {'id': 'selected', 'filename': 'sample',
                  'extracted_text': ('Unrelated product description. ' * 1000) +
                  '\n\nArticle XVI Force Majeure\nGive prompt notice and mitigate the effects.'}
        refs = select_topic_references([source], build_drafting_plan(self.snapshot))
        self.assertTrue(any('Article XVI Force Majeure' in r['extracted_text'] for r in refs))
        self.assertEqual({r['id'] for r in refs}, {'selected'})
        self.assertLess(sum(len(r['extracted_text']) for r in refs), 100_001)

    def test_retrieval_keeps_heading_and_adjacent_operative_paragraphs_together(self):
        paragraphs = ['Force Majeure',
                      'The impeded enterprise must immediately inform its counterparty.',
                      'The impeded enterprise must reduce adverse effects.',
                      'Duties shall recommence once the impediment ceases.']
        refs = select_topic_references([{'id': 'doc', 'source_locations': [
            {'locator': f'paragraph {i}', 'text': text} for i, text in enumerate(paragraphs)]}],
            build_drafting_plan(self.snapshot))
        body = '\n'.join(r['extracted_text'] for r in refs)
        for paragraph in paragraphs:
            self.assertIn(paragraph, body)

    def test_audit_must_cover_every_generated_clause(self):
        with self.assertRaisesRegex(ValueError, 'clause'):
            generate_reviewed_draft(self.snapshot, [], env=ENV,
                                    client=self.opener(omit_clause_review=True))

    def test_progress_reports_actual_ai_stages_without_extra_calls(self):
        events = []
        generate_reviewed_draft(
            self.snapshot, [], env=ENV, client=self.opener(complete=True),
            progress_callback=events.append,
        )
        self.assertEqual([c['drafting_task'] for c in self.calls], ['draft', 'audit'])
        self.assertIn('AI 계약서 초안 작성 (API 응답 대기)', events)
        self.assertIn('AI 초안 품질 검토 (API 응답 대기)', events)
        self.assertEqual(events[-1], '검증된 초안 결과 정리')

    def test_progress_failure_does_not_save_partial_draft(self):
        events = []
        original = deepcopy(self.snapshot)
        with self.assertRaises(RuntimeError):
            generate_reviewed_draft(
                self.snapshot, [], env=ENV, client=self.opener(fail_audit=True),
                progress_callback=events.append,
            )
        self.assertIn('AI 초안 품질 검토 (API 응답 대기)', events)
        self.assertEqual(self.snapshot, original)

    def test_complete_draft_needs_only_generation_and_audit(self):
        generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener(complete=True))
        self.assertEqual([c['drafting_task'] for c in self.calls], ['draft', 'audit'])

    def test_repair_is_bounded_and_preserves_title_terms_and_unrelated_clauses(self):
        original = deepcopy(self.snapshot)
        result = generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener(repair=True))
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(result['title'], 'User title')
        self.assertEqual(result['terms'], original['terms'])
        self.assertEqual(result['clauses'][0], self.scope)
        self.assertIn('prompt notice', result['clauses'][1]['sentences'][0]['text'])
        self.assertEqual(self.snapshot, original)

    def test_unresolved_quality_issues_are_not_silently_certified(self):
        result = generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener(residual=True))
        self.assertEqual(len(self.calls), 4)
        issues = [i for i in result['issues'] if i['code'].startswith('draft_quality_')]
        self.assertTrue(issues)
        self.assertTrue(all(i['severity'] == 'confirm' and not i['confirmed'] for i in issues))

    def test_failed_audit_keeps_original_snapshot(self):
        original = deepcopy(self.snapshot)
        with self.assertRaises(RuntimeError):
            generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener(fail_audit=True))
        self.assertEqual(self.snapshot, original)

    def test_repair_cannot_rewrite_unrelated_clauses(self):
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener(alter_scope=True))

    def test_saved_contract_is_not_automatically_regenerated(self):
        self.snapshot['clauses'] = [self.fm]
        with self.assertRaisesRegex(ValueError, 'existing'):
            generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener())
        self.assertEqual(self.calls, [])

    def test_nonverbatim_clause_quote_recovers_with_one_audit_retry(self):
        original = deepcopy(self.snapshot)
        events = []
        base = self.opener(complete=True)
        seen = {'count': 0}

        def first_bad_quote(request, timeout):
            response = base(request, timeout)
            if self.calls[-1].get('drafting_task') == 'audit':
                seen['count'] += 1
                if seen['count'] == 1:
                    response.value['clause_checks'][0]['evidence'][0]['quote'] = 'Paraphrased, nonexistent sentence'
            return response

        result = generate_reviewed_draft(
            self.snapshot, [], env=ENV, client=first_bad_quote,
            progress_callback=events.append,
        )
        self.assertEqual([call['drafting_task'] for call in self.calls],
                         ['draft', 'audit', 'audit'])
        self.assertIn('AI 검토 인용 불일치 · 동일 초안으로 근거 재검증 (1회)', events)
        self.assertTrue(result['draft_quality']['checks'])
        self.assertEqual(self.snapshot, original)

    def test_repeated_bad_citation_fails_closed_and_identifies_clause(self):
        original = deepcopy(self.snapshot)
        base = self.opener(complete=True)

        def always_bad(request, timeout):
            response = base(request, timeout)
            if self.calls[-1].get('drafting_task') == 'audit':
                response.value['clause_checks'][0]['evidence'][0]['quote'] = 'Never in the actual clause.'
            return response

        with self.assertRaisesRegex(ValueError, 'clause_id=scope, sentence_id=scope_s1'):
            generate_reviewed_draft(self.snapshot, [], env=ENV, client=always_bad)
        self.assertEqual([call['drafting_task'] for call in self.calls],
                         ['draft', 'audit', 'audit'])
        self.assertEqual(self.snapshot, original)

    def test_invalid_audit_structure_is_not_retried(self):
        base = self.opener(complete=True)
        def incomplete_review(request, timeout):
            response = base(request, timeout)
            if self.calls[-1].get('drafting_task') == 'audit':
                response.value['clause_checks'] = []
            return response
        with self.assertRaisesRegex(ValueError, 'every generated clause'):
            generate_reviewed_draft(self.snapshot, [], env=ENV, client=incomplete_review)
        self.assertEqual([call['drafting_task'] for call in self.calls],
                         ['draft', 'audit'])

    def test_invalid_audit_and_repair_outputs_fail_without_mutating_input(self):
        for mode in ('missing_topic', 'false_quote', 'invalid_status', 'duplicate_clause', 'lost_sentence', 'false_citation'):
            with self.subTest(mode=mode):
                self.calls = []
                original = deepcopy(self.snapshot)
                base = self.opener()

                def corrupt(request, timeout):
                    result = base(request, timeout)
                    phase = self.calls[-1]['drafting_task']
                    if phase == 'audit' and mode == 'missing_topic':
                        result.value['checks'].pop()
                    elif phase == 'audit' and mode == 'false_quote':
                        result.value['clause_checks'][0]['evidence'][0]['quote'] = 'Fabricated text.'
                    elif phase == 'audit' and mode == 'invalid_status':
                        result.value['checks'][0]['status'] = []
                    elif phase == 'draft' and mode == 'duplicate_clause':
                        duplicate = deepcopy(result.value['clauses'][0])
                        duplicate['sentences'][0]['id'] = 'different_sentence'
                        result.value['clauses'].append(duplicate)
                    elif phase == 'repair' and mode == 'lost_sentence':
                        result.value['clauses'][1]['sentences'][0]['id'] = 'replacement_id'
                    elif phase == 'repair' and mode == 'false_citation':
                        result.value['clauses'][1]['sentences'][0]['source_refs'] = [
                            {'kind': 'reference', 'document_id': 'not_selected', 'quote': 'Invented reference.'}]
                    return result

                with self.assertRaises(ValueError):
                    generate_reviewed_draft(self.snapshot, [], env=ENV, client=corrupt)
                self.assertEqual(self.snapshot, original)
                self.assertLessEqual(len(self.calls), 4)

    def test_explicit_law_omission_is_respected_by_plan(self):
        self.snapshot['omissions'] = {'governing_law': {'confirmed': True, 'reason': 'User decision'}}
        plan = build_drafting_plan(self.snapshot)
        self.assertNotIn('governing_law', {t['key'] for t in plan['topics']})
        self.assertEqual(plan['omissions'], self.snapshot['omissions'])

    def test_final_audit_sees_standing_commission_payment_clauses(self):
        self.snapshot['contract_type'] = 'trade_commission'
        result = generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener(complete=True))
        protected = {f'commission_payment_{i}' for i in range(3)}
        reviewed = {c['id'] for c in self.calls[-1]['snapshot']['clauses']}
        self.assertTrue(protected <= reviewed)
        self.assertTrue(protected <= {c['id'] for c in result['clauses']})
        self.assertEqual(len(self.calls), 2)

    def test_topic_library_search_reads_once_and_uses_only_approved_matching_guidance(self):
        from Quotation_KEKOREA.tests.test_contract_library import MemoryLibrary, tiny_docx
        from Quotation_KEKOREA.contracts.library import register_sample, publish_sample, search_library_topics
        repo = MemoryLibrary()
        good = register_sample(repo, tiny_docx(), 'good.docx', title='Generic sample',
                               contract_types=['sale'], language='en')
        publish_sample(repo, good['id'], [{'locator': 'paragraph 1', 'topic': 'force majeure',
                                         'text': 'Force majeure requires prompt notice and reasonable mitigation.'}], env={})
        wrong = register_sample(repo, tiny_docx() + b'other-sample', 'wrong.docx', title='Other type',
                                contract_types=['investment_commission'], language='en')
        publish_sample(repo, wrong['id'], [{'locator': 'paragraph 1', 'topic': 'force majeure',
                                          'text': 'Force majeure INVESTMENT ONLY confidential guidance.'}], env={})
        register_sample(repo, tiny_docx() + b'pending-sample', 'pending.docx', title='Pending sample',
                        contract_types=['sale'], language='ko')
        reads = []
        read = repo.list_library_records
        repo.list_library_records = lambda **kwargs: (reads.append(kwargs) or read(**kwargs))
        with patch('Quotation_KEKOREA.contracts.library.embed_texts', side_effect=AssertionError('Unexpected network')):
            result = search_library_topics(repo, self.snapshot, build_drafting_plan(self.snapshot)['topics'], env=ENV)
        self.assertEqual(reads, [{'approved_only': True}])
        self.assertTrue(result['references'])
        self.assertTrue(all(r['id'].startswith('library:' + good['id'] + ':') for r in result['references']))
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('INVESTMENT ONLY', json.dumps(result))

    def test_reviewed_draft_uses_extended_bounded_request_timeout(self):
        timeouts = []
        respond = self.opener(complete=True)

        def record_timeout(request, timeout):
            timeouts.append(timeout)
            return respond(request, timeout)

        generate_reviewed_draft(self.snapshot, [], env=ENV, client=record_timeout)
        self.assertEqual(len(timeouts), 2)
        self.assertTrue(all(0 < value <= 150 for value in timeouts))
        self.assertTrue(all(value > 60 for value in timeouts))

    def test_expired_pipeline_budget_cannot_return_a_draft(self):
        with patch('Quotation_KEKOREA.contracts.drafting.time.monotonic', side_effect=[0, 601]):
            with self.assertRaisesRegex(RuntimeError, 'time budget'):
                generate_reviewed_draft(self.snapshot, [], env=ENV, client=self.opener())
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
