"""Apply source-of-truth refresh handling to the completed two-stage export patch."""
from pathlib import Path
import ast

root=Path.cwd()
path=root/'Quotation_KEKOREA/contracts/ui.py'
s=path.read_text(encoding='utf-8')

def once(old,new,caption):
    global s
    if old not in s:
        raise RuntimeError(f'Missing {caption}: unexpected ui.py version. Nothing saved by this step.')
    if s.count(old)!=1:
        raise RuntimeError(f'{caption}: expected one anchor, found {s.count(old)}')
    s=s.replace(old,new,1)

once('from Quotation_KEKOREA.contracts.clause_terms import clause_evidence, merge_clause_candidates',
     'from Quotation_KEKOREA.contracts.clause_terms import clause_evidence, merge_clause_candidates\n'
     'from Quotation_KEKOREA.contracts.latest_instruction import (\n'
     '    candidate_from_latest, instruction_hash, is_explicit_change, latest_unapplied_request,\n'
     ')', 'latest import')

once('''            with st.spinner("AI가 거래조건을 분석하고 있습니다..."):
                analysis = analyze_trade(prior_messages, snapshot, selected_context, env=env)''',
'''            # A direct amendment must not be reinterpreted from older contradictory chat.
            # The saved revision is authoritative until the proposed change is approved.
            is_amendment = bool(snapshot.get('clauses')) and is_explicit_change(prompt.strip())
            analysis_messages = ([{'role': 'user', 'content': prompt.strip(), 'amendment_only': True}]
                                 if is_amendment else prior_messages)
            with st.spinner("AI가 거래조건을 분석하고 있습니다..."):
                analysis = analyze_trade(analysis_messages, snapshot, selected_context, env=env)''',
'change-request analysis isolation')

once('''            updated = apply_analysis(snapshot, analysis)
            updated['library_sources'] = library_result['sources']''',
'''            updated = (candidate_from_latest(snapshot, analysis) if is_amendment
                       else apply_analysis(snapshot, analysis))
            updated['library_sources'] = library_result['sources']''',
'latest-only commercial merge')

once('''                    "base_revision": snapshot["revision"],
                }
                st.info("기존 초안은 유지했습니다. 분석 결과는 별도 후보로 저장되며, 아래에서 선택적으로 수정안 생성 후 적용하세요.")''',
'''                    "base_revision": snapshot["revision"],
                    "latest_text": prompt.strip() if is_amendment else None,
                    "chat_hash": instruction_hash(prompt.strip()) if is_amendment else None,
                }
                st.info("기존 초안은 유지했습니다. 분석 결과는 별도 후보로 저장되며, 아래에서 선택적으로 수정안 생성 후 적용하세요.")''',
'candidate origin')

once('''                    proposal = propose_term_revision(
                        snapshot, list(unique_changes.values()), env=env)
                    st.session_state["contract_pending_proposal"] = proposal''',
'''                    proposal = propose_term_revision(
                        snapshot, list(unique_changes.values()), env=env)
                    if pending.get('chat_hash'):
                        proposal['approved_chat_hash'] = pending['chat_hash']
                    st.session_state["contract_pending_proposal"] = proposal''',
'proposal commit-origin marker')

once('''            updated = apply_proposal(snapshot, proposal, selected_ids)
            if proposal.get("note_ids"):''',
'''            updated = apply_proposal(snapshot, proposal, selected_ids)
            # Only an explicitly approved revision supersedes historical chat.
            if (proposal.get('approved_chat_hash') and
                    set(selected_ids) == {change['id'] for change in proposal.get('changes', [])}):
                updated['last_approved_chat_hash'] = proposal['approved_chat_hash']
            if proposal.get("note_ids"):''',
'commit latest approval marker')

anchor='''    consent = st.checkbox("입력한 거래 내용과 선택한 참고 문구·승인된 샘플 메모를 설정된 OpenAI API로 전송하는 데 동의합니다.",
                          key=f"contract_ai_consent_{snapshot['contract_id']}")
    prompt = st.chat_input('''
replacement='''    consent = st.checkbox("입력한 거래 내용과 선택한 참고 문구·승인된 샘플 메모를 설정된 OpenAI API로 전송하는 데 동의합니다.",
                          key=f"contract_ai_consent_{snapshot['contract_id']}")
    if snapshot.get('clauses'):
        newest_request = latest_unapplied_request(messages, snapshot)
        if newest_request:
            with st.expander('최근 수정 명령과 저장된 계약 내용 대조', expanded=True):
                st.caption('채팅 명령은 저장되지만 계약 조항은 자동 변경되지 않습니다. 마지막으로 승인한 revision이 기준입니다.')
                st.write('최근 변경 지시: ' + newest_request)
                if st.button('최근 변경 지시를 현재 revision에 다시 적용할 후보로 분석',
                             disabled=not consent,
                             key=f"contract_recheck_latest_{snapshot['contract_id']}_{snapshot['revision']}"):
                    try:
                        with st.spinner('최근 변경 지시만 현재 저장된 계약과 대조하고 있습니다...'):
                            extracted = analyze_trade(
                                [{'role': 'user', 'content': newest_request, 'amendment_only': True}], snapshot, [], env=env)
                        if extracted['contract_type'] != snapshot['contract_type']:
                            raise ValueError('계약 유형이 일치하지 않아 원본을 변경하지 않았습니다.')
                        candidate = candidate_from_latest(snapshot, extracted)
                        edits = _changed_terms(snapshot, candidate)
                        if edits:
                            st.session_state[f"contract_pending_analysis_{snapshot['contract_id']}"] = {
                                'snapshot': candidate, 'changes': edits,
                                'base_revision': snapshot['revision'],
                                'latest_text': newest_request,
                                'chat_hash': instruction_hash(newest_request)}
                            st.rerun()
                        else:
                            st.info('이번 명령으로 변경할 조건값을 찾지 못했습니다. 저장된 BOX 3의 본문도 확인하세요.')
                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                        st.error(f'최근 변경 지시 분석 실패: {exc}')
    prompt = st.chat_input('''
once(anchor,replacement,'restore most recent user amendment')

# Make the difference between a chat request and a saved revision explicit.
once('''            st.write("선택한 분석 후보만 수정안으로 만들며, 기존 조건/본문은 사용자가 적용할 때까지 바뀌지 않습니다.")''',
'''            st.write("선택한 분석 후보만 수정안으로 만들며, 기존 조건/본문은 사용자가 적용할 때까지 바뀌지 않습니다.")
            if pending.get('latest_text'):
                st.caption('최신 수정 요청: '+str(pending['latest_text']))
                st.warning('중요: 아래 후보를 선택해 수정안을 만든 뒤 **비교·승인하여 새 revision으로 저장**해야 재접속 후에도 최종 계약에 반영됩니다.')''',
'persisted amendment guidance')

ast.parse(s,filename=str(path))
path.write_text(s,encoding='utf-8')

# Extraction contract: signal explicit amend-only calls to the existing AI service.
service_path = root/'Quotation_KEKOREA/contracts/service.py'
service = service_path.read_text(encoding='utf-8')
mode_anchor = '        "messages": messages,\n        "current_snapshot": current_snapshot,'
if service.count(mode_anchor)!=1:
    raise RuntimeError('Missing service data contract; no service.py change applied.')
service=service.replace(mode_anchor,
    '        "messages": messages,\n        "amendment_only": any(m.get("amendment_only") is True for m in messages),\n        "current_snapshot": current_snapshot,',1)
prompt_anchor='        "Do not invent parties, legal facts, amounts, dates, governing law, dispute forum, terms, currencies, or triggers. "'
if service.count(prompt_anchor)!=1:
    raise RuntimeError('Missing service instruction contract; no service.py change applied.')
service=service.replace(prompt_anchor,prompt_anchor+'\n' +
    '        "If user_data.amendment_only is true, extract ONLY the terms expressly changed by the newest user message. "\n' +
    '        "The saved snapshot is context, not evidence that an old superseded term is still requested. "\n' +
    '        "A new explicit location, unit price or schedule is the candidate for that field, but MUST remain suggested until user approval. "\n' +
    '        "Never re-add previous values or unrelated fields as proposed changes in amendment-only mode. "\n' +
    '        "In ordinary conversation history, newer explicit corrections supersede earlier contradictory inputs for the SAME commercial field. "',1)
ast.parse(service,filename=str(service_path))
service_path.write_text(service,encoding='utf-8')
