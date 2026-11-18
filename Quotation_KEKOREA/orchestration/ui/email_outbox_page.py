"""MASTER human-only email approval panel: 3 AI candidates -> edit -> send.

Never sends on render, navigation, polling, AI completion, or page reload.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import importlib
import inspect
import os
import re
import streamlit as st

REPLY_RUNTIME_REVISION = "master-reply-20261118-personal-salutation-v3"
REPLY_SOURCE_MTIME_NS = Path(__file__).stat().st_mtime_ns

from Quotation_KEKOREA.orchestration.workflows.document_assets import document_export_env
from Quotation_KEKOREA.orchestration.workflows.email_reply_drafts import (
    STYLES, default_signature, reply_subject, recipient_salutation,
    with_recipient_salutation,
)
from Quotation_KEKOREA.orchestration.workflows.email_outbox import (
    OutboxError, list_replies, get_reply, save_candidates, send_approved,
    requeue_reply, delete_reply,
)

SEND_REVISION_EXPECTED = "master-smtp-stage-safe-20261118-v2"


def _resolve_send_approved():
    """Reload stale SMTP pipeline on click, before any DB claim or transport.

    Long-running Streamlit processes retain imported Python modules between
    deployments. A stale send_approved that lacks signature_text/language
    raises TypeError before claim, which used to be shown as a generic
    'sent folder check' error even when no SMTP was called.
    """
    from Quotation_KEKOREA.orchestration.workflows import email_outbox as module

    def current(mod):
        try:
            actual_mtime=Path(mod.__file__).stat().st_mtime_ns
            params=inspect.signature(mod.send_approved).parameters
        except (TypeError, ValueError, OSError, AttributeError):
            return False
        return (getattr(mod, "EMAIL_SEND_RUNTIME_REVISION", None)==SEND_REVISION_EXPECTED
                and getattr(mod, "EMAIL_SEND_SOURCE_MTIME_NS", None)==actual_mtime
                and {"confirmed", "signature_text", "language"}.issubset(params))

    if not current(module):
        try:
            importlib.invalidate_caches()
            module=importlib.reload(module)
        except (ImportError, OSError, SyntaxError, RuntimeError):
            raise OutboxError(
                "메일 발송 모듈을 최신 상태로 불러오지 못했습니다. 발송을 시작하지 않았습니다."
            ) from None
    if not current(module):
        raise OutboxError(
            "메일 발송 모듈 버전이 일치하지 않습니다. 발송을 시작하지 않았습니다."
        )
    return module.send_approved


def _safe_send_failure_status(env,principal,ident,error):
    """Read-only DB check after an unexpected exception, never SMTP/retry."""
    safe_type=type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,60}",safe_type):
        safe_type="Exception"
    try:
        fresh=get_reply(env,principal,ident)
    except Exception:
        return ("발송 중 오류 유형: "+safe_type+". 데이터베이스 상태도 확인하지 못했습니다. "
                "중복 발송하지 말고 보낸편지함 및 운영 로그를 확인하세요.")
    status=str(fresh.get("status") or "")
    started=fresh.get("send_started_at")
    if status=="draft" and not started:
        return ("발송 준비 단계 오류 ("+safe_type+"). 데이터베이스에 발송 시작 기록이 없습니다. "
                "현재 코드 흐름상 SMTP 전송 전에 중단된 상태입니다. 자동 재시도하지 않습니다.")
    if status=="sent":
        return ("발송 완료 기록이 데이터베이스에서 확인됩니다. 화면 처리 중 오류 ("+
                safe_type+")가 발생했습니다. 다시 발송하지 마세요.")
    return ("발송 상태가 '"+status+"'로 기록되어 있습니다. 오류 유형: "+safe_type+
            ". 실제 전송 여부가 불확실합니다. 재발송하지 말고 보낸편지함을 확인하세요.")


def _clear_send_approval(ident: str):
    """Any email edit invalidates the exact-value send approval."""
    st.session_state.pop("master_reply_approved_digest_"+ident, None)


def _db_env():
    return document_export_env(st.secrets,os.environ)


def _body_prefill_from_previous(full: str, language: str):
    """Keep an explicitly duplicated draft editable, without double signatures.

    For earlier records the signature is not separately persisted. An
    unrecognized custom block requires human review, not silent deletion.
    """
    message = str(full or "").strip()
    signature = default_signature(language)
    if message.endswith("\n\n" + signature):
        return message[:-(len(signature) + 2)].strip(), signature
    blocks = message.rsplit("\n\n", 1)
    if len(blocks) == 2 and (
        "www.ke-korea.co.kr" in blocks[1] or
        "KE Korea Co. Ltd" in blocks[1] or
        "(주)케이이코리아" in blocks[1]
    ):
        return blocks[0].strip(), blocks[1].strip()
    # The previous text is displayed in full so it can be edited. Do not
    # silently add a second signature if a custom one cannot be identified.
    return message, ""


def _render_delete_reply(env, principal, row):
    ident = str(row.get("id") or "")
    if row.get("status") == "sending":
        st.caption("전송 중인 발송 기록은 삭제할 수 없습니다.")
        return
    with st.expander("이 발송 기록 삭제", expanded=False):
        st.caption("선택한 기록을 영구 삭제합니다. 이미 보낸 이메일은 취소되지 않습니다.")
        acknowledged = st.checkbox(
            "이 메일 기록을 삭제하겠습니다.",
            key="master_reply_delete_confirm_" + ident,
        )
        if st.button("선택 메일 삭제", type="secondary",
                     disabled=not acknowledged,
                     key="master_reply_delete_" + ident):
            try:
                delete_reply(env, principal, ident)
            except OutboxError as error:
                st.error(str(error))
            except Exception:
                st.error("메일 기록을 삭제하지 못했습니다.")
            else:
                st.session_state.pop("master_reply_selected", None)
                st.session_state.pop("master_email_outbox_selected", None)
                st.success("선택한 발송 기록을 삭제했습니다.")
                st.rerun()


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
    # AI failure after a successful mailbox->outbox save must not be presented
    # as a lost email. Show the warning once, without exposing server secrets.
    ai_notice=st.session_state.pop("master_reply_ai_notice", None)
    if ai_notice:
        st.warning(ai_notice)
    if not rows:
        st.info("발송 대기 중인 이메일이 없습니다. 메일함 → AI 업무 요청에서 문서 불필요 메일을 보내세요.")
        return

    # Previous sent and ambiguous attempts remain selectable for the owner's
    # explicit 'make another draft' action and deletion. Never auto-retry.
    row_map={str(r["id"]):r for r in rows}
    default=st.session_state.get("master_reply_selected")
    options=list(row_map)
    index=options.index(default) if default in row_map else 0
    if st.session_state.get("master_email_outbox_selected") not in row_map:
        st.session_state.pop("master_email_outbox_selected", None)
    chosen_id=st.selectbox("처리할 메일",options,index=index,
        format_func=lambda ident:(
            str(row_map[ident].get("source_subject") or "(제목 없음)")[:65]+" · "+
            str(row_map[ident].get("recipient_email") or "")[:45]+" · "+
            {"draft":"DRAFT","sending":"발송 처리 중","send_unknown":"발송 여부 미확인","sent":"발송 완료"}.get(
                row_map[ident].get("status"),"확인 필요")
        ),key="master_email_outbox_selected")
    if not chosen_id:
        return
    row=row_map[chosen_id]
    st.caption("받은 사람: "+str(row.get("sender_header") or "")[:160])
    with st.expander("원본 메일 확인",expanded=False):
        st.text(str(row.get("source_subject") or ""))
        st.text(str(row.get("source_body") or "")[:12000])

    # Explicit read-only SMTP diagnostics, available even after an ambiguous
    # send. This connects/authenticates over TLS but NEVER issues MAIL FROM,
    # RCPT TO, DATA, or any outbound email.
    with st.expander("SMTP 연결·로그인 진단 (메일 발송 없음)", expanded=False):
        st.caption("서버 접속, TLS, 로그인만 확인합니다. 메일은 전송하지 않습니다. "
                   "기존 'send_unknown' 발송 기록의 성공 여부를 확인하는 기능은 아닙니다.")
        if st.button("SMTP 접속·로그인 검사", key="master_reply_smtp_probe_"+chosen_id):
            from Quotation_KEKOREA.orchestration.adapters.whois_mail import (
                mail_config, probe_smtp, MailConnectionError,
            )
            from Quotation_KEKOREA.orchestration.ui.mailbox_page import _settings
            try:
                config=mail_config(_settings(),principal)
                if config.smtp is None:
                    st.error("SMTP 호스트·계정 설정이 필요합니다. 전송된 메일은 없습니다.")
                else:
                    with st.spinner("SMTP 연결·인증을 검사합니다. 실제 메일은 전송하지 않습니다."):
                        probe_smtp(config.smtp)
                    st.success("SMTP TLS 연결과 로그인 성공. 메일은 보내지 않았습니다. "
                               "실제 발송 성공 여부는 별도 확인이 필요합니다.")
            except (MailConnectionError, ValueError, PermissionError) as error:
                st.error(str(error)[:250])
            except Exception:
                st.error("SMTP 접속·로그인 진단에 실패했습니다. 설정을 확인하세요.")

    _render_delete_reply(env, principal, row)

    if row.get("status")!="draft":
        if row.get("status")=="sending":
            st.warning("현재 발송 처리 중입니다. 상태가 확정되면 새 발송 건을 만들 수 있습니다.")
        else:
            st.info("이전 발송 기록은 그대로 보관됩니다. 같은 내용을 다시 보내려면 "
                    "아래에서 별도의 새 DRAFT를 만들고 발송 버튼을 직접 누르세요.")
            if row.get("status")=="send_unknown":
                st.warning("기존 발송 성공 여부가 확인되지 않았습니다. 새로 발송하면 "
                           "중복으로 도착할 수 있으며, 재발송 여부는 사용자가 결정합니다.")
        if row.get("approved_subject"):
            st.text("기존 발송 제목: "+str(row.get("approved_subject")))
            st.text_area("기존 발송 본문",value=str(row.get("approved_body") or ""),
                         disabled=True,height=200,key="master_reply_sent_view_"+chosen_id)
        if row.get("status") in ("sent","send_unknown"):
            if st.button("같은 메일로 새 발송 건 작성",type="primary",
                         key="master_reply_repeat_"+chosen_id):
                try:
                    from Quotation_KEKOREA.orchestration.ui.mailbox_page import _settings
                    fresh=requeue_reply(env,principal,chosen_id,_settings())
                except (OutboxError,ValueError,PermissionError) as error:
                    st.error(str(error))
                except Exception:
                    st.error("새 발송 초안을 작성하지 못했습니다.")
                else:
                    st.session_state["master_reply_selected"]=fresh["id"]
                    st.session_state.pop("master_email_outbox_selected",None)
                    st.rerun()
        return

    with st.expander("AI 연결 상태 진단 · 가상 데이터만 사용", expanded=False):
        from Quotation_KEKOREA.orchestration.workflows.email_reply_runtime import (
            status as reply_runtime_status, probe_connection,
        )
        from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _model_config
        diag_env = _model_config()
        diag = reply_runtime_status(diag_env)
        st.caption("실행 코드 버전: " + diag["runtime"])
        st.caption("AI 키: " + ("설정됨" if diag["key_configured"] else "미설정")
                   + " · 모델: " + diag["model"])
        st.caption("연결 검사는 원본 메일을 전송하지 않습니다. 가상 문장만 보내며 적은 API 비용이 발생할 수 있습니다.")
        probe_consent=st.checkbox("가상 AI 연결 테스트 실행에 동의합니다.",
                                  key="master_reply_probe_consent_"+chosen_id)
        if st.button("API 연결 진단 실행", disabled=not probe_consent,
                     key="master_reply_probe_"+chosen_id):
            with st.spinner("OpenAI 인증과 모델 응답을 확인합니다."):
                probe_result=probe_connection(diag_env)
            if probe_result.startswith("진단 성공"):
                st.success(probe_result)
            else:
                st.warning(probe_result)

    stored_lang=row.get("language") if row.get("language") in {"ko","en"} else "en"
    lang=st.radio("회신 및 서명 언어",["ko","en"],
                  format_func=lambda value:"한국어" if value=="ko" else "English",
                  index=0 if stored_lang=="ko" else 1,
                  horizontal=True,key="master_reply_language_"+chosen_id,
                  on_change=_clear_send_approval,args=(chosen_id,))
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
                from Quotation_KEKOREA.orchestration.workflows.email_reply_runtime import generate_reply_candidates
                options=generate_reply_candidates({
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
    salutation_source={"sender":row.get("sender_header") or "",
                       "body":row.get("source_body") or ""}
    has_ai_candidates=len(suggestions)==3 and lang==stored_lang
    prefilled_signature=default_signature(lang)
    if has_ai_candidates:
        st.markdown("#### AI 추천 회신 후보 3개")
        for index,candidate in enumerate(suggestions):
            with st.expander("후보 "+str(index+1)+" · "+STYLES[index]):
                st.text(with_recipient_salutation(candidate,salutation_source,lang))
        selected_index=st.radio("수정할 회신 후보",list(range(3)),
            horizontal=True,format_func=lambda i:str(i+1)+". "+STYLES[i],
            key="master_reply_choice_"+chosen_id,
            on_change=_clear_send_approval,args=(chosen_id,))
        suggested_body=with_recipient_salutation(
            suggestions[selected_index],salutation_source,lang)
    else:
        st.info("AI 후보가 아직 없거나 선택한 언어와 일치하지 않습니다. "
                "상단에서 AI 회신 후보를 다시 생성하거나, 아래에서 직접 회신을 작성할 수 있습니다. "
                "직접 작성한 메일도 최종 승인 전에는 발송되지 않습니다.")
        selected_index="manual"
        suggested_body=""
        # Only intentionally copied drafts have previously approved text
        # but NO approved digest. Restore it as editable, not approved.
        if row.get("approved_body") and not row.get("approved_sha256") and lang==stored_lang:
            suggested_body,prefilled_signature=_body_prefill_from_previous(
                row["approved_body"],lang)
            if not prefilled_signature:
                st.warning("이전 서명을 구분하지 못했습니다. 본문과 Signature를 "
                           "직접 확인한 후 새 발송을 승인하세요.")
    if suggested_body:
        st.caption("첫 인사말은 원본 발신인 정보 기준으로 제안됩니다. "
                   "메일 내용에서 직접 수정할 수 있습니다.")
    stamp=sha256((row["source_hash"]+"|"+str(selected_index)+"|"+lang+"|"+suggested_body).encode()).hexdigest()[:12]
    to_key="master_reply_to_"+chosen_id
    sub_key="master_reply_subject_"+chosen_id
    body_key="master_reply_body_"+chosen_id+"_"+stamp
    sig_key="master_reply_signature_"+chosen_id+"_"+lang
    recipient=st.text_input("받는 사람",value=str(row.get("recipient_email") or ""),
                            key=to_key,on_change=_clear_send_approval,args=(chosen_id,))
    subject=st.text_input("메일 제목",value=(row.get("approved_subject")
                         if row.get("approved_body") and not row.get("approved_sha256")
                         else reply_subject(row.get("source_subject") or "")),
                          key=sub_key,on_change=_clear_send_approval,args=(chosen_id,))
    body=st.text_area("메일 내용 (직접 수정 가능)",value=suggested_body,
                      height=235,key=body_key,on_change=_clear_send_approval,args=(chosen_id,))
    signature=st.text_area("Signature (기본값 · 수정 가능)",value=prefilled_signature,
                           height=150,key=sig_key,on_change=_clear_send_approval,args=(chosen_id,))
    final_body=body.strip()+("\n\n"+signature.strip() if signature.strip() else "")
    if not body.strip():
        st.warning("답장 본문을 작성해야 발송할 수 있습니다.")
    st.markdown("**최종 발송 미리보기 · KE KOREA 기업형 서명**")
    # The actual sent email includes this same escaped corporate HTML and an
    # inline company logo. This is a no-network, no-send preview only.
    try:
        from Quotation_KEKOREA.orchestration.workflows.email_signature_design import (
            preview_signature_html,
        )
        import streamlit.components.v1 as components
        rendered = preview_signature_html(body, signature)
        components.html(rendered, height=350, scrolling=True)
    except (ValueError,OSError,ImportError,RuntimeError):
        st.warning("회사 로고 미리보기를 표시할 수 없습니다. 발송 전 로고 파일을 확인하세요.")
    with st.expander("일반 텍스트 메일 미리보기"):
        st.code(final_body, language=None)

    # Approval is a separate deliberate BUTTON click, not a checkbox whose
    # state can be lost when Streamlit batches a text edit + checkbox event.
    # The exact current recipient/subject/body/signature is hashed and any
    # subsequent edit invalidates the stored approval before sending.
    digest=sha256(("\0".join((recipient,subject,final_body))).encode()).hexdigest()[:20]
    approved_key="master_reply_approved_digest_"+chosen_id
    if st.button("이 내용으로 발송 전 승인",type="secondary",
                 disabled=not body.strip() or not signature.strip(),
                 key="master_reply_approve_"+chosen_id):
        st.session_state[approved_key]=digest
        st.rerun()
    approved=(st.session_state.get(approved_key)==digest)
    if approved:
        st.success("현재 받는 사람·제목·본문·서명이 확인되었습니다. 아래 발송 버튼을 누를 때만 전송됩니다.")
    else:
        st.caption("내용을 확인한 뒤 '이 내용으로 발송 전 승인'을 누르면 발송 버튼이 활성화됩니다.")
    if st.button("발송",type="primary",disabled=not approved or not body.strip(),
                 key="master_reply_send_"+chosen_id):
        try:
            from Quotation_KEKOREA.orchestration.ui.mailbox_page import _settings
            with st.spinner("승인된 메일을 SMTP로 전송합니다."):
                current_send=_resolve_send_approved()
                result=current_send(env,principal,chosen_id,_settings(),
                                    recipient,subject,final_body,confirmed=True,
                                    signature_text=signature,language=lang)
        except (OutboxError,ValueError,PermissionError) as error:
            _clear_send_approval(chosen_id)
            st.error(str(error)[:350])
            st.info(_safe_send_failure_status(env,principal,chosen_id,error))
        except Exception as error:
            _clear_send_approval(chosen_id)
            st.error(_safe_send_failure_status(env,principal,chosen_id,error))
        else:
            if result["status"]=="sent":
                st.success("발송 완료가 확인되었습니다.")
                st.rerun()
