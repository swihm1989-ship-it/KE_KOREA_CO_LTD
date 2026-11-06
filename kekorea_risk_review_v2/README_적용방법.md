# KE KOREA · AI 핵심 위험 검토 UI 구현 패키지

적용 대상: `swihm1989-ship-it/KE_KOREA_CO_LTD` 최신 `main`의 `Quotation_KEKOREA/contracts/ui.py`.

기능 및 UI는 사용자에게 미리 보여준 예시를 기준으로 설계합니다.

- 전체 계약 문장을 나누어 AI 핵심 위험을 검토하며, 결과는 한 페이지에 최대 5건 표시합니다.
- 결과 카드 클릭 / `1, 2, 3 ...` 페이지 이동 (10페이지 이상일 경우 페이지 선택).
- 선택한 위험 항목에 AI가 **균형형 / 권리 보호형 / 보수적 협의형 3개 추천 문장**을 제시합니다.
- AI가 식별한 **숫자·기간·법인명 등 가변 정보**를 직접 입력하고, 문장 전체도 편집할 수 있습니다.
- `추천 문장 적용`: **BOX 3의 수정 미리보기만 변경**합니다. DB에 즉시 확정 저장하지 않습니다.
- `선택한 수정안 비교·승인`: 기존 계약서의 수정안 비교 및 revision 적용 절차로 연결합니다.
- 기존 위험 검토의 승인된 참고자료 검증, 거래 조건·금액·은행·법률 검증, 기존 메모 일괄 수정, ECLADO / PO / PI / CI / PL은 변경하지 않습니다.
- 모든 README 5개를 기록합니다.

**가짜 사례 12개를 실제 AI 결과처럼 표시하지 않습니다.** 결과 수는 실제 계약 본문과 모델 분석 결과에 따라 달라집니다. ‘글로벌 평균’이라고 보증하지 않으며 AI 추천은 협의용 예시입니다.

## 적용

ZIP 압축 해제 후 `kekorea_risk_review_v2` 폴더를 프로젝트 최상위 루트에 복사합니다.

```powershell
# 기존 프로젝트 폴더에서 실행
python .\kekorea_risk_review_v2\apply_risk_review_v2.py
```

스크립트는 수정 전에 파일을 `kekorea_risk_review_v2/backup_날짜_시각/`에 백업합니다. 이미 적용됐거나 예상과 다른 `ui.py`이면 파일을 덮어쓰지 않고 중단합니다.

직접 수정한 다른 기능이 있다면 백업·diff를 확인한 뒤 적용하세요. 자동으로 커밋하거나 배포하지 않습니다.

## 검증

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_contract_risk_review_v2 -v
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v
git diff --check
python scripts/check_readme_sync.py
git status --short
```

`git diff --check` 출력 없이 테스트가 `OK`여야 합니다. UI 테스트는 `streamlit.testing.v1.AppTest`를 사용하므로 Streamlit 패키지가 설치되어 있어야 합니다. 실패 시 **GitHub에 푸시하지 말고** 테스트 로그를 확인하세요.

최초 전체 테스트가 통과하고, Streamlit에서 BOX 3의 위험 항목 2개 이상을 편집·비교·승인하는 동작을 검수한 뒤, 실제 수정된 코드 3개, 테스트 1개, README 5개만 선택해서 커밋하세요. 임시 패키지 폴더나 백업은 Git에 추가하지 마세요.

## 주요 수정 파일

기존 변경: `Quotation_KEKOREA/contracts/ui.py` (해당 위험 검토 영역과 문장 미리보기 연결만).

신규 파일:

- `Quotation_KEKOREA/contracts/risk_review_workspace.py`
- `Quotation_KEKOREA/contracts/risk_review_ui.py`
- `Quotation_KEKOREA/tests/test_contract_risk_review_v2.py`

문서: `README.md`, `Quotation_KEKOREA/README.md`, `Quotation_KEKOREA/README_CONTRACTS.md`, `Quotation_KEKOREA/Team/README.md`, `Quotation_KEKOREA/Presentation/README.md`.

## 주의사항

- `추천 문장 적용`은 미리보기이며, 승인된 수정만 원본 계약서 revision으로 저장합니다.
- 커미션 지급 정책으로 생성되는 조항은 기존 BOX 2 지급조건 편집기를 이용해야 합니다.
- AI는 재검토 요청에서 여러 문장·금액 조건 사이의 모든 법적 충돌을 탐지한다는 보장이 없습니다. 사용자가 수정 전후를 확인해야 합니다.
- 검토 결과가 12개 이상인 경우에도 5건씩 페이지 이동합니다. 다만 AI가 실제로 발견하지 않은 위험을 인위적으로 생성하지 않습니다.
- 실제 운영 Streamlit 배포와 사용자 PC의 전체 테스트는 이 패키지 제작 환경에서 확인하지 못했습니다.
