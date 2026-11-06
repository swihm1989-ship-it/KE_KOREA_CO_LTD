# Contract three-box UI implementation

> Execute against current main (3991930), following the user's attached resume brief.

**Goal:** Preserve the existing engines and 296 passing tests while arranging the contract workspace into chat, manual details and paper-like preview. Collect revision-bound sentence notes into one reviewed, atomic proposal. Separate explicit DRAFT outputs from unchanged FINAL validation.

**Architecture:** Reuse `_contract_chat`, `_run_editor`, `propose_revision`, `apply_proposal`, repository methods and final exports. Add contract-only `workspace.py` for note selection/batch proposal assembly and `draft_exports.py` for visibly provisional documents. Keep payment policy, rules, service prompts, repository schema, trade app and agent modules unchanged. UI language defaults to Korean; review summaries have an explicit screen-language selector independent of document language. Original findings remain in collapsed evidence controls.

## Tasks

1. Add failing helper and Streamlit tests: box order, exact sentence selection, saved-note reload/isolation, stale/deleted/duplicate notes, overlapping proposals, one revision commit after approval, DRAFT labels/appendix/no signing page, FINAL blocked. Run to observe failures, then implement helpers.
2. Rearrange existing UI blocks without replacing their handlers. Put payment editor in BOX 2; place preview, notes, final revision request, comparison and downloads in BOX 3. Scope paper CSS to contract preview. Retain RAG, references, history and management in auxiliary expanders.
3. Add classified, deduplicated presentation summaries with links to actual editors. Keep original issue records and explicit per-issue evidence/confirmation; TBD never resolves validation. Preserve existing question limiter and AI language policy.
4. Add separate draft generation and private storage path (`exports/draft/...`) using existing export records; final generation continues through `validate_rules(..., for_export=True)`. Do not change existing final renderer.
5. Run full suite and `git diff --check`; inspect actual local UI with synthetic data. Update all five READMEs by correcting stale current descriptions, recording actual checks and leaving live deployment unverified. Verify README guard logic against changed file list without staging the user's work.

## Review focus

- Multiple proposals targeting the same sentence/term must fail closed on conflicting payloads, never partly commit.
- Notes from old revisions/deleted sentences must be visible but excluded; repeated saves of the same note are idempotent.
- Pending edits and final export cannot silently bypass review. Annotation cleanup failure after a committed revision cannot cause a second commit.
- DRAFT headers on every page and unresolved appendix must make provisional text unambiguous; no signing page.
- Existing trade source files must match baseline byte for byte.

## Execution record

- Baseline: local HEAD and fetched origin/main 3991930; clean working tree; 296 tests, OK (83.551s).
- User explicitly requests implementation in the current checkout, no reset/push/deployment. Work in place and leave changes reviewable, without automatic commit.
- Implementation complete in UI/review display and two contract-only helper modules. All original tests unchanged; 24 new tests exercise helpers and real Streamlit interactions.
- Independent read-only review found confirmation reopening and no-op review revisions; both reproduced by failing tests and fixed. Cross-sentence semantic conflict checking remains an explicit human consistency-review checkpoint, with automatic rejection of conflicting same-target patches. This preserves the existing AI service policy rather than introducing another legal-analysis call.
- Added a regression for a successful revision commit followed by failed annotation logging; UI now retains the committed revision and warns instead of presenting the old base.
- Final suite: 320/320, 0 failures, exit 0, 89.580 seconds. `git diff --check` passed. Protected business/revision/policy/schema files match HEAD.
- Synthetic multi-page Korean and English DRAFT PDFs rendered; mixed Korean evidence font regression fixed and tested. Browser verification blocked by Windows URL detection; no browser visual/responsive or Word rendering claim. No push/deployment/live data edits.
