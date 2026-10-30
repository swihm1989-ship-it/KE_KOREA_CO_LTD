# Trade Document Agent First Implementation Plan

## Goal

Implement the first local, English-first prototype described in `Quotation_KEKOREA/README.md`: pasted transaction text becomes a structured draft, code checks and calculates it, and the user reviews PDF/XLSX/HTML files.

## Scope

1. Add a typed prompt flow using OpenAI Responses structured output, without a live API test.
2. Reuse only exact local ECLADO catalog matches; separate purchase and sale price roles and block unsupported counterparty price profiles.
3. Validate commercial facts, currency, company roles, discounts, free quantities, price bases and actual packing data using deterministic code.
4. Generate English review-only draft files and a local Streamlit interface.
5. Add synthetic tests and update documentation with verified and unverified status.

## Explicitly deferred

Real Supabase migration/seed application; image, PDF and spreadsheet extraction; approved templates and business master data; finalization, numbering, signature/seal, shipment linkage, CI/PL matching, and live customs use.

## Verification

- Run Python unittest suite and syntax compilation.
- Inspect exact local catalog product count without emitting price values.
- Validate mocked API configuration, source quote blockers, price arithmetic and output container signatures.
- Report live API, UI, PDF visual rendering and Excel inspection separately if dependencies/network are unavailable.

## Status

- [x] Structured draft and source checks
- [x] Exact local ECLADO matching and price direction separation
- [x] Deterministic validation and simple PDF/XLSX/HTML draft output
- [x] Streamlit screen and `.env.example`
- [x] Synthetic suite; 31 passing on 2026-10-30
- [ ] Install/launch Streamlit and verify UI interactively
- [ ] Render/visually inspect PDF and open XLSX in Office
- [ ] Replace generic layouts with approved company templates
- [ ] Live OpenAI and Supabase verification
