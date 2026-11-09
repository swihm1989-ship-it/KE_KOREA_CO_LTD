KE KOREA Contract RAG Risk Review - Phase 1

Scope: Adds a read-only source-grounded review of up to five priority risks.
Existing RAG approved reference library, embedding and Supabase are reused.
No LangChain dependency or database migrations. No automatic contract modification.

1. Extract this ZIP inside KE_KOREA_CO_LTD (one folder contract_rag_review_patch).
2. From the KE_KOREA_CO_LTD root run:
   python .\contract_rag_review_patch\apply_contract_rag_review.py
3. Copy the regression test:
   Copy-Item .\contract_rag_review_patch\test_contract_rag_review.py .\Quotation_KEKOREA\tests\
4. Run:
   uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_contract*.py" -v
5. If successful, stage only these files:
   git add Quotation_KEKOREA/contracts/ui.py Quotation_KEKOREA/contracts/review.py Quotation_KEKOREA/tests/test_contract_rag_review.py
   git diff --cached --name-only
   git commit -m "Add source-grounded contract risk review"
   git push origin main

Important:
- This installs on the *latest simplified UI*, not the old UI version.
- Existing approved sample library is the only RAG source; unapproved uploads are excluded.
- It shows citations only when the AI returns source IDs supplied to it.
- No approved revision is automatically memorized. The current preferred-clause approval mechanism remains the source of reusable preferences. Phase 2 can surface a controlled one-click approval workflow after actual editing is confirmed.
- This is a draft review assistant, not legal advice. Current export validation is unchanged.
