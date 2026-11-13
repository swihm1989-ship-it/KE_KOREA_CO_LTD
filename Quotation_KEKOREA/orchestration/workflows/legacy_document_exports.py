"""MASTER-side adapter to the EXISTING trade-document renderer.

This does not issue final documents or change the legacy app. The existing
validation, seal resolver, PDF pagination and XLSX layout are reused unchanged.
"""
from __future__ import annotations

from Quotation_KEKOREA.observability.core import traced
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from Quotation_KEKOREA.agent.branding import resolve_company_seal
from Quotation_KEKOREA.agent.ci_import import ci_render_data, ci_import_issues
from Quotation_KEKOREA.agent.renderers import render_files
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values

REVIEW_EXPORT_REVISION = "review-pdf-safe-loader-20261113-v1"

TRADE_KINDS = frozenset({"PI", "PO", "CI", "PL"})
BANK_KEYS = ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")
MIMES = {"pdf": "application/pdf",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "html": "text/html"}


@traced('document.generate', kind_argument=True)
def render_master_trade_draft(kind: str, source: Mapping, env: Mapping[str, str]) -> dict:
    """Generate PDF/XLSX/HTML via the legacy engine, fail closed on missing inputs.

    The branded PDF requires the *original verified* KE KOREA seal. The PI
    additionally requires the same complete USD bank profile as the old app.
    """
    kind = str(kind).upper()
    if kind not in TRADE_KINDS:
        raise ValueError("Only PI, PO, CI and PL are supported")
    if not isinstance(source, Mapping):
        raise ValueError("Trade candidate must be a mapping")
    candidate = normalize_trade_values(source)
    if candidate.get("document_type") and str(candidate["document_type"]).upper() != kind:
        raise ValueError("Document type mismatch")
    candidate["document_type"] = kind
    candidate.pop("ready_for_issue", None)
    candidate.pop("status", None)
    checked = validate_and_calculate(candidate)
    blockers = list(checked.get("blocking_issues") or [])
    if kind == "CI":
        blockers.extend(ci_import_issues(checked))
    if blockers or not checked.get("ready_for_issue"):
        raise ValueError("거래조건을 먼저 보완하세요: " + "; ".join(map(str, blockers[:8])))
    bank = {key: str(env.get("KEKOREA_USD_" + key) or "").strip() for key in BANK_KEYS}
    if kind == "PI" and any(not value for value in bank.values()):
        raise ValueError("기존 업무 에이전트와 동일하게 PI 은행정보 6개 항목이 모두 필요합니다.")
    root = Path(__file__).resolve().parents[2]
    seal_path, seal_bytes, error = resolve_company_seal(root, env)
    if seal_bytes is None and not seal_path.is_file():
        raise ValueError("검증된 KE KOREA 회사 직인이 필요합니다: " + str(error or "설정 없음"))
    checked = ci_render_data(checked)
    with TemporaryDirectory(prefix="ke-master-doc-") as directory:
        actual_seal = seal_path
        if seal_bytes is not None:
            actual_seal = Path(directory) / "company_seal.png"
            actual_seal.write_bytes(seal_bytes)
        # Match the original KE KOREA app: pass the very same logo and seal
        # locations to the unmodified shared PI/PO/CI/PL PDF/XLSX renderer.
        logo_path = root / "assets" / "company_logo.png"
        paths = render_files(checked, Path(directory) / "outputs",
                             bank_details=bank, logo_path=logo_path,
                             seal_path=actual_seal)
        result = {}
        for extension in ("pdf", "xlsx", "html"):
            path = paths[extension]
            data = path.read_bytes()
            if not data:
                raise ValueError("생성된 파일이 비어 있습니다.")
            result[extension] = {
                "filename": path.name,
                "content": data,
                "mime": MIMES[extension],
                "sha256": sha256(data).hexdigest(),
                "final": False,
                "sendable": False,
            }
    return result


def render_incomplete_trade_pdf(kind: str, source: Mapping) -> dict:
    """Generate an unsealed review PDF even with unknown commercial fields.

    This is intentionally NOT a fallback for FINAL issue. The original
    branded/sealed renderer, bank checks and strict validation are unchanged.
    Never invent a legal name, shipping term, amount or bank detail.
    """
    from decimal import Decimal, InvalidOperation
    from io import BytesIO
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    from Quotation_KEKOREA.agent.trade_documents import current_issue_date

    kind = str(kind).upper()
    if kind not in TRADE_KINDS or not isinstance(source, Mapping):
        raise ValueError("Unsupported trade review request")
    if source.get("document_type") and str(source["document_type"]).upper() != kind:
        raise ValueError("Document type mismatch")
    doc = normalize_trade_values(source)
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    buffer = BytesIO()
    paper = canvas.Canvas(buffer, pagesize=(595, 842), pageCompression=1)
    paper.setTitle(kind + " - INCOMPLETE DRAFT / NOT FOR ISSUE")
    navy = (0.055, 0.20, 0.35)
    grey = (0.40, 0.47, 0.53)
    y = 780
    page = 1

    def footer():
        paper.setFillColorRGB(*grey)
        paper.setFont("Helvetica", 8)
        paper.drawString(40, 29, "INTERNAL REVIEW ONLY - NOT FOR ISSUE / NO SEAL / NOT APPROVED")
        paper.drawRightString(555, 29, "PAGE " + str(page))

    def next_page():
        nonlocal y, page
        footer()
        paper.showPage()
        page += 1
        y = 788

    def line(text, *, size=10, heading=False, spacing=7):
        nonlocal y
        value = str(text if text is not None else "").replace("\r", " ").replace("\t", " ")
        # CID font can display Korean/Chinese, but no emoji or control glyphs.
        value = "".join(ch if (ch == "\n" or 32 <= ord(ch) <= 0xFFFF) else "?" for ch in value)
        font = "HYSMyeongJo-Medium" if any(ord(ch) > 127 for ch in value) else (
            "Helvetica-Bold" if heading else "Helvetica")
        chunks = []
        for paragraph in value.split("\n"):
            if not paragraph:
                chunks.append("")
                continue
            segment = ""
            for char in paragraph:
                proposal = segment + char
                if segment and pdfmetrics.stringWidth(proposal, font, size) > 510:
                    chunks.append(segment)
                    segment = char
                else:
                    segment = proposal
            if segment:
                chunks.append(segment)
        for chunk in chunks or [""]:
            if y < 65:
                next_page()
            paper.setFillColorRGB(*(navy if heading else grey if chunk == "NOT PROVIDED" else (0.13, 0.18, 0.23)))
            paper.setFont(font, size)
            paper.drawString(40, y, chunk)
            y -= size + spacing

    def stated(value):
        text = str(value).strip() if value is not None else ""
        return text if text else "NOT PROVIDED"

    def amount(value):
        try:
            number = Decimal(str(value).replace(",", ""))
            return number if number.is_finite() and number >= 0 else None
        except (InvalidOperation, ValueError, TypeError):
            return None

    paper.setFillColorRGB(*navy)
    paper.rect(0, 802, 595, 40, stroke=0, fill=1)
    paper.setFillColorRGB(1, 1, 1)
    paper.setFont("Helvetica-Bold", 14)
    paper.drawString(40, 814, "KE KOREA  /  DOCUMENT REVIEW")
    line(kind + " - DRAFT (UNCONFIRMED)", size=17, heading=True)
    line("This is a generated PDF file for review, NOT a final issued document.")
    line("Unknown and conflicting terms are not considered approved.", spacing=10)
    line("Document No.: " + stated(doc.get("document_number")))
    line("Prepared: " + current_issue_date())
    for role in ("seller", "buyer"):
        party = doc.get(role) or {}
        line(role.upper(), size=12, heading=True)
        line("Legal name: " + stated(party.get("legal_name")))
        line("Address: " + stated(party.get("address")))
    line("COMMERCIAL TERMS", size=12, heading=True)
    for label, key in (("Currency", "currency"), ("Delivery", "incoterms"),
                       ("Payment", "payment_terms"), ("Shipment reference", "shipment_reference"),
                       ("Country of origin", "country_of_origin")):
        if key == "payment_terms" and kind not in {"PI", "PO"}:
            continue
        line(label + ": " + stated(doc.get(key)))

    line("PRODUCT / QUANTITY / PRICE", size=12, heading=True)
    running = Decimal("0")
    amounts_complete = bool(doc.get("items"))
    for number, item in enumerate(doc.get("items") or [], 1):
        if not isinstance(item, Mapping):
            item = {}
        line("Item " + str(number) + ": " + stated(item.get("product_name")), heading=True)
        qty, unit_price = amount(item.get("quantity")), amount(item.get("unit_price"))
        line("Quantity: " + stated(item.get("quantity")) + " " + stated(item.get("unit")))
        if kind != "PL":
            line("Unit price: " + stated(item.get("unit_price")) + " / " +
                 stated(item.get("price_basis")))
            try:
                discount = Decimal(str(item.get("discount_percent") or "0"))
                has_adjustments = bool(item.get("promotion")) or discount != 0
            except (InvalidOperation, TypeError, ValueError):
                has_adjustments = True
            if qty is None or unit_price is None or unit_price == 0 or has_adjustments:
                amounts_complete = False
                line("Line amount: NOT PROVIDED (unconfirmed price, quantity or discount)")
            else:
                line("Indicative line amount: " + str(qty * unit_price))
                running += qty * unit_price
        else:
            line("Packages: " + stated(item.get("package_count")) +
                 "  Net/Gross (KG): " + stated(item.get("net_weight_kg")) +
                 " / " + stated(item.get("gross_weight_kg")))
    if kind != "PL":
        if amounts_complete and str(doc.get("currency") or "").strip():
            line("INDICATIVE TOTAL: " + stated(doc.get("currency")) + " " + str(running),
                 size=12, heading=True)
        else:
            line("TOTAL: NOT PROVIDED - DO NOT ASSUME ZERO", size=12, heading=True)

    concerns = list(doc.get("conflicts") or []) + list(doc.get("missing_fields") or [])
    # Preserve uncertainty as a status, never a fictional populated value.
    line("OPEN ITEMS / REVIEW", size=12, heading=True)
    if concerns:
        for item in concerns[:30]:
            line("- " + str(item))
    else:
        line("Confirm counterparty, payment and other fields against originals.")
    line("No company seal, bank authorization, SMTP sending or FINAL approval.")
    footer()
    paper.save()
    payload = buffer.getvalue()
    if not payload.startswith(b"%PDF") or len(payload) < 300:
        raise ValueError("Draft PDF was not generated")
    return {"pdf": {
        "filename": kind + "-INCOMPLETE-DRAFT.pdf",
        "content": payload,
        "mime": "application/pdf",
        "sha256": sha256(payload).hexdigest(),
        "final": False, "sendable": False,
        "review_only": True,
    }}
