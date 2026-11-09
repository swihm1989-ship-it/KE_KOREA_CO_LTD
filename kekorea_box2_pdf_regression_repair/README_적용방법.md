# KE KOREA BOX 2 / PDF 회귀 수정

**기존 `kekorea_clean_contract_exports` 패치를 적용한 프로젝트 전용**입니다. 프로젝트 루트에서 실행합니다. 설치 전 원본을 local_patch_backups/ 안에 백업하고, 앵커가 일치하지 않으면 파일을 수정하지 않습니다.

```powershell
python .\kekorea_box2_pdf_regression_repair\apply_box2_pdf_regression.py
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_contract_three_box_ui Quotation_KEKOREA.tests.test_contract_workspace_actions Quotation_KEKOREA.tests.test_contract_clean_exports -v
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v
python scripts/check_readme_sync.py
git diff --check
```

- 기존 tests/test_contract_workspace_actions.py에서 미확정 부록을 기대하던 검사를 실제 요구사항(본문만 출력)으로 수정합니다.
- 기존 tests/test_contract_three_box_ui.py에서 새 FINAL 승인 및 암호 정책을 고려하지 않던 회귀 검사를 수정합니다.
- 당사자/역할은 아래 표만 진짜 저장소이며, 위 표의 빈 buyer/seller 행을 제거합니다.
- 자동으로 계약 본문을 삭제하거나 직인을 사용하지 않습니다. `$`는 USD로 단정하지 않습니다.
- 실제 배포·직인 출력은 별도 검증이 필요합니다. ZIP 폴더와 백업은 Git에 추가하지 마세요.
