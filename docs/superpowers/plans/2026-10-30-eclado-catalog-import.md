# ECLADO Catalog SQL Preparation Plan

> **For agentic workers:** Use superpowers:executing-plans for the authorized SQL preparation scope. Track steps below. Remote application is not authorized in this phase: the user selected SQL files first.

**Goal:** Prepare PostgreSQL schema and a validated private seed for every product in both supplied ECLADO price workbooks.

**Architecture:** Keep standard products and samples distinct. Separate KRW purchase prices from buyer/currency-specific sales prices. Preserve each source import as an immutable price snapshot and keep commercial seed data out of Git.

**Tech Stack:** Python, read-only openpyxl, Decimal, PostgreSQL/Supabase SQL.

**Spec:** `Quotation_KEKOREA/README.md` and the user's 2026-10-30 price-list instructions, including the follow-up choosing SQL files first.

## Global Constraints

- All generated trade documents must be in English.
- Main-sheet purchase price: KRW workbook column N; main-sheet Dear Glow sale price: buyer workbook column N, cross-checked against KRW workbook column P.
- Samples use the Sample sheet's declared KRW currency; missing capacity remains unknown.
- Never use retail prices, wholesale prices, margin formulas, or the workbook's FX assumption as purchase/sale prices.
- Discount reference is 10%, not a permanently active discount. Preserve base prices.
- Do not merge two different products sharing code 73568.
- Prepare files only; do not claim Supabase tables exist.

## Review Focus

- Same code with different item/capacity must remain separate.
- Missing prices must fail rather than become zero.
- Sample KRW prices must not be labeled USD.
- Mismatched source identities or buyer prices must stop the import.
- SQL strings and generated JSON must round-trip names containing apostrophes.

## Task 1: Source mapping and SQL seed

Files: `Quotation_KEKOREA/scripts/build_eclado_seed.py`, `Quotation_KEKOREA/tests/test_eclado_import.py`, `Quotation_KEKOREA/private/eclado/`.

Interfaces: `build_catalog(purchase_rows, buyer_rows, purchase_samples, buyer_samples) -> dict`; `make_seed(catalog, sources) -> tuple[str, dict]`.

- [x] Write synthetic tests for separate product identities, currency, Decimal discount calculations, missing data, source mismatch, duplicate exact identities, and SQL round-trip escaping.
- [x] Run tests and verify the missing importer fails.
- [x] Implement the read-only extractor and transactional idempotent seed generation.
- [x] Run all tests in `Quotation_KEKOREA/tests` and import both real workbooks; require 131 standard + 26 sample products and matching price row counts.

## Task 2: Schema, verification SQL and documentation

Files: `Quotation_KEKOREA/supabase/migrations/202610300001_eclado_catalog.sql`, `Quotation_KEKOREA/supabase/README.md`, `Quotation_KEKOREA/supabase/verify_catalog.sql`, `Quotation_KEKOREA/README.md`, root `.gitignore`.

- [x] Define imports, products, purchase prices and buyer prices with keys, numeric constraints, English field names, RLS and no public access policies.
- [x] Prepare verification queries for counts, missing prices, ambiguous codes and source-discount reconciliation.
- [x] Document English-only output, variable raw materials, adjustable discounts, paid/free/shipped quantity formulas, and promotion stacking as an explicit future choice.
- [x] Verify generated seed round-trip and source hashes, Git exclusion, UTF-8 files and whitespace.
- [x] Report PostgreSQL execution as unverified unless an actual database is available; no commit/push in this scope.

## Execution record

- User selected SQL preparation rather than Supabase connection/application.
- Existing workspace contains user-provided learning materials and the previous design. Work is limited to the quotation folder, this plan and a root ignore file; no branch or Git history changes.
- Application features and invoice rendering remain outside this SQL preparation scope.
- Fresh code review identified silent conflict skipping. Added a payload digest plus persisted-field conflict checks to the SQL template; a new generation test failed first and then passed. SQL guards still require actual PostgreSQL execution.
- Added strict purchase currency-header and expected snapshot-count guards, both with failing-then-passing tests. Clarified that import IDs depend on the ordered source manifest, including filenames.
