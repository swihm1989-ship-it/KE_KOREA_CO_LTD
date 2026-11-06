# Contract workspace

This document describes the contract-drafting feature added to the existing Streamlit application. The sidebar contains PI, PO, CI, PL and `계약서 만들기`. The contract label has no preparation suffix, and the separate commission-contract sidebar entry is removed. Commission implementation and stored records are retained. The PI, PO, CI and PL workflows are not replaced by this feature.

Deployment troubleshooting: a screen asking for `CONTRACT_ACCESS_PASSWORD` or `CONTRACT_ACCESS_PASSWORD_HASH` is running a different version from this checkout, which has no password gate. On Streamlit Cloud, check the deployed repository, branch and main file (`Quotation_KEKOREA/app.py`) and reboot after updating the deployed source. If retaining that older gated version, configure its access password in the app's server Secrets. This message does not indicate a missing SQL migration. Live deployment has not been verified for this menu change.

Historical menu verification (2026-11-06, before the subsequent regression fixes): the Streamlit navigation test passed with the five expected sidebar entries and preserved PI/PO/CI/PL state. The then-current requirements-based suite ran 233 tests with one product-annotation failure. This is not the current failure status: baseline `3991930` passed all 296 tests before this UI change. Use the complete requirements, including `python-docx`, for contract tests.

Classification/title verification (2026-11-06): all 37 contract tests pass with the complete requirements, including real Streamlit forms for investment-commission creation, opening all types, correcting an existing sale classification, preserving draft content for review, retaining user titles through AI drafting, and exact DOCX/PDF title text. The broader 240-test run reproduced the known product-annotation failure and initially exposed a PDF text-extraction ordering assumption in the new title test; that assertion was corrected and the 37 contract tests rerun successfully. No live records were edited and this change has not been deployed or verified against the live app.

Commission-policy verification (2026-11-06): the full requirements-based regression ran 248 tests with only the known `test_annotations_load_prices_without_bypassing_product_confirmation` failure. After adding explicit checks for repeated-AI bank redaction, changed server accounts, legal-review completion and rejecting N/A as legal evidence, all 27 selected policy/service/rules/workspace tests passed. The workspace assertion now reads the terms dataframe directly instead of relying on its truncated string representation. All fixtures use synthetic accounts and transactions. The source agreement was read locally only; no live OpenAI calls, document uploads, database changes or deployment were performed.

## What it does

- Commission drafting uses a generalized, non-verbatim reference brief from the user-supplied prior agreement. The original DOCX, transaction identities, commission percentages, bank data, guarantee signatures and negotiated periods are not copied into the repository or automatically inherited. Analysis and revision prompts consider balanced scope, proportionate non-circumvention, actual receipts, evidence, finite negotiated protection periods, confidentiality, tax and enforceability questions. Guarantees, governing law and dispute forums require explicit current instructions.
- **BOX 1 — chat:** `거래 내용과 AI 분석` retains conversation history, API consent, selected references and approved-clause RAG. The existing one-round, maximum-two-question guard and draft-first response remain unchanged. The latest 30 conversation messages accompany draft generation.
- **BOX 2 — manual details:** the terms and party editors are always available. UI states `확정 / AI 제안 / 확인 필요 / TBD 유지` map to existing confirmed/suggested/missing values; TBD preserves the supplied value without approving it. Existing term-reconciliation proposals and commission payment editing remain in this box. Confirming one finding never confirms unrelated structured values.
- **BOX 3 — document and notes:** a grey workspace surrounds a white, responsive paper preview. Sentence IDs remain stable; clicking a sentence highlights it and opens its saved note. Re-saving updates the note for that sentence and revision. `최종 수정 요청` collects current pending notes, generates proposals, compares them and requires approval before one revision commit. Old/deleted/superseded notes are shown separately and cannot be applied automatically. Direct single-sentence proposals, RAG risk review and revision restoration remain available.
- For investment/trade commissions, locally assembled payment sections default to D+7 calendar days after each confirmed trigger/tranche by TT, while explicitly confirmed custom deadlines can be used; payment completion is actual credit, not a transfer instruction. These sections take precedence over conflicting timing/default-interest wording. The server inserts only the configured KE KOREA USD corporate account when the confirmed payee and currency match. Missing/mismatched configuration blocks export. The six `KEKOREA_USD_*` bank variables are never substituted into another company's or another currency's receiving account. They are not API credentials, but are still not logged or committed. Protected account sections are stripped from AI snapshot payloads and assembled after AI generation.
- Default interest runs as daily simple interest on unpaid principal from the day after the due date; the edit form accepts an explicitly negotiated annual percentage while legal validity remains a separate review requirement. It refers to the highest rate legally applicable to the specific commission obligation in the Payer's country, subject to any lower mandatory limit under the governing/enforcement laws, with a lawful-default-interest fallback if no applicable maximum exists. No numeric cap is guessed. Lending ceilings are not treated as commission default rates, and a selected governing law does not automatically override local mandatory law. This is a drafting policy, not automated foreign-law research or certification.
- Before FINAL export, explicitly confirm the payer country, trigger, currency and payee in BOX 2, then record `late_interest_legal_review` and `late_interest_source` with the applicable-law assessment, supporting law/review document and review date. AI extraction cannot confirm these for the user. `수수료 지급조건 수정` → `지급조건 저장 및 조항 갱신` revises the trigger, deadline, payer country and negotiated annual late-interest rate, using the existing payment policy. The policy guard detects missing/edited payment clauses, changed triggers and changed server bank settings. Calendar-day counting and special-trigger rules remain unchanged. DRAFT may be exported while these checks remain unresolved, with explicit provisional labels and an unresolved-items appendix.
- The single contract workspace opens every supported contract type. New contracts require an explicit sale, trade-commission or investment-commission selection; the menu no longer defaults every contract to sale. Type is separate from title and controls the required terms and party roles.
- The saved-contract selector and workspace heading display the user's title without type labels or revision suffixes. AI drafting preserves that title, and DOCX/PDF headings use the same title. Revision information remains in a separate caption.
- Existing misclassified contracts can be corrected in `계약 정보 수정` → `현재 계약 유형` → `계약 정보 저장`. Title edits are also available there. Changes create a revision with concurrency checking, preserving terms, clauses and references. Changing type on an existing draft adds a review issue and blocks export until that review is resolved; old proposals are cleared.
- Drafts sale, trade-intermediary commission and investment-commission contracts in Korean or English from natural-language transaction notes and a structured terms table.
- Stores contract revisions, conversation messages, annotations, approved clause preferences, references and export metadata in Supabase. Revision commits use an expected-revision check to prevent overwriting a concurrent edit.
- Extracts text from PDF and DOCX references locally. Scanned PDF OCR is optional and requires a separate explicit consent before page images are sent to the configured OpenAI API. Extracted reference text is treated as data, and AI source quotations are checked against the selected material.
- Lets the user open and edit several sentence notes alongside their sentences, then save and send them together in one AI request. The separate optional single-sentence action remains available. Reported note conflicts, duplicate/missing sentence changes and protected payment changes reject the proposal without changing the contract. Different-sentence semantic conflicts still require explicit human consistency review; AI is not a legal reconciliation guarantee. Only approved changes are saved once through the existing revision RPC.
- **Review outputs:** `검토용 초안 PDF` and `검토용 초안 DOCX` require actual clauses. They preserve original wording but explicitly qualify unresolved text, add an unresolved-items appendix, and omit signature pages. PDF has a DRAFT watermark/header on every page; DOCX has a repeating DRAFT header. These are not signing copies.
- **Final outputs:** `최종 계약서 PDF` and `최종 계약서 DOCX` use the existing renderer and are enabled only after `validate_rules(..., for_export=True)` passes. No required term, bank check, legal check or AI review severity is relaxed. Both modes retain private Storage and export records, distinguished by `exports/draft/` versus `exports/final/` in their paths; legacy exports retain their existing paths.

The app does not send, sign, issue or automatically seal contracts. It does not implement BIPV construction agreements. The DOCX/PDF layout and Korean font rendering still need visual verification in the deployment environment.

## Configuration

Set these values only in the local ignored `.env` file or the hosting provider's server-side Secrets:

| Variable | Requirement |
| --- | --- |
| `OPENAI_API_KEY` | Required for analysis, drafting, revisions and consented OCR. Never expose it to browser code. |
| `OPENAI_MODEL` | Required default model. |
| `CONTRACT_OPENAI_MODEL` | Optional contract-specific model override. |
| `SUPABASE_URL` | Required Supabase project HTTPS URL. |
| `SUPABASE_SECRET_KEY` | Required server-only Supabase key. Do not use the publishable key for this feature. |

**The contract UI has no login or password gate.** Anyone who can reach the app URL can view, edit, export and delete stored contracts and reference materials through the app. Do not store confidential agreements or deploy this app publicly unless that exposure is acceptable. The Supabase bucket is private at the storage layer, but the app's server-side secret can access it on behalf of every visitor.

## Supabase setup

1. Review `supabase/migrations/202611050001_contracts.sql`.
2. Apply it manually in the intended Supabase project's SQL Editor using an administrator account. It creates private contract tables, a non-public Storage bucket, and revision/create/delete RPC functions. It does not populate contract records.
3. Configure `SUPABASE_URL` and `SUPABASE_SECRET_KEY` as server-side environment variables.
4. Verify the migration's table grants, RLS status, RPC execution grants and bucket privacy in that project before storing real contract data.

The migration has **not** been applied or verified against the live Supabase project. Do not treat database privacy, grants, or persistence as production-verified until those checks are completed. The server secret key bypasses ordinary RLS and must never be exposed in a client, public log, or repository.

## Local run and verification

From the repository root (`KE_KOREA_CO_LTD`), install the app requirements and start Streamlit:

```powershell
uv run --with-requirements Quotation_KEKOREA\requirements.txt streamlit run Quotation_KEKOREA\app.py
```

Run contract tests:

```powershell
uv run --with-requirements Quotation_KEKOREA\requirements.txt python -m unittest discover -s Quotation_KEKOREA\tests -p "test_contract_*.py"
```

Run the complete app regression suite:

```powershell
uv run --with-requirements Quotation_KEKOREA\requirements.txt python -m unittest discover -s Quotation_KEKOREA\tests
git diff --check
```

The tests use synthetic contract content and fake API/database clients. They do not call the live OpenAI API or Supabase project.

## Current rollout status

The code and local tests are present, but this feature has not been deployed. The Supabase migration, deployed secrets, live database persistence, external OCR/API behavior and production document layout remain unverified. The UI is intentionally unauthenticated. Keep real agreements, signatures, account details and keys out of test fixtures and source control.

## 2026-11-06 TASTE 계약서 UI 및 README 동기화

### Current drafting and review flow

- **Draft first:** Users enter a natural-language transaction, respond to at most a small number of initial clarifying questions, and generate a complete working draft. Draft generation and sentence edits remain possible while legal details are unresolved.
- **Sentence revisions:** Select multiple sentences in BOX 3 to keep their adjacent note fields open simultaneously. Typing is retained in the browser session; with BOX 1's API consent, `최종 수정 요청` saves all notes then sends one joint AI request. Compare and approve selected changes, including the explicit cross-sentence consistency check. Saved notes survive session reload; unsaved notes do not. Earlier-revision notes can be viewed but must be explicitly edited or saved again. Existing pending term proposals are preserved and must be applied or dismissed before a batch request. The existing payment editor remains the route for protected payment sentences.
- **Review UI:** `contracts/review_summary.py` deduplicates display cards by category/field and labels them required, recommended, legal-review or TBD-allowed-in-draft. The explicit review-language selector defaults to Korean and is separate from output language. Conservative category labels do not pretend to translate every legal nuance; company names, amounts and original evidence remain verbatim in a collapsed details area. Original findings and validation state are retained.
- **Final validation:** `contracts/rules.py` and payment policy checks remain authoritative for FINAL. Changing a previously reviewed issue to TBD reopens that issue; saving unchanged review choices creates no revision and does not invalidate notes. A summary itself cannot change confirmation, evidence, bank settings or signature readiness.
- **Commission editor:** The payment trigger, payer country, due period and optionally negotiated late-interest rate may be edited. Bank details and enforceability must be verified before final export; no guessed addresses or numeric rates.
- **RAG risk assessment:** Optional, source-grounded risk review based on approved sample clauses. Its AI suggestions do not modify a contract until the user explicitly applies them.
- **Rollout:** Work resumed from fetched `main` at `3991930`, newer than the requested `e20fcb6`, with 296 baseline tests passing. This three-box UI remains a local change; it has not been pushed or deployed. Historical smaller test runs above describe earlier stages.

Final local verification (2026-11-06): **320 tests passed, 0 failures, exit code 0**, including all 296 existing tests and 24 new helper/Streamlit interaction tests; `git diff --check` passed. No existing test was removed or weakened. Synthetic multi-page Korean/English DRAFT PDFs were rendered and inspected, including Korean original evidence in English output. Actual browser visual/responsive verification was blocked by Windows browser-URL detection; Word rendering and live OpenAI/Supabase/deployment behavior remain unverified. Existing Streamlit-width and PyMuPDF import deprecation warnings remain distinct from failures.

### Scope and privacy

No change to PO/PI/CI/PL or ECLADO pricing logic. The current contract page is not authenticated; do not use live confidential agreements on an internet-accessible instance until access control is added and tested. Never put bank account data or API keys in a README.

## 2026-11-06 commission payment wording compatibility

The default 7-calendar-day English payment clause prints `seven (7) calendar days` (D+7); confirmed alternative periods retain their numeric value. This existing wording correction was included in the passing 296-test baseline and is untouched by the UI change.

## 2026-11-06 CI regression scope

The document-export safeguard is document-specific: PO/PI product-annotation confirmation blocks PDF/Excel generation; a CI preserving attached-PI transaction prices may produce an explicitly marked DRAFT with unresolved product matching warnings. This CI rule does not relax contract-export validation or change commission clauses.
