"""Read-only DRAFT document preview sourced from existing KE KOREA validators.

Never exports PDF, saves revisions, accepts approvals, reads mailbox, or sends.
The existing trade PDF renderer requires a protected company seal; this module
intentionally does not invoke it or work around that requirement.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DocumentPreview:
    kind: str
    title: str
    status: str
    watermark: str
    blockers: tuple[str, ...]
    parties: tuple[dict[str, str], ...] = ()
    terms: tuple[dict[str, str], ...] = ()
    items: tuple[dict[str, str], ...] = ()
    clauses: tuple[dict[str, Any], ...] = ()
    currency: str = ""
    total: str = ""
    final: bool = False


def _plain(value: Any) -> str:
    return str(value) if value is not None else ""


def build_preview(kind: str, source: Mapping[str, Any]) -> DocumentPreview:
    """Return a human-readable draft derived from existing deterministic engines.

    This deliberately does not invoke AI generation, commit snapshots, expose
    company seals, or grant approval/finalization.
    """
    if not isinstance(source, Mapping):
        raise ValueError("A JSON object is required")
    kind = str(kind).strip().upper()
    if kind not in {"PO", "PI", "CI", "PL", "CONTRACT"}:
        raise ValueError("Unsupported document type")
    data = deepcopy(dict(source))
    if kind == "CONTRACT":
        from Quotation_KEKOREA.contracts.models import validate_snapshot as validate_model
        from Quotation_KEKOREA.contracts.rules import validate_snapshot as validate_rules
        valid = validate_model(data)
        issues = validate_rules(valid, for_export=True, env={})
        blockers = tuple(
            _plain(issue.get("message") or issue.get("code")) if isinstance(issue, dict) else _plain(issue)
            for issue in issues
        )
        clauses = tuple({
            "title": _plain(clause.get("title")),
            "sentences": [_plain(s.get("text")) for s in clause.get("sentences", [])],
        } for clause in sorted(valid.get("clauses", []), key=lambda c: c.get("order", 0)))
        if not any(clause["sentences"] for clause in clauses):
            blockers += ("실제로 작성된 계약서 조항이 필요합니다.",)
        parties = tuple({
            "name": _plain(p.get("legal_name")),
            "role": ", ".join(p.get("roles", [])),
            "country": _plain(p.get("country")),
            "address": _plain(p.get("address")),
        } for p in valid.get("parties", []))
        terms = tuple({
            "term": _plain(t.get("key")), "value": _plain(t.get("value")),
            "status": _plain(t.get("status")),
        } for t in valid.get("terms", []))
        return DocumentPreview(
            kind=kind,
            title=_plain(valid.get("title")) or "Contract",
            status="needs_input" if blockers else "awaiting_document_approval",
            watermark="DRAFT - FOR REVIEW ONLY / NOT FOR SIGNATURE",
            blockers=blockers, parties=parties, terms=terms, clauses=clauses,
        )

    if "document_type" in data and str(data["document_type"]).strip().upper() != kind:
        raise ValueError("Document type does not match requested preview")
    data["document_type"] = kind
    data.pop("status", None)
    data.pop("ready_for_issue", None)
    from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
    calculated = validate_and_calculate(data)
    blockers = tuple(_plain(x) for x in calculated.get("blocking_issues", []) if _plain(x).strip())
    party_rows = tuple({
        "role": role.upper(),
        "name": _plain((calculated.get(role) or {}).get("legal_name")),
        "address": _plain((calculated.get(role) or {}).get("address")),
    } for role in ("seller", "buyer"))
    term_rows = tuple({"term": key, "value": _plain(calculated.get(key))}
                      for key in ("document_number", "issue_date", "incoterms",
                                  "payment_terms", "shipment_reference", "country_of_origin")
                      if calculated.get(key) is not None)
    item_rows = tuple({
        "name": _plain(item.get("product_name")),
        "quantity": _plain(item.get("display_quantity", item.get("quantity"))),
        "unit": _plain(item.get("unit")),
        "unit_price": _plain(item.get("final_unit_price", item.get("unit_price"))),
        "line_total": _plain(item.get("line_total")),
    } for item in calculated.get("items", []))
    return DocumentPreview(
        kind=kind, title={"PO":"Purchase Order", "PI":"Proforma Invoice",
                         "CI":"Commercial Invoice", "PL":"Packing List"}[kind],
        status="needs_input" if blockers else "awaiting_document_approval",
        watermark="DRAFT - NOT FOR ISSUE",
        blockers=blockers, parties=party_rows, terms=term_rows,
        items=item_rows, total=_plain(calculated.get("total")),
        currency=_plain(calculated.get("currency")),
    )
