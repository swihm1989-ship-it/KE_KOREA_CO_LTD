"""Conservative UI-only patch for notes belonging to earlier contract revisions."""
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / 'Quotation_KEKOREA/contracts/ui.py'
DOCS = [
    ROOT / 'README.md',
    ROOT / 'Quotation_KEKOREA/README.md',
    ROOT / 'Quotation_KEKOREA/README_CONTRACTS.md',
    ROOT / 'Quotation_KEKOREA/Team/README.md',
    ROOT / 'Quotation_KEKOREA/Presentation/README.md',
]
TEST = ROOT / 'Quotation_KEKOREA/tests/test_contract_note_revision_recovery.py'
MARKER = 'def _restore_previous_revision_note('
OLD = '''    if pending['excluded']:
        with st.expander(f"이전·중복·제외 메모 ({len(pending['excluded'])})", expanded=False):
            for item in pending['excluded']:
                st.caption(f"{item['note'].get('sentence_id')} · {item['reason']}")
                st.write(item['note'].get('instruction', ''))
'''
NEW = '''    if pending['excluded']:
        with st.expander(f"이전·중복·제외 메모 ({len(pending['excluded'])})", expanded=False):
            valid_ids = {s.get('id') for c in snapshot.get('clauses', [])
                         for s in c.get('sentences', [])}
            restored_ids = set()
            for item in pending['excluded']:
                old = item['note']
                sentence_id = old.get('sentence_id')
                st.caption(f"{sentence_id} · {item['reason']}")
                st.write(old.get('instruction', ''))
                # Only same-contract, existing-sentence, non-consumed old notes
                # may be copied. The user must explicitly request restoration.
                recoverable = (old.get('contract_id') == snapshot['contract_id']
                               and old.get('base_revision') != snapshot['revision']
                               and old.get('status') == 'note'
                               and sentence_id in valid_ids
                               and sentence_id not in restored_ids
                               and sentence_id not in instructions
                               and old.get('id') not in snapshot.get('applied_note_ids', [])
                               and str(old.get('instruction') or '').strip())
                if recoverable:
                    restored_ids.add(sentence_id)
                    st.button('이 메모를 현재 revision에서 다시 사용',
                              key=f"contract_restore_note_{snapshot['contract_id']}_{snapshot['revision']}_{sentence_id}",
                              on_click=_restore_previous_revision_note,
                              args=(snapshot['contract_id'], snapshot['revision'],
                                    sentence_id, old['instruction']))
'''
HOOK = '''def _restore_previous_revision_note(contract_id, revision, sentence_id, instruction):
    """Explicitly recover a previous note without silently approving old text."""
    buffer_key = f'contract_note_buffer_{contract_id}_{revision}'
    st.session_state.setdefault(buffer_key, {})[sentence_id] = str(instruction).strip()
    widget_key = f'contract_note_{contract_id}_{revision}_{sentence_id}'
    # Streamlit on_click runs before widgets are created on the next rerun.
    st.session_state[widget_key] = str(instruction).strip()
    open_key = f'contract_open_notes_{contract_id}_{revision}'
    opened = st.session_state.setdefault(open_key, [])
    if sentence_id not in opened:
        opened.append(sentence_id)
    proposal = st.session_state.get('contract_pending_proposal') or {}
    if proposal.get('contract_id') == contract_id and proposal.get('note_ids'):
        st.session_state.pop('contract_pending_proposal', None)


'''
BANNER_ANCHOR = '    if notes and not consent:\n'
BANNER = '''    if not notes:
        st.info('현재 revision에 적용할 수정 메모가 없습니다. 문장 옆에 새 메모를 작성하거나, '
                '위의 이전 메모를 펼쳐 현재 revision으로 다시 가져오세요.')
'''

TEST_SOURCE = '''"""Regression checks for explicit previous-revision note recovery."""
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.tests import test_contract_three_box_ui as fixture


class PreviousRevisionNoteRecoveryTests(unittest.TestCase):
    setUp = fixture.ThreeBoxUiTests.setUp
    run_app = fixture.ThreeBoxUiTests.run_app

    def test_previous_note_can_be_explicitly_recovered_and_requested(self):
        self.repo.save_annotation(dict(id='prior', contract_id='sample', sentence_id='s1',
            base_revision=0, status='note', instruction='기존 메모 다시 확인'))
        self.run_app()
        button = self.at.button(key='contract_batch_request_sample_1')
        self.assertTrue(button.disabled)
        self.at.button(key='contract_restore_note_sample_1_s1').click()
        self.run_app()
        self.assertEqual(self.at.text_area(key='contract_note_sample_1_s1').value,
                         '기존 메모 다시 확인')
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        self.assertTrue(self.at.button(key='contract_batch_request_sample_1').disabled)
        self.at.checkbox(key='contract_ai_consent_sample').check()
        self.run_app()
        self.assertFalse(self.at.button(key='contract_batch_request_sample_1').disabled)

    def test_deleted_sentence_note_is_not_restorable(self):
        self.repo.save_annotation(dict(id='prior', contract_id='sample',
            sentence_id='deleted_sentence', base_revision=0,
            status='note', instruction='삭제된 문장 메모'))
        self.run_app()
        self.assertFalse(any('contract_restore_note_' in str(b.key)
                             for b in self.at.button))

    def test_previous_note_is_not_implicitly_approved(self):
        self.repo.save_annotation(dict(id='prior', contract_id='sample', sentence_id='s1',
            base_revision=0, status='note', instruction='이전 메모'))
        self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        self.assertTrue(self.at.button(key='contract_batch_request_sample_1').disabled)
'''

DOC_TEXT = '''\n### 2026-11-06 계약서 메모 revision 복구 UX 보완\n\n계약서 BOX 3에서 현재 revision에 유효한 메모가 0개이지만 이전 revision의 메모가 존재하면, 기존 메모를 **명시적으로 현재 revision으로 가져오기** 버튼으로 재사용할 수 있습니다. 다른 계약 또는 삭제된 문장에 연결된 메모는 가져올 수 없습니다. 이전 메모를 자동 확정하거나 적용하지 않으며, AI 전송 동의와 기존 수정안 충돌 검사를 유지합니다. `최종 수정 요청` 비활성 상태에는 현재 revision 메모가 필요한 이유를 안내합니다. 계약서 데이터 모델·지급 정책·FINAL 검증·ECLADO/PO/PI/CI/PL 기능은 변경하지 않았습니다. 이 기능의 실제 Streamlit 검증은 전체 테스트를 통해 확인해야 합니다.\n'''

def main():
    if not UI.is_file():
        raise SystemExit('ERROR: run from extracted folder inside KE_KOREA_CO_LTD root.')
    src = UI.read_text(encoding='utf-8')
    if MARKER in src:
        raise SystemExit('Patch already applied. No files changed.')
    if src.count(OLD) != 1 or src.count(BANNER_ANCHOR) != 1:
        raise SystemExit('Source differs from inspected main version; nothing changed. Please inspect ui.py.')
    for path in DOCS:
        if not path.is_file():
            raise SystemExit(f'Missing README: {path}')
    if TEST.exists():
        raise SystemExit('Regression test path exists; stop to avoid overwriting it.')
    new = src.replace('def _batch_request_panel(', HOOK + 'def _batch_request_panel(', 1)
    new = new.replace(OLD, NEW, 1).replace(BANNER_ANCHOR, BANNER + BANNER_ANCHOR, 1)
    compile(new, str(UI), 'exec')
    compile(TEST_SOURCE, str(TEST), 'exec')
    today = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = Path(__file__).resolve().parent / ('backup_' + today)
    originals = [UI, *DOCS]
    for original in originals:
        dst = backup / original.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, dst)
    UI.write_text(new, encoding='utf-8')
    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(TEST_SOURCE, encoding='utf-8')
    for path in DOCS:
        path.write_text(path.read_text(encoding='utf-8').rstrip() + '\n' + DOC_TEXT,
                        encoding='utf-8')
    print('Applied minimal previous-revision note recovery UI patch.')
    print('Originals backed up at:', backup)
    print('Modified: contracts/ui.py, five READMEs. Added one UI regression test.')
    print('Run full test suite before committing or pushing.')

if __name__ == '__main__':
    main()
