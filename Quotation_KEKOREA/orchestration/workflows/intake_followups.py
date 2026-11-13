"""Human-fillable missing facts for AI trade intake; no AI approval or DB writes.

Keys represent shared commercial facts. A correction to any such fact
updates BOTH the PI/PO/CI/PL candidates and the new CONTRACT candidate
in-memory and invalidates generated contract clauses.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values
from typing import Any, Mapping
from Quotation_KEKOREA.agent.review_fields import missing_review_fields, _missing

FOLLOWUP_REVISION = "visible-document-fields-20261113-v1"


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
    "buyer.contact": "Buyer · 담당자 / 대표자(선택 · 해당 없으면 N/A)",
    "buyer.phone": "Buyer · 전화번호(선택 · 해당 없으면 N/A)",
    "buyer.email": "Buyer · 이메일(선택 · 해당 없으면 N/A)",
    "seller.contact": "Seller · 담당자 / 대표자(선택 · 해당 없으면 N/A)",
    "seller.phone": "Seller · 전화번호(선택 · 해당 없으면 N/A)",
    "seller.email": "Seller · 이메일(선택 · 해당 없으면 N/A)",
    "ship_to": "배송지(추정하지 않음 · 해당 없으면 N/A)",
    "container_count": "컨테이너 수(컨테이너 운송이 아니면 0)",
    "item.discount_percent": "할인율 %(할인이 없으면 0)",
    "item.product_name": "상품명 및 규격(영문)",
    "item.quantity": "수량(숫자)",
    "item.unit": "수량 단위(PCS, W 등)",
    "item.unit_price": "단가(숫자)",
    "item.price_source": "단가의 확인 가능한 출처",
    "currency": "통화(USD 등)",
    "document_number": "문서번호 (미확정 시 DRAFT)",
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
    if key.startswith("item.") and len(key.split(".")) == 3:
        _, index, field = key.split(".")
        return "상품 " + str(int(index) + 1) + " · " + LABELS.get("item." + field, field)
    return LABELS.get(key, key)


def _party(candidate: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    contract = candidate.get("CONTRACT") or {}
    from Quotation_KEKOREA.orchestration.workflows.label_typos import canonical_label
    return next((p for p in contract.get("parties", []) if role in [canonical_label(str(x)) or str(x).casefold() for x in p.get("roles", [])]), {})


def missing_fields(candidates: Mapping[str, Any]) -> tuple[MissingField, ...]:
    """Only missing known fields; never invent or auto-confirm company identity."""
    if not isinstance(candidates, Mapping):
        raise ValueError("입력은 문서별 데이터여야 합니다.")
    trade = [(kind, normalize_trade_values(value)) for kind, value in candidates.items()
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
            if not values or any(_missing(value, True) for value in values):
                keys.append(f"{role}.{field}")
    for key, field in (("item.product_name", "product_name"), ("item.quantity", "quantity"),
                       ("item.unit", "unit"), ("item.unit_price", "unit_price"),
                       ("item.price_basis", "price_basis")):
        relevant = [(kind, (data.get("items") or [{}])[0]) for kind, data in trade]
        relevant = [(kind, row) for kind, row in relevant if kind != "PL" or key not in {
            "item.unit_price", "item.price_basis", "item.price_source"
        }]
        if relevant and not any(str(row.get(field) if row.get(field) is not None else "").strip() for _, row in relevant):
            keys.append(key)
    for key in ("currency", "incoterms", "payment_terms", "shipment_reference", "country_of_origin"):
        relevant = [(kind, data) for kind, data in trade if (
            key != "payment_terms" or kind in {"PI", "PO"}
        ) and (key != "shipment_reference" or kind in {"CI", "PL"})
            and (key != "country_of_origin" or kind == "CI")
            and (key != "currency" or kind != "PL")]
        if relevant and not any(str(data.get(key) or "").strip() for _, data in relevant):
            keys.append(key)
    if contract and not trade and contract.get("contract_type") == "sale":
        terms = {term.get("key"): term.get("value") for term in contract.get("terms", [])}
        for key in ("item.product_name", "item.quantity", "item.unit", "item.unit_price", "currency"):
            value = terms.get(TERM_MAP[key])
            if value is None or not str(value).strip():
                keys.append(key)
    # Use the original app's visible-field review, including optional values
    # that require an explicit N/A. One completed document cannot hide another's gap.
    for kind, data in trade:
        data["document_type"] = kind
        for field in missing_review_fields(data):
            path = field.path
            if path[0] == "items":
                key = ("item." + str(path[1]) + "." + path[2]
                       if path[1] else "item." + path[2])
            else:
                key = ".".join(path)
            keys.append(key)
    return tuple(MissingField(key=key, label=format_field_label(key))
                 for key in dict.fromkeys(keys))


def _apply_scoped_contact(candidates, kind, role, field, value, *, allow_blank):
    """Update contacts for the same named company, even across PO/PI roles."""
    if not isinstance(candidates, Mapping) or not isinstance(candidates.get(kind), Mapping):
        raise ValueError("연락처를 수정할 문서가 없습니다.")
    revised = deepcopy(dict(candidates))
    selected = normalize_trade_values(revised[kind])[role]
    identity = str(selected.get("legal_name") or "").strip().casefold()
    identified = not _missing(identity, True)
    for doc_kind, doc in list(revised.items()):
        if doc_kind not in {"PI", "PO", "CI", "PL"} or not isinstance(doc, Mapping):
            continue
        doc = normalize_trade_values(doc)
        for doc_role in ("buyer", "seller"):
            name = str(doc[doc_role].get("legal_name") or "").strip().casefold()
            if ((identified and name == identity) or (doc_kind == kind and doc_role == role)):
                doc = apply_answer({doc_kind: doc}, doc_role + "." + field,
                                   value, allow_blank=allow_blank)[doc_kind]
        revised[doc_kind] = doc
    contract = revised.get("CONTRACT")
    if isinstance(contract, dict):
        contract["clauses"] = []
        for party in contract.get("parties") or []:
            name = str(party.get("legal_name") or "").strip().casefold()
            if identified and name == identity:
                party["representative" if field == "contact" else field] = value.strip()
                party["status"] = "suggested"
    return revised


def apply_answer(candidates: Mapping[str, Any], key: str, value: str, *, allow_blank: bool = False) -> dict[str, Any]:
    """Return revised private candidate bundle. All approval/draft state is external.

    This is a user-supplied answer, not an automatic 'confirmed' status.
    Revoke any AI generated clauses whenever facts are revised.
    """
    parts = key.split(".")
    if (len(parts) == 3 and parts[0] in {"PI", "PO", "CI", "PL"}
            and parts[1] in {"buyer", "seller"} and parts[2] in {"contact", "phone", "email"}):
        return _apply_scoped_contact(candidates, *parts, value, allow_blank=allow_blank)
    item_index = 0
    base_key = key
    if len(parts) == 3 and parts[0] == "item" and parts[1].isdigit():
        item_index = int(parts[1])
        base_key = "item." + parts[2]
    if base_key not in LABELS:
        raise ValueError("지원하지 않는 거래조건입니다.")
    if not isinstance(value, str) or len(value) > 1500 or (not allow_blank and not value.strip()):
        raise ValueError("내용을 입력해 주세요 (1~1,500자).")
    text = value.strip()
    if text and base_key in {"item.quantity", "item.unit_price", "item.discount_percent", "container_count"}:
        try:
            number = Decimal(text.replace(",", ""))
            if not number.is_finite() or number < 0 or (base_key == "item.unit_price" and number == 0) or (base_key == "item.discount_percent" and number > 100):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise ValueError("수량·컨테이너 수는 0 이상, 단가는 0 초과, 할인율은 0~100의 숫자로 입력해 주세요.") from None
        text = format(number, "f")
    if not isinstance(candidates, Mapping):
        raise ValueError("거래조건이 없습니다.")
    revised = deepcopy(dict(candidates))
    for kind, doc in revised.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(doc, dict):
            continue
        # Keep legacy scalar party shapes from breaking the one-field editor.
        doc = normalize_trade_values(doc)
        revised[kind] = doc
        if "." in base_key:
            group, field = base_key.split(".", 1)
            if group in {"buyer", "seller"}:
                if field != "country":
                    doc.setdefault(group, {})[field] = text
            elif group == "item":
                items = doc.setdefault("items", [{}])
                if not items:
                    items.append({})
                if item_index >= len(items):
                    continue
                items[item_index][field] = text
                if field=='quantity':
                    if text:
                        from .mail_trade_normalization import apply_quantity_edit
                        apply_quantity_edit(items[item_index],text)
                    else:
                        # A cleared source quantity must not leave a hidden,
                        # stale paid/shipped value that could price a draft.
                        for calculated in ("paid_quantity", "shipped_quantity", "display_quantity"):
                            items[item_index].pop(calculated, None)
        else:
            doc[key] = text
        from .mail_trade_normalization import resolve_notice_for_answer
        if text:
            resolve_notice_for_answer(doc,key)
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
            party["representative" if field == "contact" else field] = text
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


def acknowledge_prior_source_notice(candidates: Mapping[str, Any], kind: str,
                                    category: str, index: int,
                                    expected: str) -> dict[str, Any]:
    """Manually resolve ONLY the matching historical AI note for one document.

    This does not waive validation of missing required fields, bank settings,
    seals, calculations or document approval. Stale button clicks do nothing.
    """
    if (kind not in {"PI", "PO", "CI", "PL"} or
            category not in {"missing_fields", "conflicts"} or
            not isinstance(index, int) or index < 0 or
            not isinstance(candidates, Mapping)):
        raise ValueError("확인 항목이 유효하지 않습니다.")
    revised = deepcopy(dict(candidates))
    doc = revised.get(kind)
    if not isinstance(doc, dict):
        raise ValueError("확인할 문서 후보가 없습니다.")
    notes = doc.get(category)
    if not isinstance(notes, list) or index >= len(notes):
        raise ValueError("검토 항목이 변경되었습니다. 다시 확인하세요.")
    if not isinstance(notes[index], str) or notes[index] != expected:
        raise ValueError("검토 항목이 변경되었습니다. 다시 확인하세요.")
    notes.pop(index)
    return revised
