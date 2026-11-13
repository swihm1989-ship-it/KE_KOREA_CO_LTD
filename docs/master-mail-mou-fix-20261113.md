# 2026-11-13 Master mailbox MoU routing repair

## Scope
- Recognize MoU, M.O.U., Memorandum of Understanding and 양해각서 as existing CONTRACT requests.
- Normalize line breaks in document labels only for routing; AI prompt uses original subject and body.
- Preserve terminal abbreviation period to distinguish negated adjacent sentences.
- Add mailbox document-type selector, including fallback for valid unrecognized mail, and preserve selected kinds through queue_handoff to AI request.
- Existing contract candidate analysis is reused; no dedicated MoU generation engine is introduced.

## Safety
- Explicit user click and AI processing consent required. No automatic sends or approvals.
- No real emails, credentials, attachments, or customer records in tests or GitHub.
- Document layouts, seals, financial validation, PI/PO/CI/PL engines, and final approval remain unchanged.

## Repro/test
- Synthetic regression: Quotation_KEKOREA/orchestration/tests/test_mail_mou.py
- Full offline regression: .venv/bin/python scripts/run_offline_regressions.py
- Check git diff --check and scripts/check_readme_sync.py.
- Github CI can validate source and synthetic tests, but is not live email-model accuracy or the logged-in Streamlit production UI.
- Production UI must be checked by authenticated owner; Google authorization must never be bypassed.
