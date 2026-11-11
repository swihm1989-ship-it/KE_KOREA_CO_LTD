"""Conservative typo repair for explicit trade field labels only.

Only the label preceding ':' or '=' at the start of a line is repaired.
Never fuzzy-rewrite company names, addresses, numbers or contractual values.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re

LABELS = {
    "buyer": ("buyer", "buyr", "byuer", "buer", "bayer", "byer", "purchaser", "구매자", "매수인"),
    "seller": ("seller", "seler", "sller", "sellr", "vendor", "supplier", "판매자", "매도인"),
    "quantity": ("quantity", "quantiy", "quanity", "qty", "qtty", "수량"),
    "unit_price": ("unit price", "unitprice", "unit prce", "unit_price", "price per pc", "단가"),
    "payment_terms": ("payment terms", "payment term", "paymnt terms", "결제조건", "지급조건"),
    "incoterms": ("incoterms", "incoterm", "incoterms", "delivery terms", "인도조건"),
    "currency": ("currency", "curreny", "통화"),
    "product": ("product", "prodcut", "products", "품목", "제품"),
}
_ALIAS = {alias.casefold(): canonical for canonical, aliases in LABELS.items() for alias in aliases}
_LABEL_LINE = re.compile(r"(?m)^(?P<indent>[ \\t]*)(?P<label>[^\\n:=]{2,36}?)(?P<sep>[ \\t]*[:=][ \\t]*)")
_ASCII_LABEL = re.compile(r"^[A-Za-z][A-Za-z _-]*$")


def canonical_label(label: str) -> str | None:
    key = " ".join(label.strip().casefold().replace("_", " ").replace("-", " ").split())
    if key in _ALIAS:
        return _ALIAS[key]
    # Fuzzy repair only for long, explicit English labels. Short acronyms
    # and unknown labels are intentionally left untouched.
    if len(key) < 5 or not _ASCII_LABEL.fullmatch(key):
        return None
    # Common transposition in explicit quantity labels must not be confused with values.\n    if key in {"quantiy", "quanity"}:\n        return "quantity"\n    scores = sorted(
        ((SequenceMatcher(None, key, alias).ratio(), canonical)
         for alias, canonical in _ALIAS.items()
         if len(alias) >= 5 and _ASCII_LABEL.fullmatch(alias)),
        reverse=True,
    )
    if not scores or scores[0][0] < 0.88:
        return None
    # Never choose between two similarly plausible commercial fields.
    if len(scores) > 1 and scores[1][1] != scores[0][1] and scores[0][0] - scores[1][0] < 0.08:
        return None
    return scores[0][1]


def normalize_trade_labels(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    def replace(match: re.Match[str]) -> str:
        label = canonical_label(match.group("label"))
        if label is None:
            return match.group(0)
        return match.group("indent") + label + match.group("sep")
    return _LABEL_LINE.sub(replace, text)
