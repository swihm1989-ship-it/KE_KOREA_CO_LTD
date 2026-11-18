"""CI-ONLY Streamlit browser fixture for manual-only email reply UI.

All storage, OpenAI and SMTP actions are in-memory fakes. This is not the
production login page and must never be linked from production navigation.
Run only with: streamlit run .../tests/browser_fixture.py
"""
from __future__ import annotations
from unittest.mock import patch

import streamlit as st
from Quotation_KEKOREA.orchestration.ui import email_outbox_page as page
from Quotation_KEKOREA.orchestration.workflows import email_reply_runtime as runtime

st.set_page_config(page_title="MASTER synthetic email UI QA",layout="wide")
FIXTURE_ID="00000000-0000-4000-8000-000000000001"
if "fixture_record" not in st.session_state:
    st.session_state["fixture_record"]={
        "id":FIXTURE_ID,
        "status":"draft",
        "source_subject":"입찰 건 관련",
        "source_body":"안녕하세요. 입찰 건 관련 확인 바랍니다.",
        "sender_header":"Mock buyer <buyer@example.test>",
        "recipient_email":"buyer@example.test",
        "language":"ko",
        "candidate_bodies":[],
        "source_hash":"0"*64,
        "message_id":"<synthetic@example.test>",
    }
if "fixture_send_count" not in st.session_state:
    st.session_state["fixture_send_count"]=0

def generate(_source,_env,_lang):
    return [
        "안녕하세요. 문의 내용을 확인했습니다. 확인 후 회신드리겠습니다.",
        "안녕하세요. 연락 주셔서 감사합니다. 관련 내용을 검토하여 답변드리겠습니다.",
        "안녕하세요. 문의하신 내용을 담당자가 검토한 후 자세히 안내드리겠습니다.",
    ]

def save(_env,_principal,_ident,candidates,lang):
    assert len(candidates)==3
    st.session_state["fixture_record"]["candidate_bodies"]=candidates
    st.session_state["fixture_record"]["language"]=lang
    return st.session_state["fixture_record"]

def send(_env,_principal,_ident,_settings,recipient,subject,body,*,confirmed,
         signature_text,language):
    assert confirmed is True
    assert recipient=="buyer@example.test"
    assert "www.ke-korea.co.kr" in signature_text
    assert "임석원" in signature_text
    assert "문의" in body
    assert language=="ko"
    st.session_state["fixture_send_count"]+=1
    st.session_state["fixture_record"]["status"]="sent"
    return {"status":"sent","id":_ident}

st.caption("TEST-ONLY fixture · no user credentials, live models, real mail or SMTP")
st.caption("mock-send-count: "+str(st.session_state["fixture_send_count"]))
with (
    patch.object(page,"_db_env",return_value={}),
    patch.object(page,"list_replies",side_effect=lambda *_:[st.session_state["fixture_record"]]),
    patch.object(page,"save_candidates",side_effect=save),
    patch.object(page,"send_approved",side_effect=send),
    patch.object(runtime,"generate_reply_candidates",side_effect=generate),
    patch.object(runtime,"probe_connection",return_value="진단 성공: 가상 AI 서버 응답"),
):
    page.render_email_outbox("owner@example.test")
