"""MASTER human-only email approval panel: 3 AI candidates -> edit -> send.

Never sends on render, navigation, polling, AI completion, or page reload.
"""
from __future__ import annotations

from hashlib import sha256
import os
import streamlit as st

from Quotation_KEKOREA.orchestration.workflows.document_assets import document_export_env
from Quotation_KEKOREA.orchestration.workflows.email_reply_drafts import (
    STYLES, default_signature, generate_candidates, reply_subject,
)
from Quotation_KEKOREA.orchestration.workflows.email_outbox import (
    OutboxError, list_replies, get_reply, save_candidates, send_approved,
)

def _db_env():
    return document_export_env(st.secrets,os.environ)

def render_email_outbox(principal: str):
    if not principal:
        raise PermissionError("로그인이 필요합니다.")
    st.markdown("### 이메일 발송 대기 · AI 회신 후보")
    st.caption("메일은 AI가 자동 발송하지 않습니다. 회신 후보 선택·수정·확인 후 '발송' 버튼을 누른 경우에만 보냅니다.")
    try:
        env=_db_env()
        rows=list_replies(env,principal)
    except OutboxError as error:
        st.error(str(error))
        return
    except Exception:
        st.error("메일 대기함 설정을 확인해 주세요.")
        return
    if not rows:
        st.info("발송 대기 중인 이메일이 없습니다. 메일함 → AI 업무 요청에서 문서 불필요 메일을 보내세요.")
        return

    pending=[r for r in rows if r.get("status")!="sent"]
    if not pending:
        st.info("미발송 메일이 없습니다.")
        with st.expander("발송 완료 내역"):
            for r in rows:
                st.caption((r.get("source_subject") or "(제목 없음)")+" · 발송 완료")
        return

    row_map={str(r["id"]):r for r in pending}
    default=st.session_state.get("master_reply_selected")
    options=list(row_map)
    index=options.index(default) if default in row_map else 0
    chosen_id=st.selectbox("처리할 메일",options,index=index,
        format_func=lambda ident:(
            str(row_map[ident].get("source_subject") or "(제목 없음)")[:65]+" · "+
            str(row_map[ident].get("recipient_email") or "")[:45]+" · "+
            {"draft":"DRAFT","sending":"발송 상태 확인 필요","send_unknown":"발송 여부 미확인"}.get(
                row_map[ident].get("status"),"확인 필요")
        ),key="master_email_outbox_selected")
    if not chosen_id:
        return
    row=row_map[chosen_id]
    st.caption("받은 사람: "+str(row.get("sender_header") or "")[:160])
    with st.expander("원본 메일 확인",expanded=False):
        st.text(str(row.get("source_subject") or ""))
        st.text(str(row.get("source_body") or "")[:12000])

    if row.get("status")!="draft":
        st.warning("메일 전송이 이미 시작되었거나 결과가 불확실합니다. "
                   "이 화면에서 다시 발송할 수 없습니다. 실제 보낸편지함을 먼저 확인하세요.")
        if row.get("approved_subject"):
            st.text("발송 시도 제목: "+str(row.get("approved_subject")))
            st.text_area("발송 시도 본문",value=str(row.get("approved_body") or ""),
                         disabled=True,height=200,key="master_reply_sent_view_"+chosen_id)
        return

    stored_lang=row.get("language") if row.get("language") in {"ko","en"} else "en"
    lang=st.radio("회신 및 서명 언어",["ko","en"],
                  format_func=lambda value:"한국어" if value=="ko" else "English",
                  index=0 if stored_lang=="ko" else 1,
                  horizontal=True,key="master_reply_language_"+chosen_id)
    suggestions=row.get("candidate_bodies") or []
    if lang!=stored_lang and len(suggestions)==3:
        st.warning("언어를 바꿨습니다. 아래에서 새 언어로 후보를 다시 생성한 후 발송하세요.")
    consent=st.checkbox("이 메일의 제목·본문을 OpenAI에 보내 AI 회신 후보를 생성하는 데 동의합니다.",
                        key="master_reply_ai_consent_"+chosen_id)
    if st.button("AI 회신 후보 3개 "+("다시 생성" if suggestions else "생성"),
                 key="master_reply_generate_"+chosen_id,disabled=not consent):
        try:
            with st.spinner("세 가지 스타일의 회신을 작성합니다."):
                from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _model_config
                options=generate_candidates({
                    "subject":row.get("source_subject",""),
                    "body":row.get("source_body",""),
                    "sender":row.get("sender_header",""),
                },_model_config(),lang)
                save_candidates(env,principal,chosen_id,options,lang)
            st.rerun()
        except (OutboxError,ValueError,RuntimeError) as error:
            st.error("AI 회신 생성 실패: "+str(error)[:300])
        except Exception:
            st.error("AI 회신 생성에 실패했습니다. 설정을 확인하세요.")
    if len(suggestions)!=3 or lang!=stored_lang:
        st.info("AI 회신 후보 3개를 생성한 후 직접 수정·발송할 수 있습니다.")
        return

    st.markdown("#### 추천 회신 후보 3개")
    for index,body in enumerate(suggestions):
        with st.expander("후보 "+str(index+1)+" · "+STYLES[index]):
            st.text(body)
    selected_index=st.radio("수정할 회신 후보",list(range(3)),
        horizontal=True,format_func=lambda i:str(i+1)+". "+STYLES[i],
        key="master_reply_choice_"+chosen_id)
    stamp=sha256((row["source_hash"]+"|"+str(selected_index)+"|"+lang).encode()).hexdigest()[:12]
    recipient=st.text_input("받는 사람",value=str(row.get("recipient_email") or ""),
                            key="master_reply_to_"+chosen_id)
    subject=st.text_input("메일 제목",value=reply_subject(row.get("source_subject") or ""),
                          key="master_reply_subject_"+chosen_id)
    body=st.text_area("메일 내용 (직접 수정 가능)",value=suggestions[selected_index],
                      height=235,key="master_reply_body_"+chosen_id+"_"+stamp)
    signature=st.text_area("Signature (기본값 · 수정 가능)",value=default_signature(lang),
                           height=135,key="master_reply_signature_"+chosen_id+"_"+lang)
    final_body=body.strip()+"\n\n"+signature.strip()
    st.markdown("**최종 발송 미리보기**")
    st.code(final_body, language=None)

    # Confirmation is tied to the EXACT current envelope. Any edit invalidates it.
    digest=sha256(("\0".join((recipient,subject,final_body))).encode()).hexdigest()[:20]
    approved=st.checkbox(
        "받는 사람·제목·본문·서명을 모두 확인했습니다. 발송 버튼을 누르면 실제 이메일이 전송됩니다.",
        key="master_reply_confirm_"+chosen_id+"_"+digest,
    )
    if st.button("발송",type="primary",disabled=not approved,
                 key="master_reply_send_"+chosen_id):
        try:
            from Quotation_KEKOREA.orchestration.ui.mailbox_page import _settings
            with st.spinner("승인된 메일을 SMTP로 전송합니다."):
                result=send_approved(env,principal,chosen_id,_settings(),
                                     recipient,subject,final_body,confirmed=True)
        except (OutboxError,ValueError,PermissionError) as error:
            st.error(str(error))
        except Exception:
            st.error("발송 결과 확인에 실패했습니다. 보낸편지함을 확인한 뒤 조치하세요.")
        else:
            if result["status"]=="sent":
                st.success("발송 완료가 확인되었습니다.")
                st.rerun()
