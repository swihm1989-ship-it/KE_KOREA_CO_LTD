# MASTER input synchronization and approved FINAL output

## User-visible behavior

The owner requested one live editor and a final downloadable PDF even when
information is incomplete. MASTER now presents missing facts as named warnings
and offers a per-document final approval. Approved PI/PO/CI/PL files use the
existing company layout, with unknown values left blank. The normal strict
draft path remains available. Document numbering can be generated explicitly
with the existing editor button; a missing number does not prevent the approved
blank-output path.

Unknown amounts are not zero. A row whose quantity, price, discount, currency or
necessary product classification is unknown receives a blank dependent amount.
An incomplete collection of rows does not receive a partial-sum grand total.
Known explicit zero is preserved. Optional N/A is retained only when supplied.
Exact extraction placeholders are cleared; meaningful free text is preserved.

The interface separately displays incorrect supplied values and conflicts.
Negative, nonnumeric and nonfinite values cannot disappear through promotion
recalculation or an alternative paid-quantity field. Known unit mismatches,
packing inconsistencies and invalid source amounts still block. CI continues
to require the original PI transaction-price path. Final company-branded
output continues to require the original verified seal. In approved incomplete
PI output, missing bank fields remain blank.

## Root causes and changes

1. MASTER's shared trade export adapter only produced DRAFT. Explicit
   `final=True` now selects FINAL filenames, statuses and repeated PDF footers.
2. Historical AI missing-field notes and actual absence were treated as export
   blockers even after manual edits. `trade_export_review.py` now distinguishes
   advisory warnings from unresolved invalid values. The new mode is explicit;
   strict callers retain their default behavior.
3. Rejected input could leave old valid candidate data and downloads active.
   Pending input errors now retain the rejected raw text, revoke existing files
   and approvals, and block generation until corrected. Menu navigation keeps
   that rejected text visible. Committing advanced JSON refreshes the main
   editor; unsaved JSON revokes the old final approval/download.
4. Streamlit can retain modules across deployment. The page checks workflow
   revisions and signatures; the export adapter refreshes shared renderers and
   PDF dependencies in order before invoking their current APIs.

5. Live authenticated verification exposed a separate extraction contract
   mismatch: the shared contract AI legitimately returns `status="missing"`,
   while MASTER accepted only `suggested`. Normal missing facts could therefore
   prevent any editor candidate from appearing. The adapter now accepts the
   service's missing-term shape without confirming AI-proposed facts. Both PI
   and contract candidate entry points load the current workflow revision; the
   Streamlit page revision advances to v8. Confirmed or malformed model statuses
   remain rejected.

## Approval and output boundaries

Approval is bound to normalized current document content, the Seoul issue date,
the explicit incompleteness option, and the editor revision. The backend checks
approval and fingerprint again when rendering. A change or approval withdrawal
removes old downloads. Other requested documents' missing fields do not block
an independently valid selected document.

The existing renderer produces PDF, XLSX and HTML. Partial rendering consumes
explicit nullable calculated fields, so a `None` total is authoritative and does
not fall back to stale source values. PL totals preserve unit separation and do
not synthesize missing counts or weights. The CI adapter retains its payment
redaction and FOC handling while preserving reviewed unknown discount/payment
values. Generated files remain `sendable=False`; there is no automatic email,
purchase-order transmission or contract execution.

The CONTRACT final engine and RAG changes are outside this trade-output path.

## Verification

- Required legacy document/contract suite: 707 passed, no failures or skips.
- Final MASTER suite: 470 passed, no failures or skips.
- Combined final regression result: 1,177 passed, no failures or skips.
- Live extraction regression coverage adds six tests for upstream missing-term
  responses, invalid statuses, a contract-only stale-module path, and the single
  editor's missing-quantity-to-explicit-zero flow. The related 30-test focused
  suite passed before the final full-suite run.
- Final full suites run through `scripts/run_offline_regressions.py`, which
  disables network connections and strips inherited provider credentials before
  discovery. No tests are skipped or weakened. A raw legacy run was stopped by
  automatic approval review when it attempted an unexpected external AI request;
  it is not counted as a completed passing run.
- Focused tests cover the reported stale input/approval/download conditions,
  incomplete actual PDF export, explicit zero, pricing/packing/source errors,
  incomplete sums, exact placeholder removal, and cached pre-FINAL renderer
  signatures.
- Thirteen renderer regressions include real PDF/HTML/XLSX bytes. Visual review
  of six synthetic PDFs/eight pages confirmed blank fields and unchanged row,
  page and complete closing-section placement. Synthetic logo/seal images were
  used; private company assets were not included in tests or source changes.
- `git diff --check` and the five-README synchronization guard passed.

## Production verification

The MASTER Google login screen was observed at
`https://ke-korea-master.streamlit.app/`. The first attempt to click Google
sign-in was rejected by automatic approval review. The owner subsequently
explicitly approved production Google sign-in and final PDF verification.
The authenticated AI intake screen was then observed, and two synthetic
requests reproduced the missing-term compatibility failure before deployment.
The fix is included in this release. Final PDF download, blank/zero values,
and reapproval after edits remain post-merge checks. Their final results will
be recorded in [PR #95](https://github.com/swihm1989-ship-it/KE_KOREA_CO_LTD/pull/95),
separately from local and GitHub CI results.

## GitHub publication status

The first release-tree upload was rejected by automatic approval review for
missing explicit current-turn publication authorization. The owner subsequently
explicitly approved uploading this reviewed change to
`swihm1989-ship-it/KE_KOREA_CO_LTD`, opening the PR, checking CI, and merging to
main after CI passes. The implementation, all 1,177 passing regression tests,
and local commit are complete; publication resumes under that approval. No
alternate upload path was used to bypass the original rejection.
