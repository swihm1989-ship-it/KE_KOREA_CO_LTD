"""Stage structured facts recovered from draft clauses without certifying them."""
from copy import deepcopy
from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys


def clause_evidence(snapshot):
    parts = []
    for clause in snapshot.get('clauses', []):
        for sentence in clause.get('sentences', []):
            value = str(sentence.get('text') or '').strip()
            if value:
                parts.append(f"{clause.get('title', '')} / {sentence.get('id', '')}: {value}")
    return '\n'.join(parts)


def merge_clause_candidates(snapshot, analysis):
    """Return an UNSAVED editor candidate. Never replace nonempty known values."""
    staged = deepcopy(snapshot)
    analysis, conflicts = normalize_term_keys(analysis)
    # Preserve ambiguities for human review. Never auto-certify any extraction.
    if conflicts:
        staged['clause_extraction_conflicts'] = conflicts
    existing = {str(t.get('key')): t for t in staged.get('terms', [])}
    for candidate in analysis.get('terms', []):
        key, value = str(candidate.get('key') or ''), str(candidate.get('value') or '').strip()
        if not key or not value:
            continue
        old = existing.get(key)
        if old is not None and str(old.get('value') or '').strip():
            continue
        clean = {'key': key, 'value': value, 'unit': candidate.get('unit'),
                 'currency': candidate.get('currency'), 'status': 'suggested',
                 'source_refs': deepcopy(candidate.get('source_refs') or [])}
        if old is None:
            staged.setdefault('terms', []).append(clean)
            existing[key] = clean
        else:
            old.update(clean)
    parties = staged.setdefault('parties', [])
    for candidate in analysis.get('parties', []):
        roles = [r for r in candidate.get('roles', []) if isinstance(r, str) and r]
        for role in roles:
            current = next((p for p in parties if role in p.get('roles', [])), None)
            if current is None:
                if not str(candidate.get('legal_name') or '').strip():
                    continue
                parties.append({'roles': [role], 'legal_name': candidate.get('legal_name'),
                                'country': candidate.get('country'), 'address': candidate.get('address'),
                                'representative': candidate.get('representative'), 'status': 'suggested'})
                continue
            added = False
            for field in ('legal_name', 'country', 'address', 'representative'):
                if not str(current.get(field) or '').strip() and str(candidate.get(field) or '').strip():
                    current[field] = candidate[field]
                    added = True
            if added:
                current['status'] = 'suggested'
    return staged
