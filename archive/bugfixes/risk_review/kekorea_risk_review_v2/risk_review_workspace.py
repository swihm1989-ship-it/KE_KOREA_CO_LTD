"""Additive, review-only orchestration for paginated risks and three draft alternatives.

No contract data changes here. Existing editing/validation and FINAL gating remain authoritative.
"""
from copy import deepcopy
import re
from uuid import uuid4

from Quotation_KEKOREA.contracts.editing import RevisionConflict, apply_proposal, find_sentence
from Quotation_KEKOREA.contracts.review import review_contract, RISK_ORDER

PAGE_SIZE = 5
CHUNK_SIZE = 10
PROTECTED_SENTENCES = {f'commission_payment_sentence_{i}' for i in range(3)}
PLACEHOLDER = re.compile(r'\{([a-zA-Z][a-zA-Z0-9_]{0,35})\}')


def review_full_contract(snapshot, sources, *, env, reviewer=None):
    """Review all clauses in manageable chunks, preserving original source validation."""
    reviewer = reviewer or review_contract
    chunks = []
    current = []
    for clause in sorted(snapshot.get('clauses', []), key=lambda c: c.get('order', 0)):
        sentences = clause.get('sentences', [])
        for offset in range(0, len(sentences), CHUNK_SIZE):
            section = {'id': clause.get('id'), 'title': clause.get('title'),
                       'order': clause.get('order'), 'sentences': deepcopy(sentences[offset:offset+CHUNK_SIZE])}
            if sum(len(c['sentences']) for c in current) + len(section['sentences']) > CHUNK_SIZE and current:
                chunks.append(current)
                current = []
            current.append(section)
    if current:
        chunks.append(current)
    if not chunks:
        raise ValueError('검토할 계약서 본문이 없습니다.')
    seen = set()
    result = []
    for clauses in chunks:
        subset = deepcopy(snapshot)
        subset['clauses'] = clauses
        for finding in reviewer(subset, sources, env=env):
            sentence_id = finding.get('sentence_id')
            if sentence_id not in seen:
                seen.add(sentence_id)
                result.append(finding)
    result.sort(key=lambda f: RISK_ORDER[f['severity']])
    return result


def page_items(findings, page):
    count = max(1, (len(findings) + PAGE_SIZE - 1) // PAGE_SIZE)
    selected = max(1, min(int(page), count))
    start = (selected - 1) * PAGE_SIZE
    return {'page': selected, 'pages': count, 'total': len(findings),
            'items': list(enumerate(findings[start:start + PAGE_SIZE], start + 1))}


def replace_variables(template, values):
    """Replace only validated named variables, never execute expressions."""
    def substitute(match):
        key = match.group(1)
        return str(values[key]) if key in values and str(values[key]).strip() else f'[확인 필요: {key}]'
    return PLACEHOLDER.sub(substitute, template)


def suggest_alternatives(snapshot, finding, *, env, proposer=None):
    """Provide three negotiable alternatives; placeholders must be grounded in schema."""
    from Quotation_KEKOREA.contracts.service import _call
    proposer = proposer or _call
    target = find_sentence(snapshot, finding['sentence_id'])
    instructions = (
        'You are proposing three DISTINCT negotiable business contract replacement sentences for ONE risk finding. '
        'Return JSON object {"options": [{"label": "균형형", "template": "..."}, '
        '{"label": "권리 보호형", "template": "..."}, {"label": "보수적 협의형", "template": "..."}], '
        '"variables": [{"key":"rate","label":"위약금률 (%)","value":"20"}]}. '
        'Exactly three options, ordered balanced / protective / cautious. '
        'Only use placeholder syntax {name} for variable terms whose user-editable value is grounded in the actual '
        'original sentence or confirmed snapshot; provide a variable object for EVERY placeholder used. '
        'Never invent actual party names, rates, laws, addresses, or jurisdictions. '
        'For unknown values use empty value, which UI will display as needing confirmation. '
        'Keep options in the existing contract language; short readable clauses, no invented legal citations. '
        'These are drafting alternatives, not evidence of global statistical standard or legal advice. '
        'Do not change unrelated sentences or protected payment policy.'
    )
    data = proposer(instructions, {'contract_type': snapshot.get('contract_type'),
                                  'language': snapshot.get('language'),
                                  'finding': finding, 'original_sentence': target,
                                  'terms': snapshot.get('terms', []), 'parties': snapshot.get('parties', [])}, env=env)
    options, variables = data.get('options'), data.get('variables', [])
    if not isinstance(options, list) or len(options) != 3 or not isinstance(variables, list) or len(variables) > 8:
        raise ValueError('AI가 추천 문장 3개의 올바른 형식을 제공하지 않았습니다.')
    used = set()
    seen_keys = set()
    clean_variables = []
    for var in variables:
        if not isinstance(var, dict) or not isinstance(var.get('key'), str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,35}', var['key']) or var['key'] in seen_keys:
            raise ValueError('AI 가변값 형식이 잘못되었습니다.')
        seen_keys.add(var['key'])
        clean_variables.append({'key': var['key'], 'label': str(var.get('label') or var['key'])[:80],
                                'value': str(var.get('value') or '')[:300]})
    clean_options = []
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get('template'), str) or not option['template'].strip():
            raise ValueError('AI가 빈 추천 조항을 반환했습니다.')
        template = option['template'].strip()
        if len(template) > 2200:
            raise ValueError('AI 추천 문장이 지나치게 깁니다.')
        used.update(PLACEHOLDER.findall(template))
        clean_options.append({'label': str(option.get('label') or f'추천안 {len(clean_options)+1}')[:55],
                              'template': template})
    if not used.issubset(seen_keys):
        raise ValueError('AI 추천 문장에 설명되지 않은 가변값이 있습니다.')
    return {'options': clean_options, 'variables': clean_variables}


def preview_proposal(snapshot, previews):
    """Validate proposed preview changes against unchanged editing engine without persisting."""
    if not previews:
        raise ValueError('승인 요청할 수정 문장이 없습니다.')
    changes = []
    for sentence_id, text in previews.items():
        if sentence_id in PROTECTED_SENTENCES:
            raise ValueError('커미션 지급 정책 조항은 BOX 2에서 수정해 주세요.')
        sentence = find_sentence(snapshot, sentence_id)
        if not str(text or '').strip():
            raise ValueError('빈 수정 문장은 적용할 수 없습니다.')
        changes.append({'id': f'risk_edit_{uuid4().hex}', 'sentence_id': sentence_id,
                        'original_text': sentence['text'], 'proposed_text': str(text).strip(),
                        'delete_sentence': False, 'reason': 'User selected and edited AI risk-review alternative',
                        'required_to_resolve_conflict': False, 'term_key': None})
    proposal = {'id': f'proposal_{uuid4().hex}', 'contract_id': snapshot['contract_id'],
                'base_revision': snapshot['revision'], 'target_sentence_id': None,
                'instruction': 'Apply user-approved risk-review sentence alternatives',
                'changes': changes, 'issues': [],
                'explanation': '계약서 미리보기 수정안입니다. 승인하면 새 revision으로 저장됩니다.'}
    apply_proposal(snapshot, proposal, [c['id'] for c in changes])
    return proposal
