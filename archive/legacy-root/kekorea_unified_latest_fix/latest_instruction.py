"""Conservative last-instruction candidates for saved contract revisions.

Chat messages are evidence, not the canonical contract. An explicit change to an
existing contract is prepared for review, never silently written to the DB.
"""
import hashlib
import re
from copy import deepcopy

from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys

_CHANGE_RE = re.compile(
    r'(수정|변경|바꿔|고쳐|정정|교체|다시\s*(?:설정|써)|'
    r'\b(?:change|replace|revise|amend|update|correct|modify|ubah|ganti|revisi)\b)',
    re.IGNORECASE,
)


def is_explicit_change(text):
    return bool(_CHANGE_RE.search(str(text or '')))


def instruction_hash(text):
    return hashlib.sha256(str(text or '').strip().encode('utf-8')).hexdigest()


def latest_unapplied_request(messages, snapshot):
    """Return last user change request unless that exact instruction was approved.

    Keep this only as a reminder and an input for an explicit review action.
    Old chat history is not itself an authority to modify current terms.
    """
    for message in reversed(messages or []):
        if message.get('role') != 'user':
            continue
        text = str(message.get('content') or '').strip()
        if not is_explicit_change(text):
            continue
        if instruction_hash(text) == snapshot.get('last_approved_chat_hash'):
            return None
        return text
    return None


def candidate_from_latest(snapshot, analysis):
    """Stage *only supplied* nonblank changes without dropping unrelated facts.

    Statuses on changed fields are ALWAYS suggested until user approval.
    No current approved value is overwritten in the original snapshot.
    """
    staged = deepcopy(snapshot)
    normalized, conflicts = normalize_term_keys(analysis)
    if conflicts:
        staged['clause_extraction_conflicts'] = conflicts
    by_key = {str(t.get('key')): t for t in staged.get('terms', [])}
    for suggestion in normalized.get('terms', []):
        key = str(suggestion.get('key') or '').strip()
        value = str(suggestion.get('value') or '').strip()
        if not key or not value or key in {'buyer', 'seller', 'client', 'intermediary', 'commission_payer', 'fundraiser'}:
            continue
        previous = by_key.get(key)
        if previous is None:
            item = {'key': key, 'value': value, 'unit': suggestion.get('unit'),
                    'currency': suggestion.get('currency'), 'source_refs': deepcopy(suggestion.get('source_refs') or []),
                    'status': 'suggested'}
            staged.setdefault('terms', []).append(item)
            by_key[key] = item
            continue
        different = str(previous.get('value') or '').strip() != value
        # Never erase known units/currency based on an extraction that omitted them.
        for field in ('unit', 'currency'):
            incoming = suggestion.get(field)
            if incoming is not None and str(incoming).strip() and str(previous.get(field) or '').strip() != str(incoming).strip():
                different = True
        if different:
            previous['value'] = value
            for field in ('unit', 'currency'):
                incoming = suggestion.get(field)
                if incoming is not None and str(incoming).strip():
                    previous[field] = incoming
            previous['status'] = 'suggested'
            previous['source_refs'] = deepcopy(suggestion.get('source_refs') or previous.get('source_refs') or [])
    parties = staged.setdefault('parties', [])
    for suggested in analysis.get('parties', []):
        for role in suggested.get('roles') or []:
            existing = next((p for p in parties if role in p.get('roles', [])), None)
            if existing is None:
                name = str(suggested.get('legal_name') or '').strip()
                if name:
                    parties.append({'roles': [role], 'legal_name': name,
                                    'country': suggested.get('country'), 'address': suggested.get('address'),
                                    'representative': suggested.get('representative'), 'status': 'suggested'})
            else:
                changed = False
                for field in ('legal_name', 'country', 'address', 'representative'):
                    new_value = str(suggested.get(field) or '').strip()
                    if new_value and str(existing.get(field) or '').strip() != new_value:
                        existing[field] = new_value
                        changed = True
                if changed:
                    existing['status'] = 'suggested'
    return staged
