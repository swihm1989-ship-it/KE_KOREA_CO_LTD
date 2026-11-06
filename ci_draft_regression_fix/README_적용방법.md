# CI DRAFT 회귀 보완

296개 중 실패한 `test_unconfirmed_ci_product_match_allows_draft_pdf`만을 수정합니다. PO/PI 확인 전 PDF/Excel 차단은 유지합니다.

```powershell
python .\ci_draft_regression_fix\apply_ci_draft_fix.py
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_review_ui.ReviewUiTests.test_unconfirmed_ci_product_match_allows_draft_pdf Quotation_KEKOREA.tests.test_product_matching_ui.ProductMatchingUiTests.test_annotations_load_prices_without_bypassing_product_confirmation -v
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v
git diff --check
git status --short
```

전체 테스트가 OK이면 프로젝트 README 5개와 app.py 변경사항만 `git add`/커밋하세요. 기존 서명된 계약·견적서·ECLADO 가격 데이터는 수정하지 않습니다.
