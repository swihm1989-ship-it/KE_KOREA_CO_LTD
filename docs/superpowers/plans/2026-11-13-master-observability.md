# Master Observability Implementation Plan

**Goal:** Add private JSON execution logs and AI usage monitoring to Master without changing document content, rendering, mail behavior, seals or approvals.

**Architecture:** Explicit, metadata-only spans at existing operation boundaries. A bounded asynchronous sink writes to a separate Supabase table; failures never change business results. Existing OIDC allowlist protects the dashboard. No audit trail, identities, prompts, documents, exception text, headers or credentials are collected.

**Tech stack:** Python standard library, existing Streamlit, Supabase Postgres/REST and pg_cron. No external telemetry service.

**Spec:** User request in this task; defaults: 30-day retention, hourly database cleanup, 2,000-event bounded volatile fallback, no added AI retries. Unknown usage/pricing is displayed as unavailable, never zero.

## Global Constraints
- Existing shared renderers and templates, seal resolution, mail protocol and approval behavior remain unchanged.
- Recording is explicitly enabled by authenticated Master startup; imports alone have no network side effects.
- Run existing unit, integration and Streamlit regression suites before merge. Protect private test fixtures from Git.
- Publish only after all tests pass; verify the live deployment and authenticated dashboard or report the precise authentication blocker.

## Review Focus
- Provider/exception payloads containing secrets must never reach any log or dashboard.
- Storage failure/queue pressure must preserve return values and exception identity.
- Missing usage, unknown models, cached tokens and failed/repeated calls must not produce misleading totals.
- Expired/unauthorized identities must not access telemetry or initiate store reads.
- Start events and repeated dashboard reruns must not double-count AI calls.

### Task 1: Metadata recording and private persistence
- [x] Write failing tests for safe fields, nested run correlation, timings, unknown usage/costs, failure classification and fail-open behavior.
- [x] Implement `observability/core.py`, `pricing.py`, `storage.py`; bounded async writes, safe model/error enums and server-side settings.
- [x] Add a service-role-only table, RPC aggregates, fixed 30-day expiry and hourly cleanup migration; verify access and retention in Supabase.

### Task 2: Existing operation boundaries
- [x] Add failing integration tests using fake provider/mail responses and real legacy renderer regression tests.
- [x] Instrument existing contract `_call`, trade extractor, contract analysis/drafting, mail fetch and Master trade export boundaries. Record existing retries explicitly, without adding retry behavior.
- [x] Verify unchanged outputs and failure behavior against existing tests.

### Task 3: Protected administrator dashboard
- [x] Write failing AppTest cases for empty/populated/degraded storage and unauthorized access.
- [x] Configure the sink only after Master authentication; add 관리자 모니터링 with period filters, model summaries, timings, tokens, estimated cost, errors/retries and JSON events.
- [x] Update all five required READMEs, add CI coverage and an operations guide.

### Task 4: Release verification
- [x] Full regression tests, privacy/security review, diff checks, required README guard.
- [x] Commit on independent branch, create PR, verify checks, merge to main.
- [ ] Verify deployed health/login and actual dashboard; document exact observed scope and commit IDs.

## Review and release ledger

- Branch starts from `645ad8da90f14e87c8323779a68a36837c21be0d`.
- Metadata, asynchronous storage and operation integration tests were written RED→GREEN.
- Independent review found startup URL/thread failures, malformed provider status handling and fallback percentile calculation; all three reproduced in failing tests, fixed and passed.
- Test runner isolates existing suites in subprocesses because they share module names and use non-package discovery roots. All outbound test sockets are blocked.
- Supabase RLS/role checks, 30-day forced expiry and summary estimates passed transaction-only synthetic tests; no synthetic AI records retained.
- Google reauthentication blocked by automatic approval review; no auth bypass or alternate login path attempted. Live authenticated verification remains pending.

- Final offline suites: 677 + 174 = 851 passed, no failures/skips. New telemetry tests: 27. README guard and diff checks passed.
