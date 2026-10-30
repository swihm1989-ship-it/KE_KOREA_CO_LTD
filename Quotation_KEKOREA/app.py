"""Streamlit interface for KE KOREA trade-document drafts."""
import base64
import json
import tempfile
from pathlib import Path
import sys
from decimal import Decimal, InvalidOperation
import re

import streamlit as st

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
from Quotation_KEKOREA.agent.extractor import extract_trade_data, load_env, verify_item_quotes
from Quotation_KEKOREA.agent.pricing import apply_verified_eclado_prices, load_local_seed, load_supabase_catalog
from Quotation_KEKOREA.agent.renderers import format_currency_amount, render_files
from Quotation_KEKOREA.agent.trade_documents import apply_promotion, validate_and_calculate


def _synchronize_extracted_quantities(draft):
    """Use one paid quantity consistently and calculate shipped quantities."""
    for item in draft.get("items", []):
        # The order quantity is the source of truth unless a promotion explicitly
        # separates paid units from free units. The validator calculates totals
        # from paid_quantity, so keep both quantity fields synchronized.
        paid = item.get("paid_quantity") if item.get("promotion") else item.get("quantity")
        paid = paid or item.get("quantity") or item.get("paid_quantity")
        if paid in (None, ""):
            continue
        item["quantity"] = str(paid)
        item["paid_quantity"] = str(paid)
        if item.get("free_quantity") in (None, ""):
            item["free_quantity"] = "0"
        if item.get("promotion"):
            try:
                promotion = apply_promotion(paid, item["promotion"])
                item["free_quantity"] = promotion["free_quantity"]
            except (ValueError, InvalidOperation):
                pass
        try:
            free = Decimal(str(item.get("free_quantity") or "0"))
            item["shipped_quantity"] = format(Decimal(str(paid)) + free, "f")
        except (InvalidOperation, TypeError, ValueError):
            pass


def _explicit_remark(prompt):
    """Only use remark text that the user explicitly labels in the prompt."""
    match = re.search(
        r"\bREMARKS?\s*:\s*(.*?)(?=\s+(?:BUYER|SELLER|PRODUCT|QUANTITY|PRICE|DELIVERY|PAYMENT|INCOTERMS|CURRENCY|SHIPMENT|SHIP\s+TO|BILL\s+TO|CONTACT)\s*:|$)",
        prompt or "", flags=re.IGNORECASE | re.DOTALL)
    return (match.group(1).strip(" \t\r\n;,") or "N/A") if match else "N/A"


def _keep_delivery_note_in_terms(draft, auto_remark):
    """Keep a model-classified delivery deadline under delivery terms, not remarks."""
    if not auto_remark or not re.search(r"\b(delivery|deliver|shipment deadline|ship before)\b", str(auto_remark), re.I):
        return
    terms = str(draft.get("incoterms") or "").strip()
    note = str(auto_remark).strip()
    if note and note.casefold() not in terms.casefold():
        draft["incoterms"] = f"{terms}; {note}" if terms else note


st.set_page_config(page_title="CONTRACT TEMPLATE MAKER | KE KOREA", page_icon="📄", layout="wide")
st.markdown("""
<style>
  :root { --ke-navy:#092b4c; --ke-blue:#0877c9; --ke-sky:#eaf5fc; --ke-ink:#172b3d; }
  .stApp { background:#f5f8fb; color:var(--ke-ink); }
  [data-testid="stSidebar"] { background:#092b4c; border-right:1px solid #163e61; }
  [data-testid="stSidebar"] * { color:#f5f9fd; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label { padding:11px 13px; border-radius:9px; margin:3px 0; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:#16466f; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#0877c9; }
  .ke-header { background:linear-gradient(110deg,#fff 0%,#fff 55%,#edf7fd 100%); border:1px solid #dbe8f2; border-top:4px solid #0877c9; border-radius:14px; padding:18px 24px; margin:0 0 20px; box-shadow:0 5px 18px rgba(9,43,76,.05); }
  .ke-eyebrow { color:#0877c9; letter-spacing:.12em; text-transform:uppercase; font-size:.77rem; font-weight:700; }
  .ke-header h1 { color:#092b4c; margin:.25rem 0 .2rem; font-size:1.8rem; }
  .ke-header p { color:#5b6b78; margin:0; }
  .ke-section { color:#092b4c; font-weight:700; font-size:1.1rem; margin:.6rem 0 .2rem; }
  div.stButton > button[kind="primary"] { background:#0877c9; border-color:#0877c9; border-radius:9px; font-weight:700; }
  div.stButton > button[kind="primary"]:hover { background:#065f9f; border-color:#065f9f; }
  [data-testid="stMetric"] { background:#fff; border:1px solid #dbe8f2; border-radius:11px; padding:14px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    logo = ROOT / "assets" / "company_logo.png"
    if logo.exists():
        st.image(str(logo), use_container_width=True)
    st.markdown("### CONTRACT TEMPLATE MAKER")
    st.caption("KE KOREA CO. LTD · TRADE DOCUMENTS")
    st.markdown("---")
    pages = ["PI 만들기", "PO 만들기", "CIPL 만들기", "계약서 만들기 · 준비 중", "커미션 계약서 만들기 · 준비 중"]
    page = st.radio("문서 종류", pages, label_visibility="collapsed", key="selected_document_page")
    st.markdown("---")
    st.caption("초안은 검토 후 사용하세요. 자동 발행이나 전송은 하지 않습니다.")

page_config = {
    "PI 만들기": ("PI", "Proforma Invoice", "바이어에게 제공할 견적·선결제 안내용 Proforma Invoice 초안을 만듭니다."),
    "PO 만들기": ("PO", "Purchase Order", "KE KOREA가 공급처에 발행할 Purchase Order 초안을 만듭니다."),
    "CIPL 만들기": ("CI", "Commercial Invoice & Packing List", "선적 정보를 입력하면 Commercial Invoice와 Packing List를 함께 만듭니다."),
}
if page not in page_config:
    st.markdown('<div class="ke-header"><div class="ke-eyebrow">Coming soon</div><h1>' + page.split(" ·")[0] + '</h1><p>이 메뉴는 준비 중입니다. 현재는 PI, PO, CIPL 생성을 사용할 수 있습니다.</p></div>', unsafe_allow_html=True)
    st.stop()

expected_type, title, description = page_config[page]
st.markdown(f'<div class="ke-header"><div class="ke-eyebrow">KE KOREA · CONTRACT TEMPLATE MAKER</div><h1>{title}</h1><p>{description}</p></div>', unsafe_allow_html=True)

st.warning("생성된 파일은 검토용 초안입니다. 발행·주문 전 정보와 금액을 확인하세요.")
st.info("주문 내용을 직접 입력하거나 바이어 주문서 이미지를 첨부하세요. Extract를 누르면 입력 문구와 이미지가 설정된 OpenAI API로 전송됩니다.")
st.caption("한국어·영어·중국어·인도네시아어 입력을 지원합니다. 문서는 영문으로 작성되며, 중국어 회사명과 주소는 원문 뒤에 영문 번역을 괄호로 표시합니다.")

cloud_secrets = {}
try:
    for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY",
                "KEKOREA_USD_BENEFICIARY", "KEKOREA_USD_BANK_NAME", "KEKOREA_USD_BRANCH",
                "KEKOREA_USD_SWIFT", "KEKOREA_USD_ACCOUNT_NUMBER", "KEKOREA_USD_BANK_ADDRESS",
                "KEKOREA_COMPANY_SEAL_BASE64"):
        if key in st.secrets:
            cloud_secrets[key] = st.secrets[key]
except Exception:
    pass
runtime_env = load_env(secrets=cloud_secrets)
if not runtime_env.get("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY is missing. Set it in local .env or Streamlit Cloud Settings > Secrets.")

@st.cache_data(ttl=300, show_spinner=False)
def _cached_supabase_catalog(project_url, _secret_key):
    return load_supabase_catalog({"SUPABASE_URL": project_url, "SUPABASE_SECRET_KEY": _secret_key})

active_catalog = {"products": [], "purchase_prices": [], "buyer_prices": []}
if runtime_env.get("SUPABASE_URL") and runtime_env.get("SUPABASE_SECRET_KEY"):
    try:
        with st.spinner("Loading the latest ECLADO catalog from Supabase..."):
            active_catalog = _cached_supabase_catalog(runtime_env["SUPABASE_URL"], runtime_env["SUPABASE_SECRET_KEY"])
        catalog_import = active_catalog.get("import", {})
        st.caption(f"ECLADO catalog connected: {len(active_catalog['products'])} products; import {catalog_import.get('imported_at', 'date unavailable')}.")
    except (ValueError, RuntimeError) as exc:
        st.error(f"Supabase catalog is unavailable: {exc}")
else:
    local_catalog = load_local_seed()
    if local_catalog.get("products"):
        active_catalog = local_catalog
        st.warning("Supabase credentials are not configured; using the private local catalog snapshot, which may be out of date.")
    else:
        st.error("Supabase catalog credentials are missing. Set SUPABASE_URL and SUPABASE_SECRET_KEY in Streamlit Cloud Settings > Secrets.")

with st.expander("What this menu creates"):
    if expected_type == "CI":
        st.write("CIPL creates two review files: a Commercial Invoice (CI) and a Packing List (PL). Provide actual shipment, package, and weight information; unknown details remain flagged for review.")
    else:
        st.write(f"{title} uses the KE KOREA branded PDF template. ECLADO prices are matched against the verified catalog when available. PI includes KE KOREA USD bank details; PO does not.")
    st.write("Order images may be PNG, JPG, JPEG, or WEBP. Image-derived information needs human review.")

st.markdown('<div class="ke-section">1 · 주문 정보</div>', unsafe_allow_html=True)
prompt = st.text_area("거래 조건을 입력하세요", height=180,
    placeholder=f"Example: Create a {title} for [company name, address, contact, phone, email]. List products, exact quantities, currency and prices, Incoterms and named place, payment or shipment terms. Optional: REMARK: [text]. If omitted, the document shows N/A.")
uploaded_images = st.file_uploader("바이어 주문 이미지 첨부", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
    help="이미지 최대 5개, 파일당 10 MB, 총 20 MB까지 첨부할 수 있습니다.")
if uploaded_images:
    st.caption(f"첨부 이미지 {len(uploaded_images)}개 · Extract를 누를 때 OpenAI로 전송됩니다.")
    st.image([upload.getvalue() for upload in uploaded_images], caption=[upload.name for upload in uploaded_images], use_container_width=True)

extract_clicked = st.button("정보 추출 및 초안 검토", type="primary", disabled=not prompt.strip() and not uploaded_images)
if extract_clicked:
    try:
        image_inputs = []
        if len(uploaded_images or []) > 5:
            raise ValueError("Attach no more than 5 order images at a time")
        total_image_bytes = 0
        for upload in uploaded_images or []:
            image_data = upload.getvalue()
            if len(image_data) > 10 * 1024 * 1024:
                raise ValueError(f"{upload.name} exceeds the 10 MB per-image limit")
            total_image_bytes += len(image_data)
            image_inputs.append({"name": upload.name, "mime_type": upload.type, "data": image_data})
        if total_image_bytes > 20 * 1024 * 1024:
            raise ValueError("Order images exceed the 20 MB combined limit")
        with st.spinner("Extracting candidate fields. No document is issued."):
            draft = extract_trade_data(prompt or f"Use the attached order image as source for a {title}.", images=image_inputs, env=runtime_env)
            # The selected sidebar workflow is authoritative, even if the order image mentions another form.
            draft["document_type"] = expected_type
            draft = verify_item_quotes(draft, prompt, image_context=bool(image_inputs))
            auto_remark = draft.get("remarks")
            _keep_delivery_note_in_terms(draft, auto_remark)
            draft["remarks"] = _explicit_remark(prompt)
            draft["conflicts"] = [issue for issue in draft.get("conflicts", [])
                                  if not issue.lower().startswith("remarks was not found verbatim")]
            _synchronize_extracted_quantities(draft)
            company_role = "buyer" if expected_type == "PO" else "seller"
            company = draft.get(company_role) or {}
            if not company.get("legal_name"):
                company["legal_name"] = "KE Korea Co. LTD"
            if not company.get("address"):
                company["address"] = "#1510, 157 Yangpyung Ro, Yungdeungpo Gu, Seoul, South Korea"
            if not company.get("contact"):
                company["contact"] = "Representative: DAVID, SEOKWON IHM"
            draft[company_role] = company
            apply_verified_eclado_prices(draft, active_catalog)
            st.session_state["trade_draft"] = draft
            st.session_state["trade_draft_page"] = page
            st.session_state["rendered_paths"] = {}
            st.session_state.pop("download_format", None)
            st.session_state.pop("rendered_json", None)
    except Exception as exc:
        st.error(str(exc))

raw = st.session_state.get("trade_draft") if st.session_state.get("trade_draft_page") == page else None
if raw:
    try:
        data = json.loads(json.dumps(raw, ensure_ascii=False))
        data["document_type"] = expected_type
        apply_verified_eclado_prices(data, active_catalog)
        result = validate_and_calculate(data)
        bank_keys = ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")
        bank_details = {key: runtime_env.get(f"KEKOREA_USD_{key}", "") for key in bank_keys}
        if expected_type == "PI" and any(not value for value in bank_details.values()):
            issue = "KE Korea USD bank profile is incomplete; configure all KEKOREA_USD_* values before creating the PI"
            if issue not in result["blocking_issues"]:
                result["blocking_issues"].append(issue)
            result["ready_for_issue"] = False
            result["status"] = "DRAFT"

        calculation_blockers = [issue for issue in result["blocking_issues"]
                                if issue.startswith("Valid positive number required for paid quantity")
                                or issue.startswith("Valid positive number required for unit price")]
        total_display = ("Cannot calculate" if calculation_blockers else
                         format_currency_amount(result.get("total", "0"), result.get("currency")))
        unit_totals = {}
        for item in result.get("items", []):
            unit = str(item.get("unit") or "").strip()
            if unit:
                unit_totals.setdefault(unit, Decimal("0"))
                unit_totals[unit] += Decimal(str(item.get("shipped_quantity") or item.get("quantity") or "0"))
        quantity_summary = " · ".join(
            f"{format(amount, 'f').rstrip('0').rstrip('.') if '.' in format(amount, 'f') else format(amount, 'f')} {unit}"
            for unit, amount in unit_totals.items()) or "—"
        if any("paid quantity for item" in issue.lower() for issue in calculation_blockers):
            quantity_summary = "Quantity required"

        st.markdown('<div class="ke-section">2 · Review the order summary</div>', unsafe_allow_html=True)
        top_metrics = st.columns(3)
        top_metrics[0].metric("Product lines", len(result.get("items", [])))
        top_metrics[1].metric("Total quantity", quantity_summary)
        top_metrics[2].metric("Total amount", total_display)

        seller_col, buyer_col = st.columns(2)
        for column, label, party in ((seller_col, "SELLER", result.get("seller") or {}),
                                     (buyer_col, "BUYER", result.get("buyer") or {})):
            with column:
                st.markdown(f"**{label}**")
                st.write(party.get("legal_name") or "Not provided")
                st.caption(party.get("address") or "Address not provided")
                contact_bits = [f"Contact: {party['contact']}" for _ in [0] if party.get("contact")]
                contact_bits += [f"Tel: {party['phone']}" for _ in [0] if party.get("phone")]
                contact_bits += [f"Email: {party['email']}" for _ in [0] if party.get("email")]
                if contact_bits:
                    st.caption(" · ".join(contact_bits))

        display_rows = []
        for index, item in enumerate(result.get("items", []), 1):
            quantity_missing = any(f"paid quantity for item {index}" in issue.lower() for issue in calculation_blockers)
            price_missing = any(f"unit price for item {index}" in issue.lower() for issue in calculation_blockers)
            if result.get("product_family") == "cosmetics":
                unit_price = format_currency_amount(item.get("final_unit_price", "0"), result.get("currency"))
            else:
                unit_price = f"{result.get('currency') or ''} {item.get('final_unit_price', '')}".strip()
            if price_missing:
                unit_price = "Not provided"
            line_total = ("Cannot calculate" if quantity_missing or price_missing else
                          format_currency_amount(item.get("line_total", "0"), result.get("currency")))
            display_rows.append({
                "No.": index,
                "Product": item.get("product_name") or "Not provided",
                "Capacity / Spec.": item.get("capacity") or "—",
                "Paid Qty": ("Not provided" if quantity_missing else
                             f"{item.get('paid_quantity', item.get('quantity', ''))} {item.get('unit') or ''}".strip()),
                "Free Qty": f"{item.get('free_quantity', '0')} {item.get('unit') or ''}".strip(),
                "Unit Price": unit_price,
                "Discount": f"{item.get('discount_percent', '0')}%",
                "Line Total": line_total,
            })
        st.dataframe(display_rows, hide_index=True, use_container_width=True)

        delivery_cols = st.columns(4)
        delivery_values = (
            ("Delivery terms", result.get("incoterms")),
            ("Payment terms", result.get("payment_terms")),
            ("Ship to", result.get("ship_to")),
            ("Shipment reference", result.get("shipment_reference")),
        )
        for column, (label, value) in zip(delivery_cols, delivery_values):
            with column:
                st.markdown(f"**{label}**")
                st.write(value or "To confirm")
        if result.get("remarks"):
            st.markdown("**Remarks**")
            st.write(result["remarks"])

        if result["blocking_issues"]:
            st.warning("Some information still needs confirmation. Generated files will remain marked DRAFT.")
            with st.expander("Items to confirm"):
                for issue in result["blocking_issues"]:
                    st.write(f"- {issue}")
        else:
            st.success("Summary is ready for your final review.")

        with st.expander("Advanced: view or correct extracted details"):
            edited_json = st.text_area("Extracted details", value=json.dumps(raw, ensure_ascii=False, indent=2),
                                       height=350, key=f"advanced_json_{page}")
            if st.button("Apply corrections", key=f"apply_json_{page}"):
                try:
                    corrected = json.loads(edited_json)
                    corrected["document_type"] = expected_type
                    apply_verified_eclado_prices(corrected, active_catalog)
                    st.session_state["trade_draft"] = corrected
                    st.session_state["rendered_paths"] = {}
                    st.session_state.pop("rendered_json", None)
                    st.rerun()
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    st.error(f"Could not apply corrections: {exc}")

        pdf_col, excel_col = st.columns(2)
        if calculation_blockers:
            st.error("Enter a valid quantity and unit price before creating a PDF or Excel file; the total cannot be calculated yet.")
        make_pdf = pdf_col.button("Create PDF", type="primary", use_container_width=True,
                                  disabled=bool(calculation_blockers))
        make_excel = excel_col.button("Create Excel", use_container_width=True,
                                     disabled=bool(calculation_blockers))
        if make_pdf or make_excel:
            logo_path = ROOT / "assets" / "company_logo.png"
            seal_path = ROOT / "private" / "company_seal.png"
            encoded_seal = runtime_env.get("KEKOREA_COMPANY_SEAL_BASE64")
            try:
                (ROOT / "outputs").mkdir(parents=True, exist_ok=True)
                if encoded_seal:
                    with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
                        seal_path = Path(temp_dir) / "company_seal.png"
                        seal_path.write_bytes(base64.b64decode(encoded_seal, validate=True))
                        outputs = render_files(result, ROOT / "outputs", bank_details=bank_details,
                                               logo_path=logo_path, seal_path=seal_path)
                        if expected_type == "CI":
                            packing_result = validate_and_calculate({**result, "document_type": "PL"})
                            outputs.update({f"packing_{k}": v for k, v in render_files(
                                packing_result, ROOT / "outputs", bank_details=bank_details,
                                logo_path=logo_path, seal_path=seal_path).items()})
                else:
                    outputs = render_files(result, ROOT / "outputs", bank_details=bank_details,
                                           logo_path=logo_path, seal_path=seal_path)
                    if expected_type == "CI":
                        packing_result = validate_and_calculate({**result, "document_type": "PL"})
                        outputs.update({f"packing_{k}": v for k, v in render_files(
                            packing_result, ROOT / "outputs", bank_details=bank_details,
                            logo_path=logo_path, seal_path=seal_path).items()})
                st.session_state["rendered_paths"] = {key: str(value) for key, value in outputs.items()}
                st.session_state["download_format"] = "pdf" if make_pdf else "xlsx"
            except (ValueError, OSError, TypeError, KeyError) as exc:
                st.error(f"Could not create review files: {exc}")

        selected_format = st.session_state.get("download_format")
        for kind, file_path in st.session_state.get("rendered_paths", {}).items():
            if not selected_format or not kind.endswith(selected_format):
                continue
            path = Path(file_path)
            if path.exists():
                st.download_button(f"Download {kind.upper()}: {path.name}", path.read_bytes(),
                                   file_name=path.name, key=f"download_{kind}_{path.name}")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, InvalidOperation) as exc:
        st.error(f"Could not build the order summary: {exc}")
