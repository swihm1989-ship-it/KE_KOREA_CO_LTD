"""Stable sales-contract party and trade specification clause.

All values come only from the saved party/term records. Never infer a brand,
invent 100% prepayment, or turn suggested terms into confirmed obligations.
The generated text remains individually editable through BOX 3 revisions.
"""
from copy import deepcopy
from uuid import uuid4

from Quotation_KEKOREA.contracts.signature_layout import localized_representative_title


_LABELS = {
    'ko': {
        'heading': '당사자 및 거래 범위',
        'seller': '공급자', 'buyer': '구매자',
        'brand': '브랜드', 'products': '제품', 'unit_price': '가격',
        'delivery': '인도조건', 'payment_trigger': '결제조건',
        'details': '세부 거래 명세는 아래와 같다:',
        'proposed': '제안(미확정): ',
        'obligations': '공급자는 위 거래명세에 따라 물품을 인도하고, 구매자는 이를 인수하여 합의된 대금을 지급한다.',
    },
    'en': {
        'heading': 'Parties and Scope of Sale',
        'seller': 'Supplier', 'buyer': 'Buyer',
        'brand': 'Brand', 'products': 'Product', 'unit_price': 'Price',
        'delivery': 'Delivery Terms', 'payment_trigger': 'Payment Terms',
        'details': 'The transaction details are as follows:',
        'proposed': 'Proposed (not agreed): ',
        'obligations': 'The Supplier shall deliver the goods under the agreed terms, and the Buyer shall accept the goods and pay the agreed price.',
    },
}
_FIELDS = ('brand', 'products', 'unit_price', 'delivery', 'payment_trigger')


def _term_by_key(snapshot, key):
    return next((t for t in snapshot.get('terms', [])
                 if str(t.get('key') or '') == key), None)


def _value(term, language):
    if not term or term.get('value') is None:
        return ''
    value = str(term['value']).strip()
    if not value:
        return ''
    if term.get('status') == 'confirmed':
        return value
    return _LABELS[language]['proposed'] + value


def _party(snapshot, role):
    return next((p for p in snapshot.get('parties', [])
                 if isinstance(p, dict) and role in p.get('roles', [])), {})


def _party_description(snapshot, party, role, language):
    label = _LABELS[language][role]
    company = str(party.get('legal_name') or '').strip()
    address = str(party.get('address') or '').strip()
    representative = str(party.get('representative') or '').strip()
    position = localized_representative_title(
        party.get('representative_title') or party.get('position') or party.get('title'),
        language,
    )
    if language == 'ko':
        pieces = [f'주소: {address}' for _ in [0] if address]
        if representative:
            pieces.append('대표자: ' + representative + (', ' + position if position else ''))
        detail = '(' + ', '.join(pieces) + ')' if pieces else ''
        return f'{label} {company}{detail}'.strip()
    pieces = (['Address: ' + address] if address else [])
    if representative:
        pieces.append('Representative: ' + representative + (', ' + position if position else ''))
    detail = ' (' + '; '.join(pieces) + ')' if pieces else ''
    return f'{label} {company}{detail}'.strip()


def _field_values(snapshot, language):
    goods = _term_by_key(snapshot, 'products')
    quantity = _term_by_key(snapshot, 'quantity')
    unit = _term_by_key(snapshot, 'unit')
    price = _term_by_key(snapshot, 'unit_price')
    currency = _term_by_key(snapshot, 'currency')
    delivery = _term_by_key(snapshot, 'delivery')
    payment = _term_by_key(snapshot, 'payment_trigger')
    payment_deadline = _term_by_key(snapshot, 'payment_deadline')
    brand = _term_by_key(snapshot, 'brand')

    product_text = _value(goods, language)
    quantity_text = _value(quantity, language)
    if quantity_text:
        if quantity and quantity.get('unit'):
            qty_unit = str(quantity['unit']).strip()
        else:
            qty_unit = _value(unit, language)
        quantity_piece = (quantity_text + (' ' + qty_unit if qty_unit else '')).strip()
        if not product_text or quantity_text not in product_text:
            product_text = (product_text + ' ' + quantity_piece).strip()
    price_text = _value(price, language)
    if price_text:
        ccy = str(price.get('currency') or '').strip() if price else ''
        ccy = ccy or _value(currency, language)
        if ccy and ccy.lower() not in price_text.lower():
            price_text = f'{ccy} {price_text}'
        price_unit = str(price.get('unit') or '').strip() if price else ''
        if price_unit and price_unit.casefold() not in price_text.casefold():
            price_text += '/' + price_unit
    payment_text = _value(payment, language)
    deadline = _value(payment_deadline, language)
    if deadline and deadline not in payment_text:
        payment_text = (payment_text + ' / ' + deadline).strip(' /')
    return {
        'brand': (_value(brand, language), [brand]),
        'products': (product_text, [goods, quantity, unit]),
        'unit_price': (price_text, [price, currency]),
        'delivery': (_value(delivery, language), [delivery]),
        'payment_trigger': (payment_text, [payment, payment_deadline]),
    }


def _text_sentence(text, *, field=None, terms=()):
    result = {
        'id': 'sentence_' + uuid4().hex,
        'text': text,
        'term_ids': [t['id'] for t in terms if t and t.get('id')],
        'source_refs': [],
    }
    if field:
        result['sale_spec_field'] = field
    return result


def sale_scope_clause(snapshot):
    if snapshot.get('contract_type') != 'sale':
        return None
    language = snapshot.get('language')
    if language not in _LABELS:
        return None
    seller, buyer = _party(snapshot, 'seller'), _party(snapshot, 'buyer')
    # Do not manufacture parties or a trade specification out of missing input.
    if not seller.get('legal_name') or not buyer.get('legal_name'):
        return None
    fields = _field_values(snapshot, language)
    labels = _LABELS[language]
    seller_text = _party_description(snapshot, seller, 'seller', language)
    buyer_text = _party_description(snapshot, buyer, 'buyer', language)
    if language == 'ko':
        introduction = f'이 계약의 당사자는 {seller_text}와 {buyer_text}로 한다.'
    else:
        introduction = f'The parties to this Agreement are {seller_text} and {buyer_text}.'
    sentences = [_text_sentence(introduction), _text_sentence(labels['details'])]
    for key in _FIELDS:
        value, source_terms = fields[key]
        sentences.append(_text_sentence(f"{labels[key]}: {value}", field=key,
                                        terms=source_terms))
    sentences.append(_text_sentence(labels['obligations']))
    return {
        'id': 'clause_' + uuid4().hex, 'title': labels['heading'],
        'order': 1, 'topic_key': 'scope', 'sentences': sentences,
    }


def apply_sale_scope_template(snapshot, *, repair_context=None):
    """Replace only the initial AI-generated scope prose, never saved revisions."""
    if repair_context:
        # Preserve the deterministic trade schedule across a quality-repair
        # pass. AI may improve other clauses, but must never rewrite the fixed
        # business summary or substitute new payment/price assumptions.
        previous = repair_context.get('draft') or {}
        original_scope = next(
            (clause for clause in previous.get('clauses', [])
             if any(sentence.get('sale_spec_field')
                    for sentence in clause.get('sentences', []))), None)
        if original_scope is None:
            return snapshot
        result = deepcopy(snapshot)
        index = next((i for i, clause in enumerate(result.get('clauses', []))
                      if clause.get('id') == original_scope.get('id')), None)
        if index is None:
            result['clauses'].insert(0, deepcopy(original_scope))
        else:
            result['clauses'][index] = deepcopy(original_scope)
        return result
    template = sale_scope_clause(snapshot)
    if template is None:
        return snapshot
    draft = deepcopy(snapshot)
    clauses = draft.get('clauses', [])
    found = next((i for i, c in enumerate(clauses)
                  if c.get('topic_key') == 'scope'), None)
    if found is None:
        titles = {
            'scope', 'parties and scope', 'parties and scope of sale',
            'transaction scope', 'scope of transaction', '당사자 및 거래 범위',
            '당사자와 거래 범위', '당사자 및 거래범위', '거래 범위',
        }
        found = next((i for i, c in enumerate(clauses)
                      if str(c.get('title') or '').strip().casefold() in titles), None)
    if found is None:
        for clause in clauses:
            clause['order'] = int(clause.get('order') or 1) + 1
        clauses.insert(0, template)
    else:
        old = clauses[found]
        template['id'] = old['id']
        template['order'] = old.get('order', found + 1)
        clauses[found] = template
    return draft
