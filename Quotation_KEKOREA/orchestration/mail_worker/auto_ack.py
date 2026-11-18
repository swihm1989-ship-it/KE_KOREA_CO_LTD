"""Opt-in, allowlisted, idempotent Whois receipt acknowledgements.

This is NOT AI negotiation or automated trade-document approval. Inbound text
never becomes the reply body. SMTP sending is disabled unless TWO owner-only
environment switches are enabled in the separately deployed mail worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
import re
import smtplib
import ssl

from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailConnectionError

ADDRESS = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
MESSAGE_ID = re.compile(r"^<[^<>\s@]+@[^<>\s@]+>$")
MAX_PER_RUN = 3
MAX_PER_DAY = 10

@dataclass(frozen=True)
class AckPolicy:
    allowed_senders: frozenset[str]
    not_before: datetime
    daily_limit: int = 5

@dataclass(frozen=True)
class Ack:
    recipient: str
    subject: str
    body: str
    in_reply_to: str

def _single_address(value):
    if not isinstance(value, str) or "\r" in value or "\n" in value or "," in value:
        return ""
    name, address = parseaddr(value)
    if not ADDRESS.fullmatch(address) or address != address.strip():
        return ""
    return address.casefold()

def _date(value):
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if date.tzinfo is None:
        return None
    return date.astimezone(timezone.utc)

def load_policy(values, config):
    """No opt-in, no sending. Reject partial or overly broad configuration."""
    if (str(values.get("MAIL_AUTO_ACK_ENABLED", "")).lower() != "true" or
            str(values.get("MAIL_AUTO_ACK_SEND_ENABLED", "")).lower() != "true"):
        return None
    if config.smtp is None or config.pop is None:
        raise RuntimeError("Auto ack requires dedicated POP and SMTP configuration")
    if _single_address(config.smtp.username) != _single_address(config.pop.username):
        raise RuntimeError("Auto ack requires identical POP/SMTP mailbox identities")
    members = [s.strip() for s in str(values.get("MAIL_AUTO_ACK_ALLOWED_SENDERS", "")).split(",") if s.strip()]
    if not members or len(members) > 50:
        raise RuntimeError("Auto ack requires 1-50 explicit sender addresses")
    parsed = [_single_address(s) for s in members]
    if not all(parsed) or len(set(parsed)) != len(parsed):
        raise RuntimeError("Auto ack sender allowlist must contain unique exact emails")
    text = str(values.get("MAIL_AUTO_ACK_NOT_BEFORE", "")).strip()
    try:
        start = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if start.tzinfo is None:
            raise ValueError()
        start = start.astimezone(timezone.utc)
        daily = int(values.get("MAIL_AUTO_ACK_DAILY_LIMIT", 5))
    except (ValueError, TypeError):
        raise RuntimeError("Auto ack start time/limit configuration is invalid") from None
    if not 1 <= daily <= MAX_PER_DAY:
        raise RuntimeError("Auto ack daily limit must be 1-10")
    return AckPolicy(frozenset(parsed), start, daily)

def make_ack(message, mailbox_address, policy, *, now=None):
    """Conservative non-transactional decision; database gives exactly-once claim."""
    now = now or datetime.now(timezone.utc)
    if not policy or not getattr(message, "uid", "") or not getattr(message, "body", "").strip():
        return None
    if getattr(message, "notice", "") or getattr(message, "attachments", ()):
        # Trade attachments always require review; never acknowledge blindly.
        return None
    sender = _single_address(getattr(message, "sender", ""))
    destination = _single_address(getattr(message, "reply_to", "") or getattr(message, "sender", ""))
    own = _single_address(mailbox_address)
    if not sender or sender not in policy.allowed_senders or destination != sender or sender == own:
        return None
    msg_id = str(getattr(message, "message_id", "")).strip()
    if not MESSAGE_ID.fullmatch(msg_id):
        return None
    if (str(getattr(message, "auto_submitted", "")).strip().casefold() not in ("", "no")
            or getattr(message, "list_id", "")
            or str(getattr(message, "precedence", "")).casefold() in ("bulk", "junk", "list")):
        return None
    if any(word in sender.split("@", 1)[0] for word in ("no-reply", "noreply", "mailer-daemon", "postmaster")):
        return None
    sent_at = _date(getattr(message, "received_at", ""))
    if sent_at is None or sent_at < policy.not_before or sent_at > now + timedelta(minutes=10):
        return None
    # Never auto-respond to messages over 15 minutes old, even after cold starts.
    if now - sent_at > timedelta(minutes=15):
        return None
    subject = str(getattr(message, "subject", "")).strip()
    if not subject or len(subject) > 150 or "\r" in subject or "\n" in subject:
        return None
    subject = subject if subject.casefold().startswith("re:") else "Re: " + subject
    is_korean = bool(re.search(r"[가-힣]", subject + message.body[:400]))
    body = (
        "안녕하세요.\n\n메일을 정상적으로 접수했습니다. 내용을 확인한 뒤 담당자가 회신드리겠습니다.\n"
        "이 안내는 견적, 납기, 계약 또는 주문의 승인을 의미하지 않습니다.\n\n"
        "KE KOREA CO. LTD\n(자동 접수 회신)"
        if is_korean else
        "Hello,\n\nWe have received your message. A team member will review it and respond.\n"
        "This acknowledgement is not a quotation, delivery commitment, contract acceptance, or order confirmation.\n\n"
        "KE KOREA CO. LTD\n(Automated receipt acknowledgement)"
    )
    return Ack(sender, subject, body, msg_id)

def send_ack(smtp_endpoint, ack):
    """TLS-only SMTP. Any uncertain failure is treated as send_unknown by caller."""
    if not isinstance(ack, Ack) or not ADDRESS.fullmatch(ack.recipient):
        raise MailConnectionError("Invalid automatic acknowledgement")
    sender = _single_address(smtp_endpoint.username)
    if not sender or "\n" in ack.subject or "\r" in ack.subject or not MESSAGE_ID.fullmatch(ack.in_reply_to):
        raise MailConnectionError("Invalid acknowledgement headers")
    email = EmailMessage()
    email["From"] = sender
    email["To"] = ack.recipient
    email["Subject"] = ack.subject
    email["In-Reply-To"] = ack.in_reply_to
    email["References"] = ack.in_reply_to
    email["Auto-Submitted"] = "auto-replied"
    email["X-Auto-Response-Suppress"] = "All"
    email.set_content(ack.body)
    client = None
    try:
        context = ssl.create_default_context()
        if smtp_endpoint.security == "ssl":
            client = smtplib.SMTP_SSL(smtp_endpoint.host, smtp_endpoint.port, timeout=12, context=context)
        elif smtp_endpoint.security == "starttls":
            client = smtplib.SMTP(smtp_endpoint.host, smtp_endpoint.port, timeout=12)
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        else:
            raise MailConnectionError("TLS required for automatic acknowledgements")
        client.login(smtp_endpoint.username, smtp_endpoint.password)
        client.send_message(email)
    except Exception:
        # Never include provider response text, mailbox address or credentials.
        raise MailConnectionError("Automatic reply SMTP outcome uncertain; manual review required") from None
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass

ENQUEUE = """insert into ke_mail_agent.auto_reply_intents
    (account,uidl,recipient,subject,body,in_reply_to)
    values (%s,%s,%s,%s,%s,%s) on conflict(account,uidl) do nothing"""

CLAIM = """update ke_mail_agent.auto_reply_intents
    set status='claimed',claimed_at=now()
    where id=(select id from ke_mail_agent.auto_reply_intents
        where account=%s and status='pending'
          and created_at >= now() - interval '15 minutes'
        order by id for update skip locked limit 1)
    returning id,recipient,subject,body,in_reply_to"""

def dispatch_pending(values, config, connect=None, sender=send_ack):
    """Single account-level rate gate plus one-shot claim BEFORE sending.

    Claimed/unknown messages are NEVER automatically retried, including after
    process crashes or mail server response loss. Reconcile with Sent folder.
    """
    policy = load_policy(values, config)
    if policy is None:
        return {"sent": 0, "unknown": 0, "claimed": 0}
    if connect is None:
        from psycopg import connect as connect
    account = config.pop.account_id
    counts = {"sent": 0, "unknown": 0, "claimed": 0}
    with connect(values["DATABASE_URL"], connect_timeout=10) as db:
        for _ in range(MAX_PER_RUN):
            with db.transaction():
                with db.cursor() as cur:
                    cur.execute("select pg_advisory_xact_lock(hashtext(%s))", (account,))
                    cur.execute("""select count(*) from ke_mail_agent.auto_reply_intents
                        where account=%s and created_at >= now()-interval '24 hours'
                          and status in ('claimed','sent','send_unknown')""", (account,))
                    if cur.fetchone()[0] >= policy.daily_limit:
                        break
                    cur.execute(CLAIM, (account,))
                    row = cur.fetchone()
            if row is None:
                break
            ident, recipient, subject, body, in_reply_to = row
            counts["claimed"] += 1
            status = "sent"
            try:
                sender(config.smtp, Ack(recipient, subject, body, in_reply_to))
            except Exception:
                status = "send_unknown"
            # If DB update fails, the claimed row remains and will not retry.
            with db.transaction():
                with db.cursor() as cur:
                    cur.execute("""update ke_mail_agent.auto_reply_intents
                        set status=%s, finished_at=now()
                        where id=%s and status='claimed'""", (status, ident))
            counts["sent" if status == "sent" else "unknown"] += 1
    return counts
