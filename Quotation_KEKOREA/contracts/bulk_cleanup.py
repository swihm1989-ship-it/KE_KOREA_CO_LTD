"""Optional, conservative AI clean-up of blanket pre-signature wrappers.

Never persists or applies suggestions. Existing revision proposal review and user
approval remain the only way to commit changes. Genuine missing commercial facts
remain in the document until the parties specify them.
"""
from copy import deepcopy
import re
import urllib.request
from uuid import uuid4

from Quotation_KEKOREA.contracts.editing import apply_proposal
from Quotation_KEKOREA.contracts.risk_review_workspace import PROTECTED_SENTENCES
from Quotation_KEKOREA.contracts.service import _call

SIGNATURE_WRAPPER = re.compile(
    r'\[\s*(?:서명\s*전\s*확인|TO\s*CONFIRM|TO\s*BE\s*CONFIRMED)'
    r'\s*[:：]\s*([^\]]+)\]', flags=re.I,
)
SIMPLE_PLACEHOLDER = re.compile(
    r'\[\s*(?:서명\s*전\s*확인|확인\s*필요|TBD|TO\s*CONFIRM)\s*\]', re.I
)
NUMBER = re.compile(r'(?<![\w])\d[\d,.]*(?:%|\s*(?:USD|KRW|PCS|MW|kg|일|개월|년))?', re.I)
BATCH_SIZE = 8


def candidate_sentences(snapshot):
    """Only target verbose sentence-wide wrappers, never other user clauses."""
    rows = []
    for clause in snapshot.get('clauses', []):
        for sentence in clause.get('sentences', []):
            text = str(sentence.get('text') or '')
            if sentence.get('id') in PROTECTED_SENTENCES:
                continue
            if SIGNATURE_WRAPPER.search(text):
                rows.append({'sentence_id': sentence['id'], 'text': text,
                             'clause_title': str(clause.get('title') or '')})
    return rows


def _eligible_change(original, proposed):
    """Fail closed: do not erase unresolved facts or alter explicit numbers."""
    if not isinstance(proposed, str) or not proposed.strip():
        return False
    before = original.strip()
    after = proposed.strip()
    if before == after or SIGNATURE_WRAPPER.search(after):
        return False
    # A genuine standalone placeholder cannot be silently erased.
    if len(SIMPLE_PLACEHOLDER.findall(before)) > len(SIMPLE_PLACEHOLDER.findall(after)):
        return False
    if sorted(NUMBER.findall(before)) != sorted(NUMBER.findall(after)):
        return False
    return True


def propose_bulk_signature_cleanup(snapshot, *, env, client=None):
    """Create reviewable sentence replacements; no mutation or database writes."""
    rows = candidate_sentences(snapshot)
    if not rows:
        raise ValueError('일괄 정리할 [서명 전 확인: ...] 문장이 없습니다.')
    changes = []
    skipped = []
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start+BATCH_SIZE]
        instructions = (
            'You are revising a user-authored commercial contract, NOT finalizing business terms. '
            'Return JSON with edits array of {sentence_id, revised_text, reason, needs_human_fact}. '
            'Use the exact language already present in each sentence. '
            'Rewrite only verbose full-sentence [서명 전 확인: ...] wrappers into concise, '
            'grammatical contract language when it can be done without making a new '
            'agreement or material legal assumption. Do not invent or remove parties, '
            'amounts, dates, currency, prices, delivery duties, governing law, forum, '
            'liability caps, dispute procedures or other material commitments. '
            'Preserve every numeric token exactly. Do not remove standalone placeholders. '
            'If an authentic missing decision is needed, set needs_human_fact=true and '
            'leave revised_text identical to the input. These are drafting suggestions '
            'requiring explicit human approval. Output no extra clauses.'
        )
        response = _call(instructions, {
            'drafting_task': 'bulk_cleanup', 'language': snapshot.get('language'),
            'contract_type': snapshot.get('contract_type'),
            'sentences': deepcopy(batch),
        }, env=env, opener=client or urllib.request.urlopen, timeout=120)
        edits = response.get('edits')
        if not isinstance(edits, list):
            raise ValueError('AI 문장 정리 응답 형식이 잘못되어 기존 계약서를 유지합니다.')
        mapping = {}
        for edit in edits:
            if not isinstance(edit, dict) or not isinstance(edit.get('sentence_id'), str):
                raise ValueError('AI 문장 정리 응답의 문장 ID를 검증할 수 없습니다.')
            sid = edit['sentence_id']
            if sid in mapping or sid not in {row['sentence_id'] for row in batch}:
                raise ValueError('AI 문장 정리 결과의 문장 ID가 중복되거나 다릅니다.')
            mapping[sid] = edit
        for row in batch:
            edit = mapping.get(row['sentence_id'])
            if edit is None or edit.get('needs_human_fact'):
                skipped.append(row['sentence_id'])
                continue
            new_text = edit.get('revised_text')
            if not _eligible_change(row['text'], new_text):
                skipped.append(row['sentence_id'])
                continue
            changes.append({
                'id': f'bulk_clean_{uuid4().hex}', 'sentence_id': row['sentence_id'],
                'original_text': row['text'], 'proposed_text': new_text.strip(),
                'reason': str(edit.get('reason') or '불필요한 서명 전 확인 문장 정리')[:350],
                'term_key': None, 'delete_sentence': False,
                'required_to_resolve_conflict': False,
            })
    if not changes:
        raise ValueError('합의되지 않은 조건을 만들지 않고 안전하게 정리할 수 있는 문장이 없습니다. 개별 검토가 필요합니다.')
    proposal = {
        'id': f'proposal_{uuid4().hex}',
        'contract_id': snapshot['contract_id'],
        'base_revision': snapshot['revision'],
        'target_sentence_id': None,
        'instruction': 'AI 일괄 문장 정리: 기존 서명 전 확인 문구 개선',
        'changes': changes, 'issues': [],
        'explanation': (
            f'AI가 {len(changes)}개 문장의 대체안을 만들었습니다. '
            f'실제 합의 확인이 필요한 {len(skipped)}개 문장은 변경 대상에서 제외했습니다. '
            '수정 전후를 비교하여 원하는 문장만 적용하세요. 아직 저장되지 않았습니다.'
        ),
    }
    # Existing revision engine checks sentence IDs, stale revisions and text
    # before a human is allowed to apply this proposal.
    apply_proposal(snapshot, proposal, [c['id'] for c in changes])
    return proposal
