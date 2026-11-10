"""Deterministic final-contract signature data, separate from AI draft text.

A company seal is never a person's signature. Missing names/titles stay blank.
Contract date is the explicit date, otherwise the saved creation day, otherwise
the export day in Korea. Never use an unrelated effective-date field.
"""
from datetime import datetime
import re
from zoneinfo import ZoneInfo

_SIGNATURE_SUMMARY = re.compile(
    r'^\s*(?:Supplier|Seller|Buyer|공급자|매도인|매수인)\s*[:：].*'
    r'(?:Signature\s*[:：]\s*\[signature\]|서명\s*[:：])',
    re.I | re.S,
)
_SIGNATURE_TITLES = {'서명', '서명란', 'signatures', 'signature', 'signing'}


def is_redundant_signature_line(text):
    """Remove ONLY explicit generated party signature summaries, not business terms."""
    return bool(_SIGNATURE_SUMMARY.search(str(text or '')))


def is_signature_heading(title):
    return str(title or '').strip().casefold() in _SIGNATURE_TITLES


def authored_clauses_for_final(snapshot):
    """Keep substantive authored sentences; omit duplicated signature boilerplate."""
    result = []
    for clause in sorted(snapshot.get('clauses', []), key=lambda row: row.get('order', 0)):
        retained = [sentence for sentence in clause.get('sentences', [])
                    if not is_redundant_signature_line(sentence.get('text'))]
        # A dedicated signature heading is rendered once by the final template.
        if is_signature_heading(clause.get('title')):
            if retained:
                result.append((None, retained))
        elif retained:
            result.append((clause.get('title') or '', retained))
    return result


def contract_signature_date(snapshot, *, now=None):
    terms = {str(t.get('key') or '').strip().casefold(): t
             for t in snapshot.get('terms', []) if isinstance(t, dict)}
    for key in ('contract_date', 'signing_date'):
        term = terms.get(key)
        value = (term or {}).get('value')
        if value is not None and str(value).strip():
            return str(value).strip()
    for key in ('created_at', 'contract_created_at'):
        value = snapshot.get(key)
        if value:
            raw = str(value).strip()
            try:
                return datetime.fromisoformat(raw.replace('Z', '+00:00')).date().isoformat()
            except ValueError:
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
                    return raw
    return (now or datetime.now(ZoneInfo('Asia/Seoul'))).date().isoformat()


def signature_parties(snapshot):
    parties = [p for p in snapshot.get('parties', []) if isinstance(p, dict)]
    sale = snapshot.get('contract_type') == 'sale'
    roles = (('seller', 'buyer') if sale else
             ('client', 'intermediary') if snapshot.get('contract_type') == 'trade_commission'
             else ('commission_payer', 'fundraiser'))
    picked = []
    used = set()
    for role in roles:
        match = next((p for p in parties if role in p.get('roles', [])
                      and id(p) not in used), None)
        if match is None:
            match = next((p for p in parties if id(p) not in used), None)
        if match is not None:
            used.add(id(match))
        picked.append(match or {})
    return picked


def signature_blocks(snapshot, *, now=None):
    date = contract_signature_date(snapshot, now=now)
    roles = ('Supplier', 'Buyer') if snapshot.get('contract_type') == 'sale' else (
        ('Client', 'Intermediary') if snapshot.get('contract_type') == 'trade_commission'
        else ('Commission Payer', 'Fundraiser')
    )
    blocks = []
    for label, party in zip(roles, signature_parties(snapshot)):
        name = str(party.get('representative') or '').strip()
        title = str(party.get('representative_title') or
                    party.get('position') or party.get('title') or '').strip()
        blocks.append({
            'label': label,
            'company': str(party.get('legal_name') or '').strip(),
            'name_title': (name + (', ' + title if title else '')) if name else title,
            'date': date,
            'party': party,
        })
    return blocks
