# KE KOREA — actual-source repair and login gate

이 패키지는 사용자가 업로드한 `KEKOREA_current_source.zip`의 **실제 4개 코드**를 그대로 기준으로 생성한 완성본입니다. 이전 `kekorea_*` 설치기를 다시 실행하지 마세요.

## 설치

프로젝트 루트에 `kekorea_actual_source_auth_fix` 폴더째 압축 해제하고 PowerShell에서:

```powershell
python .\kekorea_actual_source_auth_fix\install_actual.py
Test-Path .\Auth\gate.py
```

첫 번째 실행은 원본 SHA256이 업로드된 내용과 동일한지 확인하고, 전체 파일을 백업한 후 교체합니다. 이전처럼 UI 특정 문자열을 검색해 끼워 넣지 않습니다. **코드가 업로드 이후 달라졌으면 안전하게 중단합니다.**

## Streamlit Cloud Secrets

앱 Settings > Secrets 에 기존 OpenAI/Supabase 설정을 **보존**하고 다음을 추가합니다.

```toml
KEKOREA_AUTH_USERNAME = "kekorea"
KEKOREA_AUTH_PASSWORD = "12345"
KEKOREA_AUTH_SESSION_SECRET = "여기에 생성한 48자 이상의 무작위 키"
```

키 생성:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**12345는 테스트용입니다.** 외부 서비스에는 강한 암호로 변경하세요. 쿠키가 JavaScript에서 접근 가능하므로 사내 기밀용 정식 인증으로는 SSO/OIDC와 서버 측 세션 사용을 권장합니다. 로그인 최대 12시간이며, 새로고침 시 `st.context.cookies`로 복원합니다.

## 확인

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_kekorea_auth_and_issue_fix -q
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -q
python scripts/check_readme_sync.py
```

로그인이 없는 직접 UI 테스트는 의도적으로 로그인 gate와 별도 모듈에서 검증합니다. 최종 PDF 출력은 로그인된 관리자에게 직인 암호를 다시 요구하지 않습니다. 계약서 본문의 임시 확인 문구 검사·승인 체크박스·직인 이미지 검증은 유지합니다.

## Git 반영

```powershell
git add Auth/ Quotation_KEKOREA/app.py Quotation_KEKOREA/requirements.txt
 git add Quotation_KEKOREA/contracts/service.py Quotation_KEKOREA/contracts/ui.py Quotation_KEKOREA/contracts/workspace.py Quotation_KEKOREA/tests/test_kekorea_auth_and_issue_fix.py
 git add README.md Quotation_KEKOREA/README.md Quotation_KEKOREA/README_CONTRACTS.md Quotation_KEKOREA/Team/README.md Quotation_KEKOREA/Presentation/README.md
python scripts/check_readme_sync.py
git diff --cached --check
git commit -m "Integrate KE KOREA authentication and contract review fixes"
git -c gc.auto=0 push origin main
```

배포 repo `swihm1989-ship-it/KE_KOREA_CO_LTD`, branch `main`, main file `Quotation_KEKOREA/app.py`. Streamlit Cloud에서 Secrets 저장/재시작 후 로그인 화면이 뜨는지 확인하세요.
