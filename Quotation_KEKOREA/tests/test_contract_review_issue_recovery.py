"""Regression tests for recoverable AI review issues and atomic note proposals."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from Quotation_KEKOREA.contracts.service import _normalize_ai_issues
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.workspace import propose_notes_revision


class ReviewIssueRecoveryTests(TestCase):
    def test_string_issue_is_preserved_as_unconfirmed_review(self):
        result = _normalize_ai_issues(['서명자 확인 필요'], 'error')
        self.assertEqual(result[0]['message'], '서명자 확인 필요')
        self.assertEqual(result[0]['severity'], 'confirm')
        self.assertEqual(result[0]['code'], 'ai_review_text')

    def test_mixed_issue_objects_and_strings_keep_order(self):
        result = _normalize_ai_issues([
            {'message': '계약일 확인', 'severity': 'block', 'code': 'date'},
            '통화 확인',
        ], 'error')
        self.assertEqual([x['message'] for x in result], ['계약일 확인', '통화 확인'])
        self.assertEqual(result[0]['severity'], 'block')
        self.assertEqual(result[1]['severity'], 'confirm')

    def test_invalid_issue_never_silently_disappears(self):
        for issue in (None, 17, [], ''):
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                _normalize_ai_issues([issue], 'error')

    def _example(self):
        snapshot = new_snapshot('sample', 'sale', 'ko')
        snapshot['revision'] = 4
        snapshot['clauses'] = [{'id': 'c1', 'order': 1, 'title': '서명',
                                'sentences': [{'id': 's1', 'text': '서명일: [서명 전 확인]'}]}]
        note = {'id': 'n1', 'contract_id': 'sample', 'base_revision': 4,
                'sentence_id': 's1', 'status': 'note', 'instruction': '서명일을 2026년 11월 9일로 수정'}
        return snapshot, note

    def test_valid_change_with_text_issue_builds_proposal_without_mutation(self):
        snapshot, note = self._example()
        old = deepcopy(snapshot)
        def fake_call(*args, **kwargs):
            return {'changes': [{'id': 'c', 'sentence_id': 's1',
                                 'original_text': '서명일: [서명 전 확인]',
                                 'proposed_text': '서명일: 2026년 11월 9일',
                                 'delete_sentence': False,
                                 'required_to_resolve_conflict': False}],
                    'issues': ['서명 장소는 확인 필요'], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call', side_effect=fake_call):
            result = propose_notes_revision(snapshot, [note], env={})
        self.assertEqual(result['base_revision'], 4)
        self.assertEqual(result['issues'][0]['severity'], 'confirm')
        self.assertEqual(snapshot, old)
        self.assertEqual(result['note_ids'], ['n1'])

    def test_bad_issue_does_not_mutate_revision_or_memo(self):
        snapshot, note = self._example()
        before = (deepcopy(snapshot), deepcopy(note))
        def fake_call(*args, **kwargs):
            return {'changes': [{'id': 'c', 'sentence_id': 's1',
                                 'original_text': '서명일: [서명 전 확인]',
                                 'proposed_text': '서명일: 2026년 11월 9일',
                                 'delete_sentence': False,
                                 'required_to_resolve_conflict': False}],
                    'issues': [None], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call', side_effect=fake_call):
            with self.assertRaises(ValueError):
                propose_notes_revision(snapshot, [note], env={})
        self.assertEqual((snapshot, note), before)
