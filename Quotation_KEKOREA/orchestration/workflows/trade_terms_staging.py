"""Synthetic-only, deterministic trade analysis for the public staging lab.

Parses explicitly labelled Product/Quantity/Unit Price groups, including
multiple consecutive items. When a group is incomplete, never invent a
quantity, price, currency, or aggregate amount. No network or persistence.
This is not an LLM and does not replace human document review.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

_ITEM = re.compile(
    r"(?im)^[ \t]*(?:product|item|품목|제품명)(?:[ \t]*#?[0-9]{1,2})?[ \t]*[:：=]"
    r"[ \t]*(?P<name>[^\r\n]{1,180}?)[ \t]*$"
)
_QUANTITY = re.compile(
    r"(?im)^[ \t]*(?:quantity|qty|수량)[ \t]*[:：=][ \t]*"
    r"([\d,]{1,30}(?:\.\d{1,8})?)[ \t]*(pcs|units|ea|kg|sets|개|장)?"
)
_QTY_FALLBACK = re.compile(
    r"(?i)\b([\d,]{1,30}(?:\.\d{1,8})?)[ \t]*(pcs|units|ea|kg|sets)\b"
)
_PRICE = re.compile(
    r"(?im)^[ \t]*(?:unit[ \t]+price|단가)[ \t]*[:：=][ \t]*"
    r"(USD|KRW|EUR)?[ \t]*(\$|₩)?[ \t]*"
    r"([\d,]{1,30}(?:\.\d{1,8})?)[ \t]*(?:/[ \t]*(pc|pcs|unit|units|ea|kg|set|sets))?"
)
_TOTAL = re.compile(
    r"(?im)^[ \t]*(?:total(?:[ \t]+amount)?|총액|합계)[ \t]*[:：=][ \t]*"
    r"(USD|KRW|EUR)?[ \t]*(\$|₩)?[ \t]*([\d,]{1,30}(?:\.\d{1,8})?)"
)
_INCOTERM = re.compile(
    r"(?i)\b(EXW|FOB|CFR|CIF|DAP|DDP)\b(?:[ \t]+([^\r\n;,\.]{1,60}))?"
)


def _decimal(raw: str | None) -> Decimal | None:
    try:
        amount = Decimal((raw or "").replace(",", ""))
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _currency(code: str | None, symbol: str | None) -> str | None:
    return code.upper() if code else {"$": "USD", "₩": "KRW"}.get(symbol)


def _fmt(amount: Decimal | None) -> str | None:
    if amount is None:
        return None
    return f"{amount:,.8f}".rstrip("0").rstrip(".")


def _unit(raw: str | None) -> str | None:
    if not raw:
        return None
    word = raw.lower()
    if word in ("pc", "pcs", "unit", "units", "ea", "개", "장"):
        return "pcs"
    if word in ("set", "sets"):
        return "sets"
    return word


def _item_result(name: str, section: str, index: int) -> tuple[dict, Decimal | None]:
    """Read fields only between consecutive product labels."""
    issues: list[str] = []
    qs = list(_QUANTITY.finditer(section))
    if not qs:
        qs = list(_QTY_FALLBACK.finditer(section))
    if len(qs) != 1:
        issues.append("수량 " + ("미기재" if not qs else "후보 중복"))
    qmatch = qs[0] if len(qs) == 1 else None
    quantity = _decimal(qmatch.group(1)) if qmatch else None
    quantity_unit = _unit(qmatch.group(2)) if qmatch else None
    if quantity is not None and quantity <= 0:
        issues.append("수량은 0보다 커야 함")
    if qmatch and quantity is None:
        issues.append("유효하지 않은 수량")

    prices = list(_PRICE.finditer(section))
    if len(prices) != 1:
        issues.append("단가 " + ("미기재" if not prices else "후보 중복"))
    pmatch = prices[0] if len(prices) == 1 else None
    price = _decimal(pmatch.group(3)) if pmatch else None
    currency = _currency(pmatch.group(1), pmatch.group(2)) if pmatch else None
    price_unit = _unit(pmatch.group(4)) if pmatch else None
    if pmatch and price is None:
        issues.append("유효하지 않은 단가")
    if pmatch and not currency:
        issues.append("단가 통화 미기재")
    if quantity_unit and price_unit and quantity_unit != price_unit:
        issues.append("수량 단위와 단가 기준 단위 불일치")

    # Decimal exact arithmetic. Any missing/conflicting field blocks the
    # line total; a partial order must never appear as a complete quotation.
    amount = None
    if (not issues and quantity is not None and quantity > 0
            and price is not None and currency):
        amount = quantity * price
    item = {
        "number": index,
        "product": name,
        "quantity": _fmt(quantity),
        "quantity_unit": quantity_unit,
        "unit_price": _fmt(price),
        "price_unit": price_unit,
        "currency": currency,
        "line_total": _fmt(amount),
        "issues": issues,
    }
    return item, amount


def extract_trade(subject: str, body: str) -> dict:
    """Parse safe labelled rows into N items, with verified aggregate totals."""
    text = str(subject or "") + "\n" + str(body or "")
    warnings: list[str] = []
    headers = list(_ITEM.finditer(text))
    items: list[dict] = []
    amounts: list[Decimal | None] = []

    if not headers:
        warnings.append("상품명이 명시된 Product/Item/품목 행 확인 필요")
    for i, header in enumerate(headers):
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        name = header.group("name").strip()
        item, amount = _item_result(name, text[start:end], i + 1)
        items.append(item)
        amounts.append(amount)
        for issue in item["issues"]:
            warnings.append(f"품목 {i + 1} ({name[:45]}): {issue} - 확인 필요")

    currencies = {row["currency"] for row in items if row["currency"]}
    combined_currency = next(iter(currencies)) if len(currencies) == 1 else None
    if len(currencies) > 1:
        warnings.append("품목별 통화가 서로 다름: 합계 계산 불가 - 확인 필요")
    if len(items) > 1 and any(amount is None for amount in amounts):
        warnings.append("복수 품목: 일부 항목의 수량·단가가 불완전하여 합계 미확정 - 확인 필요")

    calculated = (sum(amounts, Decimal(0))
                  if items and all(amount is not None for amount in amounts)
                  and combined_currency else None)

    totals = list(_TOTAL.finditer(text))
    stated_total = None
    stated_currency = None
    if len(totals) == 1:
        m = totals[0]
        stated_total = _decimal(m.group(3))
        stated_currency = _currency(m.group(1), m.group(2))
        if stated_total is None or not stated_currency:
            warnings.append("명시된 총액 또는 통화 확인 필요")
        if (combined_currency and stated_currency
                and combined_currency != stated_currency):
            warnings.append("품목 단가 통화와 명시된 총액 통화 불일치 - 확인 필요")
        if (calculated is not None and stated_currency == combined_currency
                and stated_total is not None and calculated != stated_total):
            warnings.append(
                "총액 불일치: 계산 " + combined_currency + " " + _fmt(calculated)
                + " vs 입력 " + stated_currency + " " + _fmt(stated_total)
            )
    elif len(totals) > 1:
        warnings.append("총액 후보 중복: 합계 확정 불가 - 확인 필요")

    delivery_matches = list(_INCOTERM.finditer(text))
    delivery = None
    if len(delivery_matches) == 1:
        match = delivery_matches[0]
        delivery = match.group(1).upper() + (
            " " + match.group(2).strip() if match.group(2) else ""
        )
    elif len(delivery_matches) > 1:
        warnings.append("복수 인코텀즈 후보 - 확인 필요")

    single = items[0] if len(items) == 1 else {}
    return {
        "items": items,
        "product": single.get("product"),
        "quantity": single.get("quantity"),
        "unit_price": single.get("unit_price"),
        "currency": combined_currency,
        "stated_total": _fmt(stated_total),
        "calculated_total": _fmt(calculated),
        "delivery": delivery,
        "warnings": warnings,
    }


def describe_trade(subject: str, body: str) -> tuple[str, ...]:
    result = extract_trade(subject, body)
    lines: list[str] = ["인식 품목 수: " + str(len(result["items"]))]
    for item in result["items"]:
        name = item["product"]
        qty = item["quantity"] or "미확정"
        unit = item["quantity_unit"] or ""
        price = item["unit_price"] or "미확정"
        currency = item["currency"] or "통화 미확정"
        amount = item["line_total"]
        lines.append(
            f"품목 {item['number']}: {name} | 수량 {qty} {unit} | "
            f"단가 {currency} {price} | 금액 "
            + (f"{currency} {amount}" if amount else "미확정")
        )
    lines.append(
        "계산 총액: " + (
            (result["currency"] or "통화 미확정") + " " + result["calculated_total"]
            if result["calculated_total"] else "미확정"
        )
    )
    lines.append("인코텀즈: " + (result["delivery"] or "미확정"))
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
            warnings.append("지급조건 비율이 충돌하거나 비정상적임 - 확인 필요")
    if "선금/계약금" in payment and "잔금" in payment:
        if payment["선금/계약금"] + payment["잔금"] != Decimal(100):
            warnings.append("선금과 잔금의 합계가 100%가 아님 - 확인 필요")
        else:
            warnings.append("지급 비율 합계 100% 확인 (거래조건 진위 보증 아님)")
    return tuple(warnings or ["추출된 수치 간 추가 불일치 없음 (사실 여부 미검증)"])
