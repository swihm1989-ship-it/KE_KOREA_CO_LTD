"""Presentation-only grouping of contract review findings.

Never changes confirmation, severity or export validation state.
"""
from collections import OrderedDict

_CATEGORIES = (
    ('parties', '법인·역할 및 서명권자', '각 회사의 법적 명칭, 역할·관계 및 서명권한을 확인해 주세요.'),
    ('amounts', '거래금액·수수료 및 지급', '계산 기준, 실제 입금 증빙, 지급조건과 수취계좌를 확인해 주세요.'),
    ('scope', '거래 범위 및 부동산', '중개 대상 거래, 기존 관계와 부동산 식별정보를 확인해 주세요.'),
    ('law', '법률·세금 및 분쟁 해결', '준거법, 중재, 인허가·세무 및 국경 간 집행을 전문가와 검토해 주세요.'),
    ('terms', '거래조건·기타 미확정 사항', 'AI가 제안한 조건과 미확정 내용을 실제 합의에 맞게 확인해 주세요.'),
)


def _category(issue):
    code = str(issue.get('code') or '').casefold()
    msg = str(issue.get('message') or '').casefold()
    # Categorization deliberately uses both code and text. It is only an
    # interface summary; raw findings and export checks are never discarded.
    s = code + ' ' + msg
    if any(w in s for w in ('snapshot business terms', 'suggested or missing',
                             'condition_status', 'terms_unconfirmed')):
        return 'terms'
    if any(w in s for w in ('party', 'parties', 'legal name', 'legal_name', 'signing',
                             'investor', 'vibe development', 'payer name', 'payer jurisdiction',
                             '법인', '서명권', '투자자', '당사자')):
        return 'parties'
    if any(w in s for w in ('interest', 'payment', 'commission', 'funding', 'bank',
                             'receipt', 'account', 'withholding', 'currency', 'usd',
                             '커미션', '입금', '수수료', '연체', '계좌', '환전', '송금')):
        return 'amounts'
    if any(w in s for w in ('property', 'project', 'introduction', 'introduction',
                             'relationship', 'sale price', 'transaction scope',
                             '부동산', '소개', '거래 범위', '프로젝트', '매매대금')):
        return 'scope'
    if any(w in s for w in ('legal', 'law', 'jurisdiction', 'arbitrat', 'licen',
                             'regulat', 'tax', 'compliance', 'foreign exchange',
                             'governing', 'dispute', 'enforceab', '준거법', '분쟁',
                             '인허가', '세무', '법적', '법률')):
        return 'law'
    return 'terms'


def unresolved_issues(issues):
    result = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            result.append({'code': 'unstructured', 'message': str(issue), 'severity': 'confirm'})
            continue
        severity = issue.get('severity')
        if severity == 'info':
            continue
        if severity == 'confirm' and issue.get('confirmed'):
            continue
        if severity == 'block' and issue.get('resolved_by_user') and str(issue.get('resolution') or '').strip():
            continue
        result.append(issue)
    return result


def summarize_issues(issues, *, max_groups=5):
    if max_groups < 1:
        raise ValueError('max_groups must be positive')
    counted = OrderedDict((key, 0) for key, _, _ in _CATEGORIES)
    for issue in unresolved_issues(issues):
        counted[_category(issue)] += 1
    labels = {key: (label, guidance) for key, label, guidance in _CATEGORIES}
    groups = [{'key': key, 'label': labels[key][0], 'guidance': labels[key][1],
               'count': count} for key, count in counted.items() if count]
    # Bound visible complexity while preserving every original issue elsewhere.
    if len(groups) > max_groups:
        excess = groups[max_groups-1:]
        groups = groups[:max_groups-1] + [{
            'key': 'other', 'label': '기타 확인사항',
            'guidance': '세부 검토 사항을 확인해 주세요.',
            'count': sum(row['count'] for row in excess),
        }]
    return groups


def review_cards(issues, *, language='ko'):
    """Deduplicate presentation only; use conservative labels, not invented translations.

    A card retains indices into the original findings. Classification never changes
    severity, confirmation, resolution, or any export gate.
    """
    from Quotation_KEKOREA.contracts.rules import LABELS
    korean = language != 'en'
    kinds = {
        'required': '필수 확인' if korean else 'Required confirmation',
        'recommended': '권장 확인' if korean else 'Recommended review',
        'legal': '법률 검토 권장' if korean else 'Legal review recommended',
        'tbd': '초안에 TBD 허용' if korean else 'TBD allowed in draft',
    }
    english = {'parties': 'Parties and signing authority', 'amounts': 'Amounts, commission and payment',
               'scope': 'Transaction scope and property', 'law': 'Law, tax and dispute resolution',
               'terms': 'Terms requiring confirmation'}
    labels = {key: label for key, label, _ in _CATEGORIES}
    grouped = OrderedDict()
    for index, raw in enumerate(issues or []):
        issue = raw if isinstance(raw, dict) else {'message': str(raw)}
        if not unresolved_issues([issue]):
            continue
        category = _category(issue)
        key = str(issue.get('key') or '')
        text = (key + ' ' + str(issue.get('code') or '') + ' ' + str(issue.get('message') or '')).casefold()
        if any(word in text for word in ('address', 'representative', 'legal id', 'legal_id', '주소', '서명권자')):
            kind = 'tbd'
        elif category == 'law' or any(word in text for word in ('interest', 'tax', 'governing', 'arbitrat', 'legal_review', '연체', '준거법', '세금')):
            kind = 'legal'
        elif issue.get('severity') == 'confirm':
            kind = 'recommended'
        else:
            kind = 'required'
        identity = (kind, category, key)
        if identity not in grouped:
            label = LABELS.get(key) if korean else None
            summary = label or (labels[category] if korean else english[category])
            grouped[identity] = {
                'kind': kinds[kind], 'summary': summary,
                'category': category, 'field_key': key,
                'target': ('law' if kind == 'legal' else 'parties' if category == 'parties' else 'terms'),
                'count': 0, 'indices': [],
            }
        grouped[identity]['count'] += 1
        grouped[identity]['indices'].append(index)
    return list(grouped.values())
