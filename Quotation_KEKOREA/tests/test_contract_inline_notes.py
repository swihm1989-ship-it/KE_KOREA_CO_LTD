"""Multiple inline notes are kept together until one batch request."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from Quotation_KEKOREA.tests import test_contract_three_box_ui as three_box


class InlineNotesTests(unittest.TestCase):
    setUp = three_box.ThreeBoxUiTests.setUp
    run_app = three_box.ThreeBoxUiTests.run_app
    button = three_box.ThreeBoxUiTests.button
    def test_multiple_inline_notes_remain_open_and_are_requested_together(self):
        self.run_app()
        self.at.checkbox(key='contract_ai_consent_sample').check()
        self.run_app()
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        first = self.at.text_area(key='contract_note_sample_1_s1')
        first.set_value('첫 문장 수정')
        self.at.button(key='contract_sentence_sample_s2').click()
        self.run_app()
        self.assertEqual(self.at.text_area(key='contract_note_sample_1_s1').value, '첫 문장 수정')
        self.at.text_area(key='contract_note_sample_1_s2').set_value('둘째 문장 삭제')
        captured = []
        def batch(snapshot, notes, *, env):
            captured.append(deepcopy(notes))
            changes = []
            for note in notes:
                sentence = next(s for s in snapshot['clauses'][0]['sentences'] if s['id'] == note['sentence_id'])
                changes.append(dict(id=note['sentence_id'], sentence_id=note['sentence_id'],
                                    original_text=sentence['text'], proposed_text=note['instruction']))
            return dict(id='proposal_batch', contract_id='sample', base_revision=1,
                        changes=changes, note_ids=[n['id'] for n in notes], issues=[])
        with patch('Quotation_KEKOREA.contracts.ui.propose_notes_revision', side_effect=batch):
            self.button('최종 수정 요청').click()
            self.run_app()
        self.assertEqual(len(captured), 1)
        self.assertEqual({n['sentence_id']: n['instruction'] for n in captured[0]},
                         {'s1': '첫 문장 수정', 's2': '둘째 문장 삭제'})
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)

    def test_term_reconciliation_is_not_mislabelled_as_conflict(self):
        self.run_app()
        self.at.session_state['contract_pending_proposal'] = dict(
            id='proposal_term', contract_id='sample', base_revision=1,
            changes=[dict(id='term1', term_key='delivery', original_text='Busan', proposed_text='Seoul',
                          required_to_resolve_conflict=True, term_value={'key': 'delivery', 'value': 'Seoul'})])
        self.run_app()
        self.assertFalse(any('충돌 해소에 필요한 변경' in warning.value for warning in self.at.warning))

    def test_close_and_reopen_keeps_unsaved_note(self):
        self.run_app()
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        self.at.text_area(key='contract_note_sample_1_s1').set_value('메모를 잃지 않음')
        self.at.button(key='contract_note_close_sample_s1').click()
        self.run_app()
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        self.assertEqual(self.at.text_area(key='contract_note_sample_1_s1').value, '메모를 잃지 않음')

    def test_failed_ai_request_keeps_notes_and_original_revision(self):
        self.run_app()
        self.at.checkbox(key='contract_ai_consent_sample').check()
        self.run_app()
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        self.at.text_area(key='contract_note_sample_1_s1').set_value('초안 메모')
        self.run_app()
        with patch('Quotation_KEKOREA.contracts.ui.propose_notes_revision', side_effect=ValueError('임시 실패')):
            self.button('최종 수정 요청').click()
            self.run_app()
        self.assertTrue(any(row['instruction'] == '초안 메모' for row in self.repo.annotations.values()))
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        self.assertEqual(self.at.text_area(key='contract_note_sample_1_s1').value, '초안 메모')

    def test_editing_note_preserves_pending_term_proposal(self):
        self.run_app()
        self.at.session_state['contract_pending_proposal'] = dict(
            id='proposal_term', contract_id='sample', base_revision=1,
            changes=[dict(id='term1', term_key='delivery', original_text='Busan', proposed_text='Seoul',
                          required_to_resolve_conflict=True, term_value={'key': 'delivery', 'value': 'Seoul'})])
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        self.at.text_area(key='contract_note_sample_1_s1').set_value('본문 요청')
        self.run_app()
        self.assertEqual(self.at.session_state['contract_pending_proposal']['id'], 'proposal_term')
        self.assertTrue(self.button('최종 수정 요청').disabled)

    def test_batch_requires_explicit_api_consent(self):
        self.run_app()
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        self.at.text_area(key='contract_note_sample_1_s1').set_value('본문 수정')
        self.run_app()
        self.assertTrue(self.button('최종 수정 요청').disabled)
        self.at.checkbox(key='contract_ai_consent_sample').check()
        self.run_app()
        self.assertFalse(self.button('최종 수정 요청').disabled)

    def test_delete_last_saved_note_is_persisted(self):
        self.repo.save_annotation(dict(id='old', contract_id='sample', sentence_id='s1',
                                       base_revision=1, status='note', instruction='저장 메모'))
        self.run_app()
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        self.at.button(key='contract_note_remove_sample_s1').click()
        self.run_app()
        self.assertEqual(self.repo.annotations['old']['status'], 'dismissed')
        self.assertTrue(self.button('최종 수정 요청').disabled)

    def test_old_revision_note_can_be_read_but_not_automatically_requested(self):
        self.repo.save_annotation(dict(id='old', contract_id='sample', sentence_id='s1',
                                       base_revision=0, status='note', instruction='이전 메모'))
        self.run_app()
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        self.assertEqual(self.at.text_area(key='contract_note_sample_1_s1').value, '이전 메모')
        self.assertTrue(self.button('최종 수정 요청').disabled)


class JointAiRequestTests(unittest.TestCase):
    def test_all_notes_are_sent_in_one_ai_request(self):
        from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
        from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot, note
        snapshot = example_snapshot()
        changes = [dict(id='a', sentence_id='s1', original_text=snapshot['clauses'][0]['sentences'][0]['text'], proposed_text='첫 수정'),
                   dict(id='b', sentence_id='s2', original_text=snapshot['clauses'][0]['sentences'][1]['text'], proposed_text='둘째 수정')]
        with patch('Quotation_KEKOREA.contracts.service._call', return_value={'changes': changes, 'issues': []}) as ai:
            proposal = propose_notes_revision(snapshot, [note(), note('n2', 's2')], env={})
        self.assertEqual(ai.call_count, 1)
        self.assertEqual(len(ai.call_args.args[1]['notes']), 2)
        self.assertEqual(proposal['note_ids'], ['n1', 'n2'])

    def test_missing_note_or_protected_payment_cannot_be_applied(self):
        from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
        from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot, note
        snapshot = example_snapshot()
        changes = [dict(id='a', sentence_id='s1', original_text=snapshot['clauses'][0]['sentences'][0]['text'], proposed_text='첫 수정')]
        with patch('Quotation_KEKOREA.contracts.service._call', return_value={'changes': changes, 'issues': []}):
            with self.assertRaises(ValueError):
                propose_notes_revision(snapshot, [note(), note('n2', 's2')], env={})
        snapshot['clauses'][0]['sentences'][0]['id'] = 'commission_payment_sentence_0'
        with patch('Quotation_KEKOREA.contracts.service._call') as ai:
            with self.assertRaises(ValueError):
                propose_notes_revision(snapshot, [note(sentence='commission_payment_sentence_0')], env={})
            ai.assert_not_called()

    def test_conflicting_notes_are_returned_for_user_correction_without_changes(self):
        from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
        from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot, note
        snapshot = example_snapshot()
        with patch('Quotation_KEKOREA.contracts.service._call', return_value={
                'changes': [], 'conflicts': ['지급기한이 서로 다릅니다.'], 'issues': []}):
            with self.assertRaisesRegex(ValueError, '지급기한'):
                propose_notes_revision(snapshot, [note(), note('n2', 's2')], env={})
        self.assertEqual(snapshot['revision'], 4)

    def test_invalid_deletion_flag_is_not_accepted(self):
        from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
        from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot, note
        snapshot = example_snapshot()
        change = dict(id='a', sentence_id='s1', original_text=snapshot['clauses'][0]['sentences'][0]['text'],
                      proposed_text='수정', delete_sentence='false')
        with patch('Quotation_KEKOREA.contracts.service._call', return_value={'changes': [change], 'issues': []}):
            with self.assertRaises(ValueError):
                propose_notes_revision(snapshot, [note()], env={})

    def test_unknown_issue_severity_requires_confirmation(self):
        from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
        from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot, note
        snapshot = example_snapshot()
        change = dict(id='a', sentence_id='s1', original_text=snapshot['clauses'][0]['sentences'][0]['text'], proposed_text='수정')
        with patch('Quotation_KEKOREA.contracts.service._call', return_value={
                'changes': [change], 'issues': [{'severity': 'unclear', 'message': 'Check scope'}]}):
            proposal = propose_notes_revision(snapshot, [note()], env={})
        self.assertEqual(proposal['issues'][0]['severity'], 'confirm')

