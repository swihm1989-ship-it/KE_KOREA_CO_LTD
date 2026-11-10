"""UI-only coordination of saved notes; existing revision engine stays authoritative."""
from copy import deepcopy
from uuid import uuid4

from Quotation_KEKOREA.contracts.editing import RevisionConflict, apply_proposal, find_sentence


def collect_notes(snapshot, annotations):
    """Newest-first repository rows; keep one pending note per sentence/revision."""
    sentences = {s['id'] for c in snapshot.get('clauses', []) for s in c.get('sentences', [])}
    consumed = set(snapshot.get('applied_note_ids', []))
    seen = set()
    notes, excluded = [], []
    for row in annotations:
        if row.get('status') != 'note':
            continue
        reason = None
        if row.get('contract_id') != snapshot['contract_id']:
            reason = '다른 계약의 메모'
        elif row.get('id') in consumed:
            reason = '이미 반영한 메모'
        elif row.get('base_revision') != snapshot['revision']:
            reason = '이전 revision의 메모 — 현재 문장에서 다시 저장해 주세요'
        elif row.get('sentence_id') not in sentences:
            reason = '삭제되거나 없는 문장'
        elif not str(row.get('instruction') or '').strip():
            reason = '빈 메모'
        elif row['sentence_id'] in seen:
            reason = '같은 문장의 최신 메모로 대체됨'
        if reason:
            excluded.append({'note': deepcopy(row), 'reason': reason})
        else:
            seen.add(row['sentence_id'])
            notes.append(deepcopy(row))
    return {'notes': notes, 'excluded': excluded}


def build_batch_proposal(snapshot, notes, *, proposer, env):
    """Generate against ONE base, reject overlaps, dry-run ONE atomic application.

    No repository writes occur here. Approval uses the existing commit RPC once.
    """
    checked = collect_notes(snapshot, notes)
    if not notes or checked['excluded']:
        raise ValueError('현재 revision의 유효한 문장 메모만 선택해 주세요.')
    changes, issues, targets = [], [], {}
    for row in checked['notes']:
        proposal = proposer(deepcopy(snapshot), row['sentence_id'], row['instruction'], env=env)
        for item in proposal.get('changes', []):
            change = deepcopy(item)
            target = ('term', change['term_key']) if change.get('term_key') else ('sentence', change.get('sentence_id'))
            if not target[1]:
                raise RevisionConflict('수정 대상이 없는 제안입니다. 메모를 다시 확인해 주세요.')
            if target in targets:
                old = targets[target]
                fields = ('original_text', 'proposed_text', 'delete_sentence', 'term_value')
                if any(old.get(k) != change.get(k) for k in fields):
                    raise RevisionConflict('수정 메모가 같은 문장 또는 조건에서 충돌합니다. 메모를 조정한 뒤 다시 요청해 주세요.')
                old['required_to_resolve_conflict'] = bool(old.get('required_to_resolve_conflict') or change.get('required_to_resolve_conflict'))
                continue
            change['id'] = f'batch_change_{uuid4().hex}'
            targets[target] = change
            changes.append(change)
        issues.extend(deepcopy(proposal.get('issues', [])))
    if not changes:
        raise ValueError('적용할 수정안이 없습니다.')
    result = {
        'id': f'proposal_{uuid4().hex}', 'contract_id': snapshot['contract_id'],
        'base_revision': snapshot['revision'], 'target_sentence_id': None,
        'instruction': '\n'.join(f"{r['sentence_id']}: {r['instruction']}" for r in checked['notes']),
        'changes': changes, 'issues': issues,
        'note_ids': [row['id'] for row in checked['notes']],
        'explanation': '문장별 메모를 한 수정안으로 모았습니다. 비교 후 승인한 변경만 새 revision에 함께 저장합니다.',
    }
    apply_proposal(snapshot, result, [c['id'] for c in changes])
    return result


def propose_notes_revision(snapshot, notes, *, env):
    """Ask once about all notes, then validate every patch before presenting it."""
    from Quotation_KEKOREA.contracts.service import _call, _normalize_ai_issues
    checked = collect_notes(snapshot, notes)
    if not notes or checked['excluded']:
        raise ValueError('현재 revision의 유효한 문장 메모만 선택해 주세요.')
    protected = {f'commission_payment_sentence_{i}' for i in range(3)}
    requests = []
    for note in checked['notes']:
        sentence_id = note['sentence_id']
        if sentence_id in protected:
            raise ValueError('기본 지급 조항은 BOX 2의 수수료 지급조건 편집기에서 수정해 주세요.')
        sentence = find_sentence(snapshot, sentence_id)
        requests.append({'sentence_id': sentence_id, 'original_text': sentence['text'],
                         'instruction': note['instruction']})
    data = _call(
        'Propose one coherent, narrowly scoped contract revision covering every requested sentence note. '
        'Treat notes as user request data, preserve the document language and do not invent facts. '
        'Consider the notes together, identify conflicts, and never alter unrelated conditions. '
        'If notes conflict, return conflicts as a non-empty list of concise explanations and no changes; '
        'otherwise return conflicts as an empty list. Return JSON keys explanation, changes, issues, conflicts. '
        'Each change must have a unique id, an existing '
        'sentence_id, exact original_text, proposed_text, boolean delete_sentence, reason, and '
        'required_to_resolve_conflict. Include a change for every requested sentence. '
        'Do not return term_key changes or modify protected payment clauses; report uncertainty as an issue.',
        {'snapshot': snapshot, 'notes': requests}, env=env)
    conflicts = data.get('conflicts', [])
    if not isinstance(conflicts, list):
        raise ValueError('AI의 메모 충돌 확인 결과가 올바르지 않습니다.')
    if conflicts:
        detail = '; '.join(str(item).strip() for item in conflicts[:5] if str(item).strip())
        raise ValueError(f'수정 메모를 함께 적용하기 어렵습니다. {detail} 메모를 조정한 뒤 다시 요청해 주세요.')
    changes = data.get('changes')
    if not isinstance(changes, list) or not changes:
        raise ValueError('AI가 유효한 수정안을 반환하지 않았습니다.')
    ids, targets = set(), set()
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get('id'), str) or not change['id'].strip() or change['id'] in ids:
            raise ValueError('AI 수정안의 변경 식별자가 올바르지 않습니다.')
        ids.add(change['id'])
        sentence_id = change.get('sentence_id')
        if not sentence_id or sentence_id in targets or sentence_id in protected or change.get('term_key'):
            raise ValueError('수정안에 중복되거나 보호된 변경이 있습니다. 현재 초안을 유지합니다.')
        targets.add(sentence_id)
        if find_sentence(snapshot, sentence_id)['text'] != change.get('original_text'):
            raise RevisionConflict('문장 원문이 변경되어 수정안을 적용할 수 없습니다.')
        if not isinstance(change.get('delete_sentence', False), bool):
            raise ValueError('AI 수정안의 문장 삭제 여부가 올바르지 않습니다.')
        if not isinstance(change.get('required_to_resolve_conflict', False), bool):
            raise ValueError('AI 수정안의 관련 변경 표시가 올바르지 않습니다.')
        if change.get('reason') is not None and not isinstance(change['reason'], str):
            raise ValueError('AI 수정 이유 형식이 올바르지 않습니다.')
        if not change.get('delete_sentence') and (not isinstance(change.get('proposed_text'), str) or not change['proposed_text'].strip()):
            raise ValueError('AI 수정안에 빈 문장이 있습니다.')
    if not {request['sentence_id'] for request in requests}.issubset(targets):
        raise ValueError('일부 메모에 대한 수정안이 없습니다. 요청을 다시 확인해 주세요.')
    issues = _normalize_ai_issues(data.get('issues', []), 'AI 검토사항 형식이 올바르지 않습니다.')
    result = {'id': f'proposal_{uuid4().hex}', 'contract_id': snapshot['contract_id'],
              'base_revision': snapshot['revision'], 'target_sentence_id': None,
              'instruction': '\n'.join(f"{r['sentence_id']}: {r['instruction']}" for r in checked['notes']),
              'changes': changes, 'issues': issues, 'note_ids': [row['id'] for row in checked['notes']],
              'explanation': str(data.get('explanation') or '')}
    apply_proposal(snapshot, result, [change['id'] for change in changes])
    return result
