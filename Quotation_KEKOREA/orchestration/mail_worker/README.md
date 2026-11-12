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
