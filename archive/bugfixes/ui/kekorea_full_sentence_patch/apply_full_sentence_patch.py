"""Apply a narrowly scoped, non-destructive contract preview readability change.

Run from the KE_KOREA_CO_LTD repository root, after reviewing the diff.
"""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path.cwd()
UI = ROOT / 'Quotation_KEKOREA/contracts/ui.py'
DOCS = [
    ROOT / 'README.md',
    ROOT / 'Quotation_KEKOREA/README.md',
    ROOT / 'Quotation_KEKOREA/README_CONTRACTS.md',
    ROOT / 'Quotation_KEKOREA/Team/README.md',
    ROOT / 'Quotation_KEKOREA/Presentation/README.md',
]

OLD_BLOCK = '''                    with text_col:
                        if sentence_id in preview_texts:
                            st.caption("✎ AI 추천 수정안 미리보기 · 확정 저장 전")
                        if st.button(displayed_text, key=f"contract_sentence_{contract_id}_{sentence_id}",
                                     help="클릭해 이 문장의 메모를 열거나 선택합니다.",
                                     type='primary' if is_open else 'secondary', use_container_width=True):
                            if sentence_id not in opened:
                                opened.append(sentence_id)
                            st.rerun()
'''
NEW_BLOCK = '''                    with text_col:
                        with st.container(key=f"contract_sentence_display_{contract_id}_{sentence_id}"):
                            if sentence_id in preview_texts:
                                st.caption("✎ AI 추천 수정안 미리보기 · 확정 저장 전")
                            if st.button(displayed_text, key=f"contract_sentence_{contract_id}_{sentence_id}",
                                         help=(displayed_text if len(displayed_text) > 180 else
                                               "클릭해 이 문장의 메모를 열거나 선택합니다."),
                                         type='primary' if is_open else 'secondary', use_container_width=True):
                                if sentence_id not in opened:
                                    opened.append(sentence_id)
                                st.rerun()
                            # Full original text on mouse hover / keyboard focus for very long sentences.
                            # escape() prevents user-supplied contract text from injecting markup.
                            if len(displayed_text) > 180:
                                st.markdown(
                                    '<div class="contract-full-sentence-hover" role="tooltip">'
                                    + escape(displayed_text).replace('\\n', '<br/>') + '</div>',
                                    unsafe_allow_html=True)
'''
STYLE_ANCHOR = '''    @media(max-width:640px) {.st-key-contract_document_surface {padding:.25rem;}'''
STYLE = '''    /* Long clause readability: never shrink below a usable font size or clip text. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] {
        position:relative;min-width:0;}
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button {
        height:auto!important;max-height:none!important;min-height:2rem;
        white-space:normal!important;overflow:visible!important;text-overflow:clip!important;
        width:100%;align-items:flex-start;}
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button p {
        display:block!important;white-space:pre-wrap!important;overflow:visible!important;
        max-height:none!important;text-overflow:clip!important;overflow-wrap:anywhere;
        word-break:break-word;font-size:clamp(.8rem,1vw,1rem)!important;
        line-height:1.7!important;}
    .st-key-contract_document_paper .contract-full-sentence-hover {
        display:none;position:absolute;left:0;top:100%;z-index:50;
        width:min(38rem,80vw);max-height:65vh;overflow-y:auto;pointer-events:none;
        background:#fffdf6;color:#172b3a;border:1px solid #a6bdcc;
        border-radius:8px;box-shadow:0 12px 35px rgba(0,0,0,.17);
        padding:1rem;white-space:pre-wrap;overflow-wrap:anywhere;
        font:normal max(.875rem,11pt)/1.7 Georgia,"Malgun Gothic",serif;}
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:hover) .contract-full-sentence-hover,
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:focus-visible) .contract-full-sentence-hover {
        display:block;}
'''
MARK = '2026-11-09 · BOX 3 긴 문장 전체 보기'
DOC_BODY = (
    '\n### ' + MARK + '\n'
    '- 계약서 BOX 3의 문장 클릭 버튼을 줄바꿈 가능한 가변 높이로 변경하여 긴 문장도 생략 없이 표시합니다. '
    '폰트 크기는 6pt 이하로 줄이지 않습니다.\n'
    '- 180자 초과 문장은 마우스 오버 또는 키보드 포커스에서 전체 문장을 보여주는 보조 말풍선을 지원합니다. '
    '커서를 치우거나 포커스를 옮기면 숨깁니다. 말풍선 본문은 HTML escape 처리합니다.\n'
    '- sentence ID, 문장 클릭, 문장별 메모, AI 수정 미리보기, 수정 승인, DRAFT/FINAL 및 계약·무역 로직은 변경하지 않습니다.\n'
    '- 적용 스크립트가 문법 검사와 이전 코드 패턴 검증을 수행합니다. 전체 Streamlit 테스트·실제 배포 확인은 별도로 진행해야 합니다.\n'
)


def main():
    if not UI.is_file() or any(not d.is_file() for d in DOCS):
        raise SystemExit('ERROR: Run this script from KE_KOREA_CO_LTD root; ui.py or one of five README files is missing.')
    original = UI.read_text(encoding='utf-8')
    if 'contract-full-sentence-hover' in original or MARK in DOCS[0].read_text(encoding='utf-8'):
        raise SystemExit('Already applied (or partial application detected). No changes made.')
    if original.count(OLD_BLOCK) != 1 or original.count(STYLE_ANCHOR) != 1:
        raise SystemExit('ERROR: ui.py has changed since this patch was prepared. No changes made; preserve your local work.')
    changed = original.replace(OLD_BLOCK, NEW_BLOCK, 1).replace(STYLE_ANCHOR, STYLE + STYLE_ANCHOR, 1)
    ast.parse(changed, filename=str(UI))
    backups = ROOT / 'kekorea_full_sentence_patch' / ('backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    paths = [UI] + DOCS
    for p in paths:
        out = backups / p.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)
    try:
        UI.write_text(changed, encoding='utf-8')
        for doc in DOCS:
            old = doc.read_text(encoding='utf-8')
            if MARK not in old:
                doc.write_text(old.rstrip() + '\n' + DOC_BODY, encoding='utf-8')
    except Exception:
        for p in paths:
            shutil.copy2(backups / p.relative_to(ROOT), p)
        raise
    print('Applied: BOX 3 full sentence wrapping and optional hover/focus tooltip.')
    print('README: all five files updated.')
    print('Backups:', backups)
    print('Next: run contract UI tests, entire test suite, git diff --check, and README guard.')


if __name__ == '__main__':
    main()
