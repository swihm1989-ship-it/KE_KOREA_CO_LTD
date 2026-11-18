"""Human-readable filenames for MASTER PDFs; storage remains UUID-addressed.

Filename components are optional and never serve as a database unique key.
All original document renderers, content and archive UI remain untouched.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

_KINDS={"PI","PO","CI","PL","CONTRACT"}
_MISSING={"", "N/A", "NA", "TBD", "TO_BE_CONFIRMED", "UNKNOWN",
          "NOT PROVIDED", "NONE", "NULL", "DRAFT", "UNCONFIRMED"}


def _part(value, limit=55):
    value=str(value if value is not None else "").strip()
    if value.upper() in _MISSING:
        return ""
    # Windows/macOS download-safe, no path traversal or separators.
    value=re.sub(r'[\\/<>:"|?*\x00-\x1f\x7f]', " ", value)
    value=re.sub(r"\s+", " ", value).strip(" ._-")
    return value[:limit].rstrip(" ._-")


def _company(source, kind):
    if kind=="CONTRACT":
        for item in source.get("parties") or []:
            if not isinstance(item,Mapping):
                continue
            candidate=_part(item.get("legal_name") or item.get("name"))
            if candidate and not _is_ke(candidate):
                return candidate
        return ""
    # PO is procurement: supplier is counterparty. PI/CI/PL are sales.
    roles=("seller","buyer") if kind=="PO" else ("buyer","seller")
    for role in roles:
        party=source.get(role) or {}
        candidate=_part(party.get("legal_name") or party.get("name")) if isinstance(party,Mapping) else ""
        if candidate and not _is_ke(candidate):
            return candidate
    return ""


def _is_ke(company):
    normalized=re.sub(r"[^A-Z0-9가-힣]","",company.upper())
    return ("KEKOREA" in normalized or "케이이코리아" in normalized)


def _item(source):
    entries=[row for row in (source.get("items") or []) if isinstance(row,Mapping)]
    if not entries:
        return ""
    first=entries[0]
    product=_part(first.get("product_name") or first.get("description"),52)
    other=len(entries)-1
    if product and other:
        product += " 외 "+str(other)+"종"
    quantity=_part(first.get("shipped_quantity") or first.get("quantity") or
                   first.get("paid_quantity"),22)
    unit=_part(first.get("unit"),12)
    amount=(quantity+" "+unit).strip()
    if amount:
        return (product+"("+amount+")") if product else "("+amount+")"
    return product


def pdf_filename(kind, source):
    """Optional document number, counterparty, product and quantity.

    The base 'KIND_KE-KOREA' is always present. Repeated document numbers
    are legal because the private archive storage path uses an unrelated UUID.
    """
    kind=str(kind or "").upper()
    if kind not in _KINDS:
        raise ValueError("Unsupported PDF document kind")
    if not isinstance(source,Mapping):
        source={}
    number=_part(source.get("document_number") or source.get("number"),45)
    company=_company(source,kind)
    product=_item(source) if kind!="CONTRACT" else ""
    parts=[kind]
    if number:
        parts.append(number)
    parts.append("KE-KOREA")
    if company:
        parts.append(company)
    if product:
        parts.append(product)
    return "_".join(parts)[:168].rstrip(" ._-")+".pdf"
