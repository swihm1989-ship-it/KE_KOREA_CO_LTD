"""PI attachment adapters; existing CI renderers and ordinary workflows stay intact."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

_PAYMENT = re.compile(r'\b(?:payment|bank|beneficiary|swift|iban|bic|a/c|account\s*(?:number|no\.?)|remittance|t[./]?t)\b|은행|계좌|결제|송금|银行|銀行|付款|收款', re.I)


def is_pi_import(draft):
    return draft.get('document_type') == 'CI' and draft.get('_ci_from_pi') is True


def is_ci_conversion_request(prompt):
    text = str(prompt or '')
    pi = r'(?:\bPI\b|pro\s*forma\s+invoice)'
    ci = r'(?:\bCI\b|commercial\s+invoice)'
    return bool(re.search(r'(?:PI|proforma\s+invoice|pro\s+forma\s+invoice).{0,70}?(?:CI|commercial\s+invoice|상업송장)\s*(?:로|를|을)?\s*(?:작성|만들|생성|변환)', text, re.I)
                or re.search(rf'\b(?:convert|turn|use)\b.{{0,35}}?{pi}.{{0,45}}?\b(?:to|into|as|create|make|prepare)\b.{{0,15}}?{ci}', text, re.I)
                or re.search(rf'\b(?:create|make|prepare|generate|draft)\b.{{0,15}}?{ci}\s+(?:from|using|based\s+on)\b.{{0,35}}?{pi}', text, re.I))


def _zero_price_evidence(item):
    if str(item.get('price_source') or '').startswith('User-entered'):
        return True
    source = str(item.get('source') or '')
    return bool(re.search(r'\b(?:foc|free\s+of\s+charge|no\s+charge)\b|무료|무상', source, re.I)
                or re.search(r'(?:\b(?:USD|KRW|EUR|CNY|price|rate)|US\$|\$|₩|€)\s*[:=]?\s*0(?:\.0+)?(?![\d.])', source, re.I)
                or re.search(r'(?<![\d.])0\.0+(?![\d.]|\s*(?:pcs|ml|g|kg)\b)', source, re.I))


def _amount(value):
    try:
        text = str(value).strip()
        if ',' in text and not re.fullmatch(r'\d{1,3}(?:,\d{3})+(?:\.\d+)?', text):
            return None
        amount = Decimal(text.replace(',', ''))
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _sanitize_import(draft):
    draft['payment_terms'] = 'N/A'
    for key in ('bank_details', 'bank_information', 'payment_details', 'payment_information', 'bank_account', 'swift', 'account_number'):
        draft.pop(key, None)
    if _PAYMENT.search(str(draft.get('remarks') or '')):
        draft['remarks'] = 'N/A'
    def notices(entries):
        kept = []
        for entry in entries:
            if _PAYMENT.search(str(entry)):
                if re.search(r'currency|통화', str(entry), re.I):
                    entry = 'Currency conflict in source PI; confirm the transaction currency independently of banking information'
                else:
                    continue
            match = re.fullmatch(r'Item (\d+) (free quantity|discount percent|shipped quantity) was not found in its source quote; confirm the value', str(entry), re.I)
            if match:
                index = int(match[1]) - 1
                if 0 <= index < len(draft.get('items', [])):
                    item = draft['items'][index]
                    field = match[2].lower().replace(' ', '_')
                    value = _amount(item.get(field))
                    if field in ('free_quantity', 'discount_percent') and value == 0:
                        continue  # Omitted FOC/discount columns mean no addition.
                    paid = _amount(item.get('paid_quantity', item.get('quantity')))
                    free = _amount(item.get('free_quantity'))
                    if field == 'shipped_quantity' and paid is not None and free is not None and value == paid + free:
                        continue  # Derived shipping total need not be printed twice.
            if entry not in kept:
                kept.append(entry)
        return kept
    draft['missing_fields'] = notices(draft.get('missing_fields', []))
    draft['conflicts'] = notices(draft.get('conflicts', []))
    for item in draft.get('items', []):
        amount = _amount(item.get('unit_price'))
        if item.get('source') and amount is not None and (amount > 0 or _zero_price_evidence(item)):
            item.update(price_override_confirmed=True, master_price=False, _pi_import_price=True)
            if not item.get('price_source') or not str(item['price_source']).startswith('User-'):
                item['price_source'] = 'Attached PI transaction price; verify against source'
            if not item.get('price_basis') and item.get('unit'):
                item['price_basis'] = item['unit']
        else:
            item.pop('_pi_import_price', None)
    return draft


def prepare_ci_import(draft, *, requested_type, has_attachments):
    source = str(draft.get('source_document_type') or draft.get('document_type') or '').upper()
    if requested_type != 'CI' or not has_attachments or source != 'PI':
        return draft
    draft.update(document_type='CI', source_document_type='PI', _ci_from_pi=True)
    return _sanitize_import(draft)


def apply_document_prices(draft, catalog=None):
    if is_pi_import(draft):
        return _sanitize_import(draft)
    from Quotation_KEKOREA.agent.pricing import apply_verified_eclado_prices
    return apply_verified_eclado_prices(draft, catalog)


def pi_source_zero_price(draft, item):
    return is_pi_import(draft) and item.get('_pi_import_price') is True and bool(item.get('source')) and _amount(item.get('unit_price')) == 0 and _zero_price_evidence(item)


def ci_import_issues(result):
    if not is_pi_import(result):
        return []
    issues = []
    quantum = Decimal('1') if result.get('currency') == 'KRW' else Decimal('0.01')
    def compare(original, calculated, label):
        if original in (None, ''):
            return
        source, computed = _amount(original), _amount(calculated)
        if source is None or computed is None or source.quantize(quantum, rounding=ROUND_HALF_UP) != computed.quantize(quantum, rounding=ROUND_HALF_UP):
            issues.append(f'PI import {label}: source amount differs from the calculated amount; review the source and extracted values')
    compare(result.get('source_total'), result.get('total'), 'total')
    for index, item in enumerate(result.get('items', []), 1):
        compare(item.get('source_line_total'), item.get('line_total'), f'item {index} amount')
    for issue in result.get('blocking_issues', []):
        if issue.startswith(('Valid ', 'Shipped quantity ', 'Promotion ', 'Cosmetics price ', 'Price basis ', 'Price source ', 'Confirm discount ')):
            issues.append('PI import: ' + issue)
        elif re.search(r'Item \d+.*(?:source quote|exact quote)', issue, re.I):
            issues.append('PI import source evidence: ' + issue)
    return issues


def ci_render_data(result):
    if not is_pi_import(result):
        return result
    result = _sanitize_import(deepcopy(result))
    for item in result.get('items', []):
        free = _amount(item.get('free_quantity'))
        if free is not None and free > 0:
            # Existing CI PDF appends FOC separately. The shipping total remains
            # untouched, and the existing Excel renderer already separates FOC.
            item['display_quantity'] = item.get('paid_quantity')
    return result
