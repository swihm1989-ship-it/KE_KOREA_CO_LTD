"""Regression tests: AI issues, revision proposal, and FINAL blockers."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts.service import _normalize_ai_issues
from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.editing import apply_proposal
from Quotation_KEKOREA.contracts.final_policy import final_document_blockers


class ReviewIssueAndRevisionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = new_snapshot('review-regression', 'sale', 'ko')
        self.snapshot['clauses'] = [
            {'id': 'c1', 'title': '계약 조건', 'order': 1,
             'sentences': [{'id': 's1', 'text': '매도인의 서명일은 [서명 전 확인]으로 한다.',
                            'term_ids': [], 'source_refs': []}]}
        ]
        self.notes = [{'id': 'n1', 'contract_id': 'review-regression',
                       'sentence_id': 's1', 'base_revision': self.snapshot['revision'],
                       'status': 'note', 'instruction': '서명일을 2026년 11월 9일로 변경'}]

    def test_string_issue_is_not_discarded_and_preserves_warning(self):
        result = _normalize_ai_issues(['서명권자를 별도로 확인하세요.'], 'bad issues')
        self.assertEqual(result[0]['message'], '서명권자를 별도로 확인하세요.')
        self.assertEqual(result[0]['severity'], 'confirm')
        self.assertEqual(result[0]['code'], 'ai_review')

    def test_existing_block_issue_keeps_severity(self):
        result = _normalize_ai_issues([
            {'code': 'bank', 'severity': 'block', 'message': '계좌 검증 필요'}
        ], 'bad issues')
        self.assertEqual(result[0]['severity'], 'block')

    def test_malformed_issue_is_rejected_instead_of_hidden(self):
        for item in (None, {}, 123, ''):
            with self.subTest(item=item), self.assertRaises(ValueError):
                _normalize_ai_issues([item], 'bad issues')

    def test_note_proposal_with_string_issue_can_be_approved_and_blocker_cleared(self):
        before = deepcopy(self.snapshot)
        ai_result = {
            'changes': [{
                'id': 'change1', 'sentence_id': 's1',
                'original_text': self.snapshot['clauses'][0]['sentences'][0]['text'],
                'proposed_text': '매도인의 서명일은 2026년 11월 9일로 한다.',
                'delete_sentence': False,
                'required_to_resolve_conflict': False,
                'reason': '사용자 메모',
            }],
            'issues': ['서명권자를 확인하세요.'],
            'conflicts': [], 'explanation': '서명일 반영',
        }
        with patch('Quotation_KEKOREA.contracts.service._call', return_value=ai_result):
            proposal = propose_notes_revision(self.snapshot, self.notes, env={})
        self.assertEqual(len(proposal['changes']), 1)
        self.assertEqual(proposal['issues'][0]['severity'], 'confirm')
        updated = apply_proposal(self.snapshot, proposal, ['change1'])
        self.assertEqual(updated['revision'], self.snapshot['revision'] + 1)
        self.assertEqual(updated['clauses'][0]['sentences'][0]['text'],
                         '매도인의 서명일은 2026년 11월 9일로 한다.')
        self.assertEqual(before, self.snapshot)
        self.assertFalse(any('임시 확인 문구' in msg for msg in final_document_blockers(updated)))


if __name__ == '__main__':
    unittest.main()
