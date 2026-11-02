"""Reconcile supplier packing-list rows without mixing quantities or guessing missing data."""
from decimal import Decimal, InvalidOperation
from copy import deepcopy
import re

from .trade_documents import normalize_quantity_unit


def _number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        text = str(value).strip()
        if "," in text and not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
            return None
        number = Decimal(text.replace(",", ""))
        return number if number.is_finite() and number >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _plain(number):
    return format(number, "f") if number is not None else None


PACKING_SOURCE_FIELDS = ("actual_package_count", "container_count", "declared_net_weight_kg",
                         "declared_gross_weight_kg", "declared_volume_cbm", "declared_total_quantity",
                         "declared_total_quantity_unit")
_AMOUNT = r"(\d+(?:,\d{3})*(?:\.\d+)?)"


def normalize_packing_inputs(data):
    """Parse explicit numeric annotations, retaining the original source values."""
    result = deepcopy(data)
    result.setdefault('_packing_original_totals', {field: data.get(field) for field in PACKING_SOURCE_FIELDS})
    result['_packing_input_issues'] = []
    suffixes = {
        'actual_package_count': r'(?:pallets?|plts?|packages?|pkgs?|cartons?|ctns?|boxes?)?',
        'declared_net_weight_kg': r'(?:kgs?|kilograms?)?',
        'declared_gross_weight_kg': r'(?:kgs?|kilograms?)?',
        'declared_volume_cbm': r'(?:cbm|m3|m³)?',
        'container_count': r"(?:[x×*]\s*\d+(?:\.\d+)?\s*(?:ft|feet|'))?\s*(?:containers?|컨테이너)?",
    }
    for field, suffix in suffixes.items():
        value = result.get(field)
        if value in (None, ''):
            continue
        match = re.fullmatch(r'\s*' + _AMOUNT + r'\s*' + suffix + r'\s*', str(value), re.I)
        if match and _number(match[1]) is not None:
            result[field] = _plain(_number(match[1]))
    quantity = result.get('declared_total_quantity')
    if quantity not in (None, ''):
        match = re.fullmatch(r'\s*' + _AMOUNT + r'\s*([A-Za-z]+)?\s*', str(quantity), re.I)
        if match and _number(match[1]) is not None:
            unit = normalize_quantity_unit(match[2])
            supplied_unit = normalize_quantity_unit(result.get('declared_total_quantity_unit'))
            if unit and supplied_unit and unit != supplied_unit:
                result['_packing_input_issues'].append('Source total quantity has conflicting units; correct its unit before approving totals')
            else:
                result['declared_total_quantity'] = _plain(_number(match[1]))
                if unit:
                    result['declared_total_quantity_unit'] = unit
    return result


def packing_total_changes(data, check=None):
    """Propose only totals supported by complete row calculations."""
    check = check or reconcile_packing(data)
    changes = []
    for key, field, label in (
        ('package_count', 'actual_package_count', 'Packages'),
        ('net_weight_kg', 'declared_net_weight_kg', 'NW (kg)'),
        ('gross_weight_kg', 'declared_gross_weight_kg', 'GW (kg)'),
        ('volume_cbm', 'declared_volume_cbm', 'CBM'),
    ):
        computed = check['calculated'][key]
        if computed is not None and _number(data.get(field)) != Decimal(computed):
            original = data.get('_packing_original_totals', {}).get(field, data.get(field))
            changes.append({'field': field, 'label': label, 'source': str(original) if original is not None else 'Not provided',
                            'calculated': computed})
    if check['quantity_complete']:
        quantities = check['quantities']
        unit = normalize_quantity_unit(data.get('declared_total_quantity_unit'))
        if unit not in quantities or _number(data.get('declared_total_quantity')) != Decimal(quantities[unit]):
            original = data.get('_packing_original_totals', {}).get('declared_total_quantity', data.get('declared_total_quantity'))
            source_text = str(original) if original is not None else 'Not provided'
            original_unit = data.get('_packing_original_totals', {}).get('declared_total_quantity_unit', unit)
            if _number(original) is not None and original_unit:
                source_text += ' ' + str(original_unit)
            changes.append({'field': 'declared_total_quantity', 'label': 'Quantity (by unit)',
                            'source': source_text,
                            'calculated': ' + '.join(f'{value} {key}' for key, value in quantities.items())})
    return changes


def apply_approved_packing_totals(data):
    """Apply row totals after explicit approval; never change item rows or infer containers."""
    result = normalize_packing_inputs(data)
    check = reconcile_packing(result)
    if check['issues'] or not check['quantity_complete']:
        raise ValueError('Correct invalid packing rows, units, and container counts before approving totals')
    for key, field in (('package_count', 'actual_package_count'), ('net_weight_kg', 'declared_net_weight_kg'),
                       ('gross_weight_kg', 'declared_gross_weight_kg'), ('volume_cbm', 'declared_volume_cbm')):
        if check['calculated'][key] is not None:
            result[field] = check['calculated'][key]
    quantities = check['quantities']
    unit = normalize_quantity_unit(result.get('declared_total_quantity_unit'))
    if unit not in quantities:
        unit = next(iter(quantities)) if len(quantities) == 1 else None
    result['declared_total_quantity'] = quantities.get(unit)
    result['declared_total_quantity_unit'] = unit
    result['_packing_approved_quantities'] = dict(quantities)
    result['_packing_totals_approved'] = True
    return result


def reconcile_packing(data):
    """Return calculated totals and discrepancies; printed totals are never overwritten."""
    items = data.get("items") or []
    issues, discrepancies = list(data.get('_packing_input_issues', [])), []
    quantities = {}
    quantity_complete = bool(items)
    for index, item in enumerate(items, 1):
        quantity_value = next((item.get(key) for key in ("shipped_quantity", "quantity", "paid_quantity")
                               if item.get(key) not in (None, "")), None)
        amount = _number(quantity_value)
        unit = normalize_quantity_unit(item.get("unit"))
        if amount is None or not unit:
            quantity_complete = False
            issues.append(f"Packing row {index}: quantity and unit must be confirmed")
        else:
            quantities[unit] = quantities.get(unit, Decimal("0")) + amount
        net = _number(item.get("net_weight_kg"))
        gross = _number(item.get("gross_weight_kg"))
        if net is not None and gross is not None and net > gross:
            issues.append(f"Packing row {index}: net weight exceeds gross weight")
        for field, label in (("package_count", "package count"), ("net_weight_kg", "net weight"),
                             ("gross_weight_kg", "gross weight"), ("volume_cbm", "CBM")):
            if item.get(field) not in (None, "") and _number(item.get(field)) is None:
                issues.append(f"Packing row {index}: {label} is invalid")

    calculated = {}
    for field, label, declared_field in (
        ("package_count", "package count", "actual_package_count"),
        ("net_weight_kg", "net weight (kg)", "declared_net_weight_kg"),
        ("gross_weight_kg", "gross weight (kg)", "declared_gross_weight_kg"),
        ("volume_cbm", "volume (CBM)", "declared_volume_cbm"),
    ):
        values = [_number(item.get(field)) for item in items]
        total = sum(values, Decimal("0")) if values and all(value is not None for value in values) else None
        if field == "package_count" and total is not None:
            package_types = {normalize_quantity_unit(item.get("package_type")) for item in items}
            if len(package_types) > 1:
                issues.append("Package counts use different package types; confirm their totals separately")
                total = None
        calculated[field] = _plain(total)
        declared_raw = data.get(declared_field)
        declared = _number(declared_raw)
        if declared_raw not in (None, "") and declared is None:
            message = f"Source {label} total is invalid"
            (discrepancies if total is not None else issues).append(message)
        elif total is not None and declared is not None and total != declared:
            discrepancies.append(f"Source {label} total {_plain(declared)} differs from row sum {_plain(total)}")

    declared_quantity = _number(data.get("declared_total_quantity"))
    declared_unit = normalize_quantity_unit(data.get("declared_total_quantity_unit"))
    if data.get("declared_total_quantity") not in (None, "") and declared_quantity is None:
        (discrepancies if quantity_complete else issues).append("Source quantity total is invalid")
    elif declared_quantity is not None:
        if not declared_unit or declared_unit not in quantities:
            discrepancies.append("Source quantity total unit does not match the item units; confirm the total")
        elif quantities[declared_unit] != declared_quantity:
            discrepancies.append(f"Source quantity total {_plain(declared_quantity)} {declared_unit} differs from row sum {_plain(quantities[declared_unit])} {declared_unit}")

    raw_containers = data.get("container_count")
    if raw_containers not in (None, ""):
        containers = _number(raw_containers)
        if containers is None or containers != containers.to_integral_value():
            issues.append("Container count must be a non-negative whole number")

    return {"quantities": {unit: _plain(value) for unit, value in quantities.items()},
            "quantity_complete": quantity_complete, "calculated": calculated,
            "issues": issues, "discrepancies": discrepancies}
