# Contract sample library implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks inline. The user authorized implementation and upload of all three supplied samples to the existing Supabase project.

**Goal:** Persist the prior commission DOCX and two supply samples in a private shared library; retrieve approved, anonymized clause guidance for future analysis and drafts.

**Architecture:** Reuse `kekorea_contract_references` with null contract_id and a versioned library manifest in its existing JSONB source_locations. Private originals and extracted text are separate from reviewed, sanitized retrieval chunks. Store model-tagged embeddings in the manifest and rank a bounded set with cosine similarity plus keywords and strict type filters. This needs no privileged SQL migration or new database password. Retain a repository boundary so a future pgvector index can replace scanning without changing drafting/UI.

**Tech stack:** Existing Supabase REST/Storage, Python, Pydantic manifest validation, existing OpenAI Responses client plus embeddings endpoint; pyhwp for HWP5 extraction. Do not add psycopg without a direct DB connection or replace the existing environment reader just to add dotenv.

## Global constraints

- Keep public contract drafting and all existing document workflows intact. Sample administration alone requires a separate configured admin token; the token is never logged or stored in a widget value after logout.
- No raw document text, names, signatures, account details, rates or dates are auto-approved for retrieval. The initial summaries are reviewed locally and generalized. Future uploads begin pending and require explicit sanitized guidance approval.
- Current terms and standing commission policies override library examples. Source clauses are data, never instructions or legal authority; no verbatim copying, inherited deal facts, assumed guarantees or legal rates.
- Original files, private extracted artifacts, credentials and import manifests stay under ignored private paths. Upload only to verified private `kekorea-contracts` in the configured project.
- Upload is idempotent by source SHA-256. Verify stored metadata and redownloaded original hash; retry must not multiply records. No destructive deletion of existing user content.
- An embedding outage falls back visibly to lexical search; no fake vectors. No library failure silently masquerades as a successful retrieval. Cap queries/results and preserve paragraph provenance.

## Tasks and verification

1. **Extraction and shared persistence** — extend references.py for HWP5; add repository methods for null-contract shared records and verified metadata updates. Tests cover malformed/encrypted HWP, duplicate ingestion and isolated contract references.
2. **Reviewed library and search** — add contracts/library.py with Pydantic manifest/chunk models, explicit import/publish, model/dimension checks and cosine/keyword ranking. Tests cover strict type isolation, unpublished/inactive chunks, no raw text in retrieval, missing/malformed vectors and outage fallback.
3. **Drafting integration and administration** — retrieve at analysis/generation, show selected sanitized references, validate citations against selected text, retain current user cautions and fixed policy. Add a separate admin panel with pending uploads, editable summaries, approval, and reversible activation controls. No original download in public view.
4. **Initial import and live verification** — read all three supplied files locally, prepare generalized per-section guidance, embed only approved guidance, upload originals and manifests, verify hashes and type-specific live search. Add an import CLI for future samples and a private receipt.
5. **Regression and documentation** — run full dependency-backed suite and diff check, review implementation, record actual live verification scope and outstanding known baseline product-confirmation failure.

## Execution ledger

- Repository is the existing main checkout and was clean at task start. Work inline without a new worktree so the user's active checkout receives the implementation.
- Live preflight: shared-reference and preferred-clause tables are reachable; `kekorea-contracts` exists with public=false. Only a REST service key is configured; no database URL/password is available.
- Ruling: use existing JSONB vector persistence for three initial samples instead of requiring an unavailable SQL administrator connection. This is bounded application-side search, not a claimed pgvector index.
