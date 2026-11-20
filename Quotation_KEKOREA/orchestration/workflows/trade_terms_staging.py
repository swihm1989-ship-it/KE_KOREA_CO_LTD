"""Synthetic-only structured trade term extraction for the public staging lab.

Deliberately deterministic: no LLM/network use, no credentials, no persistence.
A single line item is supported; multi-item inputs are always flagged for review.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

_QUANTITY = re.compile(
    r"(?im)^\s*(?:quantity|qty|수량)\s*[:：=]\s*([\d,]+(?:\.\d+)?)\s*(pcs|units|ea|kg|sets|개|장)?"
)
_QTY_FALLBACK = re.compile(
    r"(?i)\b([\d,]+(?:\.\d+)?)\s*(pcs|units|ea|kg|sets)\b"
)
_PRICE = re.compile(
    r"(?im)^\s*(?:unit\s*price|단가)\s*[:：=]\s*(USD|KRW|EUR)?\s*(\$|₩)?\s*([\d,]+(?:\.\d+)?)\s*(?:/\s*(pc|pcs|unit|ea|kg|set))?"
)
_TOTAL = re.compile(
    r"(?im)^\s*(?:total(?:\s+amount)?|총액|합계)\s*[:：=]\s*(USD|KRW|EUR)?\s*(\$|₩)?\s*([\d,]+(?:\.\d+)?)"
)
_PRODUCT = re.compile(r"(?im)^\s*(?:product|item|품목|제품명)\s*[:：=]\s*(.+?)\s*$")
_INCOTERM = re.compile(r"(?i)\b(EXW|FOB|CFR|CIF|DAP|DDP)\b(?:\s+([^\n;,\.]{1,60}))?")


def _decimal(value: str) -> Decimal | None:
    try:
        result = Decimal(value.replace(",", ""))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, AttributeError, TypeError):
        return None


def _currency(code: str | None, symbol: str | None) -> str | None:
    return code.upper() if code else {"$": "USD", "₩": "KRW"}.get(symbol)


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.6f}".rstrip("0").rstrip(".")


def extract_trade(subject: str, body: str) -> dict:
    """Extract explicit, reviewable single-line-item facts without guessing."""
    text = str(subject or "") + "\n" + str(body or "")
    warnings: list[str] = []
    products = [m.group(1).strip()[:140] for m in _PRODUCT.finditer(text)]
    product = products[0] if len(products) == 1 else None
    if len(products) > 1 or re.search(r"(?im)^\s*(?:item|품목)\s*#?\s*\d+\s*[:：.\-]", text):
        warnings.append("복수 품목: 단일 품목 자동 계산 불가 (개별 검토 필요)")
    if not product:
        warnings.append("상품명 확인 필요")

    qty_matches = list(_QUANTITY.finditer(text))
    if not qty_matches:
        qty_matches = list(_QTY_FALLBACK.finditer(text))
    quantities = [_decimal(m.group(1)) for m in qty_matches]
    quantities = [q for q in quantities if q is not None]
    quantity = quantities[0] if len(quantities) == 1 else None
    if len(quantities) > 1:
        warnings.append("수량 후보가 여러 개: 품목별 수량 검토 필요")
    if quantity is None:
        warnings.append("수량 확인 필요")
    if quantity is not None and quantity <= 0:
        warnings.append("수량은 0보다 커야 함")

    prices = list(_PRICE.finditer(text))
    price_match = prices[0] if len(prices) == 1 else None
    unit_price = _decimal(price_match.group(3)) if price_match else None
    price_currency = _currency(price_match.group(1), price_match.group(2)) if price_match else None
    if len(prices) > 1:
        warnings.append("단가 후보가 여러 개: 단일 품목 계산 불가")
    if unit_price is None:
        warnings.append("명시적인 Unit Price/단가 확인 필요")
    if unit_price is not None and not price_currency:
        warnings.append("단가 통화 미확정 (USD 등 명시 필요)")

    totals = list(_TOTAL.finditer(text))
    total_match = totals[0] if len(totals) == 1 else None
    stated_total = _decimal(total_match.group(3)) if total_match else None
    total_currency = _currency(total_match.group(1), total_match.group(2)) if total_match else None
    if len(totals) > 1:
        warnings.append("총액 후보가 여러 개: 검토 필요")
    if stated_total is not None and price_currency and total_currency and price_currency != total_currency:
        warnings.append("단가 통화와 총액 통화가 다름")
    elif stated_total is not None and not total_currency:
        warnings.append("명시된 총액의 통화 미확정")

    delivery_matches = list(_INCOTERM.finditer(text))
    delivery = None
    if len(delivery_matches) == 1:
        d = delivery_matches[0]
        delivery = d.group(1).upper() + ((" " + d.group(2).strip()) if d.group(2) else "")
    elif len(delivery_matches) > 1:
        warnings.append("복수 인코텀즈 후보: 검토 필요")

    calculated_total = None
    if (product is not None and quantity is not None and quantity > 0
            and unit_price is not None and price_currency and len(prices) == 1
            and len(quantities) == 1 and "복수 품목: 단일 품목 자동 계산 불가 (개별 검토 필요)" not in warnings):
        calculated_total = quantity * unit_price
        if (stated_total is not None and total_currency == price_currency
                and calculated_total != stated_total):
            warnings.append(
                "총액 불일치: 계산 " + price_currency + " " + _fmt(calculated_total)
                + " vs 입력 " + total_currency + " " + _fmt(stated_total)
            )

    return {
        "product": product,
        "quantity": _fmt(quantity) if quantity is not None else None,
        "unit_price": (_fmt(unit_price) if unit_price is not None else None),
        "currency": price_currency,
        "stated_total": (_fmt(stated_total) if stated_total is not None else None),
        "calculated_total": (_fmt(calculated_total) if calculated_total is not None else None),
        "delivery": delivery,
        "warnings": warnings,
    }


def describe_trade(subject: str, body: str) -> tuple[str, ...]:
    result = extract_trade(subject, body)
    lines = []
    for title, key in (("상품", "product"), ("수량", "quantity"), ("단가", "unit_price"),
                       ("계산 총액", "calculated_total"), ("인코텀즈", "delivery")):
        value = result[key]
        if key in ("unit_price", "calculated_total") and value:
            value = (result["currency"] or "통화 미확정") + " " + value
        lines.append(title + ": " + (value or "미확정"))
    return tuple(lines)


def crosscheck(subject: str, body: str, payment_details: tuple[str, ...]) -> tuple[str, ...]:
    trade = extract_trade(subject, body)
    warnings = list(trade["warnings"])
    payment = {}
    for detail in payment_details:
        match = re.fullmatch(r"(선금/계약금|잔금):\s*(\d+(?:\.\d+)?)%", detail)
        if match:
            payment[match.group(1)] = Decimal(match.group(2))
        if "상충하는 비율" in detail or "비정상 비율" in detail:
            warnings.append("지급조건 비율이 충돌하거나 비정상적임")
    if "선금/계약금" in payment and "잔금" in payment:
        if payment["선금/계약금"] + payment["잔금"] != Decimal(100):
            warnings.append("선금과 잔금의 합계가 100%가 아님")
        else:
            warnings.append("지급 비율 합계 100% 확인 (거래조건 진위 보증 아님)")
    return tuple(warnings or ["명시적 수량·단가·지급조건에서 추가 경고 없음 (사실 여부 미검증)"])
