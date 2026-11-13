"""MASTER-side adapter to the EXISTING trade-document renderer.

The default remains a strict draft; a revision-bound explicit approval enables
FINAL in the existing layout with verified company assets and no automatic send.
"""
from __future__ import annotations

from Quotation_KEKOREA.observability.core import traced
from hashlib import sha256
import importlib
from inspect import signature
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from Quotation_KEKOREA.agent.branding import resolve_company_seal
from Quotation_KEKOREA.agent.renderers import render_files
from Quotation_KEKOREA.agent.ci_import import ci_render_data, ci_import_issues
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
from Quotation_KEKOREA.agent.review_fields import missing_review_fields
from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values

REVIEW_EXPORT_REVISION = "review-pdf-safe-loader-20261113-v4"

TRADE_KINDS = frozenset({"PI", "PO", "CI", "PL"})
BANK_KEYS = ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")
MIMES = {"pdf": "application/pdf",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "html": "text/html"}


_BOUND_RENDER_FILES = render_files


def _ensure_trade_renderers_current():
    """Refresh the two shared renderer dependencies in order after hot deploys."""
    global render_files, _BOUND_RENDER_FILES
    revision = 'approved-blank-final-20261113-v1'
    shared = importlib.import_module('Quotation_KEKOREA.agent.renderers')
    def compatible(module, marker, function):
        try:
            return (getattr(module, marker, None) == revision
                    and 'final' in signature(getattr(module, function)).parameters)
        except (AttributeError, TypeError, ValueError):
            return False
    refreshed = (not compatible(shared, 'TRADE_RENDERER_REVISION', 'render_files')
                 or any(not callable(getattr(shared, helper, None)) for helper in (
                     '_display_value', '_final_number', '_final_packing_totals', '_final_quantities')))
    if refreshed:
        importlib.invalidate_caches()
        shared = importlib.reload(shared)
    pdf = importlib.import_module('Quotation_KEKOREA.agent.pi_pdf')
    if refreshed or not compatible(pdf, 'TRADE_PDF_REVISION', 'render_trade_document'):
        importlib.invalidate_caches()
        pdf = importlib.reload(pdf)
    if (not compatible(shared, 'TRADE_RENDERER_REVISION', 'render_files')
            or not compatible(pdf, 'TRADE_PDF_REVISION', 'render_trade_document')):
        raise RuntimeError('최종 PDF 출력 모듈 버전이 일치하지 않습니다. 앱을 재시작한 후 다시 시도하세요.')
    if render_files is _BOUND_RENDER_FILES:
        render_files = shared.render_files
        _BOUND_RENDER_FILES = render_files


@traced('document.generate', kind_argument=True)
def render_master_trade_draft(kind: str, source: Mapping, env: Mapping[str, str]) -> dict:
    return _render_master_trade(kind, source, env)


@traced('document.generate', kind_argument=True)
def render_master_trade_final(kind: str, source: Mapping, env: Mapping[str, str], *,
                              approved=False, expected_fingerprint=None,
                              allow_optional_na=False, allow_incomplete=False) -> dict:
    # Retained Streamlit sessions may reload the review module independently.
    from .trade_export_review import review_trade_document, trade_export_fingerprint, TradeExportValidationError
    if approved is not True:
        raise ValueError('최종 PDF 생성에 대한 사용자 승인이 필요합니다.')
    current = trade_export_fingerprint(kind, source, allow_optional_na=allow_optional_na,
                                       allow_incomplete=allow_incomplete)
    if expected_fingerprint != current:
        raise ValueError('승인 후 문서 내용이 변경되었습니다. 다시 확인하고 승인하세요.')
    report = review_trade_document(kind, source, final=True, allow_optional_na=allow_optional_na,
                                    allow_incomplete=allow_incomplete)
    if report['issues']:
        raise TradeExportValidationError(report['issues'])
    return _render_master_trade(kind, report['candidate'], env, final=True,
                                reviewed=report if allow_incomplete is True else None)


def _render_master_trade(kind: str, source: Mapping, env: Mapping[str, str], *, final=False,
                         reviewed=None) -> dict:
    """Generate PDF/XLSX/HTML through the legacy layout and verified assets.

    The branded PDF requires the *original verified* KE KOREA seal. Strict PI
    drafts require the complete USD bank profile; approved incomplete finals
    preserve missing bank fields as blanks.
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
    if final and reviewed is not None:
        checked = reviewed['render_data']
    else:
        checked = validate_and_calculate(candidate)
        blockers = list(checked.get("blocking_issues") or [])
        if kind == "CI":
            blockers.extend(ci_import_issues(checked))
        if blockers or not checked.get("ready_for_issue"):
            raise ValueError("거래조건을 먼저 보완하세요: " + "; ".join(map(str, blockers[:8])))
        pending = missing_review_fields(candidate)
        if pending:
            raise ValueError("문서 생성 전 누락 정보 입력: " + "; ".join(field.label for field in pending))
    bank = {key: str(env.get("KEKOREA_USD_" + key) or "").strip() for key in BANK_KEYS}
    if kind == "PI" and reviewed is None and any(not value for value in bank.values()):
        raise ValueError("기존 업무 에이전트와 동일하게 PI 은행정보 6개 항목이 모두 필요합니다.")
    root = Path(__file__).resolve().parents[2]
    seal_path, seal_bytes, error = resolve_company_seal(root, env)
    if seal_bytes is None and not seal_path.is_file():
        raise ValueError("검증된 KE KOREA 회사 직인이 필요합니다: " + str(error or "설정 없음"))
    prepared = checked
    checked = ci_render_data(checked)
    if final and reviewed is not None and kind == 'CI':
        # The old CI adapter removes payment/bank details and supplies default
        # N/A/zero values. Keep its redaction/FOC behavior but preserve reviewed
        # unknown facts on the explicitly approved blank-output path.
        if checked.get('payment_terms') != prepared.get('payment_terms'):
            checked['payment_terms'] = ''
        if checked.get('remarks') != prepared.get('remarks'):
            checked['remarks'] = ''
        for original, row in zip(prepared.get('items') or [], checked.get('items') or []):
            if original.get('discount_percent') is None:
                row['discount_percent'] = None
    with TemporaryDirectory(prefix="ke-master-doc-") as directory:
        actual_seal = seal_path
        if seal_bytes is not None:
            actual_seal = Path(directory) / "company_seal.png"
            actual_seal.write_bytes(seal_bytes)
        # Match the original KE KOREA app: pass the very same logo and seal
        # locations to the unmodified shared PI/PO/CI/PL PDF/XLSX renderer.
        logo_path = root / "assets" / "company_logo.png"
        _ensure_trade_renderers_current()
        paths = render_files(checked, Path(directory) / "outputs",
                             bank_details=bank, logo_path=logo_path,
                             seal_path=actual_seal, **({"final": True} if final else {}))
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
                "final": bool(final),
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
        line("Tel: " + stated(party.get("phone")))
        line("Email: " + stated(party.get("email")))
        line("Representative: " + stated(party.get("contact")))
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
