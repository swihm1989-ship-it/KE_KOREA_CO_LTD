# 위험 검토 UI 테스트 오류 수정

## 원인

`test_contract_risk_review_v2.py`의 테스트 데이터는 `sentence_id = 's1' if i % 2 else 's2'`로 생성됩니다. 따라서 6번 위험(index 5)은 s1이고 7번 위험(index 6)은 s2입니다. 원래 테스트는 7번을 클릭해 놓고 `risk_edited_sample_1_s1`을 찾았기 때문에 `KeyError`가 발생했습니다.

## 적용

1. ZIP의 `kekorea_risk_review_test_fix` 폴더를 프로젝트 최상위 `KE_KOREA_CO_LTD`에 압축 해제합니다.
2. 프로젝트 최상위 PowerShell에서 다음 명령을 실행합니다.

```powershell
python .\kekorea_risk_review_test_fix\apply_test_fix.py
```

해당 스크립트는 **테스트 파일 1개만 수정**하며 기존 테스트 파일 백업을 `.bak`으로 만듭니다. 실제 Streamlit UI, 위험 검토, AI, PDF/Word, README는 전혀 변경하지 않습니다.

## 검증

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_contract_risk_review_v2 -v
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v
git diff --check
git status --short
```

모든 테스트 통과 후 필요하다면 테스트 파일 1개만 Git에 추가하세요. `.bak`, ZIP 및 적용 스크립트 폴더는 커밋하지 않습니다.

```powershell
git add Quotation_KEKOREA/tests/test_contract_risk_review_v2.py
git diff --cached --check
git commit -m "Fix risk review pagination test sentence selection"
git push origin main
```

**주의:** 이미 다른 미커밋 변경이 있다면 무단으로 추가하거나 삭제하지 마세요. `use_container_width` 경고는 이번 KeyError와 무관하며, 다른 코드 수정을 방지하기 위해 이번 패치에서 처리하지 않습니다.
