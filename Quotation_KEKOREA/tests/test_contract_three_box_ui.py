"""Real Streamlit interactions with synthetic contract data and no network."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot
from Quotation_KEKOREA.tests.test_contract_workspace_ui import MemoryContracts


class WorkspaceRepository(MemoryContracts):
    def __init__(self):
        super().__init__()
        self.annotations = {}
        self.exports = []
        self.files = {}

    def save_annotation(self, row):
        self.annotations[row['id']] = deepcopy(row)

    def list_annotations(self, contract_id):
        return [deepcopy(row) for row in reversed(list(self.annotations.values()))
                if row['contract_id'] == contract_id]

    def upload_private_file(self, bucket, path, content, mime):
        self.files[path] = content

    def save_export(self, row):
        self.exports.append(dict(row, id=str(len(self.exports))))

    def list_exports(self, contract_id):
        return [row for row in self.exports if row['contract_id'] == contract_id]

    def delete_export(self, contract_id, revision, extension, path):
        self.exports = [row for row in self.exports if row['storage_path'] != path]

    def delete_private_file(self, bucket, path):
        self.files.pop(path, None)


class ThreeBoxUiTests(unittest.TestCase):
    def setUp(self):
        self.repo = WorkspaceRepository()
        snapshot = example_snapshot()
        snapshot['revision'] = 1
        self.repo.create_contract(dict(title=snapshot['title'], contract_type='sale', language='ko'), snapshot)
        patcher = patch('Quotation_KEKOREA.contracts.ui._repository', return_value=self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.at = AppTest.from_string(
            "from Quotation_KEKOREA.contracts.ui import render_contract_page\n"
            "render_contract_page('계약서 만들기', {})")
        self.at.session_state['contract_active_id'] = 'sample'

    def run_app(self):
        self.at.run(timeout=20)
        self.assertFalse(self.at.exception)

    def button(self, label):
        return next(b for b in self.at.button if b.label == label)

    def save_note(self, sentence_id, instruction):
        self.at.button(key=f'contract_sentence_sample_{sentence_id}').click()
        self.run_app()
        next(t for t in self.at.text_area if t.label == '수정 메모 / 원하는 변경을 입력하세요').set_value(instruction)
        self.button('메모 저장').click()
        self.run_app()

    def test_three_boxes_in_order_with_manual_editor_before_preview(self):
        self.run_app()
        headings = [m.value for m in self.at.markdown]
        expected = ['### BOX 1 · 계약조건 입력 및 AI 대화',
                    '### BOX 2 · 상세조건 직접 입력', '### BOX 3 · 계약서 미리보기']
        indices = [headings.index(h) for h in expected]
        self.assertEqual(indices, sorted(indices))
        self.assertEqual(len(self.at.dataframe), 2)

    def test_sentence_notes_reload_without_cross_contamination(self):
        self.run_app()
        self.save_note('s1', '첫 문장만 간결하게')
        self.save_note('s2', '둘째 문장 삭제')
        self.at.button(key='contract_sentence_sample_s1').click()
        self.run_app()
        note = next(t for t in self.at.text_area if t.label == '수정 메모 / 원하는 변경을 입력하세요')
        self.assertEqual(note.value, '첫 문장만 간결하게')
        self.assertEqual({r['sentence_id'] for r in self.repo.annotations.values()}, {'s1', 's2'})
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)

    def test_final_revision_request_commits_only_after_comparison_approval(self):
        self.run_app()
        self.save_note('s1', '첫째 수정')
        self.save_note('s2', '둘째 수정')
        def proposer(snapshot, sentence_id, instruction, *, env):
            original = next(s['text'] for s in snapshot['clauses'][0]['sentences'] if s['id'] == sentence_id)
            return {'changes': [{'id': sentence_id, 'sentence_id': sentence_id,
                                 'original_text': original, 'proposed_text': instruction}], 'issues': []}
        with patch('Quotation_KEKOREA.contracts.ui.propose_revision', side_effect=proposer):
            self.button('최종 수정 요청').click()
            self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        self.assertTrue(self.button('선택한 변경을 하나의 revision으로 적용').disabled)
        next(c for c in self.at.checkbox if c.label == '선택한 수정안 사이의 금액·기한·역할 충돌을 확인했습니다').check()
        self.run_app()
        self.button('선택한 변경을 하나의 revision으로 적용').click()
        self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 2)
        saved = self.repo.revisions['sample'][-1]['snapshot']
        self.assertEqual([s['text'] for s in saved['clauses'][0]['sentences']], ['첫째 수정', '둘째 수정'])
        self.assertTrue(self.button('최종 수정 요청').disabled)

    def test_draft_private_export_allowed_while_final_stays_blocked(self):
        self.run_app()
        with patch('Quotation_KEKOREA.contracts.ui.export_contract') as final_export:
            self.assertTrue(self.button('최종 계약서 PDF').disabled)
            self.button('검토용 초안 PDF').click()
            self.run_app()
            final_export.assert_not_called()
        self.assertEqual(len(self.repo.exports), 1)
        self.assertIn('/exports/draft/', self.repo.exports[0]['storage_path'])
        self.assertEqual(self.repo.exports[0]['revision'], 1)

    def test_default_review_has_no_duplicated_english_error_checkbox(self):
        self.run_app()
        self.assertFalse(any('Confirm payment' in e.value for e in self.at.error))
        self.assertFalse(any('Confirm payment' in c.label for c in self.at.checkbox))

    def test_tbd_reopens_only_the_selected_previously_confirmed_issue(self):
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['issues'] = [dict(id='i1', severity='confirm', code='review_one', confirmed=True, message='One'),
                              dict(id='i2', severity='confirm', code='review_two', confirmed=True, message='Two'),
                              dict(id='i3', severity='block', code='review_three', message='Three')]
        self.run_app()
        self.at.radio(key='contract_issue_action_sample_1_0').set_value('TBD 유지')
        self.button('항목별 검토 상태 저장').click()
        self.run_app()
        saved = self.repo.revisions['sample'][-1]['snapshot']
        self.assertFalse(saved['issues'][0]['confirmed'])
        self.assertTrue(saved['issues'][1]['confirmed'])
        from Quotation_KEKOREA.contracts.rules import validate_snapshot
        self.assertIn('review_one', [i['code'] for i in validate_snapshot(saved, for_export=True)])

    def test_unchanged_review_does_not_make_saved_notes_stale(self):
        self.run_app()
        self.save_note('s1', '저장된 요청')
        self.button('항목별 검토 상태 저장').click()
        self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        self.assertFalse(self.button('최종 수정 요청').disabled)

    def test_previously_resolved_block_can_be_explicitly_reopened(self):
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['issues'][0].update(severity='info', original_severity='block', resolved_by_user=True,
                                     resolution='기존 근거')
        snapshot['issues'].append(dict(id='i2', severity='confirm', code='other', message='Other'))
        self.run_app()
        self.at.radio(key='contract_issue_action_sample_1_0').set_value('TBD 유지')
        self.button('항목별 검토 상태 저장').click()
        self.run_app()
        issue = self.repo.revisions['sample'][-1]['snapshot']['issues'][0]
        self.assertEqual(issue['severity'], 'block')
        self.assertFalse(issue['resolved_by_user'])

    def test_manual_editor_saves_explicit_statuses_without_resolving_other_issues(self):
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['clauses'] = []
        snapshot['terms'] = [dict(key='scope', value='기존 범위', status='suggested')]
        self.run_app()
        rows = next(d.value for d in self.at.dataframe if '항목' in d.value.columns)
        scope_index = rows.index[rows['key'] == 'scope'][0]
        currency_index = rows.index[rows['key'] == 'currency'][0]
        self.at.session_state['contract_terms_table_sample_1'] = {
            'edited_rows': {int(scope_index): {'value': '사용자 확정 범위', 'status': '확정'},
                            int(currency_index): {'value': 'USD', 'status': 'TBD 유지'}},
            'added_rows': [], 'deleted_rows': []}
        self.button('조건표 변경 저장 / 초안 영향 확인').click()
        self.run_app()
        saved = self.repo.revisions['sample'][-1]['snapshot']
        terms = {t['key']: t for t in saved['terms']}
        self.assertEqual(terms['scope']['status'], 'confirmed')
        self.assertEqual(terms['scope']['value'], '사용자 확정 범위')
        self.assertEqual(terms['currency']['status'], 'missing')
        self.assertEqual(terms['currency']['value'], 'USD')
        self.assertEqual(saved['issues'][0]['severity'], 'block')

    def test_ai_analysis_keeps_existing_draft_in_candidate_flow(self):
        self.repo.messages = []
        self.repo.list_messages = lambda contract_id: deepcopy(self.repo.messages)
        self.repo.add_message = lambda contract_id, role, content: self.repo.messages.append(dict(role=role, content=content))
        self.run_app()
        original = deepcopy(self.at.session_state['contract_snapshot_sample']['clauses'])
        self.at.checkbox(key='contract_ai_consent_sample').check()
        self.at.checkbox(key='contract_use_library_sample').uncheck()
        self.run_app()
        with patch('Quotation_KEKOREA.contracts.ui.analyze_trade', return_value={
                'contract_type': 'sale', 'terms': [], 'parties': [], 'issues': [], 'questions': []}):
            self.at.chat_input(key='contract_prompt_sample').set_value('지급일을 바꿔 주세요')
            self.run_app()
        self.assertIn('contract_pending_analysis_sample', self.at.session_state)
        self.assertEqual(self.at.session_state['contract_snapshot_sample']['clauses'], original)

    def test_changing_one_unconfirmed_review_does_not_create_empty_revision(self):
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['issues'][0]['severity'] = 'confirm'
        self.run_app()
        self.button('항목별 검토 상태 저장').click()
        self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)

    def test_final_download_uses_existing_validation_and_renderer(self):
        from Quotation_KEKOREA.contracts.rules import COMMON_REQUIRED, TYPE_REQUIRED, validate_snapshot
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['issues'] = []
        snapshot['terms'] = [dict(key=key, value='Agreed value', status='confirmed')
                             for key in COMMON_REQUIRED + TYPE_REQUIRED['sale'] if key not in {'buyer', 'seller'}]
        snapshot['parties'] = [dict(id=role, legal_name=role + ' Example Ltd', country='KR', address='Seoul',
                                   roles=[role], status='confirmed') for role in ('buyer', 'seller')]
        self.assertEqual(validate_snapshot(snapshot, for_export=True), [])
        self.run_app()
        self.assertFalse(self.button('최종 계약서 PDF').disabled)
        self.button('최종 계약서 PDF').click()
        self.run_app()
        self.assertEqual(len(self.repo.exports), 1)
        self.assertIn('/exports/final/', self.repo.exports[0]['storage_path'])
        self.assertNotIn('-DRAFT-', self.repo.exports[0]['storage_path'])

    def test_failed_draft_export_record_is_cleaned_up(self):
        from Quotation_KEKOREA.contracts.repository import ContractRepositoryError
        self.run_app()
        with patch.object(self.repo, 'save_export', side_effect=ContractRepositoryError('synthetic failure')):
            self.button('검토용 초안 PDF').click()
            self.run_app()
        self.assertFalse(self.repo.files)
        self.assertFalse(self.repo.exports)
        self.assertNotIn('contract_output_draft_sample_1_pdf', self.at.session_state)

    def test_annotation_log_failure_does_not_hide_committed_revision(self):
        from Quotation_KEKOREA.contracts.repository import ContractRepositoryError
        self.run_app()
        snapshot = self.at.session_state['contract_snapshot_sample']
        proposal = dict(id='proposal_synthetic', contract_id='sample', base_revision=1, note_ids=['n1'],
                        instruction='수정', changes=[dict(id='change1', sentence_id='s1',
                        original_text=snapshot['clauses'][0]['sentences'][0]['text'], proposed_text='승인된 새 문장')])
        self.at.session_state['contract_pending_proposal'] = proposal
        self.run_app()
        with patch.object(self.repo, 'save_annotation', side_effect=ContractRepositoryError('synthetic log failure')):
            self.button('선택한 변경을 하나의 revision으로 적용').click()
            self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 2)
        self.assertEqual(self.at.session_state['contract_snapshot_sample']['revision'], 2)
        self.assertNotIn('contract_pending_proposal', self.at.session_state)
        self.assertTrue(any('수정 이력 메모' in w.value for w in self.at.warning))

