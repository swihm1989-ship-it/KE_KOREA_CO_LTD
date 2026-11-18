"""Owner-scoped, durable mail reply drafts and explicitly approved SMTP sending.

No timers, cron, poller or automatic sending. The ONLY path to SMTP is a
successful owner-confirmed click on the Streamlit send button.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from email.message import EmailMessage
from email.utils import parseaddr
from hashlib import sha256
import re
import smtplib
import ssl
from uuid import UUID

from Quotation_KEKOREA.contracts.repository import ContractRepository
from Quotation_KEKOREA.orchestration.adapters.whois_mail import mail_config
from Quotation_KEKOREA.orchestration.workflows.email_reply_drafts import (
    reply_subject, source_hash, preferred_language,
)

EMAIL_SEND_RUNTIME_REVISION = "master-smtp-stage-safe-20261118-v2"
EMAIL_SEND_SOURCE_MTIME_NS = Path(__file__).stat().st_mtime_ns

TABLE="kekorea_master_mail_outbox"
ADDRESS=re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
MESSAGE_ID=re.compile(r"^<[^<>\s@]+@[^<>\s@]+>$")

class OutboxError(RuntimeError):
    pass


class SMTPBeforeDataError(OutboxError):
    """Transport failed before send_message was called. No DATA was submitted.

    This is intentionally distinct from an ambiguous send_message exception.
    Only this class can safely restore a claimed draft, never auto-retry it.
    """
    def __init__(self, safe_message: str, *, stage: str):
        super().__init__(safe_message)
        self.stage = stage


def _predata_message(stage: str, exc: Exception) -> str:
    # Never expose SMTP server replies: they can include customer addresses
    # and account details. Numeric SMTP codes are safe.
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        code = getattr(exc, "smtp_code", None)
        number = f" (SMTP {code})" if type(code) is int else ""
        return ("SMTP 인증 실패"+number+". 메일은 전송되지 않았습니다. "
                "후이즈 SMTP 계정·비밀번호 및 SMTP 사용 권한을 확인하세요.")
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return ("SMTP STARTTLS 지원 오류. 메일은 전송되지 않았습니다. "
                "서버 호스트·포트·TLS 설정을 확인하세요.")
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "SMTP 인증서 검증 실패. 메일은 전송되지 않았습니다. 서버 TLS 설정을 확인하세요."
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return (f"SMTP {stage} 단계 응답 시간 초과/연결 실패. "
                "메일은 전송되지 않았습니다. 서버 연결을 확인하세요.")
    if isinstance(exc, smtplib.SMTPResponseException):
        code = getattr(exc, "smtp_code", None)
        number = f" (SMTP {code})" if type(code) is int else ""
        return (f"SMTP {stage} 단계 서버 거부"+number+". "
                "메일은 전송되지 않았습니다. 서버 정책을 확인하세요.")
    return (f"SMTP {stage} 단계 오류. 메일은 전송되지 않았습니다. "
            "발송 대기의 'SMTP 연결·로그인 진단'에서 확인하세요.")

def email_address(value: str) -> str:
    raw=str(value or "").strip()
    if not raw or any(c in raw for c in ("\r","\n","\x00",",",";")):
        raise ValueError("유효한 이메일 주소 하나만 입력해 주세요.")
    _display,addr=parseaddr(raw)
    if not ADDRESS.fullmatch(addr) or raw.count("@")!=1:
        raise ValueError("유효한 이메일 주소 하나만 입력해 주세요.")
    if raw!=addr and not (raw.endswith(">") and "<" in raw):
        raise ValueError("수신 이메일 주소를 다시 확인해 주세요.")
    return addr.lower()

def valid_message_id(value: str) -> str:
    raw=str(value or "").strip()
    return raw if len(raw)<255 and MESSAGE_ID.fullmatch(raw) else ""

def _owner(principal: str) -> str:
    return email_address(principal)

def _repo(env: dict):
    try:
        return ContractRepository(env)
    except Exception:
        raise OutboxError("MASTER Supabase 비공개 메일 보관 설정을 확인해 주세요.") from None

def _safe_id(ident: str) -> str:
    try:
        return str(UUID(str(ident)))
    except (TypeError,ValueError):
        raise OutboxError("답장 식별자가 유효하지 않습니다.") from None

def _rows(env: dict, principal: str, *, ident: str | None = None, limit=100):
    filters=[("owner_email","eq."+_owner(principal)),
             ("order","created_at.desc"),("limit",str(limit))]
    if ident is not None:
        filters.append(("id","eq."+_safe_id(ident)))
    try:
        rows=_repo(env).request("GET",TABLE,query=filters)
    except Exception:
        raise OutboxError("비공개 발송 대기함을 조회하지 못했습니다.") from None
    return rows if isinstance(rows,list) else []

def list_replies(env:dict,principal:str):
    return _rows(env,principal)

def get_reply(env:dict,principal:str,ident:str):
    rows=_rows(env,principal,ident=ident,limit=1)
    if not rows:
        raise OutboxError("이 메일을 조회할 권한이 없거나 삭제되었습니다.")
    return rows[0]

def queue_reply(env:dict,principal:str,source:dict,config_values:dict):
    """Store an incoming email once after explicit AI intake routing."""
    owner=_owner(principal)
    config=mail_config(config_values,owner)
    if config.pop is None:
        raise OutboxError("현재 메일함의 POP 연결 설정이 필요합니다.")
    uid=str(source.get("uid") or "").strip()
    sender=str(source.get("sender") or "")
    subject=str(source.get("subject") or "")
    body=str(source.get("body") or "")
    if not uid or len(uid)>500 or not body.strip() or len(body)>20000:
        raise OutboxError("선택한 메일의 원문 정보가 불완전합니다.")
    recipient=email_address(sender)
    try:
        reply_subject(subject)
    except ValueError:
        raise OutboxError("메일 제목을 확인해 주세요.") from None
    record={
        "owner_email":owner,"mailbox_hash":config.pop.account_id,
        "mail_uid":uid,"sender_header":sender[:500],"recipient_email":recipient,
        "source_subject":subject[:250],"source_body":body,
        "source_hash":source_hash(uid,sender,subject,body),
        "message_id":valid_message_id(source.get("message_id")),
        "language":preferred_language(subject,body),
    }
    try:
        _repo(env).request("POST",TABLE,payload=record,query=[
            ("on_conflict","owner_email,mailbox_hash,mail_uid")],
            headers={"Prefer":"resolution=ignore-duplicates,return=minimal"})
        matching=_repo(env).request("GET",TABLE,query=[
            ("owner_email","eq."+owner),("mailbox_hash","eq."+config.pop.account_id),
            ("mail_uid","eq."+uid),("limit","1")])
    except Exception:
        raise OutboxError("메일을 발송 대기함에 저장하지 못했습니다.") from None
    if not isinstance(matching,list) or not matching:
        raise OutboxError("발송 대기함 저장 결과를 확인할 수 없습니다.")
    return matching[0]

def save_candidates(env:dict,principal:str,ident:str,candidates:list[str],language:str):
    from Quotation_KEKOREA.orchestration.workflows.email_reply_drafts import _validated_candidates
    bodies=_validated_candidates([{"body":s} for s in candidates])
    if language not in {"ko","en"}:
        raise OutboxError("회신 언어가 유효하지 않습니다.")
    row=get_reply(env,principal,ident)
    if row["status"]!="draft":
        raise OutboxError("이미 발송 처리가 시작된 메일은 수정할 수 없습니다.")
    try:
        updated=_repo(env).request("PATCH",TABLE,
            payload={"candidate_bodies":bodies,"language":language},
            query=[("id","eq."+_safe_id(ident)),("owner_email","eq."+_owner(principal)),
                   ("status","eq.draft"),("source_hash","eq."+row["source_hash"])],
            headers={"Prefer":"return=representation"})
    except Exception:
        raise OutboxError("답장 후보를 저장하지 못했습니다.") from None
    if not isinstance(updated,list) or len(updated)!=1:
        raise OutboxError("다른 창에서 메일이 변경되었습니다. 다시 불러오세요.")
    return updated[0]

def _validate_message(to_addr:str,subject:str,body:str):
    recipient=email_address(to_addr)
    subject=str(subject or "").strip()
    body=str(body or "").strip()
    if not subject or len(subject)>240 or any(c in subject for c in ("\r","\n","\x00")):
        raise OutboxError("발송 제목이 유효하지 않습니다.")
    if not body or len(body)>12000 or "\x00" in body:
        raise OutboxError("발송 본문을 확인해 주세요.")
    return recipient,subject,body

def send_smtp(config,recipient:str,subject:str,body:str,message_id:str="",*,
              html_body:str|None=None,logo_bytes:bytes|None=None):
    """One SMTP send, only after atomic owner-confirmed DB claim.

    Any connection/TLS/auth/composition failure that occurs BEFORE calling
    send_message is provably unsent. Once send_message starts, all failures
    remain ambiguous to prevent unsafe duplicate mail.
    """
    if config.smtp is None:
        raise SMTPBeforeDataError(
            "SMTP 발신 서버 연결 설정이 필요합니다. 메일을 전송하지 않았습니다.",
            stage="configuration")
    client = None
    stage = "composition"
    try:
        from_addr=email_address(config.smtp.username)
        email=EmailMessage()
        email["From"]=from_addr
        email["To"]=recipient
        email["Subject"]=subject
        msg_id=valid_message_id(message_id)
        if msg_id:
            email["In-Reply-To"]=msg_id
            email["References"]=msg_id
        email.set_content(body)
        if html_body is not None:
            from Quotation_KEKOREA.orchestration.workflows.email_signature_design import LOGO_CID
            if not logo_bytes or not logo_bytes.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
                raise OutboxError("KE KOREA 로고 파일을 확인할 수 없습니다.")
            if "cid:" + LOGO_CID not in html_body:
                raise OutboxError("서명의 회사 로고 연결이 올바르지 않습니다.")
            email.add_alternative(html_body, subtype="html")
            html_part=email.get_body(preferencelist=("html",))
            html_part.add_related(logo_bytes,maintype="image",subtype="png",
                                  cid="<"+LOGO_CID+">",disposition="inline",
                                  filename="ke-korea-logo.png")
        tls=ssl.create_default_context()
        stage="connect"
        if config.smtp.security=="ssl":
            client=smtplib.SMTP_SSL(config.smtp.host,config.smtp.port,timeout=20,context=tls)
        elif config.smtp.security=="starttls":
            client=smtplib.SMTP(config.smtp.host,config.smtp.port,timeout=20)
            stage="ehlo"
            client.ehlo()
            stage="starttls"
            client.starttls(context=tls)
            stage="ehlo_tls"
            client.ehlo()
        else:
            raise OutboxError("SMTP 암호화 연결만 허용합니다.")
        stage="login"
        client.login(config.smtp.username,config.smtp.password)
        stage="send_message"
        result=client.send_message(email)
        if result:
            # Some recipients might have been accepted. Never retry.
            raise OutboxError("SMTP에서 일부 수신자가 거부됐습니다. 실제 전송 여부를 확인하세요.")
    except Exception as exc:
        if stage!="send_message":
            raise SMTPBeforeDataError(_predata_message(stage,exc),stage=stage) from None
        # After entering send_message, including DATA/timeout/disconnect,
        # the server may already have accepted it.
        raise OutboxError(
            "SMTP 메일 전송 처리 후 결과가 불명확합니다. 중복 발송하지 말고 "
            "실제 보낸편지함 또는 수신함을 확인하세요."
        ) from None
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass

def send_approved(env:dict,principal:str,ident:str,config_values:dict,
                  recipient:str,subject:str,body:str,*,confirmed:bool=False,
                  signature_text:str|None=None,language:str|None=None,
                  transport=send_smtp):
    """No call without a real user's send-button click and confirmation."""
    if confirmed is not True:
        raise OutboxError("발송 전 최종 확인 체크가 필요합니다.")
    owner=_owner(principal)
    config=mail_config(config_values,owner)
    if config.pop is None or config.smtp is None:
        raise OutboxError("메일 수신·발신 설정을 확인하세요.")
    row=get_reply(env,owner,ident)
    if row["mailbox_hash"]!=config.pop.account_id:
        raise OutboxError("메일함 계정이 변경됐습니다. 발송하지 않았습니다.")
    # Manual drafting is allowed when the AI service is unavailable. Both
    # manual and AI-assisted replies require the same explicit owner approval.
    # Reject partially written candidate bundles rather than guessing intent.
    if row["status"]!="draft" or len(row.get("candidate_bodies") or []) not in (0,3):
        raise OutboxError("이 메일은 수정 가능한 DRAFT 상태가 아닙니다.")
    recipient,subject,body=_validate_message(recipient,subject,body)
    html_body=None
    logo_bytes=None
    if signature_text is not None:
        from Quotation_KEKOREA.orchestration.workflows.email_signature_design import (
            optimized_logo, delivery_signature_html,
        )
        signature=str(signature_text).strip()
        if language not in ("ko","en") or not signature or not body.endswith("\n\n"+signature):
            raise OutboxError("현재 승인할 메일 본문과 서명이 일치하지 않습니다.")
        reply_text=body[:-(len(signature)+2)]
        if not reply_text.strip():
            raise OutboxError("회신 본문을 작성해 주세요.")
        # Resolve the logo and email HTML BEFORE claiming a send, so a
        # missing/corrupt asset cannot create an uncertain outbound attempt.
        try:
            logo_bytes=optimized_logo()
            html_body=delivery_signature_html(reply_text,signature)
        except (ValueError,OSError,RuntimeError):
            raise OutboxError("KE KOREA 이메일 서명 디자인을 준비하지 못했습니다.") from None
    digest=sha256((recipient+"\0"+subject+"\0"+body).encode("utf-8")).hexdigest()
    repo=_repo(env)
    stamp=datetime.now(timezone.utc).isoformat()
    try:
        claimed=repo.request("PATCH",TABLE,payload={
            "status":"sending","recipient_email":recipient,
            "approved_subject":subject,"approved_body":body,
            "approved_sha256":digest,"send_started_at":stamp},
            query=[("id","eq."+_safe_id(ident)),("owner_email","eq."+owner),
                   ("mailbox_hash","eq."+config.pop.account_id),("status","eq.draft")],
            headers={"Prefer":"return=representation"})
    except Exception:
        raise OutboxError("발송 승인 기록을 저장하지 못했습니다. 실제 메일은 보내지 않았습니다.") from None
    if not isinstance(claimed,list) or len(claimed)!=1:
        raise OutboxError("다른 창에서 발송이 시작됐습니다. 중복 발송하지 않습니다.")
    status="sent"
    before_data_error = None
    try:
        if html_body is None:
            transport(config,recipient,subject,body,row.get("message_id") or "")
        else:
            transport(config,recipient,subject,body,row.get("message_id") or "",
                      html_body=html_body,logo_bytes=logo_bytes)
    except SMTPBeforeDataError as error:
        # No SMTP DATA was attempted. Restore the single draft atomically,
        # clearing approval and send-start. An existing ambiguous attempt
        # from an earlier run is NEVER restored or retried here.
        before_data_error = error
        status="draft"
    except Exception:
        status="send_unknown"
    if before_data_error is not None:
        try:
            restored=repo.request("PATCH",TABLE,payload={
                "status":"draft", "send_started_at":None, "sent_at":None,
                "approved_sha256":None, "approved_subject":None,
                "approved_body":None},
                query=[("id","eq."+_safe_id(ident)),("owner_email","eq."+owner),
                       ("status","eq.sending"),("approved_sha256","eq."+digest)],
                headers={"Prefer":"return=representation"})
        except Exception:
            raise OutboxError("SMTP 발신 전 오류가 발생했고 DRAFT 복구를 확인하지 못했습니다. "
                              "중복 발송하지 말고 운영 상태를 확인하세요.") from None
        if not isinstance(restored,list) or len(restored)!=1:
            raise OutboxError("SMTP 발신 전 오류가 발생했지만 DRAFT 상태를 확인하지 못했습니다. "
                              "다시 발송하지 말고 관리자에게 확인하세요.")
        raise before_data_error
    try:
        finished=repo.request("PATCH",TABLE,payload={
            "status":status,"sent_at":datetime.now(timezone.utc).isoformat() if status=="sent" else None},
            query=[("id","eq."+_safe_id(ident)),("owner_email","eq."+owner),
                   ("status","eq.sending"),("approved_sha256","eq."+digest)],
            headers={"Prefer":"return=representation"})
    except Exception:
        raise OutboxError("발송 상태 저장 실패: 전송 여부 불확실. 재발송하지 말고 보낸편지함을 확인하세요.") from None
    if not isinstance(finished,list) or len(finished)!=1:
        raise OutboxError("발송 상태 확인 실패: 전송 여부 불확실. 재발송하지 말고 보낸편지함을 확인하세요.")
    if status!="sent":
        raise OutboxError("발송 결과가 불확실합니다. 자동 재시도하지 않습니다. 보낸편지함을 확인하세요.")
    return {"status":"sent","id":_safe_id(ident)}
