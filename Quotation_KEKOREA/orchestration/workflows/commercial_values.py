"""Parse explicit commercial notation without supplying product-based defaults."""
from copy import deepcopy
import re

from Quotation_KEKOREA.agent.trade_documents import normalize_quantity_unit

_NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
_UNIT = r'(?:PCS?|PIECES?|장|KG|KGS|W|MW|MT|SET|BOX|CTN|PALLET)'
_CURRENCY = r'(?:US\$|USD|KRW|EUR|CNY|\$|₩|€)'
_CURRENCIES = {'$': 'USD', 'US$': 'USD', '₩': 'KRW', '€': 'EUR'}


def _text(value):
    return '' if value is None else str(value).strip()


def _unit(value):
    text = _text(value)
    return 'PCS' if text == '장' else normalize_quantity_unit(text)


def normalize_trade_values(source):
    """Return a copy with only unambiguous explicit numbers/units normalized.

    A denominator is evidence of the quantity unit only when none was supplied.
    Conflicting declared currencies leave the original price for validation.
    Price-source/confirmation metadata is never synthesized.
    """
    result = deepcopy(dict(source))
    currency = _text(result.get('currency')).upper()
    currency = _CURRENCIES.get(currency, currency)
    for item in result.get('items') or []:
        quantity = _text(item.get('quantity'))
        match = re.fullmatch(rf'({_NUMBER})\s*({_UNIT})?', quantity, re.I)
        if match and (not match[2] or not _text(item.get("unit"))
                      or _unit(item["unit"]) == _unit(match[2])):
            item['quantity'] = match[1].replace(',', '')
            if match[2] and not _text(item.get('unit')):
                item['unit'] = _unit(match[2])
        price = _text(item.get('unit_price'))
        match = re.fullmatch(rf'\s*({_CURRENCY})?\s*({_NUMBER})\s*({_CURRENCY})?\s*(?:(?:/|per\s+)\s*({_UNIT}))?\s*', price, re.I)
        if match:
            symbols = [_CURRENCIES.get(value.upper(), value.upper()) for value in (match[1], match[3]) if value]
            if (len(set(symbols)) <= 1 and (not currency or not symbols or symbols[0] == currency)
                    and (not match[4] or not _text(item.get("price_basis"))
                         or _unit(item["price_basis"]) == _unit(match[4]))
                    and (not match[4] or not _text(item.get("unit"))
                         or _unit(item["unit"]) == _unit(match[4]))):
                item['unit_price'] = match[2].replace(',', '')
                if symbols and not currency:
                    currency = symbols[0]
                if match[4]:
                    if not _text(item.get('price_basis')):
                        item['price_basis'] = _unit(match[4])
                    if not _text(item.get('unit')):
                        item['unit'] = _unit(match[4])
        if _text(item.get('unit')):
            item['unit'] = _unit(item['unit'])
        if not _text(item.get('price_basis')) and _text(item.get('unit')):
            item['price_basis'] = item['unit']
    result['currency'] = currency
    return result


def normalize_analysis_values(analysis):
    """Normalize extracted terms while keeping suggested status and source refs."""
    result = deepcopy(analysis)
    terms = {term['key']: term for term in result['terms']}
    row = {field: terms.get(key, {}).get('value', '') for field, key in (
        ('quantity', 'quantity'), ('unit', 'unit'), ('unit_price', 'unit_price'))}
    if not _text(row['unit']):
        row['unit'] = terms.get('quantity', {}).get('unit', '')
    currency = terms.get('currency', {}).get('value', '')
    if not _text(currency):
        currency = terms.get('unit_price', {}).get('currency', '')
    parsed = normalize_trade_values({'items': [row], 'currency': currency})
    quantity_has_unit = re.fullmatch(rf'({_NUMBER})\s*({_UNIT})', _text(row['quantity']), re.I)
    def evidence_for(key):
        if key == 'unit' and (quantity_has_unit or _text(terms.get('quantity', {}).get('unit'))):
            return terms.get('quantity') or {}
        return terms.get('unit_price') or {}
    for key, value in {**parsed['items'][0], 'currency': parsed['currency']}.items():
        if key == 'price_basis' or value in ('', None):
            continue
        if key in terms:
            term = terms[key]
            if not _text(term.get('value')):
                evidence = evidence_for(key)
                term['source_refs'] = deepcopy(evidence.get('source_refs', []))
            term['value'] = value
        else:
            evidence = evidence_for(key)
            result['terms'].append({'key': key, 'value': value, 'status': 'suggested',
                                    'source_refs': deepcopy(evidence.get('source_refs', []))})
    return result
