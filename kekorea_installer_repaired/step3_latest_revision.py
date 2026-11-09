"""Idempotent, variant-tolerant latest-instruction integration.

Operates in a staged workspace made by apply_all.py, never directly on live user files.
Only touches the named contract chat/proposal functions. Refuses ambiguous code.
"""
from pathlib import Path
import ast
import re

root = Path.cwd()
path = root / 'Quotation_KEKOREA/contracts/ui.py'
s = path.read_text(encoding='utf-8')


def update_function(name, transform):
    global s
    tree = ast.parse(s)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1:
        raise RuntimeError(f'Function {name} missing or duplicated; staged changes discarded.')
    node = nodes[0]
    ls = s.splitlines(keepends=True)
    before = ''.join(ls[node.lineno - 1:node.end_lineno])
    after = transform(before)
    ast.parse(after)
    ls[node.lineno - 1:node.end_lineno] = [after]
    s = ''.join(ls)


def unique_replace(source, pattern, replacement, label, flags=0):
    matches = list(re.finditer(pattern, source, flags))
    if len(matches) != 1:
        raise RuntimeError(f'Cannot locate one {label} (found {len(matches)}). No user files changed.')
    return source[:matches[0].start()] + replacement + source[matches[0].end():]


if 'from Quotation_KEKOREA.contracts.latest_instruction import (' not in s:
    anchor = 'from Quotation_KEKOREA.contracts.clause_terms import clause_evidence, merge_clause_candidates'
    s = unique_replace(s, re.escape(anchor), anchor + '\n' +
        'from Quotation_KEKOREA.contracts.latest_instruction import (\n'
        '    candidate_from_latest, instruction_hash, is_explicit_change, latest_unapplied_request,\n'
        ')', 'latest-instruction import')


def chat_transform(body):
    # Select the actual assignment to `analysis` using Python syntax, not an
    # exact textual spelling of the old call. This handles multi-line calls,
    # renamed history variables, and projects partially patched before today.
    def _call_sites(text):
        parsed = ast.parse(text)
        sites = []
        for node in ast.walk(parsed):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'analysis'
                            for t in node.targets)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == 'analyze_trade'):
                sites.append(node)
        return parsed, sites

    parsed, sites = _call_sites(body)
    if len(sites) != 1 or not sites[0].value.args:
        # Never overwrite unknown code, and provide enough information to
        # identify the real variant instead of generating more guessed patches.
        call_lines = [(i, line.strip()) for i, line in enumerate(body.splitlines(), 1)
                      if 'analyze_trade(' in line]
        raise RuntimeError('Cannot identify unique analysis assignment in _contract_chat '
                           f'(found {len(sites)}). Candidate call lines: {call_lines[:8]}')
    statement = sites[0]
    first_arg = statement.value.args[0]
    original_argument = ast.unparse(first_arg)
    if original_argument == 'analysis_messages' and 'prior_messages' in body:
        # A previous attempt already rewrote the call but omitted its setup.
        original_argument = 'prior_messages'

    def _edit_span(text, node, replacement):
        lines = text.splitlines(keepends=True)
        start = sum(len(line) for line in lines[:node.lineno-1]) + node.col_offset
        end = sum(len(line) for line in lines[:node.end_lineno-1]) + node.end_col_offset
        return text[:start] + replacement + text[end:]

    if 'is_amendment = ' not in body:
        body = _edit_span(body, first_arg, 'analysis_messages')
        parsed, sites = _call_sites(body)
        statement = sites[0]
        spinner_nodes = [node for node in ast.walk(parsed)
                         if isinstance(node, (ast.With, ast.AsyncWith))
                         and node.lineno <= statement.lineno <= node.end_lineno
                         and any(isinstance(item.context_expr, ast.Call)
                                 and isinstance(item.context_expr.func, ast.Attribute)
                                 and item.context_expr.func.attr == 'spinner'
                                 for item in node.items)]
        anchor = max(spinner_nodes, key=lambda node: node.lineno) if spinner_nodes else statement
        lines = body.splitlines(keepends=True)
        indent = re.match(r'[ \t]*', lines[anchor.lineno - 1]).group(0)
        if original_argument == 'analysis_messages':
            raise RuntimeError('The AI history call uses analysis_messages but no prior_messages '
                               'fallback is present; please inspect this partial installation.')
        injected = (indent + '# Latest explicit amendment is reviewed separately from old chat history.\n'
                    + indent + "is_amendment = bool(snapshot.get('clauses')) and is_explicit_change(prompt.strip())\n"
                    + indent + "analysis_messages = ([{'role': 'user', 'content': prompt.strip(), 'amendment_only': True}]\n"
                    + indent + '                     if is_amendment else ' + original_argument + ')\n')
        lines.insert(anchor.lineno - 1, injected)
        body = ''.join(lines)
    else:
        # An existing amendment implementation must actually prepare the
        # isolated messages. Do not introduce a reference to an undefined name.
        if 'analysis_messages' not in body:
            raise RuntimeError('Existing amendment flag lacks analysis_messages; manual review required.')
        if ast.unparse(first_arg) != 'analysis_messages':
            body = _edit_span(body, first_arg, 'analysis_messages')
    ast.parse(body)

    if 'candidate_from_latest(snapshot, analysis)' not in body:
        pattern = r'updated\s*=\s*apply_analysis\(\s*snapshot\s*,\s*analysis\s*\)'
        body = unique_replace(body, pattern,
            'updated = (candidate_from_latest(snapshot, analysis) if is_amendment\n'
            '                       else apply_analysis(snapshot, analysis))', 'candidate merge')

    if '"chat_hash": instruction_hash(prompt.strip())' not in body and "'chat_hash': instruction_hash(prompt.strip())" not in body:
        pattern = r"(?m)^(?P<indent>[ \t]*)[\"']base_revision[\"']\s*:\s*snapshot\[[\"']revision[\"']\]\s*,\s*$"
        matches = list(re.finditer(pattern, body))
        candidate = [m for m in matches if 'contract_pending_analysis_' in body[max(0, m.start()-260):m.start()]]
        if len(candidate) != 1:
            raise RuntimeError('Cannot locate one pending-analysis candidate block.')
        m = candidate[0]
        indent = m.group('indent')
        addition = (indent + '"latest_text": prompt.strip() if is_amendment else None,\n'
                    + indent + '"chat_hash": instruction_hash(prompt.strip()) if is_amendment else None,\n')
        line_end = body.find('\n', m.end())
        if line_end < 0:
            raise RuntimeError('Unterminated pending-analysis revision line.')
        body = body[:line_end+1] + addition + body[line_end+1:]

    if "pending.get('chat_hash')" not in body:
        pattern = (r'(?m)^(?P<indent>[ \t]*)st\.session_state\[["\']contract_pending_proposal["\']\]\s*=\s*proposal')
        matches=list(re.finditer(pattern,body))
        # Only the proposal in the candidate reconciliation branch, not elsewhere.
        candidate = [m for m in matches if 'proposal = propose_term_revision' in body[max(0,m.start()-350):m.start()]]
        if len(candidate)!=1:
            raise RuntimeError('Cannot uniquely locate candidate reconciliation proposal.')
        m=candidate[0]; indent=m.group('indent')
        addition=(indent + "if pending.get('chat_hash'):\n" + indent + "    proposal['approved_chat_hash'] = pending['chat_hash']\n")
        body=body[:m.start()] + addition + body[m.start():]

    if 'latest_unapplied_request(messages, snapshot)' not in body:
        prompt_matches = list(re.finditer(r'(?m)^[ \t]*prompt\s*=\s*st\.chat_input\(',body))
        if len(prompt_matches)!=1:
            raise RuntimeError('Cannot locate a unique chat input.')
        m=prompt_matches[0]; indent=re.match(r'[ \t]*',body[m.start():]).group(0)
        block=(indent + "if snapshot.get('clauses'):\n"
               + indent + '    newest_request = latest_unapplied_request(messages, snapshot)\n'
               + indent + '    if newest_request:\n'
               + indent + "        with st.expander('최근 수정 명령과 저장된 계약 내용 대조', expanded=True):\n"
               + indent + "            st.caption('마지막 승인 revision이 기준입니다. 대화 요청은 자동 반영되지 않습니다.')\n"
               + indent + "            st.write('최근 변경 지시: ' + newest_request)\n"
               + indent + "            if st.button('최근 변경 지시를 현재 revision에 다시 적용할 후보로 분석',\n"
               + indent + '                         disabled=not consent,\n'
               + indent + '                         key=f"contract_recheck_latest_{snapshot[\'contract_id\']}_{snapshot[\'revision\']}"):\n'
               + indent + '                try:\n'
               + indent + "                    with st.spinner('최근 변경 지시를 비교합니다...'):\n"
               + indent + "                        extracted = analyze_trade([{'role': 'user', 'content': newest_request, 'amendment_only': True}], snapshot, [], env=env)\n"
               + indent + "                    if extracted['contract_type'] != snapshot['contract_type']:\n"
               + indent + "                        raise ValueError('계약 유형이 일치하지 않습니다.')\n"
               + indent + '                    candidate = candidate_from_latest(snapshot, extracted)\n'
               + indent + '                    edits = _changed_terms(snapshot, candidate)\n'
               + indent + '                    if edits:\n'
               + indent + '                        st.session_state[f"contract_pending_analysis_{snapshot[\'contract_id\']}"] = {\n'
               + indent + "                            'snapshot': candidate, 'changes': edits,\n"
               + indent + "                            'base_revision': snapshot['revision'],\n"
               + indent + "                            'latest_text': newest_request,\n"
               + indent + "                            'chat_hash': instruction_hash(newest_request)}\n"
               + indent + '                        st.rerun()\n'
               + indent + '                    else:\n'
               + indent + "                        st.info('변경할 조건값을 찾지 못했습니다. BOX 3 조항도 확인하세요.')\n"
               + indent + '                except (ValueError, RuntimeError, ContractRepositoryError) as exc:\n'
               + indent + "                    st.error(f'최근 변경 지시 분석 실패: {exc}')\n")
        body=body[:m.start()] + block + body[m.start():]

    if "if pending.get('latest_text')" not in body:
        matches=list(re.finditer(r'(?m)^(?P<indent>[ \t]*)st\.write\(["\']선택한 분석 후보만 수정안으로 만들며, 기존 조건/본문은 사용자가 적용할 때까지 바뀌지 않습니다\.["\']\)',body))
        if len(matches)!=1:
            raise RuntimeError('Cannot locate the candidate-approval notice.')
        m=matches[0]; indent=m.group('indent')
        extra=("\n"+indent+"if pending.get('latest_text'):\n"+indent+"    st.caption('최신 수정 요청: ' + str(pending['latest_text']))\n"+indent+"    st.warning('선택한 변경을 비교·승인하여 새 revision으로 저장해야 재접속 후 반영됩니다.')")
        body=body[:m.end()] + extra + body[m.end():]
    return body


def proposal_transform(body):
    if "proposal.get('approved_chat_hash')" not in body:
        pattern=r'(?m)^(?P<indent>[ \t]*)updated\s*=\s*apply_proposal\(snapshot\s*,\s*proposal\s*,\s*selected_ids\)'
        m=re.search(pattern,body)
        if not m:
            raise RuntimeError('Cannot locate approved revision application.')
        indent=m.group('indent')
        extra=("\n"+indent+"if (proposal.get('approved_chat_hash') and\n"
               +indent+"        set(selected_ids) == {change['id'] for change in proposal.get('changes', [])}):\n"
               +indent+"    updated['last_approved_chat_hash'] = proposal['approved_chat_hash']")
        body=body[:m.end()] + extra + body[m.end():]
    return body


# Work on the chat function first; AST verifies the result before continuing.
update_function('_contract_chat', chat_transform)
update_function('_proposal_panel', proposal_transform)
ast.parse(s,filename=str(path))

service_path = root / 'Quotation_KEKOREA/contracts/service.py'
service = service_path.read_text(encoding='utf-8')
if '"amendment_only": any(m.get("amendment_only") is True for m in messages)' not in service:
    anchor='        "messages": messages,\n        "current_snapshot": current_snapshot,'
    if service.count(anchor)!=1:
        raise RuntimeError('Service analysis contract does not match expected version.')
    service=service.replace(anchor,
       '        "messages": messages,\n'
       '        "amendment_only": any(m.get("amendment_only") is True for m in messages),\n'
       '        "current_snapshot": current_snapshot,',1)
if 'If user_data.amendment_only is true' not in service:
    prompt_anchor='        "Do not invent parties, legal facts, amounts, dates, governing law, dispute forum, terms, currencies, or triggers. "'
    if service.count(prompt_anchor)!=1:
        raise RuntimeError('Service AI instructions do not match expected version.')
    service=service.replace(prompt_anchor,prompt_anchor+'\n' +
        '        "If user_data.amendment_only is true, extract ONLY the terms expressly changed by the newest user message. "\n'
        '        "The saved snapshot is context, not evidence that an old superseded term is still requested. "\n'
        '        "A new explicit location, unit price or schedule is the candidate for that field, but MUST remain suggested until user approval. "\n'
        '        "Never re-add previous values or unrelated fields as proposed changes in amendment-only mode. "\n'
        '        "In ordinary conversation history, newer explicit corrections supersede earlier contradictory inputs for the SAME commercial field. "',1)
ast.parse(service,filename=str(service_path))
path.write_text(s,encoding='utf-8')
service_path.write_text(service,encoding='utf-8')
print('Latest-instruction linking patched in staged project.')
