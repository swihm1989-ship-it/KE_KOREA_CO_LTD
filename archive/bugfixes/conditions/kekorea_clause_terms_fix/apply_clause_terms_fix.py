"""Apply only BOX2 clause candidate staging + selective DRAFT flags. Preserve backups."""
from datetime import datetime
from pathlib import Path
import ast
import shutil
import sys

ROOT = Path.cwd()
UI = ROOT / 'Quotation_KEKOREA/contracts/ui.py'
DRAFT = ROOT / 'Quotation_KEKOREA/contracts/draft_exports.py'
MODULE = ROOT / 'Quotation_KEKOREA/contracts/clause_terms.py'
TEST = ROOT / 'Quotation_KEKOREA/tests/test_contract_clause_term_bridge.py'
PKG = Path(__file__).resolve().parent
READMES = [ROOT / name for name in (
    'README.md', 'Quotation_KEKOREA/README.md', 'Quotation_KEKOREA/README_CONTRACTS.md',
    'Quotation_KEKOREA/Team/README.md', 'Quotation_KEKOREA/Presentation/README.md')]

UI_IMPORT = 'from Quotation_KEKOREA.contracts.clause_terms import clause_evidence, merge_clause_candidates\n'
UI_ANCHOR = 'def _run_editor(repo, snapshot, state_key, env):\n'
UI_ORIGINAL = '''    st.markdown('<span id="contract-terms"></span>', unsafe_allow_html=True)
    st.markdown("#### 거래금액·수수료·지급·기간·법률 및 기타 조건")
    state_key_terms = f"contract_terms_table_{snapshot['contract_id']}_{snapshot['revision']}"
    terms_rows = st.data_editor(
        _term_rows(snapshot), key=state_key_terms, hide_index=True,
'''
UI_UPDATED = '''    st.markdown('<span id="contract-terms"></span>', unsafe_allow_html=True)
    st.markdown("#### 거래금액·수수료·지급·기간·법률 및 기타 조건")
    candidate_key = f"contract_clause_candidates_{snapshot['contract_id']}_{snapshot['revision']}"
    editor_version_key = f"contract_clause_editor_version_{snapshot['contract_id']}_{snapshot['revision']}"
    st.caption('계약서 본문과 구조화 조건표는 별도 데이터입니다. 이미 본문에 있는 정보만 AI가 다시 추출해 입력 후보로 보여줍니다.')
    can_extract = bool(clause_evidence(snapshot)) and st.session_state.get(f"contract_ai_consent_{snapshot['contract_id']}", False)
    if st.button('계약서 본문에서 조건 후보 불러오기', disabled=not can_extract,
                 key=f"contract_clause_extract_{snapshot['contract_id']}_{snapshot['revision']}"):
        try:
            with st.spinner('현재 계약서 본문에서 거래조건 후보를 찾는 중입니다...'):
                analysis = analyze_trade([{'role': 'user', 'content': clause_evidence(snapshot)}],
                                         snapshot, [], env=env)
            if analysis['contract_type'] != snapshot['contract_type']:
                raise ValueError('계약 유형이 달라 기존 조건을 보존했습니다.')
            staged = merge_clause_candidates(snapshot, analysis)
            st.session_state[candidate_key] = staged
            st.session_state[editor_version_key] = st.session_state.get(editor_version_key, 0) + 1
            st.rerun()
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(f'본문 거래조건 후보 추출 실패: {exc}')
    editor_snapshot = st.session_state.get(candidate_key) or snapshot
    if candidate_key in st.session_state:
        st.info('본문에서 찾은 조건이 입력표에 AI 제안으로 나타납니다. 실제 값과 당사자 정보를 검토하고 상태를 확정한 뒤 기존 저장 버튼을 누르세요. 아직 원본은 변경되지 않았습니다.')
        if st.button('불러온 후보 취소', key=f"contract_clause_cancel_{snapshot['contract_id']}_{snapshot['revision']}"):
            st.session_state.pop(candidate_key, None)
            st.session_state[editor_version_key] = st.session_state.get(editor_version_key, 0) + 1
            st.rerun()
    state_key_terms = f"contract_terms_table_{snapshot['contract_id']}_{snapshot['revision']}_{st.session_state.get(editor_version_key, 0)}"
    terms_rows = st.data_editor(
        _term_rows(editor_snapshot), key=state_key_terms, hide_index=True,
'''
DRAFT_ORIGINAL = '''    for clause in sorted(snapshot['clauses'], key=lambda c: c.get('order', 0)):
        lines.append((clause.get('title') or '', True))
        for sentence in clause.get('sentences', []):
            # An unresolved contract must not present ANY sentence as approved fact.
            # Preserve the exact original text, visibly qualify it instead of guessing replacements.
            prefix = ('[확인 필요] ' if korean else '[TBD / UNCONFIRMED] ') if issues else ''
            lines.append((prefix + sentence['text'], False))
'''
DRAFT_UPDATED = '''    term_map = {}
    for term in snapshot.get('terms', []):
        for identifier in (term.get('key'), term.get('id')):
            if identifier:
                term_map[str(identifier)] = term
    for clause in sorted(snapshot['clauses'], key=lambda c: c.get('order', 0)):
        lines.append((clause.get('title') or '', True))
        for sentence in clause.get('sentences', []):
            # Scope markers to directly linked, unconfirmed terms only. All other
            # unresolved concerns remain in the complete appendix and DRAFT notice.
            linked = [term_map.get(str(identifier)) for identifier in sentence.get('term_ids', [])]
            unresolved = any(term is None or term.get('status') != 'confirmed'
                             or not str(term.get('value') or '').strip() for term in linked)
            raw_text = sentence['text']
            already_marked = ('[서명 전 확인]' in raw_text or '[확인 필요]' in raw_text
                              or '[TBD' in raw_text or '[TO CONFIRM]' in raw_text)
            prefix = ('[확인 필요] ' if korean else '[TBD / UNCONFIRMED] ') if unresolved and not already_marked else ''
            lines.append((prefix + raw_text, False))
'''


def unique_replace(source, before, after, name):
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f'{name}: expected exactly one anchor, found {count}; no files changed.')
    return source.replace(before, after, 1)


def main():
    for p in [UI, DRAFT, *READMES]:
        if not p.is_file():
            raise RuntimeError(f'Missing project file: {p}')
    if MODULE.exists() or TEST.exists():
        raise RuntimeError('Module or test already exists. Avoid applying patches twice.')
    ui = UI.read_text('utf-8')
    draft = DRAFT.read_text('utf-8')
    if UI_IMPORT in ui:
        raise RuntimeError('This patch is already applied.')
    ui = unique_replace(ui, UI_ANCHOR, UI_ANCHOR, 'editor entry')
    ui = unique_replace(ui, UI_ORIGINAL, UI_UPDATED, 'BOX2 editor')
    ui = unique_replace(ui, '_party_rows(snapshot), key=f"contract_parties_table_{snapshot[\'contract_id\']}_{snapshot[\'revision\']}"',
                        '_party_rows(editor_snapshot), key=f"contract_parties_table_{snapshot[\'contract_id\']}_{snapshot[\'revision\']}_{st.session_state.get(editor_version_key, 0)}"', 'party editor')
    draft = unique_replace(draft, DRAFT_ORIGINAL, DRAFT_UPDATED, 'draft rendering')
    ui = UI_IMPORT + ui
    for p, body in [(UI, ui), (DRAFT, draft), (MODULE, (PKG/'clause_terms.py').read_text('utf-8')),
                    (TEST, (PKG/'test_contract_clause_term_bridge.py').read_text('utf-8'))]:
        ast.parse(body, filename=str(p))
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = ROOT / ('clause_terms_fix_backup_' + stamp)
    for p in [UI, DRAFT, *READMES]:
        target = backup / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    MODULE.parent.mkdir(parents=True, exist_ok=True)
    TEST.parent.mkdir(parents=True, exist_ok=True)
    UI.write_text(ui, 'utf-8')
    DRAFT.write_text(draft, 'utf-8')
    MODULE.write_text((PKG/'clause_terms.py').read_text('utf-8'), 'utf-8')
    TEST.write_text((PKG/'test_contract_clause_term_bridge.py').read_text('utf-8'), 'utf-8')
    note = ('\n\n### 2026-11-09 · 본문 조건 후보 연결 및 DRAFT 문장별 표시\n'
            '- BOX 2에서 계약서 본문을 AI로 재분석하여 값이 비어 있는 구조화 조건과 당사자 필드에 미승인 후보를 불러옵니다. 기존 비어 있지 않은 값은 보존하고 사용자 승인과 본문 영향 비교 절차를 유지합니다.\n'
            '- 검토용 PDF/DOCX는 미확정 조건과 직접 연결된 문장에만 추가 표시를 붙이고, 미확정 전체 목록은 부록에 유지합니다. DRAFT 워터마크와 FINAL 검증은 변경하지 않습니다.\n')
    for p in READMES:
        with p.open('a', encoding='utf-8') as f:
            f.write(note)
    print('Applied. Backup:', backup)
    print('Updated:', UI.relative_to(ROOT), DRAFT.relative_to(ROOT), MODULE.relative_to(ROOT), TEST.relative_to(ROOT))
    print('5 README files updated. Run unit tests and README sync guard before commit.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('No changes committed:', exc, file=sys.stderr)
        sys.exit(1)
