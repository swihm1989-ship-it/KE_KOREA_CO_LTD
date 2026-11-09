# Root folder organization

Goal: Organize historical root patches, backups and logs per the selected scope.
Architecture: Preserve each historical package as a unit. Keep application, tests, private data and deployment paths unchanged.

- [x] Record old/new paths, file sizes and SHA-256 before moving.
- [x] Validate all paths stay inside workspace and reject destination collisions.
- [x] Move 34 entries and verify all 145 files remain byte-identical.
- [x] Add folder index and update five maintained READMEs.
- [x] Confirm full unittest result and git diff --check: 403 tests passed in 116.182s; no skips. Existing Streamlit/PyMuPDF warnings remain.

Archived scripts are historical records; review path assumptions and source version before reuse. Package-local backups and test helpers stay beside their source.
