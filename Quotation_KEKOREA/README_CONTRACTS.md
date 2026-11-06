# Contract workspace

This document describes the contract-drafting feature added to the existing Streamlit application. The sidebar contains PI, PO, CI, PL and `계약서 만들기`. The contract label has no preparation suffix, and the separate commission-contract sidebar entry is removed. Commission implementation and stored records are retained. The PI, PO, CI and PL workflows are not replaced by this feature.

Deployment troubleshooting: a screen asking for `CONTRACT_ACCESS_PASSWORD` or `CONTRACT_ACCESS_PASSWORD_HASH` is running a different version from this checkout, which has no password gate. On Streamlit Cloud, check the deployed repository, branch and main file (`Quotation_KEKOREA/app.py`) and reboot after updating the deployed source. If retaining that older gated version, configure its access password in the app's server Secrets. This message does not indicate a missing SQL migration. Live deployment has not been verified for this menu change.

Menu verification (2026-11-06): the Streamlit navigation test passed with the five expected sidebar entries and preserved PI/PO/CI/PL state. The full requirements-based suite ran 233 tests with one failure, `test_annotations_load_prices_without_bypassing_product_confirmation`; that same failure was reproduced against the unchanged HEAD application. The minimal dependency command also encountered missing `python-docx`; use the complete requirements for contract tests.

Classification/title verification (2026-11-06): all 37 contract tests pass with the complete requirements, including real Streamlit forms for investment-commission creation, opening all types, correcting an existing sale classification, preserving draft content for review, retaining user titles through AI drafting, and exact DOCX/PDF title text. The broader 240-test run reproduced the known product-annotation failure and initially exposed a PDF text-extraction ordering assumption in the new title test; that assertion was corrected and the 37 contract tests rerun successfully. No live records were edited and this change has not been deployed or verified against the live app.

## What it does

- The single contract workspace opens every supported contract type. New contracts require an explicit sale, trade-commission or investment-commission selection; the menu no longer defaults every contract to sale. Type is separate from title and controls the required terms and party roles.
- The saved-contract selector and workspace heading display the user's title without type labels or revision suffixes. AI drafting preserves that title, and DOCX/PDF headings use the same title. Revision information remains in a separate caption.
- Existing misclassified contracts can be corrected in `계약 정보 수정` → `현재 계약 유형` → `계약 정보 저장`. Title edits are also available there. Changes create a revision with concurrency checking, preserving terms, clauses and references. Changing type on an existing draft adds a review issue and blocks export until that review is resolved; old proposals are cleared.
- Drafts sale, trade-intermediary commission and investment-commission contracts in Korean or English from natural-language transaction notes and a structured terms table.
- Stores contract revisions, conversation messages, annotations, approved clause preferences, references and export metadata in Supabase. Revision commits use an expected-revision check to prevent overwriting a concurrent edit.
- Extracts text from PDF and DOCX references locally. Scanned PDF OCR is optional and requires a separate explicit consent before page images are sent to the configured OpenAI API. Extracted reference text is treated as data, and AI source quotations are checked against the selected material.
- Lets the user select a sentence, save a note, request a sentence-level revision, compare proposed changes and apply selected changes as a new revision. Restoring a prior version also creates a new revision.
- Generates editable DOCX and PDF files from the current snapshot only. Export is blocked while required terms or unresolved review issues remain. The output is not legal advice or legal-validity certification.

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
