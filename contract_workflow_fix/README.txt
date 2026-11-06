KE KOREA -- Contract draft-first conversation fix

Scope: Quotation_KEKOREA/contracts/ui.py, service.py, and NEW flow.py.
No changes to ECLADO, quotation generation, or export-validation code.

Problem: AI analysis returns questions on every chat turn; draft requires a
separate button. Users repeatedly answer the same questions.

Changes:
1. The first user entry receives at most two essential questions.
2. The next user response automatically triggers draft creation.
3. An explicit request like '계약서 초안을 작성해줘' triggers draft immediately.
4. After draft creation, users click an existing draft sentence to issue edits.
5. Missing data stay unresolved and do not become invented legal facts.
6. Existing pre-signature/export validations remain in effect.

From the KE_KOREA_CO_LTD repository root in PowerShell:
  python .\contract_workflow_fix\apply_contract_flow_fix.py
  Copy-Item .\contract_workflow_fix\test_contract_flow.py .\Quotation_KEKOREA\tests\
  uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_contract*.py" -v

Only if ALL tests pass:
  git status --short
  git add Quotation_KEKOREA/contracts/ui.py Quotation_KEKOREA/contracts/service.py Quotation_KEKOREA/contracts/flow.py Quotation_KEKOREA/tests/test_contract_flow.py
  git diff --cached --name-only
  git commit -m "Stop repeated contract questions and draft first"
  git push origin main

Do not add contract_workflow_fix/ helper directory to Git.
Do not re-run the apply script after a successful run; it checks exact original anchors.
GitHub and Streamlit deployment are NOT completed by this package.
