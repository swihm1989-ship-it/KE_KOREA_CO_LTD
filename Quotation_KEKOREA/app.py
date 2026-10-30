"""Local Streamlit interface for English trade-document drafts."""
import json
import base64
import tempfile
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from agent.extractor import extract_trade_data, load_env, verify_item_quotes
from agent.pricing import apply_verified_eclado_prices, load_local_seed, load_supabase_catalog
from agent.renderers import format_currency_amount, render_files
from agent.trade_documents import validate_and_calculate


st.set_page_config(page_title="KE KOREA Trade Documents", layout="wide")
st.title("KE KOREA Trade Document Drafts")
st.caption("English document drafts: PO · PI · Commercial Invoice · Packing List")
st.warning("Drafts require your review. This app does not send orders, issue documents, email customers, or file customs declarations.")
st.info("When you click Extract, the prompt and any uploaded order images are sent to OpenAI using the configured API key and model. Use local .env on your computer or App settings > Secrets on Streamlit Cloud. Do not include information you do not want sent to the configured API.")
st.caption("You may enter transaction details in Chinese, Indonesian, Korean, or English. Document content is translated into English. Chinese company names and addresses retain the Chinese original followed by the English translation in parentheses.")

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

with st.expander("Supported in this verification build"):
    st.write("Enter buyer/company details and upload buyer order screenshots (PNG, JPG, JPEG, or WEBP). Image contents are sent to OpenAI when extracted and every image-derived detail needs visual review. ECLADO prices are read from the latest Supabase catalog import. Cosmetics display KRW without decimals and USD to two decimals. PI drafts include the KE Korea USD bank profile; PO and CI omit bank details. The corporate-blue PI places Quotation_KEKOREA/assets/company_logo.png in the header and the private company seal in the signature area. For Streamlit Cloud, store the seal image as KEKOREA_COMPANY_SEAL_BASE64 in Secrets. Email ingestion and automatic final numbering are not connected yet.")

prompt = st.text_area("Transaction details", height=220,
    placeholder="Example: Create a draft PI for buyer [legal name, address, contact, phone, email]. Use the attached order image. Currency USD, no discount, FOB [named place], T/T [payment terms].")
uploaded_images = st.file_uploader("Attach buyer order image(s)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
    help="Attach up to 5 screenshots/photos (PNG, JPG, JPEG, WEBP; 10 MB each, 20 MB combined).")
if uploaded_images:
    st.caption(f"{len(uploaded_images)} image(s) attached. Image content will be sent to OpenAI only when you click Extract.")
    st.image([upload.getvalue() for upload in uploaded_images], caption=[upload.name for upload in uploaded_images], use_container_width=True)

if st.button("Extract draft from prompt and images", type="primary", disabled=not prompt.strip() and not uploaded_images):
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
            st.session_state["trade_draft"] = verify_item_quotes(
                extract_trade_data(prompt or "Use the attached order image as the transaction source.", images=image_inputs, env=runtime_env),
                prompt, image_context=bool(image_inputs))
            draft = st.session_state["trade_draft"]
            company_role = "buyer" if draft.get("document_type") == "PO" else "seller"
            company = draft.get(company_role) or {}
            if not company.get("legal_name"):
                company["legal_name"] = "KE Korea Co. LTD"
            if not company.get("address"):
                company["address"] = "#1510, 157 Yangpyung Ro, Yungdeungpo Gu, Seoul, South Korea"
            if not company.get("contact"):
                company["contact"] = "Representative: DAVID, SEOKWON IHM"
            draft[company_role] = company
            apply_verified_eclado_prices(st.session_state["trade_draft"], active_catalog)
            st.session_state["prompt_snapshot"] = prompt
            st.session_state.pop("rendered_paths", None)
            st.session_state.pop("rendered_json", None)
    except Exception as exc:
        st.error(str(exc))

raw = st.session_state.get("trade_draft")
if raw:
    st.subheader("Review the extracted English draft data")
    st.caption("Edit the JSON to correct extraction. Values without verified sources remain blocked. Cosmetics prices are replaced by an exact local catalog match when available.")
    edited = st.text_area("Draft data (JSON)", value=json.dumps(raw, ensure_ascii=False, indent=2), height=480, key="draft_json")
    try:
        data = json.loads(edited)
        apply_verified_eclado_prices(data, active_catalog)
        result = validate_and_calculate(data)
        bank_keys = ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")
        bank_details = {key: runtime_env.get(f"KEKOREA_USD_{key}", "") for key in bank_keys}
        if result.get("document_type") == "PI" and any(not value for value in bank_details.values()):
            issue = "KE Korea USD bank profile is incomplete; configure all KEKOREA_USD_* values before creating the PI"
            if issue not in result["blocking_issues"]:
                result["blocking_issues"].append(issue)
            result["ready_for_issue"] = False
            result["status"] = "DRAFT"
        if result["blocking_issues"]:
            st.error("DRAFT ONLY — resolve these items before using the document:")
            for issue in result["blocking_issues"]:
                st.write(f"- {issue}")
        else:
            st.success("Calculated draft is ready for a final human check. It is not yet issued.")
        total_display = (format_currency_amount(result.get("total", "0"), result.get("currency"))
                         if result.get("product_family") == "cosmetics"
                         else f"{result.get('currency') or ''} {result.get('total', '0')}")
        st.metric("Calculated total", total_display)
        if st.button("Create review files (PDF + Excel + HTML)"):
            logo_path = ROOT / "assets" / "company_logo.png"
            seal_path = ROOT / "private" / "company_seal.png"
            encoded_seal = runtime_env.get("KEKOREA_COMPANY_SEAL_BASE64")
            if encoded_seal:
                try:
                    (ROOT / "outputs").mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
                        seal_path = Path(temp_dir) / "company_seal.png"
                        seal_path.write_bytes(base64.b64decode(encoded_seal, validate=True))
                        outputs = render_files(result, ROOT / "outputs", bank_details=bank_details,
                                               logo_path=logo_path, seal_path=seal_path)
                except (ValueError, OSError):
                    st.error("Company seal secret is invalid or could not be read.")
                    outputs = None
            else:
                outputs = render_files(result, ROOT / "outputs", bank_details=bank_details,
                                       logo_path=logo_path, seal_path=seal_path)
            if outputs is None:
                st.stop()
            st.session_state["rendered_paths"] = {k: str(v) for k, v in outputs.items()}
            st.session_state["rendered_json"] = edited
        if st.session_state.get("rendered_json") != edited:
            st.session_state.pop("rendered_paths", None)
            st.session_state.pop("rendered_json", None)
        for kind, file_path in st.session_state.get("rendered_paths", {}).items():
            path = Path(file_path)
            if path.exists():
                st.download_button(f"Download {kind.upper()}: {path.name}", path.read_bytes(), file_name=path.name)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        st.error(f"Draft JSON could not be validated: {exc}")
