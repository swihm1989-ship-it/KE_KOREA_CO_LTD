"""One-shot, read-only Whois mail ingestion for a separately deployed scheduler.

Requires an explicitly enabled worker. Does not send email, call LLMs,
or modify POP3 messages. Stores only text and attachment names in a
private database schema. The sender can later submit drafts for review.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

from Quotation_KEKOREA.orchestration.adapters.whois_mail import (
    MailConnectionError, mail_config, fetch_messages,
)
from Quotation_KEKOREA.orchestration.mail_worker.auto_ack import (
    ENQUEUE, dispatch_pending, load_policy, make_ack,
)

INSERT = """
insert into ke_mail_agent.inbox
(account,uidl,sender,subject,received_at,body,attachment_names,message_id,
 reply_to,auto_submitted,list_id,precedence,status)
values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
on conflict(account,uidl) do nothing
returning id
"""

def record_from_message(account, message):
    attachments = [attachment.filename for attachment in message.attachments]
    return (
        account,
        message.uid,
        message.sender,
        message.subject,
        message.received_at,
        message.body,
        json.dumps(attachments, ensure_ascii=False),
        message.message_id, message.reply_to, message.auto_submitted,
        message.list_id, message.precedence,
        "review_needed" if message.notice or not message.body else "unreviewed",
    )


def run(environ=None, connect=None, fetch=fetch_messages):
    values = dict(os.environ if environ is None else environ)
    if values.get("MAIL_WORKER_ENABLED", "").lower() != "true":
        return {"status": "disabled", "new": 0}
    required = ("DATABASE_URL", "MAIL_WORKER_PRINCIPAL")
    missing = [k for k in required if not values.get(k)]
    if missing:
        raise RuntimeError("Missing mail worker configuration: " + ", ".join(missing))
    config = mail_config(values, values["MAIL_WORKER_PRINCIPAL"])
    if config.pop is None:
        raise RuntimeError("Missing Whois POP configuration")
    policy = load_policy(values, config)
    if connect is None:
        from psycopg import connect as connect
    messages = fetch(config.pop, limit=5)
    account = config.pop.account_id
    inserted = 0
    with connect(values["DATABASE_URL"], connect_timeout=10) as db:
        with db.transaction():
            for message in messages:
                with db.cursor() as cur:
                    cur.execute(INSERT, record_from_message(account, message))
                    fresh = cur.fetchone()
                    if fresh is not None:
                        inserted += 1
                        # Only newly collected messages may enter the auto-ack
                        # queue, and only with both explicit opt-in switches.
                        if policy is not None:
                            ack = make_ack(message, config.smtp.username, policy)
                            if ack is not None:
                                cur.execute(ENQUEUE, (
                                    account, message.uid, ack.recipient, ack.subject,
                                    ack.body, ack.in_reply_to,
                                ))
            with db.cursor() as cur:
                cur.execute(
                    """insert into ke_mail_agent.poll_runs
                       (completed_at,result,count_seen,count_new,note)
                       values (%s,%s,%s,%s,%s)""",
                    (datetime.now(timezone.utc), "success",
                     len(messages), inserted, "POP3 read-only batch"),
                )
    result = {"status": "success", "new": inserted, "seen": len(messages)}
    if policy is not None:
        # Worker-only send path: never called by Streamlit or its refresh button.
        result["auto_ack"] = dispatch_pending(values, config, connect=connect)
    return result


def main():
    # Never print subjects, email addresses, message bodies, passwords or DB URL.
    try:
        result = run()
        print("MAIL_WORKER", result)
    except (RuntimeError, MailConnectionError):
        print("MAIL_WORKER failed (configuration or mailbox transport)")
        raise SystemExit(1) from None
    except Exception:
        print("MAIL_WORKER failed (database or unexpected error)")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
