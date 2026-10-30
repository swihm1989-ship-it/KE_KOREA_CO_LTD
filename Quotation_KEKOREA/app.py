"""Local Streamlit interface for English trade-document drafts."""
import json
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from agent.extractor import extract_trade_data, load_env, verify_item_quotes
from agent.pricing import apply_verified_eclado_prices, load_local_seed
from agent.renderers import render_files
from agent.trade_documents import validate_and_calculate


st.set_page_config(page_title="KE KOREA Trade Documents", layout="wide")
st.title("KE KOREA Trade Document Drafts")
st.caption("English document drafts: PO · PI · Commercial Invoice · Packing List")
st.warning("Drafts require your review. This app does not send orders, issue documents, email customers, or file customs declarations.")
st.info("When you click Extract, the text in the prompt box is sent to OpenAI using the API key and model in Quotation_KEKOREA/.env. Do not include information you do not want sent to the configured API.")

with st.expander("Supported in this first verification build"):
    st.write("Paste a transaction request as text. PDF, screenshot, email, Supabase live lookup, company/bank profiles, official company templates, and automatic final numbering are not connected yet.")

prompt = st.text_area("Transaction details", height=220,
    placeholder="Example: Create a draft PI for [buyer legal name and address]. ECLADO [exact item and capacity], [quantity] PCS, [discount or confirm none], [currency], ship to [address], [Incoterms and named place], payment [terms].")

if st.button("Extract draft from prompt", type="primary", disabled=not prompt.strip()):
    try:
        with st.spinner("Extracting candidate fields. No document is issued."):
            st.session_state["trade_draft"] = verify_item_quotes(extract_trade_data(prompt), prompt)
            draft = st.session_state["trade_draft"]
            company_role = "buyer" if draft.get("document_type") == "PO" else "seller"
            company = draft.get(company_role) or {}
            if not company.get("legal_name"):
                company["legal_name"] = "KE Korea Co. LTD"
            draft[company_role] = company
            apply_verified_eclado_prices(st.session_state["trade_draft"], load_local_seed())
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
        apply_verified_eclado_prices(data, load_local_seed())
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
