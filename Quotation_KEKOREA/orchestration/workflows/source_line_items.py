"""Recover independent priced order rows from explicit, human-typed source text.

Opt-in only after fresh MASTER extraction, before legacy catalog verification.
No AI inference, no discount defaults, no interaction with stored contracts.
A mixed, incomplete or ambiguous collection remains a manual-review candidate.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re

_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_UNIT = r"(?:개|장|PCS?|PIECES?|EA|SET|SETS|BOX|BOXES|KG|KGS|MT|W|MW|톤|박스)"
_CURRENCY = r"(?:USD|KRW|EUR|CNY)"
_EXPLICIT = re.compile(
    rf"(?P<name>.+?)\s+(?P<quantity>{_NUMBER})\s*(?P<unit>{_UNIT})"
    rf"\s*(?:\(\s*|단가\s*[:：]?\s*|개당\s*|@\s*)?"
    rf"(?P<currency>{_CURRENCY})\s*(?P<price>{_NUMBER})"
    rf"\s*(?:/\s*(?:PCS?|PIECES?|EA|KG|MT|W|MW))?\s*\)?",
    re.I,
)
_QUANTITY_EVIDENCE = re.compile(rf"(?<![\d.]){_NUMBER}\s*{_UNIT}\b", re.I)
_SENTENCES = re.compile(r"\.\s+")


def _name(raw):
    """Strip explicit transaction introductions without changing product codes."""
    value = str(raw or "").strip(" \t\n:;,.")
    match = list(re.finditer(r"(?:품목|상품|제품)\s*[:：]\s*", value, re.I))
    if match:
        value = value[match[-1].end():]
    elif _SENTENCES.search(value):
        value = _SENTENCES.split(value)[-1]
    for marker in ("로부터 ", "에게 ", "에서 ", "에 "):
        if marker in value:
            value = value.rsplit(marker, 1)[-1]
    return value.strip(" \t\n:;,.")


def _decimal(raw):
    try:
        number = Decimal(str(raw).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return format(number, "f")


def extract_explicit_priced_rows(instruction: str):
    """Parse ONLY 2+ separately priced rows, all sharing explicit ISO currency.

    An isolated unmatched quantity disqualifies the entire set: never present
    a partial recovered amount as the full order total.
    """
    text = str(instruction or "")
    if len(text) > 12000:
        return []
    chunks = re.split(r"(?:\s*;\s*|\n+|,\s*(?!\d))", text)
    priced = []
    for fragment in chunks:
        match = _EXPLICIT.search(fragment.strip())
        if not match:
            continue
        name = _name(match.group("name"))
        qty = _decimal(match.group("quantity"))
        price = _decimal(match.group("price"))
        currency = match.group("currency").upper()
        if (not name or not qty or not price
                or len(name) > 260 or len(priced) >= 100):
            return []
        # No English name should be invented from a Korean item name.
        original_unit = match.group("unit").upper()
        unit = {
            "개": "PCS", "장": "PCS", "EA": "PCS", "PC": "PCS",
            "PIECE": "PCS", "PIECES": "PCS",
            "톤": "MT", "박스": "BOX", "KGS": "KG", "BOXES": "BOX",
            "SETS": "SET",
        }.get(original_unit, original_unit)
        priced.append({
            "product_name": name, "quantity": qty, "unit": unit,
            "unit_price": price, "price_basis": unit,
            "price_source": "", "currency": currency,
        })
    if len(priced) < 2 or len({row["currency"] for row in priced}) != 1:
        return []
    # Every item quantity cited in the untrusted prompt must be accounted for.
    # The qualifier excludes deposit percentages, years and interest rates.
    evidence = _QUANTITY_EVIDENCE.findall(text)
    if len(evidence) != len(priced):
        return []
    return priced


def restore_explicit_priced_rows(candidate_map: dict, instruction: str):
    """Restore documented price-bearing rows only where the AI lost products.

    Return a deep-copy and recovered item count; never replace an already
    complete multi-row extraction or a user's post-extraction manual edits.
    """
    revised = deepcopy(candidate_map)
    recovered = extract_explicit_priced_rows(instruction)
    if not recovered:
        # A combined product name plus 2+ separately declared quantities is
        # demonstrably not a verified *single* unit-price row. Fail safely
        # rather than printing the last item's amount as the FULL invoice.
        count = len(_QUANTITY_EVIDENCE.findall(str(instruction or "")))
        if count >= 2:
            for kind, doc in revised.items():
                if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(doc, dict):
                    continue
                items = doc.get("items") or []
                if (len(items) == 1 and isinstance(items[0], dict)
                        and re.search(r"[,，;]", str(items[0].get("product_name") or ""))):
                    items[0]["unit_price"] = ""
                    items[0]["price_source"] = ""
                    doc.setdefault("missing_fields", []).append(
                        "원본 요청에 여러 품목 수량이 있지만 AI가 한 행으로 합쳤습니다. "
                        "상품별 수량·단가를 각각 확인하세요.")
        return revised, 0
    currency = recovered[0]["currency"]
    total_replaced = 0
    for kind, document in revised.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(document, dict):
            continue
        previous = document.get("items") or []
        if len(previous) >= len(recovered):
            continue
        current_currency = str(document.get("currency") or "").upper().strip()
        if current_currency and current_currency != currency:
            # Explicit source currency differs from the AI proposal: don't
            # silently patch the financial meaning; block until user review.
            document["currency"] = ""
        else:
            document["currency"] = currency
        document["items"] = [
            {k: value for k, value in row.items() if k != "currency"}
            for row in recovered
        ]
        total_replaced = max(total_replaced, len(recovered))
    return revised, total_replaced
