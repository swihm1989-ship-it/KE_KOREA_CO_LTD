"""Streamlit interface for KE KOREA trade-document drafts."""
import json
import hashlib
import tempfile
from uuid import uuid4
from pathlib import Path
import sys
from decimal import Decimal, InvalidOperation
import re

import streamlit as st

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
from Quotation_KEKOREA.agent.workflow_state import DocumentWorkspaces
from Quotation_KEKOREA.agent.counterparties import (load_company_profiles, apply_company_profiles,
                                                  apply_ke_korea_company_defaults)
from Quotation_KEKOREA.agent.promotions import apply_promotion_commands, recalculate_order_promotions
from Quotation_KEKOREA.agent.samples import ensure_sample_rows, edit_sample_rows, is_manual_sample
from Quotation_KEKOREA.agent.attachments import prepare_uploads
from Quotation_KEKOREA.agent.extractor import extract_trade_data, load_env, verify_item_quotes
from Quotation_KEKOREA.agent.branding import resolve_company_seal
from Quotation_KEKOREA.agent.seal_storage import download_company_seal
from Quotation_KEKOREA.agent.pricing import (is_eclado_supplier, load_local_seed, load_supabase_catalog,
                                             match_eclado_product)
from Quotation_KEKOREA.agent.ci_import import (prepare_ci_import, is_pi_import, ci_import_issues, ci_render_data,
                                           is_ci_conversion_request, apply_document_prices as apply_verified_eclado_prices)
from Quotation_KEKOREA.agent.packing_review import (reconcile_packing, normalize_packing_inputs, packing_total_changes,
                                           apply_approved_packing_totals, PACKING_SOURCE_FIELDS)
from Quotation_KEKOREA.agent.renderers import format_currency_amount, render_files
from Quotation_KEKOREA.agent.review_fields import missing_review_fields, apply_review_value
from Quotation_KEKOREA.agent.trade_documents import apply_promotion, current_issue_date, normalize_quantity_unit, validate_and_calculate


# Public document-agent and MASTER now share one canonical extraction
# postprocessor; keep these established names for UI/backwards compatibility.
from Quotation_KEKOREA.agent.document_engine import (
    _apply_ke_korea_company_defaults,
    _synchronize_extracted_quantities,
    _format_quantity_display,
    _explicit_remark,
    _has_explicit_ship_to,
    _discount_instruction,
    _normalize_quantity_aliases,
    _normalize_currency_alias,
    _requested_document_type,
    _keep_delivery_note_in_terms,
    _extract_draft,
)


def _render_draft(result, output_root, bank_details, logo_path, local_seal_path, seal_bytes):
    """Keep existing render rules; each background job owns its output directory."""
    result = ci_render_data(result)
    output_dir = Path(output_root) / uuid4().hex
    seal_path = local_seal_path
    output_dir.mkdir(parents=True, exist_ok=True)
    if seal_bytes is not None:
        with tempfile.TemporaryDirectory(dir=output_dir) as temp_dir:
            seal_path = Path(temp_dir) / "company_seal.png"
            seal_path.write_bytes(seal_bytes)
            outputs = render_files(result, output_dir, bank_details=bank_details,
                                   logo_path=logo_path, seal_path=seal_path)
    else:
        outputs = render_files(result, output_dir, bank_details=bank_details,
                               logo_path=logo_path, seal_path=seal_path)
    return outputs


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

from Auth.gate import require_login
require_login(st, ROOT)

with st.sidebar:
    logo = ROOT / "assets" / "company_logo.png"
    if logo.exists():
        st.image(str(logo), use_container_width=True)
    st.markdown("### CONTRACT TEMPLATE MAKER")
    st.caption("KE KOREA CO. LTD · TRADE DOCUMENTS")
    st.markdown("---")
    pages = ["PI 만들기", "PO 만들기", "CI 만들기", "PL 만들기", "계약서 만들기"]
    if "selected_document_page" in st.session_state and st.session_state["selected_document_page"] not in pages:
        st.session_state["selected_document_page"] = pages[0]
    page = st.radio("문서 종류", pages, label_visibility="collapsed", key="selected_document_page")
    st.markdown("---")
    st.caption("초안은 검토 후 사용하세요. 자동 발행이나 전송은 하지 않습니다.")

work = st.session_state.setdefault("_document_workspaces", DocumentWorkspaces())
work.activate(st.session_state, page)
work.collect(st.session_state)


@st.fragment(run_every=1 if work.jobs else None)
def _show_background_jobs():
    # Only the UI thread applies results, before widgets are instantiated.
    if any(job.future.done() for job in work.jobs.values()):
        st.rerun()
    with st.sidebar:
        for (job_page, kind), job in work.jobs.items():
            action = "자료 추출" if kind == "extract" else "서류 생성"
            st.caption(f"⏳ {job_page}: {action} 진행 중")
        for saved_page, values in work.pages.items():
            if saved_page != page and values.get("trade_draft"):
                st.caption(f"✓ {saved_page}: 초안 보관 중")
    if page in work.errors:
        st.error(work.errors[page])


_show_background_jobs()

page_config = {
    "PI 만들기": ("PI", "Proforma Invoice", "바이어에게 제공할 견적·선결제 안내용 Proforma Invoice 초안을 만듭니다."),
    "PO 만들기": ("PO", "Purchase Order", "KE KOREA가 공급처에 발행할 Purchase Order 초안을 만듭니다."),
    "CI 만들기": ("CI", "Commercial Invoice", "통관 제출용 Commercial Invoice 초안을 만듭니다."),
    "PL 만들기": ("PL", "Packing List", "선적 포장 수량과 중량을 표시하는 Packing List 초안을 만듭니다."),
}
contract_pages = {"계약서 만들기"}
if page not in page_config and page not in contract_pages:
    st.error("문서 메뉴를 다시 선택해 주세요.")
    st.stop()

cloud_secrets = {}
try:
    for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY",
                "KEKOREA_USD_BENEFICIARY", "KEKOREA_USD_BANK_NAME", "KEKOREA_USD_BRANCH",
                "KEKOREA_USD_SWIFT", "KEKOREA_USD_ACCOUNT_NUMBER", "KEKOREA_USD_BANK_ADDRESS",
                "KEKOREA_COMPANY_SEAL_BASE64", "CONTRACT_OPENAI_MODEL",
                "CONTRACT_LIBRARY_ADMIN_TOKEN", "CONTRACT_LIBRARY_EMBEDDING_MODEL",
                "CONTRACT_FINAL_SEAL_PASSWORD"):
        if key in st.secrets:
            cloud_secrets[key] = st.secrets[key]
except Exception:
    pass
runtime_env = load_env(secrets=cloud_secrets)
if page in contract_pages:
    from Quotation_KEKOREA.contracts.ui import render_contract_page
    render_contract_page(page, runtime_env)
    st.stop()

expected_type, title, description = page_config[page]
st.markdown(f'<div class="ke-header"><div class="ke-eyebrow">KE KOREA · CONTRACT TEMPLATE MAKER</div><h1>{title}</h1><p>{description}</p></div>', unsafe_allow_html=True)

st.warning("생성된 파일은 검토용 초안입니다. 발행·주문 전 정보와 금액을 확인하세요.")
st.info("주문 내용을 직접 입력하거나 바이어 주문서 이미지를 첨부하세요. Extract를 누르면 입력 문구와 이미지가 설정된 OpenAI API로 전송됩니다.")
st.caption("한국어·영어·중국어·인도네시아어 입력을 지원합니다. 문서는 영문으로 작성되며, 중국어 회사명과 주소는 원문 뒤에 영문 번역을 괄호로 표시합니다.")

if not runtime_env.get("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY is missing. Set it in local .env or Streamlit Cloud Settings > Secrets.")

@st.cache_data(ttl=300, show_spinner=False)
def _cached_supabase_catalog(project_url, _secret_key):
    return load_supabase_catalog({"SUPABASE_URL": project_url, "SUPABASE_SECRET_KEY": _secret_key})


@st.cache_data(ttl=900, show_spinner=False)
def _cached_supabase_seal(project_url, _secret_key, expected_sha256):
    return download_company_seal({"SUPABASE_URL": project_url, "SUPABASE_SECRET_KEY": _secret_key}, expected_sha256)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_company_profiles(project_url, _secret_key):
    return load_company_profiles({"SUPABASE_URL": project_url, "SUPABASE_SECRET_KEY": _secret_key})


active_company_profiles = []
if runtime_env.get("SUPABASE_URL") and runtime_env.get("SUPABASE_SECRET_KEY"):
    try:
        active_company_profiles = _cached_company_profiles(runtime_env["SUPABASE_URL"], runtime_env["SUPABASE_SECRET_KEY"])
    except (ValueError, RuntimeError) as exc:
        st.warning("거래처 DB 자동 입력을 사용할 수 없습니다. 회사 정보를 직접 입력해 주세요. " + str(exc))

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
    st.write(f"{title} uses the KE KOREA branded PDF template. ECLADO prices are matched against the verified catalog when available. PI includes KE KOREA USD bank details; PO, CI, and PL do not.")
    st.write("Source documents may be PNG, JPG, JPEG, WEBP, or PDF. Extracted information needs human review.")

st.markdown('<div class="ke-section">1 · 주문 정보</div>', unsafe_allow_html=True)
prompt = st.text_area("거래 조건을 입력하세요", height=180, key=f"order_prompt_{page}",
    placeholder=f"Example: Create a {title} for [company name, address, contact, phone, email]. List products, exact quantities, currency and prices, Incoterms and named place, payment or shipment terms. Optional: REMARK: [text]. If omitted, the document shows N/A.")
def _remember_order_uploads():
    work.remember_uploads(page, st.session_state.get(f"order_upload_{page}") or [])


current_uploads = st.file_uploader("공급처 패킹리스트 이미지/PDF 첨부" if expected_type == "PL" else "주문·PI 이미지/PDF 첨부", type=["png", "jpg", "jpeg", "webp", "pdf"], accept_multiple_files=True,
    key=f"order_upload_{page}", on_change=_remember_order_uploads,
    help="이미지/PDF를 섞어서 최대 5개, 파일당 10 MB, 총 20 MB까지 첨부할 수 있습니다. PDF의 모든 페이지를 추출 대상으로 전달합니다.")
if current_uploads:
    work.remember_uploads(page, current_uploads)
uploaded_images = work.uploads.get(page, [])
has_pdf_upload = any(upload.type == 'application/pdf' or upload.name.lower().endswith('.pdf') for upload in uploaded_images)
if uploaded_images and st.button("첨부 파일 모두 지우기" if has_pdf_upload else "첨부 이미지 모두 지우기", key=f"clear_uploads_{page}"):
    work.remember_uploads(page, [])
    st.session_state.pop(f"order_upload_{page}", None)
    st.rerun()
st.caption("For ECLADO, the entered discount is applied to the Supabase list price. If no discount is stated, the full list price (0% discount) is used. Enter one discount rate per invoice.")
st.caption("Common labels such as Qty/Q'ty/Volume, Unit Price/Rate, Shipping Terms/Delivery Terms, and Payment Conditions are interpreted by meaning. Volume and package-count labels may require your confirmation.")
if uploaded_images:
    st.caption(f"첨부 {'파일' if has_pdf_upload else '이미지'} {len(uploaded_images)}개 · Extract를 누를 때 OpenAI로 전송됩니다.")
    preview_images = [upload for upload in uploaded_images if upload.type != 'application/pdf' and not upload.name.lower().endswith('.pdf')]
    if preview_images:
        st.image([upload.getvalue() for upload in preview_images], caption=[upload.name for upload in preview_images], use_container_width=True)
    for upload in uploaded_images:
        if upload not in preview_images:
            st.caption(f"PDF: {upload.name} · 모든 페이지를 추출합니다.")

extract_clicked = st.button("정보 추출 및 초안 검토", type="primary", disabled=(not prompt.strip() and not uploaded_images) or work.busy(page, "extract") or work.busy(page, "render"))
if extract_clicked:
    try:
        requested_type = ('CI' if expected_type == 'CI' and uploaded_images and is_ci_conversion_request(prompt)
                          else _requested_document_type(prompt))
        selected_type = expected_type
        if requested_type and requested_type != selected_type:
            raise ValueError(
                f"Your prompt requests {requested_type}, but the sidebar is set to {selected_type}. "
                "Choose the matching document menu, then extract again."
            )
        image_inputs = prepare_uploads(uploaded_images)
        work.start(page, "extract", _extract_draft, prompt, title, expected_type,
                   image_inputs, runtime_env, active_catalog, active_company_profiles)
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

raw = st.session_state.get("trade_draft") if st.session_state.get("trade_draft_page") == page else None
if raw:
    try:
        data = json.loads(json.dumps(raw, ensure_ascii=False))
        data["document_type"] = expected_type
        _apply_ke_korea_company_defaults(data, expected_type)
        if expected_type == "PO":
            seller = data.get("seller") or {}
            data["seller"] = seller
            st.caption("PO supplier details (fill in the supplier's legal name and address when known).")
            seller["legal_name"] = st.text_input("Supplier legal name", value=seller.get("legal_name") or "", key=f"po_seller_name_{page}") or None
            seller["address"] = st.text_input("Supplier address", value=seller.get("address") or "", key=f"po_seller_address_{page}") or None
        if expected_type == "PL":
            buyer = data.get("buyer") or {}
            data["buyer"] = buyer
            party_columns = st.columns(2)
            buyer["legal_name"] = party_columns[0].text_input("Buyer legal name", value=buyer.get("legal_name") or "", key=f"packing_{page}_buyer") or None
            buyer["address"] = party_columns[1].text_input("Buyer address", value=buyer.get("address") or "", key=f"packing_{page}_buyer_address") or None
            shipment_columns = st.columns(2)
            data["ship_to"] = shipment_columns[0].text_input("Ship-to address", value=data.get("ship_to") or "", key=f"packing_{page}_ship_to") or None
            data["shipment_reference"] = shipment_columns[1].text_input("Shipment reference", value=data.get("shipment_reference") or "", key=f"packing_{page}_shipment_reference") or None
            origin_columns = st.columns(2)
            data["country_of_origin"] = origin_columns[0].text_input("Country of origin", value=data.get("country_of_origin") or "", key=f"packing_{page}_origin") or None
            data["hs_code"] = origin_columns[1].text_input("Shipment HS code", value=data.get("hs_code") or "", key=f"packing_{page}_hs_code") or None
            st.markdown("**Packing details — compare the extracted values with the supplier document**")
            packing_fields = (("product_name", "Product"), ("capacity", "Specification"),
                              ("quantity", "Quantity"), ("unit", "Unit"),
                              ("package_type", "Package type"), ("package_count", "Packages"),
                              ("net_weight_kg", "NW (kg)"), ("gross_weight_kg", "GW (kg)"), ("volume_cbm", "CBM"), ("hs_code", "HS code"))
            original_items = data.get("items", [])
            packing_rows = []
            for index, item in enumerate(original_items, 1):
                row = {"Row": str(index)}
                for field, label in packing_fields:
                    value = item.get(field)
                    row[label] = "" if value is None else str(value)
                packing_rows.append(row)
            if not packing_rows and expected_type == "PL":
                packing_rows = [{"Row": "", **{label: "" for _, label in packing_fields}}]
            packing_rows = work.editor_input(page, packing_rows)
            edited_rows = st.data_editor(packing_rows, hide_index=True, num_rows="dynamic",
                                         disabled=["Row"], use_container_width=True, key=f"packing_{page}_rows")
            work.editor_rows[page] = json.loads(json.dumps(edited_rows))
            updated_items = []
            for row in edited_rows:
                row_id = str(row.get("Row") or "")
                item = dict(original_items[int(row_id) - 1]) if row_id.isdigit() and 1 <= int(row_id) <= len(original_items) else {}
                for field, label in packing_fields:
                    item[field] = str(row.get(label) or "").strip() or None
                if expected_type == "PL":
                    item["paid_quantity"] = item.get("quantity")
                    item["shipped_quantity"] = item.get("quantity")
                    item["free_quantity"] = "0"
                updated_items.append(item)
            data["items"] = updated_items
            st.caption("공급처 원본의 합계입니다. 품목별 계산 합계와 다르면 아래 비교표에서 합계 수정을 승인해 주세요. 원본 인식이 틀렸을 때는 이 입력칸을 수정하세요.")
            total_fields = (("actual_package_count", "Source total packages"), ("container_count", "Containers"),
                            ("declared_net_weight_kg", "Source NW (kg)"), ("declared_gross_weight_kg", "Source GW (kg)"),
                            ("declared_volume_cbm", "Source CBM"), ("declared_total_quantity", "Source total quantity"),
                            ("declared_total_quantity_unit", "Source quantity unit"))
            columns = st.columns(2)
            for index, (field, label) in enumerate(total_fields):
                column = columns[index % len(columns)]
                data[field] = column.text_input(label, value="" if data.get(field) is None else str(data[field]), key=f"packing_{page}_{field}") or None
            data.pop('_packing_original_totals', None)
            data = normalize_packing_inputs(data)
        apply_company_profiles(data, active_company_profiles)
        apply_verified_eclado_prices(data, active_catalog)
        if data.get("product_family") == "cosmetics" or expected_type in {"CI", "PL"}:
            for index, item in enumerate(data.get("items", [])):
                if is_manual_sample(data, item):
                    continue
                match = match_eclado_product(item.get("product_name"), item.get("capacity"),
                                             active_catalog.get("products", []), item.get("product_code"))
                needs_double_check = (match["status"] in {"suggested", "ambiguous", "not_found"}
                                      or match.get("match_method") == "fuzzy")
                if not needs_double_check:
                    continue
                st.warning(f"Item {index + 1}: Double-check this product / 제품을 다시 확인해 주세요.")
                if match.get("suggestions"):
                    st.caption("Possible catalog matches: " + "; ".join(
                        f"{candidate['product']['item_name']} ({candidate['similarity']:.0%})"
                        for candidate in match["suggestions"]))
                elif match["status"] == "ambiguous":
                    st.caption("Multiple catalog products match. Confirm the product and capacity/SKU.")
                else:
                    st.caption("No unique catalog match. The name you enter below will be kept as written.")
                item["product_name"] = st.text_input(
                    f"Item {index + 1}: product name to print on the quote",
                    value=str(item.get("product_name") or ""),
                    key=f"product_double_check_{page}_{index}")
            apply_verified_eclado_prices(data, active_catalog)
        sample_review_paths = edit_sample_rows(data, page)
        review_fields = missing_review_fields(data)
        if expected_type == "CI" and not is_pi_import(data):
            review_fields = [field for field in review_fields if not (
                field.path[0] == "items" and field.path[-1] in {"unit_price", "discount_percent"})]
        existing_review_paths = set(sample_review_paths)
        if expected_type == "PO":
            existing_review_paths.update({("seller", "legal_name"), ("seller", "address")})
        if expected_type == "PL":
            existing_review_paths.update({("buyer", "legal_name"), ("buyer", "address"), ("ship_to",),
                                          ("shipment_reference",), ("country_of_origin",), ("container_count",)})
        if review_fields:
            st.markdown("### 문서 생성 전 누락 정보 입력")
            st.caption("빈 항목을 영문으로 입력해 주세요. * 항목은 필수입니다. 선택 항목이 해당 없으면 N/A를 직접 입력해 주세요.")
            review_columns = st.columns(2)
            review_values = st.session_state.setdefault(f"review_values_{page}", {})
            for index, field in enumerate(field for field in review_fields if field.path not in existing_review_paths):
                widget_key = f"review_missing_{page}_" + "_".join(map(str, field.path))
                if widget_key not in st.session_state:
                    st.session_state[widget_key] = review_values.get(widget_key, "")
                value = review_columns[index % 2].text_input(
                    field.label + (" *" if field.required else ""), key=widget_key,
                    help="Enter the confirmed value in English." if field.required else "Enter the value, or N/A if not applicable.")
                review_values[widget_key] = value
                apply_review_value(data, field, value)
            apply_company_profiles(data, active_company_profiles)
            apply_verified_eclado_prices(data, active_catalog)
        data = recalculate_order_promotions(data)
        pending_review_fields = missing_review_fields(data)
        if expected_type == "PO":
            verified_count = sum(item.get("master_price") is True for item in data.get("items", []))
            st.caption(f"PO는 ECLADO KRW 매입 카탈로그 기준 · 확인된 가격 적용: {verified_count}/{len(data.get('items', []))}개 상품")
        if pending_review_fields:
            st.warning("PDF/Excel 생성 전에 다음 항목을 입력해 주세요: " + "; ".join(field.label for field in pending_review_fields))
        result = validate_and_calculate(data)
        packing_check = reconcile_packing(data) if expected_type == "PL" else None
        if packing_check and packing_check["issues"]:
            st.error("포장 항목에서 확인 또는 수정이 필요한 값이 있습니다:")
            for issue in packing_check["issues"]:
                st.write(f"- {issue}")
        packing_image_confirmed = True
        if packing_check is not None:
            review_snapshot = {"items": data.get("items", []),
                               "source": data.get('_packing_original_totals', {}),
                               **{field: data.get(field) for field in PACKING_SOURCE_FIELDS}}
            review_digest = hashlib.sha256(json.dumps(review_snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
            changes = packing_total_changes(data, packing_check)
            if changes or packing_check['discrepancies']:
                st.warning("원본 합계와 품목별 계산 합계를 비교해 주세요. 단위가 다른 수량은 각각 표시하며, 승인한 경우에만 계산된 합계로 문서를 생성합니다.")
                if changes:
                    st.dataframe([{"항목": change['label'], "원본 합계": change['source'],
                                   "품목별 계산 합계": change['calculated']} for change in changes],
                                 hide_index=True, use_container_width=True)
                for discrepancy in packing_check['discrepancies']:
                    st.write(f"- {discrepancy}")
                packing_image_confirmed = st.checkbox(
                    "합계를 수정할까요? 품목별 값을 확인했으며 계산된 합계로 수정하는 것을 승인합니다.",
                    key=f"packing_{page}_approve_totals_{review_digest}",
                    disabled=bool(packing_check['issues']) or not changes)
                if packing_image_confirmed:
                    data = apply_approved_packing_totals(data)
                    result = validate_and_calculate(data)
                    packing_check = reconcile_packing(data)
                    st.success("합계 수정이 승인되었습니다. 원본 합계는 보존하며 PDF/Excel에는 계산된 합계를 적용합니다.")
            elif data.get('source_image_attached'):
                packing_image_confirmed = st.checkbox("원본 문서와 추출된 포장 정보를 확인했습니다." if data.get('source_pdf_attached') else "원본 이미지와 추출된 포장 정보를 확인했습니다.",
                                                      key=f"packing_{page}_confirmed_{review_digest}")
        if packing_check:
            calculated = packing_check["calculated"]
            st.caption("Calculated row totals: " + " | ".join(
                f"{label}: {_format_quantity_display(calculated[field]) if calculated[field] is not None else 'Incomplete'}"
                for field, label in (("package_count", "Packages"), ("net_weight_kg", "NW kg"),
                                     ("gross_weight_kg", "GW kg"), ("volume_cbm", "CBM"))))
        bank_keys = ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")
        bank_details = {key: str(runtime_env.get(f"KEKOREA_USD_{key}", "")).strip() for key in bank_keys}
        missing_bank_keys = [f"KEKOREA_USD_{key}" for key, value in bank_details.items() if not value]
        local_seal_path, seal_bytes, seal_secret_error = resolve_company_seal(
            ROOT, runtime_env,
            storage_loader=lambda env, expected: _cached_supabase_seal(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"], expected))
        missing_seal = seal_bytes is None and not local_seal_path.is_file()
        if expected_type == "PI" and missing_bank_keys:
            issue = "KE Korea USD bank profile is incomplete; missing runtime keys: " + ", ".join(missing_bank_keys)
            if issue not in result["blocking_issues"]:
                result["blocking_issues"].append(issue)
            result["ready_for_issue"] = False
            result["status"] = "DRAFT"
        if missing_seal:
            issue = "Company seal is unavailable: " + (seal_secret_error or "upload the requested image to private Supabase storage")
            if issue not in result["blocking_issues"]:
                result["blocking_issues"].append(issue)
            result["ready_for_issue"] = False
            result["status"] = "DRAFT"

        buyer_name = str((result.get("buyer") or {}).get("legal_name") or "").strip().casefold()
        source_import_blockers = ci_import_issues(result)
        if source_import_blockers:
            result['blocking_issues'].extend(source_import_blockers)
            result.update(ready_for_issue=False, status='DRAFT')
            st.error('원본 PI와 추출값을 확인해 주세요: ' + '; '.join(source_import_blockers))
        if is_pi_import(result):
            st.caption('첨부 PI의 거래 단가·할인율·수량을 사용합니다. 은행·결제 값은 CI에 가져오지 않습니다.')
        buyer_key = re.sub(r"[^a-z0-9]", "", buyer_name)
        if expected_type == "PI" and result.get("product_family") == "cosmetics" and "dearglow" not in buyer_key:
            st.warning("The current ECLADO sale-price catalog is for Dear Glow only. This buyer has no stored catalog price yet, so enter an approved price before creating a document.")

        supported_currencies = {"USD", "KRW", "EUR", "CNY"}
        currency = str(result.get("currency") or "").strip().upper()
        # Keep the calculation display separate from overall document readiness.
        # A catalog lookup can supply the authoritative currency after extraction,
        # while a stale "currency" entry remains in missing_fields. Only an
        # invalid/missing currency or an explicit currency conflict makes a
        # numeric total unsafe to display.
        currency_conflicts = [
            issue for issue in result["blocking_issues"]
            if issue.lower().startswith("resolve conflicting information:")
            and "currency" in issue.lower()
        ]
        calculation_blockers = [issue for issue in result["blocking_issues"]
                                if issue.startswith(("Valid number required for paid quantity", "Valid positive number required for paid quantity"))
                                or issue.startswith("Valid positive number required for unit price")]
        calculation_blockers.extend(currency_conflicts)
        calculation_blockers.extend(issue for issue in result["blocking_issues"] if issue.startswith("Sample "))
        calculation_blockers.extend(source_import_blockers)
        if expected_type != "PL" and currency not in supported_currencies:
            calculation_blockers.append("Currency must be confirmed as a supported three-letter code")
        discount_blockers = [] if expected_type == "PL" else [issue for issue in result["blocking_issues"] if "discount" in issue.lower()]
        total_display = ("Cannot calculate" if calculation_blockers or discount_blockers else
                         format_currency_amount(result.get("total", "0"), result.get("currency")))
        unit_totals = {}
        for item in result.get("items", []):
            unit = str(item.get("unit") or "").strip()
            if unit:
                unit_totals.setdefault(unit, Decimal("0"))
                unit_totals[unit] += Decimal(str(item.get("shipped_quantity") or item.get("quantity") or "0"))
        quantity_summary = " · ".join(
            f"{_format_quantity_display(amount)} {unit}"
            for unit, amount in unit_totals.items()) or "—"
        if any("paid quantity for item" in issue.lower() for issue in calculation_blockers):
            quantity_summary = "Quantity required"

        st.markdown('<div class="ke-section">2 · Review the order summary</div>', unsafe_allow_html=True)
        top_metrics = st.columns(3)
        top_metrics[0].metric("Product lines", len(result.get("items", [])))
        top_metrics[1].metric("Total quantity", quantity_summary)
        if expected_type == "PL":
            top_metrics[2].metric("Total CBM", packing_check["calculated"].get("volume_cbm") or "To confirm")
        else:
            top_metrics[2].metric("Total amount", total_display)
            st.caption(f"Currency: {result.get('currency') or 'To confirm'}")

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
            source_item = (data.get("items") or [])[index - 1]
            discount_missing = bool(discount_blockers) or source_item.get("discount_percent") is None
            if result.get("product_family") == "cosmetics":
                unit_price = format_currency_amount(item.get("final_unit_price", "0"), result.get("currency"))
            else:
                unit_price = f"{result.get('currency') or ''} {item.get('final_unit_price', '')}".strip()
            if price_missing:
                unit_price = "Not provided"
            if not result.get("currency"):
                unit_price = "Currency to confirm"
            line_total = ("Cannot calculate" if quantity_missing or price_missing or discount_missing or
                          not result.get("currency") else
                          format_currency_amount(item.get("line_total", "0"), result.get("currency")))
            display_rows.append({
                "No.": index,
                "Product": item.get("product_name") or "Not provided",
                "Capacity / Spec.": item.get("capacity") or "—",
                "Paid Qty": ("Not provided" if quantity_missing else
                             f"{_format_quantity_display(item.get('paid_quantity', item.get('quantity', '')))} {item.get('unit') or ''}".strip()),
                "Free Qty": f"{_format_quantity_display(item.get('free_quantity', '0'))} {item.get('unit') or ''}".strip(),
                "Unit Price": unit_price,
                "Discount": "Not confirmed" if discount_missing else f"{item.get('discount_percent', '0')}%",
                "Line Total": line_total,
            })
        if expected_type != "PL":
            st.dataframe(display_rows, hide_index=True, use_container_width=True)

        unconfirmed_aliases = []
        unconfirmed_product_matches = []
        for index, confirmation in enumerate(data.get("pending_confirmations", []), 1):
            if not st.checkbox(confirmation, key=f"confirm_source_alias_{page}_{index}"):
                if str(confirmation).startswith(("Confirm product annotation for ", "Double-check this product:")):
                    unconfirmed_product_matches.append(confirmation)
                else:
                    unconfirmed_aliases.append(confirmation)

        delivery_cols = st.columns(4)
        delivery_values = (
            ("Delivery terms", result.get("incoterms")),
            ("Payment terms", result.get("payment_terms")),
            ("Ship to", result.get("ship_to") or "N/A"),
            ("Shipment reference", result.get("shipment_reference")),
        )
        for column, (label, value) in zip(delivery_cols, delivery_values):
            with column:
                st.markdown(f"**{label}**")
                st.write(value or ("N/A" if label == "Ship to" else "To confirm"))
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
            advanced_source = json.dumps(data, ensure_ascii=False, indent=2)
            if st.session_state.get(f"advanced_source_{page}") != advanced_source:
                st.session_state[f"advanced_json_{page}"] = advanced_source
                st.session_state[f"advanced_source_{page}"] = advanced_source
            edited_json = st.text_area("Extracted details", height=350, key=f"advanced_json_{page}")
            if st.button("Apply corrections", key=f"apply_json_{page}"):
                try:
                    corrected = json.loads(edited_json)
                    corrected["document_type"] = expected_type
                    corrected.pop("pending_confirmations", None)
                    apply_company_profiles(corrected, active_company_profiles, prompt=prompt)
                    apply_verified_eclado_prices(corrected, active_catalog)
                    st.session_state["trade_draft"] = corrected
                    work.reset_editor(page)
                    for state_key in list(st.session_state):
                        if str(state_key).startswith((f"review_missing_{page}_", f"review_values_{page}", f"packing_{page}_", f"po_seller_name_{page}", f"po_seller_address_{page}", f"product_double_check_{page}_")):
                            del st.session_state[state_key]
                    st.session_state["rendered_paths"] = {}
                    st.session_state.pop("rendered_json", None)
                    st.rerun()
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    st.error(f"Could not apply corrections: {exc}")

        pdf_col, excel_col = st.columns(2)
        render_context = json.dumps({"document": result, "bank": bank_details}, sort_keys=True, ensure_ascii=False)
        if st.session_state.get("rendered_json") != render_context:
            st.session_state["rendered_paths"] = {}
            st.session_state.pop("download_format", None)
        st.session_state["rendered_json"] = render_context
        bank_blockers = [issue for issue in result["blocking_issues"] if "bank profile is incomplete" in issue.lower()]
        seal_blockers = [issue for issue in result["blocking_issues"]
                         if "company seal is unavailable" in issue.lower()
                         or "KEKOREA_COMPANY_SEAL_BASE64" in issue]
        financial_blockers = calculation_blockers + discount_blockers
        promotion_blockers = ([issue for issue in result["blocking_issues"]
                               if any(marker in issue.lower() for marker in
                                      ("promotion rule", "promotion quantity", "promotion command"))]
                              if expected_type in {"PO", "PI"} else [])
        sample_blockers = [issue for issue in result["blocking_issues"] if issue.startswith("Sample ")]
        export_blocked = bool((expected_type in {"PO", "PI"} and unconfirmed_product_matches) or pending_review_fields or financial_blockers or bank_blockers or seal_blockers or
                              promotion_blockers or sample_blockers or source_import_blockers or (packing_check and packing_check["issues"]) or not packing_image_confirmed)
        if sample_blockers:
            st.error("샘플 입력값을 확인해 주세요: " + "; ".join(sample_blockers))
        if promotion_blockers:
            st.error("행사 조건 또는 행사 수량을 확인해 주세요: " + "; ".join(promotion_blockers))
        if financial_blockers:
            st.error("Confirm valid quantities, unit prices, and discounts before creating a PDF or Excel file.")
        if unconfirmed_product_matches:
            st.warning("Unconfirmed product details will be included as entered; generated files will remain marked DRAFT.")
        if unconfirmed_aliases:
            st.warning("Confirm the interpreted order field above before creating the documents.")
        if not packing_image_confirmed:
            st.warning("공급처 원본과 품목별 값을 대조한 뒤 확인란을 선택해 주세요.")
        if bank_blockers:
            st.error("PI download is disabled until all six KEKOREA_USD_* bank details are configured in this runtime.")
        if seal_blockers:
            st.error("Document download is disabled: " + seal_blockers[0] + ".")
            st.caption("Streamlit Cloud uses the private Supabase seal file and the configured server-side Supabase key.")
        make_pdf = pdf_col.button("Create PDF", type="primary", use_container_width=True,
                                  disabled=export_blocked or work.busy(page, "extract") or work.busy(page, "render"))
        make_excel = excel_col.button("Create Excel", use_container_width=True,
                                     disabled=export_blocked or work.busy(page, "extract") or work.busy(page, "render"))
        if make_pdf or make_excel:
            work.save(st.session_state)
            work.start(page, "render", _render_draft, result,
                       ROOT / "outputs" / work.session_id, bank_details,
                       ROOT / "assets" / "company_logo.png", local_seal_path,
                       seal_bytes, context=render_context,
                       file_format="pdf" if make_pdf else "xlsx")
            st.rerun()

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

# Keep non-widget snapshots before Streamlit cleans up hidden menu widgets.
work.save(st.session_state)
