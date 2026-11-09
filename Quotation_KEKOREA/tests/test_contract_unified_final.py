"""Regression tests for final-position combined revision flow."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts.editing import RevisionConflict
from Quotation_KEKOREA.contracts.final_merge import merge_revision_requests
from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot


class UnifiedFinalMergeTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = example_snapshot()
        self.snapshot['revision'] = 1

    def _note_proposer(self, snapshot, notes, *, env):
        out = []
        for note in notes:
            sid = note['sentence_id']
            before = next(s['text'] for c in snapshot['clauses'] for s in c['sentences'] if s['id'] == sid)
            out.append({'id': 'note-' + sid, 'sentence_id': sid, 'original_text': before,
                        'proposed_text': note['instruction'], 'delete_sentence': False})
        return {'contract_id': snapshot['contract_id'], 'base_revision': snapshot['revision'],
                'note_ids': [n['id'] for n in notes], 'issues': [], 'changes': out}

    def test_risk_only_can_request_without_ai_call(self):
        result = merge_revision_requests(self.snapshot, [], {'s1': 'Revised risk text'},
                                         propose_notes=self._note_proposer, env={})
        self.assertEqual(result['changes'][0]['proposed_text'], 'Revised risk text')
        self.assertEqual(result['note_ids'], [])
        self.assertEqual(self.snapshot['revision'], 1)

    def test_combines_one_note_and_one_risk_in_one_revision(self):
        notes = [{'id': 'n1', 'contract_id': self.snapshot['contract_id'], 'base_revision': 1,
                  'sentence_id': 's1', 'instruction': 'Updated note', 'status': 'note'}]
        result = merge_revision_requests(self.snapshot, notes, {'s2': 'Updated risk'},
                                         propose_notes=self._note_proposer, env={})
        self.assertEqual(len(result['changes']), 2)
        self.assertEqual(set(c['sentence_id'] for c in result['changes']), {'s1', 's2'})
        self.assertEqual(result['note_ids'], ['n1'])
        self.assertEqual(self.snapshot['clauses'][0]['sentences'][0]['text'],
                         example_snapshot()['clauses'][0]['sentences'][0]['text'])

    def test_conflicting_same_sentence_never_calls_ai(self):
        notes = [{'id': 'n1', 'sentence_id': 's1', 'instruction': 'Note text'}]
        with patch('Quotation_KEKOREA.contracts.final_merge.preview_proposal') as risk:
            with self.assertRaises(RevisionConflict):
                merge_revision_requests(self.snapshot, notes, {'s1': 'Risk text'},
                                        propose_notes=self._note_proposer, env={})
            risk.assert_not_called()

    def test_does_not_accept_empty_request(self):
        with self.assertRaises(ValueError):
            merge_revision_requests(self.snapshot, [], {}, propose_notes=self._note_proposer, env={})


class UnifiedFinalUiTests(unittest.TestCase):
    def setUp(self):
        from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests
        ThreeBoxUiTests.setUp(self)

    def run_app(self):
        from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests
        ThreeBoxUiTests.run_app(self)

    def test_risk_only_enables_final_request_and_saves_once_after_approval(self):
        self.at.session_state['contract_risk_preview_sample'] = {
            'revision': 1, 'sentences': {'s1': 'Selected risk recommendation'}}
        self.run_app()
        btn = self.at.button(key='contract_batch_request_sample_1')
        self.assertFalse(btn.disabled)
        btn.click()
        self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        next(b for b in self.at.button if b.label == '선택한 변경을 하나의 revision으로 적용').click()
        self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 2)
        self.assertEqual(self.repo.revisions['sample'][-1]['snapshot']['clauses'][0]['sentences'][0]['text'],
                         'Selected risk recommendation')

    def test_order_review_then_final_then_download(self):
        # Inspect the current composition order rather than relying on a
        # Streamlit widget's type (buttons are not markdown elements).
        import inspect
        from Quotation_KEKOREA.contracts.ui import render_contract_page
        source = inspect.getsource(render_contract_page)
        self.assertLess(source.index('render_risk_review(repo, snapshot, state_key, env)'),
                        source.index('_batch_request_panel(repo, snapshot, state_key, env, pending, buffers)'))
        self.assertLess(source.index('_batch_request_panel(repo, snapshot, state_key, env, pending, buffers)'),
                        source.index('_export_panel(repo, snapshot, env)'))
