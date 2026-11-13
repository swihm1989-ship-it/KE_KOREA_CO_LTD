# MASTER trade final PDF and actionable validation

> For agentic workers: implement the isolated renderer task, then integrate validation/UI and run whole-branch review.

Goal: show the exact remaining fields/errors after each input and allow an explicitly user-approved FINAL PI/PO/CI/PL in the existing layout.

Accepted continuation: preserve quantity zero, price/CI source and packing checks, original pagination, verified seal and contract FINAL policy. No automatic sends or invented trade facts. Default legacy rendering remains DRAFT. The owner's explicit request supersedes the earlier missing-field gate: after per-document approval, missing fields and bank values stay blank in FINAL, including document number; automatic numbering is optional. Uncomputable amounts stay blank. Supplied invalid values and genuine conflicts still need correction.

Task 1 (renderer): add final=False keyword to agent.renderers.render_files and agent.pi_pdf.render_trade_document. FINAL filenames/status/header/footer must omit DRAFT/NOT FOR ISSUE; default output unchanged. Test actual multipage PDF plus default preservation. Do not change layout, prices, assets or legacy renderer aliases.

Task 2 (workflow/UI): reusable normalized per-document review separates missing warnings from blocking invalid inputs; explicit final approval permits blanks, with separate final downloads. Display missing keys/labels and actual validation. Never let unrelated CONTRACT or other document gaps block a valid selected PI. Preserve old strict/internal-review paths. Bind final approval/files to current input fingerprint; accepted or rejected edits revoke old files. Keep rejected raw text across navigation and refresh widgets after JSON commits. Refresh hot-loaded workflow and renderer/PDF dependencies.

Task 3: meaningful AppTest/data/PDF regressions, five synchronized READMEs, required full suites and diff/compile checks, fresh code review, then publish/CI/merge within existing authorization. If automatic publication is rejected, do not bypass; retain a concrete verified artifact.
