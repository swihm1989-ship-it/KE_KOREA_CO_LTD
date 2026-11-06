KE KOREA CONTRACT CHAT KOREAN/ENGLISH FOLLOW-UP FIX (v2)

WHY: Earlier change classified mixed Korean-English input correctly but accepted
English questions from the model. This adds a conditional translation call for
questions/issues with the wrong language, preserving all contract business data.

Run inside KE_KOREA_CO_LTD project root in VS Code PowerShell:

  python .\apply_contract_language_v2.py
  Copy-Item .\test_contract_language_fallback.py .\Quotation_KEKOREA\tests\
  uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_contract_language_fallback -v
  uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_contract*.py" -v

The first script changes ONLY Quotation_KEKOREA/contracts/service.py. It stops
safely when the expected code is absent and is idempotent (re-running is safe).
The test should be copied to Quotation_KEKOREA/tests before running.

When tests pass, commit ONLY the contract service and test files, then push
main using your usual controlled GitHub workflow. No changes to ECLADO or PI/PO/CI/PL.

NOTE: Localization consumes a second OpenAI API request only when needed. If
AI still produces output in the wrong language after translation, the program
reports an error rather than saving a noncompliant analysis. This implementation
uses the same configured model and API key as contract analysis.
