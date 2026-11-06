# Contract workspace

This document describes the contract-drafting feature added to the existing Streamlit application. The two existing sidebar labels remain unchanged; their screens now open the sale-contract and commission-contract workflows. The PI, PO, CI and PL workflows are not replaced by this feature.

## What it does

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
