"""User-controlled FINAL export gate; review warnings are not contract text."""
import re

_PLACEHOLDER = re.compile(
    r'\[(?:서명\s*전\s*확인|확인\s*필요|필수\s*확인|TBD(?:\s*/[^\]]*)?|'
    r'TO\s*CONFIRM|TO\s*BE\s*CONFIRMED|PENDING\s*CONFIRMATION)\]', re.I)

def final_document_blockers(snapshot, *, allow_unresolved_text=False):
    """Block unsafe final exports; allow authored placeholders only by opt-in.

    Leaving review questions unresolved must not be mistaken for approving them.
    An explicit user acknowledgement in the UI is required for this opt-in;
    it never bypasses signatory, seal-authorization, or pending-change checks.
    """
    problems = []
    clauses = snapshot.get('clauses') or []
    if not any(str(s.get('text') or '').strip() for c in clauses for s in c.get('sentences', [])):
        problems.append('최종 계약서에 실제 계약 조항이 없습니다.')
    for clause in clauses:
        for sentence in clause.get('sentences', []):
            if not allow_unresolved_text and _PLACEHOLDER.search(str(sentence.get('text') or '')):
                problems.append('BOX 3에 임시 확인 문구가 남았습니다: '+str(sentence.get('text') or '')[:90])
    if snapshot.get('pending_reconciliation'):
        problems.append('BOX 2 변경사항의 본문 반영·승인이 남아 있습니다.')
    parties = snapshot.get('parties') or []
    if not any(re.sub(r'[^a-z0-9]', '',str(p.get('legal_name') or '').casefold()) in
               {'kekorea', 'kekorealtd', 'kekoreacoltd', 'kekoreacolimited'} for p in parties):
        problems.append('서명 당사자에 KE KOREA가 없어 직인을 안전하게 날인할 수 없습니다.')
    if snapshot.get('contract_type') == 'sale':
        roles={role for p in parties for role in p.get('roles', [])}
        if not {'seller','buyer'}.issubset(roles):
            problems.append('매매계약의 매도인·매수인 서명 당사자가 모두 필요합니다.')
    return problems
