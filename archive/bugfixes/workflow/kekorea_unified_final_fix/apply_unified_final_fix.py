"""Strict, reversible UI patch from current GitHub main contract code.
Run from KE_KOREA_CO_LTD root. Never touches trade app or business rules.
"""
from pathlib import Path
from datetime import datetime
import shutil
import sys

ROOT = Path.cwd()
PACKAGE = Path(__file__).resolve().parent
UI = ROOT / 'Quotation_KEKOREA/contracts/ui.py'
RISK = ROOT / 'Quotation_KEKOREA/contracts/risk_review_ui.py'
DEST = ROOT / 'Quotation_KEKOREA/contracts/final_merge.py'
TEST = ROOT / 'Quotation_KEKOREA/tests/test_contract_unified_final.py'
READMES = [ROOT / 'README.md', ROOT / 'Quotation_KEKOREA/README.md',
           ROOT / 'Quotation_KEKOREA/README_CONTRACTS.md',
           ROOT / 'Quotation_KEKOREA/Team/README.md',
           ROOT / 'Quotation_KEKOREA/Presentation/README.md']
MARK = '2026-11-09 통합 최종 수정 요청 UI'


def once(src, old, new, name):
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f'{name}: expected exactly one anchor, found {count}. No files changed.')
    return src.replace(old, new, 1)


def build():
    if not UI.is_file() or not RISK.is_file() or not all(p.is_file() for p in READMES):
        raise RuntimeError('Repository root or README structure does not match. No files changed.')
    if DEST.exists() or TEST.exists() or MARK in UI.read_text(encoding='utf-8'):
        raise RuntimeError('Patch appears already applied. No files changed.')
    ui = UI.read_text(encoding='utf-8')
    risk = RISK.read_text(encoding='utf-8')
    ui = once(ui,
        'from Quotation_KEKOREA.contracts.workspace import collect_notes, propose_notes_revision',
        'from Quotation_KEKOREA.contracts.workspace import collect_notes, propose_notes_revision\n'
        'from Quotation_KEKOREA.contracts.final_merge import merge_revision_requests', 'import')
    ui = once(ui,
        '    _batch_request_panel(repo, snapshot, state_key, env, pending, buffers)\n',
        '    # ' + MARK + ': the final action is placed after AI risk review.\n'
        '    return pending, buffers\n', 'inline note panel')
    ui = once(ui,
        "    st.caption(\"버튼을 누르면 메모를 저장하고 AI에 한 번에 전달합니다. 본문은 수정안 비교·승인 후에 변경됩니다.\")\n"
        "    consent = st.session_state.get(f\"contract_ai_consent_{snapshot['contract_id']}\", False)\n"
        "    existing_proposal = st.session_state.get('contract_pending_proposal') or {}\n"
        "    other_proposal = (existing_proposal.get('contract_id') == snapshot['contract_id']\n"
        "                      and not existing_proposal.get('note_ids'))\n",
        "    preview_state = st.session_state.get(f\"contract_risk_preview_{snapshot['contract_id']}\") or {}\n"
        "    risk_previews = (preview_state.get('sentences', {})\n"
        "                     if preview_state.get('revision') == snapshot['revision'] else {})\n"
        "    risk_previews = {sid: str(value).strip() for sid, value in risk_previews.items()\n"
        "                     if str(value or '').strip()}\n"
        "    st.caption(f'현재 revision의 문장 메모 {len(notes)}건 + 위험 검토 선택안 {len(risk_previews)}건을 함께 검토합니다.')\n"
        "    st.caption('최종 수정 요청은 AI 수정안을 준비하는 단계입니다. 본문은 비교·승인 후 새 revision으로 저장됩니다.')\n"
        "    consent = st.session_state.get(f\"contract_ai_consent_{snapshot['contract_id']}\", False)\n"
        "    existing_proposal = st.session_state.get('contract_pending_proposal') or {}\n"
        "    other_proposal = existing_proposal.get('contract_id') == snapshot['contract_id']\n",
        'combined status')
    ui = once(ui,
        "    if not notes:\n"
        "        st.info('현재 revision에 적용할 수정 메모가 없습니다. 문장 옆에 새 메모를 작성하거나, '\n"
        "                '위의 이전 메모를 펼쳐 현재 revision으로 다시 가져오세요.')\n"
        "    if notes and not consent:\n"
        "        st.caption('BOX 1의 AI 전송 동의를 선택해야 수정 요청을 보낼 수 있습니다.')\n"
        "    if notes and other_proposal:\n"
        "        st.caption('먼저 아래 조건 수정안을 적용하거나 취소해 주세요. 작성한 문장 메모는 유지됩니다.')\n"
        "    if st.button('최종 수정 요청', type='primary', disabled=not notes or not consent or other_proposal,\n",
        "    if not notes and not risk_previews:\n"
        "        st.info('현재 revision에 수정할 내용이 없습니다. 문장 옆 메모 또는 위의 AI 위험 검토에서 추천안을 적용하세요.')\n"
        "    if notes and not consent:\n"
        "        st.caption('문장 메모의 AI 통합 수정에는 BOX 1의 AI 전송 동의가 필요합니다.')\n"
        "    if other_proposal:\n"
        "        st.caption('이미 생성한 수정안이 있습니다. 아래에서 비교·승인하거나 취소한 다음 요청하세요.')\n"
        "    overlap = set(n['sentence_id'] for n in notes) & set(risk_previews)\n"
        "    if overlap:\n"
        "        st.warning('같은 문장에 메모와 위험 검토 추천안이 함께 있습니다: '\n"
        "                   + ', '.join(sorted(overlap)) + '. 한쪽을 제거하거나 메모를 통합하세요.')\n"
        "    if st.button('최종 수정 요청', type='primary',\n"
        "                 disabled=(not (notes or risk_previews) or (notes and not consent) or other_proposal or bool(overlap)),\n",
        'button disabled state')
    ui = once(ui,
        "            with st.spinner('모든 메모를 함께 검토해 수정안을 작성하고 있습니다...'):\n"
        "                proposal = propose_notes_revision(snapshot, notes, env=env)\n",
        "            with st.spinner('문장 메모와 위험 검토 추천안을 하나의 수정안으로 통합하고 있습니다...'):\n"
        "                proposal = merge_revision_requests(\n"
        "                    snapshot, notes, risk_previews,\n"
        "                    propose_notes=propose_notes_revision, env=env)\n",
        'merge invocation')
    ui = once(ui,
        "        else:\n"
        "            _render_draft(repo, snapshot, state_key, env)\n"
        "        proposal = st.session_state.get('contract_pending_proposal')\n"
        "        if proposal and proposal.get('contract_id') == active_id:\n"
        "            _proposal_panel(repo, snapshot, proposal, state_key)\n"
        "        if snapshot.get('clauses'):\n"
        "            render_risk_review(repo, snapshot, state_key, env)\n",
        "        else:\n"
        "            pending, buffers = _render_draft(repo, snapshot, state_key, env)\n"
        "        if snapshot.get('clauses'):\n"
        "            render_risk_review(repo, snapshot, state_key, env)\n",
        'box 3 composition')
    ui = once(ui,
        "            _export_panel(repo, snapshot, env)\n",
        "            # Final action follows the risk panel and revision history.\n"
        "            _batch_request_panel(repo, snapshot, state_key, env, pending, buffers)\n"
        "            proposal = st.session_state.get('contract_pending_proposal')\n"
        "            if proposal and proposal.get('contract_id') == active_id:\n"
        "                _proposal_panel(repo, snapshot, proposal, state_key)\n"
        "            _export_panel(repo, snapshot, env)\n",
        'move final panel to bottom')
    risk = once(risk,
        "            if st.button('선택한 수정안 비교·승인', key=f'risk_review_changes_{contract_id}_{revision}'):\n"
        "                try:\n"
        "                    proposal = preview_proposal(snapshot, previews)\n"
        "                    st.session_state['contract_pending_proposal'] = proposal\n"
        "                    st.session_state['contract_pending_proposal_key'] = state_key\n"
        "                    st.rerun()\n"
        "                except (ValueError, RuntimeError, ContractRepositoryError) as exc:\n"
        "                    st.error(str(exc))\n",
        "            st.caption('선택한 위험 수정안은 아래 최종 수정 요청 버튼에서 문장 메모와 함께 비교·승인합니다.')\n",
        'remove separate risk-approval button')
    return ui, risk


def main():
    try:
        ui, risk = build()
        # Validate all replacements BEFORE creating any backups or modifying files.
        import ast
        ast.parse(ui); ast.parse(risk)
        ast.parse((PACKAGE/'contract_final_merge.py').read_text(encoding='utf-8'))
        ast.parse((PACKAGE/'test_contract_unified_final.py').read_text(encoding='utf-8'))
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = PACKAGE / ('backup_' + stamp)
        backup_dir.mkdir(parents=True)
        for p in [UI, RISK] + READMES:
            dest = backup_dir / p.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        UI.write_text(ui, encoding='utf-8')
        RISK.write_text(risk, encoding='utf-8')
        shutil.copy2(PACKAGE/'contract_final_merge.py', DEST)
        shutil.copy2(PACKAGE/'test_contract_unified_final.py', TEST)
        text = ('\n\n### ' + MARK + '\n'
                '- BOX 3의 문장 메모, 이전·제외 메모, AI 핵심 위험 검토 이후 최종 수정 요청을 배치한다.\n'
                '- 최종 수정 요청은 현재 revision의 메모와 AI 위험 검토 추천안을 충돌 검사 후 하나의 수정안으로 모으며, 비교·승인 전에는 원본 계약서를 수정하지 않는다.\n'
                '- 같은 문장을 두 경로로 수정하면 조정을 요구하고, 빈 메모라도 위험 검토 선택안이 있으면 통합 요청할 수 있다.\n'
                '- 사용자 승인 뒤에만 새 revision을 저장한다. 기존 필수 검증·DRAFT/FINAL 출력과 ECLADO·PO/PI/CI/PL 기능은 변경하지 않는다.\n'
                '- 운영 Streamlit 배포는 별도 검증이 필요하다.\n')
        for p in READMES:
            with p.open('a', encoding='utf-8') as out:
                out.write(text)
        print('Applied unified final modification. Backups:', backup_dir)
        print('Modified:', UI.relative_to(ROOT), RISK.relative_to(ROOT))
        print('Added:', DEST.relative_to(ROOT), TEST.relative_to(ROOT))
        print('Updated 5 READMEs. Run focused tests and full suite before committing.')
    except (RuntimeError, OSError, SyntaxError) as exc:
        print('NO PATCH APPLIED:', exc, file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
