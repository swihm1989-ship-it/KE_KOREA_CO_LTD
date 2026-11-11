"""Human-fillable missing facts for AI trade intake; no AI approval or DB writes.

Keys represent shared commercial facts. A correction to any such fact
updates BOTH the PI/PO/CI/PL candidates and the new CONTRACT candidate
in-memory and invalidates generated contract clauses.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class MissingField:
    key: str
    label: str


LABELS = {
    "buyer.legal_name": "Buyer · 구매자 법인명(영문)",
    "buyer.address": "Buyer · 구매자 법인 주소(영문)",
    "buyer.country": "Buyer · 구매자 설립국",
    "seller.legal_name": "Seller · 판매자 법인명(영문)",
    "seller.address": "Seller · 판매자 법인 주소(영문)",
    "seller.country": "Seller · 판매자 설립국",
    "item.product_name": "상품명 및 규격(영문)",
    "item.quantity": "수량(숫자)",
    "item.unit": "수량 단위(PCS, W 등)",
    "item.unit_price": "단가(숫자)",
    "item.price_source": "단가의 확인 가능한 출처",
    "currency": "통화(USD 등)",
    "incoterms": "Incoterms 및 정확한 인도 장소",
    "payment_terms": "결제조건",
    "shipment_reference": "선적 참고번호",
    "country_of_origin": "제품 원산지",
    "item.price_basis": "단가 기준(PCS, W 등)",
}
TERM_MAP = {
    "item.product_name": "products", "item.quantity": "quantity",
    "item.unit": "unit", "item.unit_price": "unit_price",
    "currency": "currency", "incoterms": "delivery",
    "payment_terms": "payment_trigger",
}


def format_field_label(key: str) -> str:
    return LABELS.get(key, key)


def _party(candidate: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    contract = candidate.get("CONTRACT") or {}
    from Quotation_KEKOREA.orchestration.workflows.label_typos import canonical_label
    return next((p for p in contract.get("parties", []) if role in [canonical_label(str(x)) or str(x).casefold() for x in p.get("roles", [])]), {})


def missing_fields(candidates: Mapping[str, Any]) -> tuple[MissingField, ...]:
    """Only missing known fields; never invent or auto-confirm company identity."""
    if not isinstance(candidates, Mapping):
        raise ValueError("입력은 문서별 데이터여야 합니다.")
    trade = [(kind, value) for kind, value in candidates.items()
             if kind in {"PI", "PO", "CI", "PL"} and isinstance(value, Mapping)]
    contract = candidates.get("CONTRACT") or {}
    keys = []
    for role in ("buyer", "seller"):
        role_parties = [_party(candidates, role)] if contract else []
        trade_parties = [data.get(role) or {} for _, data in trade]
        if not (role_parties or trade_parties):
            continue
        for field in ("legal_name", "address", "country"):
            if field == "country" and not contract:
                continue
            values = [str(item.get(field) or "").strip() for item in role_parties + trade_parties
                      if field != "country" or item in role_parties]
            if not any(values):
                keys.append(f"{role}.{field}")
    for key, field in (("item.product_name", "product_name"), ("item.quantity", "quantity"),
                       ("item.unit", "unit"), ("item.unit_price", "unit_price"),
                       ("item.price_basis", "price_basis"), ("item.price_source", "price_source")):
        relevant = [(kind, (data.get("items") or [{}])[0]) for kind, data in trade]
        relevant = [(kind, row) for kind, row in relevant if kind != "PL" or key not in {
            "item.unit_price", "item.price_basis", "item.price_source"
        }]
        if relevant and not any(str(row.get(field) or "").strip() for _, row in relevant):
            keys.append(key)
    for key in ("currency", "incoterms", "payment_terms", "shipment_reference", "country_of_origin"):
        relevant = [(kind, data) for kind, data in trade if (
            key != "payment_terms" or kind in {"PI", "PO"}
        ) and (key != "shipment_reference" or kind in {"CI", "PL"})
            and (key != "country_of_origin" or kind == "CI")
            and (key != "currency" or kind != "PL")]
        if relevant and not any(str(data.get(key) or "").strip() for _, data in relevant):
            keys.append(key)
    # A required contract role can be missing even where no trade document exists.
    return tuple(MissingField(key=key, label=format_field_label(key)) for key in keys)


def apply_answer(candidates: Mapping[str, Any], key: str, value: str) -> dict[str, Any]:
    """Return revised private candidate bundle. All approval/draft state is external.

    This is a user-supplied answer, not an automatic 'confirmed' status.
    Revoke any AI generated clauses whenever facts are revised.
    """
    if key not in LABELS:
        raise ValueError("지원하지 않는 거래조건입니다.")
    if not isinstance(value, str) or not value.strip() or len(value) > 1500:
        raise ValueError("내용을 입력해 주세요 (1~1,500자).")
    text = value.strip()
    if key in {"item.quantity", "item.unit_price"}:
        try:
            number = Decimal(text.replace(",", ""))
            if not number.is_finite() or number <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise ValueError("수량·단가에는 0보다 큰 숫자를 입력해 주세요.") from None
        text = format(number, "f")
    if not isinstance(candidates, Mapping):
        raise ValueError("거래조건이 없습니다.")
    revised = deepcopy(dict(candidates))
    for kind, doc in revised.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(doc, dict):
            continue
        if "." in key:
            group, field = key.split(".", 1)
            if group in {"buyer", "seller"}:
                if field != "country":
                    doc.setdefault(group, {})[field] = text
            elif group == "item":
                items = doc.setdefault("items", [{}])
                if not items:
                    items.append({})
                items[0][field] = text
        else:
            doc[key] = text
    contract = revised.get("CONTRACT")
    if isinstance(contract, dict):
        # Cannot reuse a previously AI-drafted clause after business conditions change.
        contract["clauses"] = []
        if key.startswith(("buyer.", "seller.")):
            role, field = key.split(".", 1)
            parties = contract.setdefault("parties", [])
            party = next((p for p in parties if role in p.get("roles", [])), None)
            if party is None:
                party = {"roles": [role], "legal_name": "", "country": "", "address": "",
                         "status": "suggested", "source_refs": []}
                parties.append(party)
            party[field] = text
            party["status"] = "suggested"
        elif key in TERM_MAP:
            term_key = TERM_MAP[key]
            terms = contract.setdefault("terms", [])
            term = next((t for t in terms if t.get("key") == term_key), None)
            if term is None:
                term = {"key": term_key, "status": "suggested", "source_refs": []}
                terms.append(term)
            term["value"] = text
            term["status"] = "suggested"
    return revised
