KE KOREA - contract UI simplification patch

1. Extract ZIP into the KE_KOREA_CO_LTD repository root.
2. In VS Code PowerShell, run:
   python .\contract_ui_simplification\apply_contract_ui_simplification.py
3. Contract tests:
   uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_contract*.py" -v
4. Confirm contract draft body appears before the collapsed review section.
5. Commit only Quotation_KEKOREA/contracts/ui.py after testing.

Note: This is a UI order/display change only. Export safety checks remain active.
