"""Reorder KE KOREA contract Streamlit UI: draft first, review later.

Run once from repository root. Only changes Quotation_KEKOREA/contracts/ui.py.
Does not relax export validation or change ECLADO/quotation code.
"""
from pathlib import Path
import ast
import re
import sys

PATH = Path('Quotation_KEKOREA/contracts/ui.py')
if not PATH.is_file():
    sys.exit(f'ERROR: Run from repo root; missing {PATH}')
source = PATH.read_text(encoding='utf-8')
if '상세 거래조건 수정 (선택)' in source and '검토 사항 (' in source:
    print('Already applied; no changes.')
    sys.exit(0)

# Do not modify the file until all required anchors have been verified.
start = '    if snapshot.get("issues"):\n        with st.expander("AI/검토 참고 사항", expanded=True):\n'
end = '    selected_key = f"contract_selected_sentence_{snapshot[\'contract_id\']}"\n'
if source.count(start) != 1 or source.count(end) != 1:
    sys.exit('ERROR: Draft review block not as expected. No changes made.')
start_pos = source.index(start)
end_pos = source.index(end, start_pos)
review = source[start_pos:end_pos]
if 'st.checkbox(' not in review or '_save_snapshot' not in review:
    sys.exit('ERROR: Review block did not match expected features. No changes made.')
review = review.replace(
    'with st.expander("AI/검토 참고 사항", expanded=True):',
    'with st.expander(f"검토 사항 ({len(snapshot[\'issues\'])}개) · 필요할 때 열기", expanded=False):'
)
replacement = (
    '    if snapshot.get("issues"):\n'
    '        st.caption(f"미확정·검토 항목 {len(snapshot[\'issues\'])}개는 계약서 본문 아래에서 확인할 수 있습니다.")\n'
)
source = source[:start_pos] + replacement + source[end_pos:]

# Append review after the text and annotations rather than above the contract.
next_func = '\n\ndef _export_panel(repo, snapshot, env):\n'
if source.count(next_func) != 1:
    sys.exit('ERROR: Export panel anchor mismatch. No changes made.')
source = source.replace(next_func, '\n' + review + next_func, 1)

# Remove full data editors from the top of the document view.
top_editor = '    st.markdown("### 거래조건표")\n    _run_editor(repo, snapshot, state_key, env)\n'
if source.count(top_editor) != 1:
    sys.exit('ERROR: Top transaction editor anchor mismatch. No changes made.')
source = source.replace(top_editor, '', 1)

# Once a draft exists, place the optional editor after the displayed contract.
draft_render = '        _render_draft(repo, snapshot, state_key, env)\n'
if source.count(draft_render) != 1:
    sys.exit('ERROR: Contract draft render anchor mismatch. No changes made.')
source = source.replace(
    draft_render,
    draft_render +
    '        with st.expander("상세 거래조건 수정 (선택)", expanded=False):\n'
    '            st.markdown("### 거래조건표")\n'
    '            _run_editor(repo, snapshot, state_key, env)\n', 1,
)

# Before first draft, retain the same editor in an optional collapsed section.
reference_anchor = '    _references_panel(repo, active_id, env)\n'
if source.count(reference_anchor) != 1:
    sys.exit('ERROR: References anchor mismatch. No changes made.')
source = source.replace(
    reference_anchor,
    '    if not snapshot.get("clauses"):\n'
    '        with st.expander("상세 거래조건 수정 (선택)", expanded=False):\n'
    '            st.markdown("### 거래조건표")\n'
    '            _run_editor(repo, snapshot, state_key, env)\n'
    + reference_anchor, 1,
)

try:
    ast.parse(source, filename=str(PATH))
except SyntaxError as exc:
    sys.exit(f'ERROR: Syntax check failed at line {exc.lineno}: {exc.msg}. No changes made.')
PATH.write_text(source, encoding='utf-8')
print('Updated only Quotation_KEKOREA/contracts/ui.py')
print('Draft body now appears first; optional detailed editing and AI review are collapsed.')
print('Existing contract export checks are unchanged.')
