#!/bin/sh
set -eu
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/Quotation_KEKOREA/contracts" "$WORK/Quotation_KEKOREA/tests" "$WORK/Quotation_KEKOREA/Team" "$WORK/Quotation_KEKOREA/Presentation"
for f in README.md Quotation_KEKOREA/README.md Quotation_KEKOREA/README_CONTRACTS.md Quotation_KEKOREA/Team/README.md Quotation_KEKOREA/Presentation/README.md; do echo 'original README' > "$WORK/$f"; done
printf 'streamlit>=1.40,<2\n' > "$WORK/Quotation_KEKOREA/requirements.txt"
cat > "$WORK/Quotation_KEKOREA/app.py" <<'PY'
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='test')
with st.sidebar:
    logo = ROOT / "assets" / "company_logo.png"
    st.caption('test')
PY
cat > "$WORK/Quotation_KEKOREA/contracts/service.py" <<'PY'
def _normalize_ai_issues(issues, error_message):
    if not isinstance(issues, list):
        raise ValueError(error_message)
    normalized = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("Contract AI returned an invalid review issue.")
        candidate = dict(issue)
        message = candidate.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Contract AI returned a review issue without a message.")
        normalized.append(candidate)
    return normalized
PY
cat > "$WORK/Quotation_KEKOREA/contracts/workspace.py" <<'PY'
def propose_notes_revision(snapshot, notes, *, env):
    data = _call(
        'Do not return term_key changes or modify protected payment clauses; report uncertainty as an issue.',
        {'snapshot':snapshot}, env=env)
    return data
PY
cat > "$WORK/Quotation_KEKOREA/contracts/ui.py" <<'PY'
import streamlit as st

def _proposal_panel(repo, snapshot, proposal, state_key):
    selected_ids=[]
    for change in proposal['changes']:
        selected_ids.append(change['id'])
    batch_reviewed = True
    if batch_reviewed:
        try:
            saved = snapshot
            st.session_state[state_key] = saved
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _batch_request_panel(repo, snapshot, state_key, env, pending, buffers):
    if True:
        try:
            proposal=None
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))


def _review_panel(repo, snapshot, state_key, issues):
    return


def _export_panel(repo, snapshot, env):
    if True:
        password = st.text_input('FINAL 회사 직인 사용 암호', type='password',
                                 key=f"contract_final_seal_access_{snapshot['contract_id']}_{snapshot['revision']}")
        configured = str(env.get('CONTRACT_FINAL_SEAL_PASSWORD') or '')
        authorized = bool(configured) and hmac.compare_digest(str(password), configured)
        if not configured:
            st.caption('관리자: 비공개 Streamlit Secrets에 CONTRACT_FINAL_SEAL_PASSWORD를 설정하세요.')
        disabled = not authorized


def render_contract_page(page, env):
    if True:
        if True:
            _export_panel(repo, snapshot, env)

    with st.expander("저장·복사·언어 버전 관리", expanded=False):
        pass
PY
(cd "$WORK" && python /mnt/data/kekorea_auth_integrated/apply_all.py)
(cd "$WORK" && python /mnt/data/kekorea_auth_integrated/apply_all.py)
