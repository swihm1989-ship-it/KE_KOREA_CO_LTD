"""Combine user sentence notes and selected risk-review preview in one revision proposal.

Pure coordination: no DB writes, no changes to payment policy, final checks, or export.
"""
from copy import deepcopy
from uuid import uuid4

from Quotation_KEKOREA.contracts.editing import RevisionConflict, apply_proposal
from Quotation_KEKOREA.contracts.risk_review_workspace import preview_proposal


def merge_revision_requests(snapshot, notes, risk_previews, *, propose_notes, env):
    """Build one atomic revision proposal; preserve explicit human approval.

    Sentence notes are AI-proposed together; chosen risk edits are user-supplied
    replacements. A sentence addressed by both paths is always a conflict,
    not a reason to silently prioritize one edit.
    """
    if not notes and not risk_previews:
        raise ValueError('수정 메모 또는 AI 핵심 위험 검토에서 적용한 추천 문장이 필요합니다.')
    noted_ids = [note['sentence_id'] for note in notes]
    if len(noted_ids) != len(set(noted_ids)):
        raise RevisionConflict('같은 문장에 수정 메모가 중복되어 있습니다. 하나로 정리해 주세요.')
    overlaps = sorted(set(noted_ids) & set(risk_previews))
    if overlaps:
        raise RevisionConflict('문장 메모와 위험 검토 수정안이 같은 문장을 변경합니다: '
                               + ', '.join(overlaps) + '. 한쪽 수정만 남기거나 메모를 통합해 주세요.')
    note_proposal = propose_notes(snapshot, notes, env=env) if notes else None
    risk_proposal = preview_proposal(snapshot, risk_previews) if risk_previews else None
    changes = []
    for proposal in (note_proposal, risk_proposal):
        if proposal:
            if proposal.get('contract_id') != snapshot['contract_id'] or proposal.get('base_revision') != snapshot['revision']:
                raise RevisionConflict('수정안이 현재 계약서 revision과 일치하지 않습니다.')
            changes.extend(deepcopy(proposal.get('changes') or []))
    targets = set()
    used_change_ids = set()
    for change in changes:
        target = ('term', change['term_key']) if change.get('term_key') else ('sentence', change.get('sentence_id'))
        if not target[1] or target in targets:
            raise RevisionConflict('여러 수정안이 같은 문장 또는 계약조건을 변경합니다. 충돌을 해결한 후 다시 요청하세요.')
        targets.add(target)
        if change.get('id') in used_change_ids:
            change['id'] = f'unified_change_{uuid4().hex}'
        used_change_ids.add(change['id'])
    merged = {
        'id': f'proposal_{uuid4().hex}',
        'contract_id': snapshot['contract_id'],
        'base_revision': snapshot['revision'],
        'target_sentence_id': None,
        'instruction': '문장별 메모 및 AI 핵심 위험 검토 추천안 통합 최종 수정',
        'changes': changes,
        'issues': deepcopy(note_proposal.get('issues', [])) if note_proposal else [],
        'note_ids': list(note_proposal.get('note_ids', [])) if note_proposal else [],
        'explanation': ('문장별 메모와 위험 검토에서 선택한 추천 문구를 하나의 수정안으로 통합했습니다. '
                        '변경 전후를 확인하고 승인해야 계약서 본문에 최종 저장됩니다.'),
    }
    # Dry-run the unchanged revision engine to catch stale originals and other conflicts.
    apply_proposal(snapshot, merged, [change['id'] for change in changes])
    return merged
