"""Safe AI review issue recovery and full revision preview regression tests."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.service import _normalize_ai_issues
from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
from Quotation_KEKOREA.contracts.editing import apply_proposal


class AiReviewAndPreviewTests(TestCase):
    def setUp(self):
        self.snapshot = new_snapshot('sample','sale','ko')
        self.snapshot['revision'] = 4
        self.snapshot['clauses'] = [{'id':'c1','title':'서명','order':1,'sentences':[
            {'id':'s1','text':'서명일: [서명 전 확인]'}]}]
        self.note = {'id':'n1','contract_id':'sample','sentence_id':'s1',
                     'base_revision':4,'status':'note',
                     'instruction':'서명일을 2026년 11월 9일로 수정'}

    def test_text_and_dict_issues_are_preserved_not_silently_discarded(self):
        result = _normalize_ai_issues(['검토 필요',{'code':'date','severity':'block','message':'확인'}], 'error')
        self.assertEqual([i['severity'] for i in result], ['confirm','block'])
        self.assertEqual(result[0]['code'], 'ai_review_text')

    def test_malformed_issues_fail_closed(self):
        for value in (None, 3, [], ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _normalize_ai_issues([value], 'error')

    def test_valid_notes_make_reviewable_preview_without_automatic_commit(self):
        before=deepcopy(self.snapshot)
        def fake_call(*_args,**_kwargs):
            return {'changes':[{'id':'change1','sentence_id':'s1',
                      'original_text':'서명일: [서명 전 확인]',
                      'proposed_text':'서명일: 2026년 11월 9일',
                      'delete_sentence':False,'required_to_resolve_conflict':False}],
                    'issues':['통지처도 확인'], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call',side_effect=fake_call):
            proposal=propose_notes_revision(self.snapshot,[self.note],env={})
        self.assertEqual(self.snapshot,before)
        candidate=apply_proposal(self.snapshot, proposal, [x['id'] for x in proposal['changes']])
        self.assertEqual(candidate['revision'],5)
        self.assertEqual(candidate['clauses'][0]['sentences'][0]['text'],'서명일: 2026년 11월 9일')
        self.assertEqual(self.snapshot['revision'],4)
        self.assertEqual(self.note['status'],'note')

    def test_bad_ai_issue_keeps_contract_and_note_unchanged(self):
        before=deepcopy((self.snapshot,self.note))
        def fake_call(*_args,**_kwargs):
            return {'changes':[{'id':'change1','sentence_id':'s1',
                      'original_text':'서명일: [서명 전 확인]',
                      'proposed_text':'서명일: 2026년 11월 9일',
                      'delete_sentence':False,'required_to_resolve_conflict':False}],
                    'issues':[None], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call',side_effect=fake_call):
            with self.assertRaises(ValueError):
                propose_notes_revision(self.snapshot,[self.note],env={})
        self.assertEqual((self.snapshot,self.note), before)
