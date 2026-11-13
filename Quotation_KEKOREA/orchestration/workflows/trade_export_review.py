"""Per-document export diagnostics; facts stay private and are never auto-approved."""
from copy import deepcopy
from hashlib import sha256
import json
from collections.abc import Mapping
from decimal import Decimal
import re

from Quotation_KEKOREA.agent.review_fields import missing_review_fields, _missing
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate, current_issue_date, normalize_quantity_unit
from Quotation_KEKOREA.agent.ci_import import ci_import_issues
from .commercial_values import normalize_trade_values
from .intake_followups import format_field_label

TRADE_REVIEW_REVISION = 'approved-blank-final-20261113-v1'


class TradeExportValidationError(ValueError):
    def __init__(self, issues):
        self.issues = deepcopy(issues)
        super().__init__('문서 발행 전 확인 필요: ' + '; '.join(row['message'] for row in issues))


def _key(path):
    if path[0] == 'items':
        return 'item.' + (str(path[1])+'.' if path[1] else '') + path[2]
    return '.'.join(path)


def trade_export_fingerprint(kind, source, *, allow_optional_na=False, allow_incomplete=False):
    data={'kind':kind,'date':current_issue_date(),'source':normalize_trade_values(source),
          'allow_optional_na':bool(allow_optional_na), 'allow_incomplete':bool(allow_incomplete)}
    return sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _set_path(data, path, value):
    target = data
    for part in path[:-1]:
        target = target.setdefault(part, {}) if isinstance(target, dict) else target[part]
    target[path[-1]] = value


def _quantity(item, kind):
    keys = ('shipped_quantity', 'quantity', 'paid_quantity') if kind == 'PL' else ('paid_quantity', 'quantity')
    return next((item[key] for key in keys if not _missing(item.get(key), True)), None)


def _blank_unknowns(candidate):
    """Remove extraction placeholders, preserving explicit optional N/A and zero."""
    candidate = deepcopy(candidate)
    for field in missing_review_fields(candidate):
        _set_path(candidate, field.path, '')
    if str(candidate.get('document_number') or '').upper().startswith('DRAFT'):
        candidate['document_number'] = ''
    for key in ('product_family', 'currency', 'actual_package_count', 'container_count',
                'declared_total_quantity', 'declared_total_quantity_unit',
                'declared_net_weight_kg', 'declared_gross_weight_kg', 'declared_volume_cbm'):
        if key in candidate and _missing(candidate[key], True):
            candidate[key] = ''
    for key in ('remarks', 'bill_to', 'hs_code'):
        if key in candidate and _missing(candidate[key], False):
            candidate[key] = ''
    for role in ('buyer', 'seller'):
        party = candidate.get(role) or {}
        if 'registration_details' in party and _missing(party['registration_details'], False):
            party['registration_details'] = ''
    for row in list(candidate.get('items') or []) + list(candidate.get('packages') or []):
        for key in ('quantity', 'paid_quantity', 'shipped_quantity', 'free_quantity',
                    'unit_price', 'discount_percent', 'package_count', 'net_weight_kg',
                    'gross_weight_kg', 'volume_cbm'):
            if key in row and _missing(row[key], True):
                row[key] = None
        for key in ('product_name', 'unit', 'price_basis', 'package_type', 'capacity', 'specification',
                    'hs_code', 'dimensions', 'shipping_marks'):
            if key in row and _missing(row[key], key in {'product_name', 'unit', 'price_basis'}):
                row[key] = ''
    candidate.pop('_final_packing_totals', None)
    return candidate


def _missing_validation_messages(candidate):
    """Identify only absent inputs; entered invalid values stay blocking.

    These are the legacy validator's exact missing-input diagnostics. Keeping
    the whitelist here leaves its normal strict callers and arithmetic intact.
    """
    kind = candidate['document_type']
    missing = set()
    for key, message in (
            ('product_family', 'Product family must be confirmed'),
            ('currency', 'Currency must be confirmed as a three-letter code'),
            ('document_number', 'Document number is required or must be marked DRAFT'),
            ('incoterms', 'Incoterms and named place'),
            ('payment_terms', 'Payment terms'),
            ('shipment_reference', 'Shipment reference'),
            ('country_of_origin', 'Country of origin must be confirmed')):
        if _missing(candidate.get(key), True):
            missing.add(message)
    for role in ('buyer', 'seller'):
        party = candidate.get(role) or {}
        for key, label in (('legal_name', 'legal name'), ('address', 'address')):
            if _missing(party.get(key), True):
                missing.add(f'{role.title()} {label} is required')
        if _missing(party.get('legal_name'), True):
            if role == 'buyer' and kind == 'PO':
                missing.add('PO buyer must be KE KOREA')
            elif role == 'seller':
                missing.add(f'{kind} seller must be KE KOREA')
                missing.add('PO seller must be the supplier and buyer must be KE KOREA')
    items = candidate.get('items') or []
    if not items:
        missing.add('At least one line item is required')
    for index, item in enumerate(items, 1):
        name = item.get('product_name') or f'item {index}'
        for key, message in (
                ('product_name', f'Product name is required for item {index}'),
                ('unit', f'Quantity unit for item {index}'),
                ('price_basis', f'Price basis for {name}')):
            if _missing(item.get(key), True):
                missing.add(message)
        quantity_missing = _quantity(item, kind) is None
        if quantity_missing:
            missing.add(f'Valid number required for paid quantity for item {index}')
            missing.add(f'Packing: Packing row {index}: quantity and unit must be confirmed')
        if _missing(item.get('unit'), True):
            missing.add(f'Packing: Packing row {index}: quantity and unit must be confirmed')
        for key, label in (('unit_price', 'unit price'), ('discount_percent', 'discount percent'),
                           ('free_quantity', 'free quantity'), ('shipped_quantity', 'shipped quantity')):
            if _missing(item.get(key), True):
                missing.add(f'Valid number required for {label} for item {index}')
                missing.add(f'Valid positive number required for {label} for item {index}')
        if _missing(item.get('discount_percent'), True):
            missing.add(f'Confirm discount percentage, including whether no discount applies, for {name}')
        if _missing(item.get('unit_price'), True):
            missing.add(f'Cosmetics price for {name} must match the verified price master')
        if quantity_missing or any(_missing(item.get(key), True) for key in ('product_name', 'unit', 'unit_price')):
            # Real invalid values still have their own numeric/identity errors.
            missing.add(f'Sample {index}: confirm a valid name, quantity, unit and non-negative unit price')
        if quantity_missing or any(key in item and _missing(item[key], True)
                                   for key in ('free_quantity', 'shipped_quantity')):
            missing.add(f'Shipped quantity must equal paid plus free quantity for {name}')
            # A well-formed promotion cannot be calculated without quantity.
            if re.fullmatch(r'\s*[1-9]\d*\s*\+\s*\d+\s*', str(item.get('promotion') or '')):
                missing.add(f'Promotion quantity mismatch for {name}')
    if kind == 'PL':
        if _missing(candidate.get('actual_package_count'), True):
            missing.add('Actual package count must be a positive whole number')
            missing.add('Sum of package counts must equal actual package count')
        missing.add('Actual package count and weights')
        for index, package in enumerate(candidate.get('packages') or [], 1):
            for key, label in (('net_weight_kg', 'net weight'), ('gross_weight_kg', 'gross weight'),
                               ('package_count', 'count')):
                if _missing(package.get(key), True):
                    missing.add(f'Valid positive number required for package {index} {label}')
            if _missing(package.get('net_weight_kg'), True) or _missing(package.get('gross_weight_kg'), True):
                missing.add(f'Net weight cannot exceed gross weight for package {index}')
            if _missing(package.get('package_count'), True):
                missing.add('Sum of package counts must equal actual package count')
    return missing


def _renderable_partial(candidate, checked):
    """Retain legacy calculations only where all their inputs are known."""
    result = deepcopy(checked)
    kind = candidate['document_type']
    all_amounts = bool(candidate.get('items'))
    currency_known = not _missing(candidate.get('currency'), True)
    family_known = not _missing(candidate.get('product_family'), True)
    for original, row in zip(candidate.get('items') or [], result['items']):
        known_shipped = row.get('shipped_quantity')
        quantity_known = _quantity(original, kind) is not None
        price_known = not _missing(original.get('unit_price'), True)
        discount_known = not _missing(original.get('discount_percent'), True)
        additions_known = not any(key in original and _missing(original[key], True)
                                  for key in ('free_quantity', 'shipped_quantity'))
        if not quantity_known:
            for key in ('quantity', 'paid_quantity', 'shipped_quantity', 'display_quantity'):
                row[key] = None
        if not additions_known:
            for key in ('free_quantity', 'shipped_quantity', 'display_quantity'):
                row[key] = None
        if not price_known:
            row['base_unit_price'] = None
            row['unit_price'] = None
        if not discount_known:
            row['discount_percent'] = None
        if not (price_known and discount_known and currency_known and family_known):
            row['final_unit_price'] = None
        if not (quantity_known and price_known and discount_known and currency_known and family_known):
            row['line_total'] = None
            all_amounts = False
        # Preserve a separately supplied shipped quantity when its paid part is
        # unknown; do not turn it into a fabricated paid quantity or amount.
        if not quantity_known and not _missing(original.get('shipped_quantity'), True):
            row['shipped_quantity'] = known_shipped
            row['display_quantity'] = known_shipped
    if not all_amounts or kind == 'PL':
        result['total'] = result['subtotal'] = None
    result['blocking_issues'] = []
    result['ready_for_issue'] = False  # Only the explicit export approval permits this file.
    if kind == 'PL':
        from Quotation_KEKOREA.agent.packing import reconcile_packing, _number
        packing = reconcile_packing(candidate)
        totals = dict(packing['calculated'])
        totals['quantities'] = packing['quantities'] if packing['quantity_complete'] else None
        packages = candidate.get('packages') or []
        has_item_packing = any(not _missing(item.get(key), True)
                               for item in candidate.get('items') or []
                               for key in ('package_count', 'net_weight_kg', 'gross_weight_kg', 'volume_cbm'))
        if packages and not has_item_packing:
            for key in ('package_count', 'net_weight_kg', 'gross_weight_kg', 'volume_cbm'):
                numbers = [_number(package.get(key)) for package in packages]
                totals[key] = (format(sum(numbers, Decimal('0')), 'f')
                               if all(number is not None for number in numbers) else None)
        result['_final_packing_totals'] = totals
    return result


def _explicit_numeric_issues(candidate):
    """Check supplied numbers before promotions and aliases can replace them."""
    from Quotation_KEKOREA.agent.packing import _number
    issues = []
    fields = ('quantity', 'paid_quantity', 'shipped_quantity', 'free_quantity',
              'unit_price', 'discount_percent', 'package_count', 'net_weight_kg',
              'gross_weight_kg', 'volume_cbm')
    for group in ('items', 'packages'):
        for index, row in enumerate(candidate.get(group) or [], 1):
            for key in fields:
                raw = row.get(key)
                if _missing(raw, True):
                    continue
                number = _number(raw)
                if number is None or (key == 'discount_percent' and number > 100):
                    issues.append(f'{group} {index}: {key} must be a valid non-negative finite number'
                                  + (' between 0 and 100' if key == 'discount_percent' else ''))
                elif key == 'package_count' and number != number.to_integral_value():
                    issues.append(f'{group} {index}: package count must be a whole number')
            # Missing classification cannot disable a directly known mismatch.
            if group == 'items' and candidate['document_type'] != 'PL' and _missing(candidate.get('product_family'), True):
                basis = str(row.get('price_basis') or '').upper().replace('USD/', '').replace('KRW/', '').replace('PER ', '').strip()
                basis = normalize_quantity_unit(basis)
                unit = normalize_quantity_unit(row.get('unit'))
                if basis and unit and basis not in {unit, 'SET'}:
                    issues.append(f'Price basis {basis} does not match quantity unit {unit} for item {index}')
    return issues


def review_trade_document(kind, source, *, final=False, allow_optional_na=False, allow_incomplete=False):
    """Describe real gaps separately from old AI notes; never mutates input.

    The default is strict. Explicit final incomplete mode reports missing facts
    as warnings and leaves them blank; supplied invalid values, conflicts and
    original-PI price requirements continue to block.
    """
    kind=str(kind).upper()
    if kind not in {'PI','PO','CI','PL'} or not isinstance(source,Mapping):
        raise ValueError('지원하지 않는 무역 문서입니다.')
    if not isinstance(source.get('items') or [], list) or any(
            not isinstance(item, Mapping) for item in source.get('items') or []):
        raise ValueError('상품 목록 형식을 확인해 주세요.')
    candidate=normalize_trade_values(source)
    if candidate.get('document_type') and str(candidate['document_type']).upper()!=kind:
        raise ValueError('Document type mismatch')
    candidate['document_type']=kind
    partial = final and allow_incomplete is True
    if partial:
        candidate = _blank_unknowns(candidate)
    if allow_optional_na:
        for field in missing_review_fields(candidate):
            if not field.required:
                target=candidate
                for part in field.path[:-1]:target=target.setdefault(part,{})
                target[field.path[-1]]='N/A'
    missing=[]
    for field in missing_review_fields(candidate):
        key=_key(field.path)
        missing.append({'key':key,'label':format_field_label(key), 'required':field.required,
                        'message':format_field_label(key) + (' · 필수 입력' if field.required else ' · 값 또는 N/A 입력')})
    checked=validate_and_calculate(candidate)
    render_data = _renderable_partial(candidate, checked) if partial else checked
    messages=list(checked.get('blocking_issues') or [])
    if partial:
        messages.extend(_explicit_numeric_issues(candidate))
    if kind=='CI':
        messages.extend(ci_import_issues(checked))
    issues=[]
    warnings=[]
    missing_messages = _missing_validation_messages(candidate) if partial else set()
    for message in dict.fromkeys(map(str,messages)):
        code='validation'
        if message.startswith('Confirm missing information: '):code='ai_missing'
        elif message.startswith('Resolve conflicting information: '):code='ai_conflict'
        entry={'code':code,'key':'','message':message}
        is_missing = partial and (code=='ai_missing' or message in missing_messages)
        if partial and message.startswith('PI import: '):
            is_missing = message.removeprefix('PI import: ') in missing_messages
        # A source total cannot be compared with an amount whose inputs are
        # absent. Display that limitation; never replace the price with a catalog.
        if partial and kind == 'CI' and 'source amount differs from the calculated amount' in message:
            from Quotation_KEKOREA.agent.ci_import import _amount
            match = re.match(r'PI import item (\d+) amount:', message)
            is_missing = (match is not None and
                          _amount(candidate['items'][int(match[1])-1].get('source_line_total')) is not None and
                          render_data['items'][int(match[1])-1]['line_total'] is None)
            if message.startswith('PI import total:'):
                is_missing = (_amount(candidate.get('source_total')) is not None and
                              render_data.get('total') is None)
        if (partial and kind == 'PL'
                and message.startswith('Packing source discrepancy: Source quantity total ')
                and render_data['_final_packing_totals']['quantities'] is None):
            from Quotation_KEKOREA.agent.packing import _number
            declared_unit = normalize_quantity_unit(candidate.get('declared_total_quantity_unit'))
            units = {normalize_quantity_unit(item.get('unit')) for item in candidate.get('items') or []}
            is_missing = (_number(candidate.get('declared_total_quantity')) is not None
                          and (not declared_unit or declared_unit in units or '' in units or not units))
        (warnings if is_missing else issues).append(entry)
    for row in missing:
        (warnings if partial else issues).append({'code':'missing',**row})
    number=str(candidate.get('document_number') or '').strip()
    if final and not partial and (_missing(number,True) or number.upper().startswith('DRAFT')):
        issues.append({'code':'final_number','key':'document_number',
                       'message':'최종 문서번호를 입력하거나 문서번호 자동 생성을 누르세요. DRAFT 번호로 최종 발행하지 않습니다.'})
    return {'candidate':candidate,'checked':checked,'render_data':render_data,
            'missing':missing,'issues':issues,'warnings':warnings, 'ready':not issues}
