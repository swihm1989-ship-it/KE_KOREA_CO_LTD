# Mail document intake implementation plan and continuation record

Goal: A selected incoming mail such as “Dear Mr. David, Please provide PI for below” can populate AI 업무 요청 and extract reviewable PI/PO/CONTRACT/CI/PL candidates in one explicit action. CIPL expands to existing CI and PL documents. Preserve legacy formats, seals, prices, missing-information and approval rules; no automatic sends or final issuance.

Current findings: mailbox `_use_for_ai` only copies up to 20,000 characters and resets consent; AI extraction requires another click. Shared classifier misses CIPL and quotation wording. Generic contract-to-trade mapping uses only one item and omits packing fields. Existing CI policy requires source PI for final export.

Implementation:
- [x] Add failing tests and a safe mail request adapter with full-source bounds, current-message routing, CIPL aliases, explicit one-shot handoff state.
- [x] Reuse existing trade extractor for multiple line items and packing fields; preserve contract extraction for contract candidates; never accept remote approval/internal flags. Missing PI/packing facts remain blockers.
- [x] Add selected-mail direct extraction button and editable detected document choices in AI 업무 요청. Consume a pending action once, including on failure; text changes cancel it.
- [x] Add 160+ synthetic mail cases with independent golden facts, provider-transport integration, calculation and privacy checks. Add real Streamlit handoff/rerun/error tests. No production mail or external model calls in regressions.
- [ ] Run all offline regressions, independent review, update five READMEs, commit/PR/CI/merge main. Live app verification remains subject to prior Google authentication block.

Execution branch: `feature/mail-document-intake-20261113`, base `b2e03def2246b449b5fb55faa7033408fe17c515`.

Usage-limit instruction: Account quota percentage is not exposed to the agent. If a concrete limit warning shows remaining quota below 3%, stop immediately, record completed work/tests/commit and provide the following continuation instruction in chat. Do not claim percentage monitoring exists.

Continuation command:
“Continue the KE KOREA selected-mail → AI 업무 요청 document intake implementation in https://github.com/swihm1989-ship-it/KE_KOREA_CO_LTD. Check branch feature/mail-document-intake-20261113 and docs/superpowers/plans/2026-11-13-mail-document-intake.md first. Preserve existing forms/seal/approval rules, finish 160+ dummy-mail tests and full offline regressions, then commit/CI/merge main. No Audit Log. Google production authentication was previously blocked by automatic approval review; do not bypass it. Current checkpoint is recorded in this plan and git history.”

Progress: Mail adapter, routing aliases, one-shot consented handoff, multi-row extraction, explicit attachments and UI integration implemented. 160 dummy mail cases plus 6 policy tests pass. 5 UI tests are being finalized; full offline regressions and review/commit/CI/merge remain pending. Local checkout: /workspace/scratch/5a817cb4e5ab/repository. Existing Python test runtime .venv/bin/python and scripts/run_offline_regressions.py available. Previous feature: 851 tests passed and PR #74 merged. This plan is a Git-backed artifact; it is not the product output.

Review checkpoint: independent reviewer found nullable strict-schema quantities/discounts, inferred ship-to, unresolved missing notices, contract missing-status recovery, stale paid/shipped after human quantity edits, and missing CI source PI guard. All reproduced in failing tests and fixed. 160 fixtures now include every required nullable API field. 172 mail tests and 7 legacy export policy tests pass; 6 Streamlit tests and full offline regressions running. No templates, seals or private credentials modified.

Final checkpoint: implementation and independent review fixes complete. All offline suites passed: 678 + 352 = 1,030 tests, no skips/failures. Dummy-specific 172 and Streamlit-specific 6 passed. Five README guard/diff checks passed. Next: upload tested tree to GitHub branch, create PR, verify three CIs, merge main; no further product code needed. Live verification still needs user Google authorization and must not be claimed complete.

Publication checkpoint: automatic approval review rejected republishing an existing README containing a real contact email/phone and project URL. A materially safer revision replaces those three documentation values with server-configuration placeholders; no runtime settings changed. Continue uploads using the sanitized staged README, not the rejected payload.
