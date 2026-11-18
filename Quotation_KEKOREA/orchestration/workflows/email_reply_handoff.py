"""Resilient mailbox -> draft-outbox handoff.

Always persist the incoming email BEFORE attempting optional AI generation.
Model failures can never erase or block the saved draft; only the owner can send.
This module has no SMTP calls and requires explicit AI consent from the caller.
"""
from __future__ import annotations

from pathlib import Path

REPLY_RUNTIME_REVISION = "master-reply-20261118-http400-schema-v2"
REPLY_SOURCE_MTIME_NS = Path(__file__).stat().st_mtime_ns

from Quotation_KEKOREA.orchestration.workflows.email_outbox import (
    queue_reply, save_candidates,
)
from Quotation_KEKOREA.orchestration.workflows.email_reply_drafts import (
    generate_candidates,
)


def prepare_email_handoff(
    db_env, principal, mail_source, mailbox_settings, model_config, language,
    *, ai_consented: bool, queue=queue_reply,
    generate=generate_candidates, save=save_candidates,
):
    """Return (persisted_draft_row, ai_failure_notice).

    If saving the email fails, that failure propagates; nothing pretends it was
    queued. If AI generation or candidate persistence fails, the already
    queued draft survives. The caller can show a warning in the outbox.
    """
    row = queue(db_env, principal, mail_source, mailbox_settings)
    if row.get("candidate_bodies") or not ai_consented:
        return row, None
    try:
        suggestions = generate(mail_source, model_config, language)
        save(db_env, principal, row["id"], suggestions, language)
    except (ValueError, RuntimeError) as exc:
        return row, str(exc)
    except Exception:
        return row, "AI 회신 후보를 생성하거나 저장하지 못했습니다. 발송 대기에서 다시 시도하세요."
    return row, None
