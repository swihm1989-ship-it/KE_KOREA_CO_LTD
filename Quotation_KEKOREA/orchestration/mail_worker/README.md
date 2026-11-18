# Separate mail-only worker (not started or deployed until credentials,
# database DSN, and paid scheduler are explicitly approved).
# Required environment variables in the future Render Cron service:
# MAIL_WORKER_ENABLED=true
# MAIL_WORKER_PRINCIPAL=<authorized Master login email>
# WHOIS_MAIL_OWNER_EMAILS=<same authorized login>
# WHOIS_POP_HOST=pop.whoisworks.com
# WHOIS_POP_PORT=995
# WHOIS_POP_SECURITY=ssl
# WHOIS_POP_USERNAME=<actual mailbox address>
# WHOIS_POP_PASSWORD=<enter privately in Render>
# DATABASE_URL=<server-only Postgres URI, never Streamlit UI or GitHub>
# No SMTP secret required. No SMTP sending implemented.
#
# Suggested command:
# python -m Quotation_KEKOREA.orchestration.mail_worker.ingest
# Suggested Render cron schedule: * * * * * (UTC; potential charges).
# Each one-shot read is at most five latest messages, de-duped by UIDL.
# A durable cursor/pagination is required before production high-volume use.


## Opt-in automatic receipt acknowledgements (not AI negotiations)
The existing worker is read-only until BOTH MAIL_AUTO_ACK_ENABLED=true and
MAIL_AUTO_ACK_SEND_ENABLED=true are set privately for its cron process. Default:
OFF. No Streamlit UI action sends mail. Add a private, dedicated worker only
after verifying POP3, SMTP, and database migrations; code merge does not deploy
a cron service or enable mail sending. Before the first enabled run, apply
\`schema.sql\` in a backed-up database (adds RFC headers and a separate
RLS-protected \`auto_reply_intents\` table).

Mandatory private settings:
- MAIL_AUTO_ACK_ALLOWED_SENDERS=buyer@example.com,partner@example.com
  (exact email addresses only, never wildcards or domains)
- MAIL_AUTO_ACK_NOT_BEFORE=2026-11-18T12:00:00+09:00
  (set to actual rollout time; dates outside the last 15 minutes do not send)
- MAIL_AUTO_ACK_DAILY_LIMIT=5 (1..10; at most 3 per worker run)
- WHOIS_SMTP_* TLS credentials. POP/SMTP mailbox addresses must match exactly.

Only newly inserted POP3 messages are considered. Never reply to own
messages, no-reply accounts, mailing lists, auto-generated messages, messages
with attachments, missing Message-ID, unknown dates, stale messages, mismatched
Reply-To, or non-allowlisted senders. All replies contain a FIXED acknowledgement
that neither offers a price nor approves any transaction. No inbound email
text is sent to an AI provider. Ingest->enqueue transaction is unique on
(account,uidl); one-shot claim is persisted BEFORE SMTP, and ambiguous
outcomes are marked send_unknown. Do not automatically retry claimed or unknown
messages; compare the actual Sent folder before manual reconciliation.
The worker prints only counts. A successful simulated test is not proof of
real transport or deployment. This is not a content-aware AI reply system.
