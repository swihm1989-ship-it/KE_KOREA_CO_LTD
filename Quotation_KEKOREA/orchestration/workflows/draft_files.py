"""Review-only file generation. No mail, signatures, storage or FINAL export.

Trade PDFs are deliberately unavailable: the existing branded PDF renderer
requires a verified company seal and its authorization workflow. Trade DOCX
is an independent, visibly provisional review worksheet generated from the
existing deterministic trade engine's validated quantities/prices.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from typing import Any, Mapping
import re

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
KINDS = {"PI", "PO", "CI", "PL", "CONTRACT"}


def _safe_file_stem(value: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value))[:75].strip("_")
    return stem or "Document"


def _asset(content: bytes, filename: str, mime: str) -> dict[str, Any]:
    return {"filename": filename, "content": content, "mime": mime,
            "sha256": sha256(content).hexdigest(), "final": False, "sendable": False}


def _trade_docx(calculated: Mapping[str, Any]) -> bytes:
    """Create an unsigned, unbranded review sheet (not a trade document for issue)."""
    from docx import Document
    from docx.shared import Pt
    document = Document()
    document.core_properties.title = "DRAFT - NOT FOR ISSUE"
    section = document.sections[0]
    section.header.paragraphs[0].text = "DRAFT / INTERNAL REVIEW ONLY - NOT FOR ISSUE"
    document.add_heading(f"{calculated['document_type']} - DRAFT", level=0)
    document.add_paragraph("Internal review worksheet. Not an invoice, signature or payment demand.")
    for party in ("seller", "buyer"):
        value = calculated.get(party) or {}
        document.add_heading(party.upper(), level=2)
        document.add_paragraph(str(value.get("legal_name") or ""))
        document.add_paragraph(str(value.get("address") or ""))
    for field, label in (("document_number", "Number"),
                         ("issue_date", "Issue date"),
                         ("incoterms", "Delivery terms"),
                         ("payment_terms", "Payment terms"),
                         ("shipment_reference", "Shipment reference"),
                         ("country_of_origin", "Origin")):
        if calculated.get(field):
            document.add_paragraph(f"{label}: {calculated[field]}")
    table = document.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    for idx, label in enumerate(("Product", "Quantity", "Unit", "Unit price", "Line total")):
        table.rows[0].cells[idx].text = label
    for item in calculated.get("items", []):
        cells = table.add_row().cells
        values = (
            item.get("product_name"), item.get("display_quantity"),
            item.get("unit"), item.get("final_unit_price"), item.get("line_total"),
        )
        for idx, value in enumerate(values):
            cells[idx].text = str(value if value is not None else "")
    document.add_paragraph(f"TOTAL: {calculated.get('currency') or ''} {calculated.get('total') or ''}")
    document.add_paragraph("DRAFT - NO COMPANY SEAL - NOT APPROVED - NOT SENDABLE")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def create_review_files(kind: str, source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Generate unapproved drafts from actual previously authored/validated data.

    Contract: call the EXISTING contracts.draft_exports.export_draft only.
    Trade: use EXISTING calculate/validate engine, require zero blockers, then
    produce a non-branded DRAFT DOCX. No trade PDF or finalization.
    """
    if not isinstance(source, Mapping):
        raise ValueError("Source must be a JSON object")
    kind = str(kind).strip().upper()
    if kind not in KINDS:
        raise ValueError("Unsupported document kind")
    data = deepcopy(dict(source))

    if kind == "CONTRACT":
        from Quotation_KEKOREA.contracts.draft_exports import export_draft
        exported = export_draft(data, formats=("docx", "pdf"), env={})
        output = {}
        for extension, item in exported.items():
            payload = item["content"]
            output[extension] = _asset(
                payload, item["filename"], DOCX_MIME if extension == "docx" else PDF_MIME
            )
        return output

    if "document_type" in data and str(data["document_type"]).strip().upper() != kind:
        raise ValueError("Document type does not match requested kind")
    data["document_type"] = kind
    data.pop("ready_for_issue", None)
    data.pop("status", None)
    from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
    validated = validate_and_calculate(data)
    blockers = validated.get("blocking_issues") or []
    if blockers or not validated.get("ready_for_issue"):
        raise ValueError("Trade details require confirmation: " + "; ".join(map(str, blockers[:8])))
    payload = _trade_docx(validated)
    return {"docx": _asset(payload, _safe_file_stem(kind) + "-DRAFT.docx", DOCX_MIME)}
