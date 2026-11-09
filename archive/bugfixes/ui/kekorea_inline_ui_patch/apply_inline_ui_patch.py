"""Conservative patch: preserve contract business logic, improve inline note layout.
Run from KE_KOREA_CO_LTD repository root. Refuses unexpected code versions.
"""
from pathlib import Path
from datetime import datetime
import shutil

ROOT=Path.cwd()
UI=ROOT/'Quotation_KEKOREA/contracts/ui.py'
READMES=[ROOT/'README.md',ROOT/'Quotation_KEKOREA/README.md',ROOT/'Quotation_KEKOREA/README_CONTRACTS.md',ROOT/'Quotation_KEKOREA/Team/README.md',ROOT/'Quotation_KEKOREA/Presentation/README.md']

BEFORE = '''                    text_col, note_col = st.columns([7, 3]) if is_open else (st.container(), None)
                    with text_col:
                        if st.button(sentence['text'], key=f"contract_sentence_{contract_id}_{sentence_id}",
                                     help="클릭해 이 문장의 메모를 열거나 선택합니다.",
                                     type='primary' if is_open else 'secondary', use_container_width=True):
                            if sentence_id not in opened:
                                opened.append(sentence_id)
                            st.rerun()
                    if note_col is None:
                        continue
                    with note_col:
                        st.caption("이 문장의 수정 메모")'''
AFTER = '''                    # A stable two-column row, even before the note is opened.
                    # Keeps document text aligned with a Word-style comment gutter.
                    text_col, note_col = st.columns([7, 3], gap="medium", vertical_alignment="top")
                    with text_col:
                        if st.button(sentence['text'], key=f"contract_sentence_{contract_id}_{sentence_id}",
                                     help="클릭해 이 문장의 메모를 열거나 선택합니다.",
                                     type='primary' if is_open else 'secondary', use_container_width=True):
                            if sentence_id not in opened:
                                opened.append(sentence_id)
                            st.rerun()
                    with note_col:
                        if not is_open:
                            st.caption("✎ 메모 추가 · 문장 클릭")
                            continue
                        st.caption("✎ 이 문장의 수정 메모")'''

CSS_OLD = '''    .st-key-contract_document_paper h4 {color:#092b4c;font-size:1rem;margin-top:1.5rem;}
'''
CSS_NEW = '''    .st-key-contract_document_paper h4 {color:#092b4c;font-size:1rem;margin-top:1.5rem;}
    /* Word-style comment gutter: stable row alignment and visible note cards. */
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] {
        align-items:flex-start;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child {
        min-width:0;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child [data-testid="stTextArea"] {
        border-radius:8px;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child textarea {
        background:#fffcf4;border:1px solid #eadbb8;min-height:96px;color:#243746;
        border-radius:6px;font-size:.88rem;line-height:1.5;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child textarea:focus {
        background:#fff;border-color:#0877c9;box-shadow:0 0 0 1px #0877c9;}
'''

# Existing code has the same phrase in only the contract-paper CSS block.
MARKER='현재 BOX 3에서는 문장 왼쪽과 메모 오른쪽의 고정 7:3 열을 사용합니다.'

def run():
    if not UI.is_file():
        raise SystemExit('Run this from KE_KOREA_CO_LTD repository root.')
    src=UI.read_text(encoding='utf-8')
    if BEFORE not in src:
        if ('text_col, note_col = st.columns([7, 3], gap="medium", vertical_alignment="top")' in src
                and 'with st.container(border=True):' in src):
            raise SystemExit('Inline note layout already applied. No change made.')
        raise SystemExit('Unexpected ui.py version; refusing to overwrite. Save git diff and ask for a refreshed patch.')
    if src.count(BEFORE)!=1 or src.count(CSS_OLD)!=1:
        raise SystemExit('Expected UI anchors are not unique. No change made.')
    for file in READMES:
        if not file.is_file():
            raise SystemExit(f'Missing required README: {file}')
    changed=src.replace(BEFORE,AFTER).replace(CSS_OLD,CSS_NEW)
    # Visually group the existing note controls into a bordered comment card.
    # Indent *only* the already-existing note block; no callbacks or behavior change.
    start='                        st.caption("✎ 이 문장의 수정 메모")\n'
    end='    _batch_request_panel(repo, snapshot, state_key, env, pending, buffers)\n'
    if changed.count(start)!=1 or changed.count(end)!=1:
        raise SystemExit('Comment-card anchors not found uniquely; no change made.')
    before_note,note_tail=changed.split(start,1)
    note_body,after_note=note_tail.split(end,1)
    note_block=start+note_body
    if not note_block.endswith('\n'):
        raise SystemExit('Note block unexpectedly lacks final newline.')
    indented=''.join('    '+line if line.strip() else line for line in note_block.splitlines(keepends=True))
    changed=(before_note+'                        with st.container(border=True):\n'
             +indented+end+after_note)
    compile(changed,str(UI),'exec')
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup=ROOT/f'.local_contract_ui_backup_{stamp}'
    backup.mkdir()
    shutil.copy2(UI,backup/'ui.py')
    for i,path in enumerate(READMES):
        shutil.copy2(path,backup/f'README_{i}.md')
    UI.write_text(changed,encoding='utf-8')
    additions={
        READMES[0]:'\n### 계약서 인라인 메모 UI 조정 (2026-11-06)\n계약서 BOX 3에서 문장과 메모 여백이 항시 좌우 정렬되도록 표시한다. 문장 선택 후 오른쪽 메모 입력란이 열리며 여러 문장을 동시에 편집하고 `최종 수정 요청`으로 일괄 AI 수정안을 요청한다. 최종 검증·ECLADO/PO/PI/CI/PL 로직은 변경하지 않았다.\n',
        READMES[1]:'\n### 2026-11-06 BOX 3 댓글 배치 보완\n문서형 초안의 각 문장을 7:3 고정 행으로 렌더링해 메모를 열기 전후에도 문장 정렬을 유지한다. 우측의 댓글 입력란은 선택한 문장에만 표시되고 다른 문장 메모는 동시에 유지된다. 기존 DB 저장, 일괄 AI 요청, revision 승인 및 출력 규칙은 변경하지 않았다.\n',
        READMES[2]:'\n### 2026-11-06 문장 옆 인라인 메모 UI 보완\nBOX 3에서는 문장과 우측 메모 영역이 모든 행에 고정 배치된다. 문장을 누르면 해당 행 오른쪽에 입력란이 열리며 다른 메모가 자동으로 닫히지 않는다. 메모 버퍼·일괄 AI 요청·검토와 승인 동작은 그대로 유지한다. 운영 브라우저 시각 QA는 별도 검증이 필요하다.\n',
        READMES[3]:'\n### 계약서 UX 업데이트 (2026-11-06)\nBOX 3 문장/댓글은 고정된 두 열로 렌더링하여 클릭 전후에 레이아웃이 이동하지 않는다. 수정 전후 비교·수동 승인·revision 동작은 동일하다. 기존 거래 문서 영역 및 위험 통제는 수정하지 않았다.\n',
        READMES[4]:'\n### 계약서 메모 시연 (2026-11-06)\n계약서 BOX 3의 문장을 클릭하면 같은 행 오른쪽에서 메모를 작성할 수 있다. 다른 문장 메모도 함께 열린다. 마지막 `최종 수정 요청`으로 한꺼번에 AI 제안을 비교하고 승인한다. 스크린샷과 실제 앱 운영 검증은 아직 별도로 수행해야 한다.\n',
    }
    for p,addition in additions.items():
        prior=p.read_text(encoding='utf-8')
        if MARKER in prior:
            continue
        p.write_text(prior.rstrip()+'\n'+addition,encoding='utf-8')
    print('Applied inline comment layout. Backups at:',backup)
    print('Changed UI:',UI)
    print('Changed five README files. Run tests and git diff --check; do not deploy until verified.')

if __name__=='__main__':
    run()
