"""Surgical additive visibility fix for BOX 3 review suggestions.

Does not change validation, proposal, storage or AI services.
Run once from KE_KOREA_CO_LTD repository root.
"""
from __future__ import annotations

from pathlib import Path
import shutil
from datetime import datetime

ROOT = Path.cwd()
TARGET = ROOT / 'Quotation_KEKOREA/contracts/ui.py'
DOCS = [
    ROOT/'README.md',
    ROOT/'Quotation_KEKOREA/README.md',
    ROOT/'Quotation_KEKOREA/README_CONTRACTS.md',
    ROOT/'Quotation_KEKOREA/Team/README.md',
    ROOT/'Quotation_KEKOREA/Presentation/README.md',
]
TEST = ROOT/'Quotation_KEKOREA/tests/test_contract_risk_preview_visibility.py'

ANCHOR = '''    with st.container(key="contract_document_surface"):
        with st.container(key="contract_document_paper"):
            st.markdown(f"<h2>{escape(snapshot.get('title') or 'Contract')}</h2>", unsafe_allow_html=True)
            st.caption("DRAFT / 검토용 · 미확정 내용은 최종 합의가 아닙니다.")
'''
REPLACEMENT = '''    # The AI risk-review panel is rendered BELOW this document. Surface its
    # session-only edits here too, so they cannot be mistaken for saved clauses.
    active_preview = st.session_state.get(f'contract_risk_preview_{contract_id}') or {}
    preview_texts = (active_preview.get('sentences', {})
                     if active_preview.get('revision') == revision else {})
    with st.container(key="contract_document_surface"):
        with st.container(key="contract_document_paper"):
            st.markdown(f"<h2>{escape(snapshot.get('title') or 'Contract')}</h2>", unsafe_allow_html=True)
            st.caption("DRAFT / 검토용 · 미확정 내용은 최종 합의가 아닙니다.")
            if preview_texts:
                st.info(f"AI 위험 검토 수정안 {len(preview_texts)}개를 아래 문장에 미리 반영했습니다. "
                        "아직 저장된 계약서가 아닙니다. 아래 'AI 핵심 위험 검토'에서 "
                        "'선택한 수정안 비교·승인'을 완료해야 새 revision으로 저장됩니다.")
'''
OLD_PER_SENTENCE = '''                    preview = st.session_state.get(f'contract_risk_preview_{contract_id}') or {}
                    preview_texts = preview.get('sentences', {}) if preview.get('revision') == revision else {}
                    displayed_text = preview_texts.get(sentence_id, sentence['text'])
'''
NEW_PER_SENTENCE = '''                    displayed_text = preview_texts.get(sentence_id, sentence['text'])
'''
OLD_BUTTON = '''                    with text_col:
                        if st.button(displayed_text, key=f"contract_sentence_{contract_id}_{sentence_id}",
'''
NEW_BUTTON = '''                    with text_col:
                        if sentence_id in preview_texts:
                            st.caption("✎ AI 추천 수정안 미리보기 · 확정 저장 전")
                        if st.button(displayed_text, key=f"contract_sentence_{contract_id}_{sentence_id}",
'''

TEST_SOURCE = '''"""Rerun-safe BOX 3 visibility of uncommitted AI risk-review edits."""
import unittest
from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests


class RiskPreviewVisibilityTests(unittest.TestCase):
    setUp = ThreeBoxUiTests.setUp
    run_app = ThreeBoxUiTests.run_app
    def test_box3_displays_changed_sentence_and_unsaved_notice(self):
        self.at.session_state['contract_risk_preview_sample'] = {
            'revision': 1, 'sentences': {'s1': '사용자가 수정한 지급 조항'}
        }
        self.run_app()
        self.assertEqual(self.at.button(key='contract_sentence_sample_s1').label,
                         '사용자가 수정한 지급 조항')
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        texts = [info.value for info in self.at.info]
        self.assertTrue(any('AI 위험 검토 수정안 1개' in value for value in texts))
        self.assertTrue(any('새 revision으로 저장' in value for value in texts))
        self.run_app()
        self.assertEqual(self.at.button(key='contract_sentence_sample_s1').label,
                         '사용자가 수정한 지급 조항')

    def test_outdated_preview_not_displayed_as_current(self):
        self.at.session_state['contract_risk_preview_sample'] = {
            'revision': 0, 'sentences': {'s1': '오래된 수정안'}
        }
        self.run_app()
        self.assertNotEqual(self.at.button(key='contract_sentence_sample_s1').label,
                            '오래된 수정안')
        self.assertFalse(any('AI 위험 검토 수정안 1개' in info.value for info in self.at.info))


if __name__ == '__main__':
    unittest.main()
'''

DOC_ADDITION = '''\n### 2026-11-06 · 계약서 위험 검토 미리보기 표시 보강\n\n- `추천 문장 적용`은 기존 계약서 조항을 즉시 확정 저장하지 않으며, 같은 revision의 BOX 3 문장에만 임시 수정 문구를 표시한다.\n- BOX 3 상단에 미저장 위험 검토 수정안 개수와 `선택한 수정안 비교·승인` 경로를 명시하고, 변경된 각 문장에 미리보기 상태를 표시한다.\n- 비교·승인 및 revision 저장·PDF/DOCX 최종 검증 로직은 그대로 유지한다. 실제 Streamlit 운영 브라우저의 반영 여부는 별도 검증이 필요하다.\n'''

def main():
    if not TARGET.is_file() or not all(p.is_file() for p in DOCS):
        raise SystemExit('저장소 루트에서 실행해야 합니다. ui.py 또는 README 파일을 찾지 못했습니다.')
    text = TARGET.read_text(encoding='utf-8')
    markers = [(ANCHOR,1),(OLD_PER_SENTENCE,1),(OLD_BUTTON,1)]
    if 'AI 위험 검토 수정안 {len(preview_texts)}개' in text:
        raise SystemExit('이미 해당 UI 표시 패치가 적용된 것으로 보입니다. 중복 적용하지 않습니다.')
    for marker,expected in markers:
        if text.count(marker)!=expected:
            raise SystemExit('ui.py가 예상 코드와 다릅니다. 변경을 멈췄습니다. 현재 작업을 보존하세요.')
    if TEST.exists():
        raise SystemExit('동명 테스트 파일이 존재합니다. 덮어쓰지 않습니다.')
    updated = text.replace(ANCHOR, REPLACEMENT).replace(OLD_PER_SENTENCE, NEW_PER_SENTENCE).replace(OLD_BUTTON, NEW_BUTTON)
    compile(updated, str(TARGET), 'exec')
    compile(TEST_SOURCE, str(TEST), 'exec')
    backup_dir = ROOT/'kekorea_risk_preview_visibility_fix'/('backup_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in [TARGET,*DOCS]:
        destination=backup_dir/path.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,destination)
    TARGET.write_text(updated,encoding='utf-8')
    TEST.write_text(TEST_SOURCE,encoding='utf-8')
    for path in DOCS:
        original=path.read_text(encoding='utf-8')
        path.write_text(original.rstrip()+"\n"+DOC_ADDITION,encoding='utf-8')
    print('적용 완료: BOX 3 상태 표시, 문장별 강조, 회귀 테스트 1개 파일, README 5개')
    print('백업:',backup_dir)
    print('이 스크립트는 기존 AI / 계약 검증 / PDF 출력 경로를 수정하지 않았습니다.')

if __name__=='__main__':
    main()
