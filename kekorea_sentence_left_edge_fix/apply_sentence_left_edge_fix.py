#!/usr/bin/env python3
"""Conservative BOX 3 visible sentence renderer patch; no backend changes."""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
import py_compile
import shutil
import sys

UI = Path('Quotation_KEKOREA/contracts/ui.py')
DOCS = [
    Path('README.md'),
    Path('Quotation_KEKOREA/README.md'),
    Path('Quotation_KEKOREA/README_CONTRACTS.md'),
    Path('Quotation_KEKOREA/Team/README.md'),
    Path('Quotation_KEKOREA/Presentation/README.md'),
]
MARKER = '/* Sentence text is real left-aligned document prose; the button is a click target only. */'
DOC_MARKER = 'BOX 3 문장 왼쪽 정렬(본문/클릭영역 분리)'
CSS_TARGET = '    /* Long clause readability: never shrink below a usable font size or clip text. */'
CSS = '''    /* Sentence text is real left-aligned document prose; the button is a click target only. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] {
        position:relative;min-width:0;
    }
    .st-key-contract_document_paper .contract-sentence-body {
        display:block;width:100%;box-sizing:border-box;margin:0;padding:.35rem .5rem;
        text-align:left!important;white-space:pre-wrap;overflow-wrap:anywhere;
        word-break:break-word;font:normal clamp(.8rem,1vw,1rem)/1.7 Georgia,"Malgun Gothic",serif;
        color:#172b3a;cursor:pointer;border-radius:2px;min-height:2rem;
    }
    /* Keep original button key and accessible label, but use it only as a full-surface hit area. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button {
        position:absolute!important;inset:0!important;z-index:3;
        display:block!important;width:100%!important;height:100%!important;
        min-height:0!important;opacity:0!important;margin:0!important;
        cursor:pointer!important;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:hover) .contract-sentence-body {
        background:#f0f7fc;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:focus-visible) .contract-sentence-body {
        outline:2px solid #0877c9;outline-offset:2px;
    }
    .st-key-contract_document_paper .contract-sentence-body.is-open {
        background:#e7f2fa;border-left:3px solid #0877c9;padding-left:calc(.5rem - 3px);
    }
'''
BUTTON_TARGET = '''                            if st.button(displayed_text, key=f"contract_sentence_{contract_id}_{sentence_id}",'''
BUTTON_REPLACEMENT = '''                            # Render document prose independently of Streamlit's button label alignment.
                            # The same keyed button remains the clickable, keyboard-accessible hit area.
                            st.markdown(
                                '<div class="contract-sentence-body' + (' is-open' if is_open else '') + '">'
                                + escape(displayed_text).replace('\\n', '<br/>') + '</div>',
                                unsafe_allow_html=True)
                            if st.button(displayed_text, key=f"contract_sentence_{contract_id}_{sentence_id}",'''
DOC_ADD = '''\n### BOX 3 문장 왼쪽 정렬(본문/클릭영역 분리)\n\n- 계약서 문장 표시를 Streamlit 버튼의 기본 텍스트 정렬과 분리해, 짧거나 긴 문장 모두 왼쪽 기준선에서 시작합니다.\n- 기존 문장 클릭 키/메모·AI 위험 검토·revision 처리와 긴 문장 전체 보기 기능은 유지합니다.\n- 기능 변경은 `Quotation_KEKOREA/contracts/ui.py`의 BOX 3 문장 렌더링과 CSS에만 한정됩니다.\n'''

def apply(root: Path):
    f = root / UI
    if not f.is_file():
        raise RuntimeError(f'프로젝트 루트에서 실행하세요. 파일을 찾지 못함: {UI}')
    source = f.read_text(encoding='utf-8')
    if MARKER in source:
        print('이미 적용되어 있습니다. 추가 변경 없음.')
        return
    for target, label in ((CSS_TARGET, 'CSS 앵커'), (BUTTON_TARGET, '문장 버튼 앵커')):
        occurrences = source.count(target)
        if occurrences != 1:
            raise RuntimeError(f'{label}가 정확히 한 번 나타나야 합니다 (발견: {occurrences}). 이전 수정사항을 보존하고 중단합니다.')
    for doc in DOCS:
        if not (root / doc).is_file():
            raise RuntimeError(f'README가 없어 작업하지 않았습니다: {doc}')
    revised = source.replace(CSS_TARGET, CSS + CSS_TARGET, 1).replace(BUTTON_TARGET, BUTTON_REPLACEMENT, 1)
    if revised == source:
        raise RuntimeError('코드가 바뀌지 않았습니다.')
    # Verify in memory first, then write backups and changes.
    compile(revised, str(f), 'exec')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = root / f'kekorea_sentence_left_edge_fix_backup_{stamp}'
    backup_dir.mkdir(parents=True)
    paths = [UI] + DOCS
    for item in paths:
        backup = backup_dir / item
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / item, backup)
    f.write_text(revised, encoding='utf-8')
    for doc in DOCS:
        path = root / doc
        old = path.read_text(encoding='utf-8')
        if DOC_MARKER not in old:
            path.write_text(old.rstrip() + '\n' + DOC_ADD, encoding='utf-8')
    py_compile.compile(str(f), doraise=True)
    print(f'적용 완료. 백업: {backup_dir}')
    print('수정 소스: Quotation_KEKOREA/contracts/ui.py / README 5개')
    print('주의: 로컬 전체 테스트 및 배포 화면 검증은 별도 수행해야 합니다.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.', help='KE_KOREA_CO_LTD 프로젝트 루트')
    args = parser.parse_args()
    try:
        apply(Path(args.root).resolve())
    except Exception as e:
        print(f'적용 중단: {e}', file=sys.stderr)
        sys.exit(1)
