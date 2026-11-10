"""Self-check the combined installer on an isolated fixture, without touching a repo."""
from pathlib import Path
import tempfile
import subprocess
import sys

BASE=Path(__file__).resolve().parent
UI='''from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.clause_terms import clause_evidence, merge_clause_candidates
# contract_direct_draft_ marker
# server direct download, 서버 업로드 없이 한 번 클릭

def _verified_contract_seal(env):
    return None

def _proposal_panel(repo, snapshot, proposal, state_key):
    try:
            updated = apply_proposal(snapshot, proposal, selected_ids)
            if proposal.get("note_ids"):
                pass
    except Exception:
        pass

def _contract_chat(repo, snapshot, state_key, env):
    consent = st.checkbox("입력한 거래 내용과 선택한 참고 문구·승인된 샘플 메모를 설정된 OpenAI API로 전송하는 데 동의합니다.",
                          key=f"contract_ai_consent_{snapshot['contract_id']}")
    prompt = st.chat_input("hi")
    if prompt:
        if True:
            with st.spinner("AI가 거래조건을 분석하고 있습니다..."):
                analysis = analyze_trade(prior_messages, snapshot, selected_context, env=env)
            updated = apply_analysis(snapshot, analysis)
            updated['library_sources'] = library_result['sources']
            if snapshot.get('clauses'):
                st.session_state[f"contract_pending_analysis_{snapshot['contract_id']}"] = {
                    "snapshot": updated,
                    "changes": _changed_terms(snapshot, updated),
                    "base_revision": snapshot["revision"],
                }
                st.info("기존 초안은 유지했습니다. 분석 결과는 별도 후보로 저장되며, 아래에서 선택적으로 수정안 생성 후 적용하세요.")
    pending = st.session_state.get('x')
    if pending:
            st.write("선택한 분석 후보만 수정안으로 만들며, 기존 조건/본문은 사용자가 적용할 때까지 바뀌지 않습니다.")
            if True:
                    proposal = propose_term_revision(
                        snapshot, list(unique_changes.values()), env=env)
                    st.session_state["contract_pending_proposal"] = proposal
'''
UI += """

def render_contract_page(page, env):
    with st.expander("저장·복사·언어 버전 관리", expanded=False):
        if copy_col.button("거래 조건 초기화 후 새 계약으로 복사"):
            copied["clauses"] = []
            st.rerun()
        if language_col.button("English 버전 새로 만들기"):
            st.rerun()
"""
NORMALIZER='''def normalize_term_keys(d):
  alias={"unit price":"unit_price"}
  return {**d, "terms":[{**t,"key":alias.get(t.get("key"),t.get("key"))} for t in d.get("terms",[])]}, []
'''
with tempfile.TemporaryDirectory() as d:
    root=Path(d)
    files={
        'Quotation_KEKOREA/contracts/ui.py':UI,
        'Quotation_KEKOREA/contracts/final_policy.py':'def final_document_blockers(snapshot):\n    return []\n',
        'Quotation_KEKOREA/contracts/normalize_terms.py':NORMALIZER,
        'Quotation_KEKOREA/contracts/models.py':'def validate_snapshot(snapshot):\n    return snapshot\n',
        'Quotation_KEKOREA/contracts/service.py':'''def _call(*args, **kwargs):
    return {}

def analyze_trade(messages, current_snapshot):
    user_data = {
        "messages": messages,
        "current_snapshot": current_snapshot,
    }
    policy = (
        "Do not invent parties, legal facts, amounts, dates, governing law, dispute forum, terms, currencies, or triggers. "
    )
    return user_data
''',
        'Quotation_KEKOREA/contracts/draft_exports.py':'def export_draft(): pass\n',
        'Quotation_KEKOREA/contracts/exports.py':'def export_contract(): pass\n',
        'Quotation_KEKOREA/app.py':'x=1\n',
        'Quotation_KEKOREA/tests/test_contract_three_box_ui.py':'x=1\n',
        'Quotation_KEKOREA/tests/test_contract_export_storage_fallback.py':'x=1\n',
    }
    for name in ['README.md','Quotation_KEKOREA/README.md','Quotation_KEKOREA/README_CONTRACTS.md',
                 'Quotation_KEKOREA/Team/README.md','Quotation_KEKOREA/Presentation/README.md']:
        files[name]='# doc\n'
    for name,content in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    result=subprocess.run([sys.executable,str(BASE/'apply_all.py')],cwd=root,
                          capture_output=True,text=True)
    print('INSTALL EXIT:',result.returncode,'\n',result.stdout,result.stderr)
    if result.returncode:sys.exit(result.returncode)
    changed=(root/'Quotation_KEKOREA/contracts/ui.py').read_text(encoding='utf-8')
    assert 'latest_unapplied_request(messages, snapshot)' in changed
    assert 'last_approved_chat_hash' in changed
    assert (root/'Quotation_KEKOREA/tests/test_contract_latest_instruction.py').exists()
    repeat=subprocess.run([sys.executable,str(BASE/'apply_all.py')],cwd=root,capture_output=True,text=True)
    print('REPEAT:',repeat.returncode,repeat.stdout)
    assert repeat.returncode==0
    assert '중복 변경하지 않았습니다' in repeat.stdout
print('SMOKE CHECK OK')
