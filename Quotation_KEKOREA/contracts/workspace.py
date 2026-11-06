"""UI-only coordination of saved notes; existing revision engine stays authoritative."""
from copy import deepcopy
from uuid import uuid4

from Quotation_KEKOREA.contracts.editing import RevisionConflict, apply_proposal


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
