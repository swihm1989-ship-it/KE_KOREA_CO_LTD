"""Owner-scoped, durable mail reply drafts and explicitly approved SMTP sending.

No timers, cron, poller or automatic sending. The ONLY path to SMTP is a
successful owner-confirmed click on the Streamlit send button.
"""
from __future__ import annotations
from datetime import datetime, timezone
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

TABLE="kekorea_master_mail_outbox"
ADDRESS=re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
MESSAGE_ID=re.compile(r"^<[^<>\s@]+@[^<>\s@]+>$")

class OutboxError(RuntimeError):
    pass

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

def send_smtp(config,recipient:str,subject:str,body:str,message_id:str=""):
    """Actual transport, exclusively after an atomic user-approved claim."""
    if config.smtp is None:
        raise OutboxError("SMTP 발신 서버 연결 설정이 필요합니다.")
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
    client=None
    try:
        tls=ssl.create_default_context()
        if config.smtp.security=="ssl":
            client=smtplib.SMTP_SSL(config.smtp.host,config.smtp.port,timeout=20,context=tls)
        elif config.smtp.security=="starttls":
            client=smtplib.SMTP(config.smtp.host,config.smtp.port,timeout=20)
            client.ehlo()
            client.starttls(context=tls)
            client.ehlo()
        else:
            raise OutboxError("SMTP 암호화 연결만 허용합니다.")
        client.login(config.smtp.username,config.smtp.password)
        client.send_message(email)
    except Exception:
        raise OutboxError("SMTP 결과를 확인할 수 없습니다. 보낸편지함에서 확인하세요.") from None
    finally:
        if client is not None:
            try:client.quit()
            except Exception:
                try:client.close()
                except Exception:pass

def send_approved(env:dict,principal:str,ident:str,config_values:dict,
                  recipient:str,subject:str,body:str,*,confirmed:bool=False,
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
    if row["status"]!="draft" or len(row.get("candidate_bodies") or [])!=3:
        raise OutboxError("발송할 AI 후보를 먼저 선택하고 수정해 주세요.")
    recipient,subject,body=_validate_message(recipient,subject,body)
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
    try:
        transport(config,recipient,subject,body,row.get("message_id") or "")
    except Exception:
        status="send_unknown"
    try:
        repo.request("PATCH",TABLE,payload={
            "status":status,"sent_at":datetime.now(timezone.utc).isoformat() if status=="sent" else None},
            query=[("id","eq."+_safe_id(ident)),("owner_email","eq."+owner),
                   ("status","eq.sending"),("approved_sha256","eq."+digest)],
            headers={"Prefer":"return=representation"})
    except Exception:
        raise OutboxError("발송 상태 저장 실패: 전송 여부 불확실. 재발송하지 말고 보낸편지함을 확인하세요.") from None
    if status!="sent":
        raise OutboxError("발송 결과가 불확실합니다. 자동 재시도하지 않습니다. 보낸편지함을 확인하세요.")
    return {"status":"sent","id":_safe_id(ident)}
