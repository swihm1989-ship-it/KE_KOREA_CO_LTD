"""Explicitly opted-in, single-use REAL Resend delivery probe.

Enabled only by KEKOREA_RESEND_ONE_SHOT_ID in the Render service. The
record must exist in the private MASTER outbox with this ID, test recipient
and draft status. A single conditional database claim is consumed BEFORE
the Resend call; process restarts cannot repeat it. Never sends routine
customer email. The probe should be disabled immediately after testing.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import urllib.error
import urllib.request
from uuid import UUID

from Quotation_KEKOREA.contracts.repository import ContractRepository
from Quotation_KEKOREA.orchestration.workflows.email_outbox import (
    SMTPBeforeDataError, send_resend_https,
)

RECIPIENT = "swihm1989@gmail.com"
OWNER = "david.ihm@ke-korea.com"
SUBJECT = "[KE KOREA MASTER TEST] Resend actual delivery verification"
BODY = (
    "This is an explicitly authorized one-time real email delivery test "
    "from master.ke-korea.co.kr using the Resend HTTPS transport.\n"
    "No commercial document or customer data is attached.\n"
    "Test date: 2026-11-19.\n"
)
TABLE = "kekorea_master_mail_outbox"


def _repo():
    return ContractRepository(dict(os.environ))


def run():
    raw = os.environ.get("KEKOREA_RESEND_ONE_SHOT_ID", "").strip()
    if not raw:
        return
    try:
        ident = str(UUID(raw))
    except ValueError:
        print("RESEND_SMOKE invalid_test_id", flush=True)
        return
    if not os.environ.get("RESEND_API_KEY", "").strip():
        print("RESEND_SMOKE missing_RESEND_API_KEY_no_send", flush=True)
        return
    if os.environ.get("RESEND_FROM_EMAIL", "").strip().lower() != OWNER:
        print("RESEND_SMOKE missing_valid_sender_no_send", flush=True)
        return
    if os.environ.get("MAIL_DELIVERY_TRANSPORT", "").strip().lower() != "resend":
        print("RESEND_SMOKE incorrect_transport_no_send", flush=True)
        return
    try:
        repo = _repo()
        claim = repo.request(
            "PATCH", TABLE,
            payload={
                "status": "sending",
                "approved_subject": SUBJECT,
                "approved_body": BODY,
                "send_started_at": datetime.now(timezone.utc).isoformat(),
            },
            query=[
                ("id", "eq." + ident),
                ("owner_email", "eq." + OWNER),
                ("recipient_email", "eq." + RECIPIENT),
                ("mail_uid", "eq.render-resend-smoke-20261119"),
                ("status", "eq.draft"),
            ],
            headers={"Prefer": "return=representation"},
        )
    except Exception:
        print("RESEND_SMOKE database_claim_error_no_send", flush=True)
        return
    if not isinstance(claim, list) or len(claim) != 1:
        print("RESEND_SMOKE already_claimed_no_repeat", flush=True)
        return
    status = "send_unknown"
    message = "unknown"
    provider_id = ""
    try:
        provider_id = send_resend_https(None, RECIPIENT, SUBJECT, BODY)
        if provider_id:
            status = "sent"
            message = "provider_accepted"
    except SMTPBeforeDataError as exc:
        # A definitive 4xx rejection cannot be interpreted as a delivery.
        message = "provider_rejected_" + str(exc.stage)
    except Exception as exc:
        # Network timeouts / non-4xx errors may already have been accepted.
        message = "provider_outcome_uncertain_" + type(exc).__name__
    try:
        saved = repo.request(
            "PATCH", TABLE,
            payload={
                "status": status,
                "sent_at": datetime.now(timezone.utc).isoformat() if status == "sent" else None,
            },
            query=[
                ("id", "eq." + ident),
                ("owner_email", "eq." + OWNER),
                ("status", "eq.sending"),
            ],
            headers={"Prefer": "return=representation"},
        )
        print("RESEND_SMOKE " + message +
              (" db_saved" if isinstance(saved,list) and len(saved)==1 else " db_unconfirmed"),
              flush=True)
    except Exception:
        print("RESEND_SMOKE " + message + " db_update_error", flush=True)
    if not provider_id:
        return
    # Provider events can lag delivery; look them up but do not retry a send.
    url = "https://api.resend.com/emails/" + provider_id
    for _ in range(2):
        try:
            request = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
                "Accept": "application/json",
            }, method="GET")
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            event = str(data.get("last_event", "unknown"))
            if event not in ("delivered", "failed", "bounced"):
                continue
            print("RESEND_SMOKE provider_last_event=" + event, flush=True)
            break
        except Exception:
            print("RESEND_SMOKE provider_event_unavailable", flush=True)
            break


if __name__ == "__main__":
    run()
