"""Local Streamlit interface for English trade-document drafts."""
import json
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
from Quotation_KEKOREA.agent.extractor import extract_trade_data, load_env, verify_item_quotes
from Quotation_KEKOREA.agent.pricing import apply_verified_eclado_prices, load_local_seed, load_supabase_catalog
from Quotation_KEKOREA.agent.renderers import render_files
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate


st.set_page_config(page_title="KE KOREA Trade Documents", layout="wide")
st.title("KE KOREA Trade Document Drafts")
st.caption("English document drafts: PO · PI · Commercial Invoice · Packing List")
st.warning("Drafts require your review. This app does not send orders, issue documents, email customers, or file customs declarations.")
st.info("When you click Extract, the prompt text is sent to OpenAI using the configured API key and model. Use local .env on your computer or App settings > Secrets on Streamlit Cloud. Do not include information you do not want sent to the configured API.")
st.caption("You may enter transaction details in Chinese, Indonesian, Korean, or English. Document content is translated into English. Chinese company names and addresses retain the Chinese original followed by the English translation in parentheses.")

cloud_secrets = {}
try:
    for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY"):
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

with st.expander("Supported in this first verification build"):
    st.write("Paste a transaction request as text. ECLADO prices are read from the latest Supabase catalog import. PDF, screenshot, email, company/bank profiles, official company templates, and automatic final numbering are not connected yet.")

prompt = st.text_area("Transaction details", height=220,
    placeholder="Example: Create a draft PI for [buyer legal name and address]. ECLADO [exact item and capacity], [quantity] PCS, [discount or confirm none], [currency], ship to [address], [Incoterms and named place], payment [terms].")

if st.button("Extract draft from prompt", type="primary", disabled=not prompt.strip()):
    try:
        with st.spinner("Extracting candidate fields. No document is issued."):
            st.session_state["trade_draft"] = verify_item_quotes(extract_trade_data(prompt, env=runtime_env), prompt)
            draft = st.session_state["trade_draft"]
            company_role = "buyer" if draft.get("document_type") == "PO" else "seller"
            company = draft.get(company_role) or {}
            if not company.get("legal_name"):
                company["legal_name"] = "KE Korea Co. LTD"
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
        if result["blocking_issues"]:
            st.error("DRAFT ONLY — resolve these items before using the document:")
            for issue in result["blocking_issues"]:
                st.write(f"- {issue}")
        else:
            st.success("Calculated draft is ready for a final human check. It is not yet issued.")
        st.metric("Calculated total", f"{result.get('currency') or ''} {result.get('total', '0')}")
        if st.button("Create review files (PDF + Excel + HTML)"):
            outputs = render_files(result, ROOT / "outputs")
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
