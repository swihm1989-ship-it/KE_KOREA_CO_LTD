# Contract draft quality implementation plan

Goal: Add the approved seven internal drafting stages while preserving UI, user flow, revisions, approvals and FINAL validation.
Architecture: A new drafting module plans clauses, retrieves bounded topic-specific excerpts from complete selected documents and approved library records, generates, audits, optionally repairs once, then audits again. Return the existing snapshot shape only after validation. Existing saved clauses are never automatically regenerated.
Limits: At most four generation/audit requests, at most 60 seconds per request and 180 seconds total inside the pipeline. No model switch. Library retrieval uses one approved-record read and local keyword ranking; no additional embedding calls. Preserve confirmed terms, explicit omissions, source validation and standing commission policy.

- [x] Add failing tests for tail retrieval, clause requirements, request limits, review validation, atomic failure, stable unaffected clauses, payment protection and fresh-draft-only behavior.
- [x] Implement clause standards, selected-document excerpts, approved per-topic retrieval and quality orchestration.
- [x] Wire both existing generation entry points; keep controls, flow.py and user-visible layout unchanged.
- [x] Run targeted tests and full suite; review changes and update all five READMEs with actual verification and limitations.

Review focus: unselected/private/unapproved references; fabricated citations and review evidence; inherited commercial numbers; unresolved conditions; failed audit/repair and timeout; changed unrelated IDs; protected payment clauses; final consistency after policy application. Semantic checks assist drafting and do not certify legal validity. Live AI quality and deployed app verification are separate from synthetic tests.

Verification: 15 new focused tests and the complete 437-test suite pass; final full run 109.838 seconds, no skips. git diff --check passes. Independent review findings (paragraph context and complete per-clause coverage) were reproduced with failing tests and fixed. Live model quality and deployed UI remain unverified.
