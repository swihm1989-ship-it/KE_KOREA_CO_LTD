"""Idempotent, narrow installer. Run from KE_KOREA_CO_LTD repository root.

Only adds contracts/review.py and edits contracts/ui.py; never changes
quotation/ECLADO code, DB schemas, or contract export validation.
"""
import ast
from pathlib import Path
import sys

ROOT = Path('Quotation_KEKOREA')
UI = ROOT / 'contracts/ui.py'
REVIEW = ROOT / 'contracts/review.py'
MARKER = '# Contract RAG risk-review panel (read-only; user approval required)'

if not UI.is_file():
    sys.exit('ERROR: Run at project root; cannot find Quotation_KEKOREA/contracts/ui.py.')
src = UI.read_text(encoding='utf-8')
if MARKER in src:
    print('Already installed; no files changed.')
    sys.exit(0)
if REVIEW.exists():
    sys.exit('ERROR: contracts/review.py already exists; will not overwrite it.')

# Put the panel immediately below the generated draft and above advanced edit controls.
anchor = '        _render_draft(repo, snapshot, state_key, env)\n'
if src.count(anchor) != 1 or '상세 거래조건 수정 (선택)' not in src:
    sys.exit('ERROR: Expected simplified contract UI not found. No changes made.')
if 'from Quotation_KEKOREA.contracts.library import search_library' not in src:
    sys.exit('ERROR: Existing RAG integration not found. No changes made.')

panel = '''        # Contract RAG risk-review panel (read-only; user approval required)
        with st.expander("AI 핵심 위험 검토 · 필요할 때 실행", expanded=False):
            st.caption("승인된 기존 조항을 검색하여 현재 초안의 중요한 위험만 최대 5개 검토합니다. "
                       "AI 제안은 자동 적용되지 않으며 법률 자문을 대체하지 않습니다.")
            review_key = f"contract_rag_risk_{active_id}"
            review_state = st.session_state.get(review_key)
            if review_state and review_state.get("revision") != snapshot["revision"]:
                st.session_state.pop(review_key, None)
                review_state = None
            if st.button("현재 초안의 핵심 위험 3~5개 검토", key=f"rag_review_run_{active_id}_{snapshot['revision']}"):
                try:
                    from Quotation_KEKOREA.contracts.review import review_contract
                    parts = []
                    for clause in snapshot.get("clauses", []):
                        parts.extend(str(s.get("text") or "") for s in clause.get("sentences", []))
                    query = " ".join(parts)[:6000]
                    result = search_library(repo, snapshot, query, env=env)
                    findings = review_contract(snapshot, result.get("sources", []), env=env)
                    st.session_state[review_key] = {
                        "revision": snapshot["revision"], "findings": findings,
                        "sources": result.get("sources", []), "notices": result.get("notices", []),
                    }
                    st.rerun()
                except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                    st.error(str(exc))
            if review_state:
                for notice in review_state.get("notices", []):
                    st.caption(notice)
                findings = review_state.get("findings", [])
                if not findings:
                    st.success("현재 초안에서 우선 표시할 핵심 위험을 발견하지 못했습니다. 법률 검토가 불필요하다는 뜻은 아닙니다.")
                for index, finding in enumerate(findings, 1):
                    severity = {"high": "높음", "medium": "보통", "low": "낮음"}.get(finding["severity"], "검토")
                    st.markdown(f"**{index}. [{severity}] {finding['title']}**")
                    st.write(f"이유: {finding['reason']}")
                    st.write(f"수정 제안: {finding['suggestion']}")
                    sentence_id = finding["sentence_id"]
                    sentence_text = next((s.get("text", "") for clause in snapshot["clauses"]
                                          for s in clause.get("sentences", [])
                                          if s.get("id") == sentence_id), "")
                    with st.expander("검토 대상 조항 및 근거", expanded=False):
                        st.caption(f"문장 ID: {sentence_id}")
                        st.write(sentence_text)
                        for source_id in finding.get("source_ids", []):
                            source = next((x for x in review_state.get("sources", [])
                                           if x.get("id") == source_id), None)
                            if source:
                                st.caption(f"참고: {source.get('title', '')} · {source.get('locator', '')}")
                    if st.button("이 조항을 선택하여 수정 메모 작성", key=f"rag_select_{active_id}_{snapshot['revision']}_{index}"):
                        st.session_state[f"contract_selected_sentence_{active_id}"] = sentence_id
                        st.info("선택했습니다. 위의 계약서 조항에서 수정 메모를 입력하세요. AI가 자동으로 계약서를 변경하지는 않습니다.")
                    st.divider()
'''
result = src.replace(anchor, anchor + panel, 1)
try:
    ast.parse(result, filename=str(UI))
    review_code = (Path(__file__).resolve().parent / 'contract_review.py').read_text(encoding='utf-8')
    ast.parse(review_code, filename='review.py')
except (SyntaxError, OSError) as exc:
    sys.exit(f'ERROR: Validation failed, no files changed: {exc}')
REVIEW.write_text(review_code, encoding='utf-8')
try:
    UI.write_text(result, encoding='utf-8')
except Exception:
    REVIEW.unlink(missing_ok=True)
    raise
print('Updated only Quotation_KEKOREA/contracts/ui.py')
print('Added only Quotation_KEKOREA/contracts/review.py')
print('RAG review is opt-in, displays up to 5 risks and never automatically edits the contract.')
