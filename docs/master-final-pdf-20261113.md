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

6. Live browser verification then exposed a client/server state mismatch after
   advanced JSON replacement. The server candidate was correct, but the browser
   retained keyed inputs because only their defaults changed. Its next widget
   payload restored the old DRAFT number and empty unit/basis/discount. AppTest
   `.value` checks had seen only the correct server state. New regressions replay
   the real `WidgetStates` payload. Candidate replacement now advances the
   editor generation; normal synchronized fields receive an explicit frontend
   value update. Pending invalid text and approval revocation are preserved.
   The page and entrypoint revisions advance together to v9.

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
- Final MASTER suite: 472 passed, no failures or skips.
- Combined final regression result: 1,179 passed, no failures or skips.
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

PR #95 was merged as `818939344b9808477780c11e3e2a0ec224a59df7`. Its three
pull-request CI workflows and the subsequent main push contract workflow passed.
The authenticated MASTER app at `https://ke-korea-master.streamlit.app/` then
successfully accepted the previously failing synthetic request with missing
quantity and opened the single editor.

The live app generated and downloaded two synthetic FINAL PDFs. The first
retained the manually typed buyer address/email, left quantity and dependent
amounts blank, used the existing company layout and seal, and had a FINAL
footer without DRAFT or unknown-value placeholders. Changing quantity to `0`
removed the prior approval/download. A new approval produced a second actual
PDF showing `0 PCS` and `$0.00`. No email, order, saved transaction, or contract
execution was performed. Real company assets and bank details were not added
to this repository.

The same live session exposed the advanced-JSON widget-state overwrite described
above. The follow-up is covered by two protocol regressions plus 57 focused
UI/mail/editor tests; the complete suites passed again (707 legacy plus 472 MASTER) before publication. The
exact browser replacement/edit/download sequence will be repeated after the
follow-up deploy. Final live results are recorded in
[PR #95](https://github.com/swihm1989-ship-it/KE_KOREA_CO_LTD/pull/95), separately
from local and GitHub CI results.

## GitHub publication status

The first release-tree upload was rejected by automatic approval review for
missing explicit current-turn publication authorization. The owner subsequently
explicitly approved uploading this reviewed change to
`swihm1989-ship-it/KE_KOREA_CO_LTD`, opening the PR, checking CI, and merging to
main after CI passes. The implementation, all 1,179 passing regression tests,
and local commit are complete; publication resumes under that approval. No
alternate upload path was used to bypass the original rejection.

## Browser follow-up publication blocker

The browser widget-state follow-up passed all 1,179 local regressions and
independent review, but its 10-file release-tree upload was rejected by automatic
approval review. A read-only check confirmed that the authenticated GitHub
account owns the target repository and has admin/push permission, and that the
repository is public. The follow-up adds reviewed UI code, synthetic tests and
README/verification updates; private assets, configuration and downloaded PDFs
are excluded. Retrying the same upload after those checks was also rejected
because the trusted user text did not explicitly name this follow-up payload
and its public destination. No alternate upload method was attempted.

PR #95 remains merged and its blank/zero FINAL production checks succeeded.
The widget-state follow-up is preserved in the local commit and patch, with no
follow-up remote branch or PR created. Its publication requires explicit
authorization naming public repository `swihm1989-ship-it/KE_KOREA_CO_LTD` and
the 10 source/test/documentation files. After approval, the remaining steps are
PR creation, CI, main merge, and the exact browser edit/download recheck.
