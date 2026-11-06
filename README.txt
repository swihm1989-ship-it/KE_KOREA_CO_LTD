KE KOREA contract-chat language patch (contracts only)

1. Extract this ZIP into a folder OUTSIDE the KE_KOREA_CO_LTD repo.
2. Open VS Code PowerShell terminal at the KE_KOREA_CO_LTD repo root.
3. Before applying, confirm you are on the intended branch:
     git branch --show-current
4. Run the patch (adjust location to the extracted script):
     python ..\contract_language_patch\apply_contract_language.py
5. Copy the test file into the repository's existing tests folder:
     Copy-Item ..\contract_language_patch\test_contract_language_policy.py .\Quotation_KEKOREA\tests\
6. Verify contract-only tests:
     uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_contract*.py" -v
7. Verify no unrelated files were changed:
     git diff --name-only
8. Full regression suite should also be run; a preexisting ECLADO product matching
   test failure may persist. Do NOT change any ECLADO or pricing code as a workaround.

Language policy:
- Korean or Korean+English -> Korean questions, replies.
- English-only -> English questions, replies.
- Output document language remains independent of conversation language.
- Existing stored messages are not rewritten.

This package does not automatically push or deploy anything.
