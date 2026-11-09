KE KOREA TASTE 계약서 UI + README 동기화 패키지
적용 대상: swihm1989-ship-it/KE_KOREA_CO_LTD 의 GitHub main, 2026-11-06 커밋 f9e7d05 기준.
변경 내용
- Quotation_KEKOREA/contracts/ui.py: 계약서 원문 우선, 서명 전 확인사항 한국어 요약, 원본 검토/확인 근거 입력 고급 메뉴, 최종 내보내기 검증 전체 항목 표시.
- Quotation_KEKOREA/contracts/review_summary.py: 미확정 이슈를 최대 5개 주제로 묶되 원본·상태는 절대 수정하지 않는 표시 전용 함수.
- Quotation_KEKOREA/tests/test_contract_review_summary.py: 검토항목 16개 요약·상태 보존 등 5개 테스트.
- scripts/check_readme_sync.py + Quotation_KEKOREA/tests/test_readme_sync_guard.py: 코드 변경/삭제를 커밋할 때 5개 README가 함께 스테이징됐는지 검사하는 회귀 검증.
- .githooks/pre-commit: 위 자동 검사를 실행하는 git hook (기존 사용자 정의 hook이 있으면 덮어쓰지 않음).
- 5개 README (루트, 프로젝트, 계약서, Team, Presentation)와 AGENTS.md의 최신 설명·기능 변경 보호 규칙을 동기화.
미변경: 무역 문서 PO/PI/CI/PL 계산·가격 로직, contracts/rules.py 최종 검증, Supabase 마이그레이션/DB, 기존 계약 데이터, AI 채팅·RAG 엔진.
적용 전 주의
- VS Code 프로젝트 루트의 작업 상태를 먼저 확인: git status --short
- 이전에 제공한 contract_review_ui_fix 패키지를 먼저 적용하지 않았다면 이 패키지만 사용한다. 이미 적용했다면 중복 패치하지 말고 오류 메시지를 확인한다.
- 다른 개발 중 파일 수정이 있는 경우 먼저 별도 커밋/백업한다. 스크립트는 일치하는 소스 코드 앵커가 없으면 수정 전에 중단한다.
- 자동으로 GitHub에 푸시하지 않는다.
실행 (프로젝트 루트 PowerShell)
ZIP을 압축 풀고 taste_contract_readme_update 폴더를 프로젝트 루트에 옮긴다.
python .\taste_contract_readme_update\apply_taste_contract_update.py
수정 전 원본 파일은 taste_contract_readme_update/backup_날짜_시각/에 자동 보관된다. 백업 폴더는 Git에 추가하지 않는다.
테스트
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_contract*.py" -v
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_readme_sync_guard.py" -v
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v
git diff --check
missing ScriptRunContext 와 use_container_width 경고는 테스트 결과 OK 여부와 구분한다. 전체 테스트는 기존 독립적인 실패가 있는지도 검토한다.
문서 변경 검토 및 Git 반영
git diff -- README.md Quotation_KEKOREA/README.md Quotation_KEKOREA/README_CONTRACTS.md Quotation_KEKOREA/Team/README.md Quotation_KEKOREA/Presentation/README.md Quotation_KEKOREA/AGENTS.md
코드와 5개 README, 보호 지침/자동 검사를 정확히 스테이징:
git add README.md
git add Quotation_KEKOREA/README.md
git add Quotation_KEKOREA/README_CONTRACTS.md
git add Quotation_KEKOREA/Team/README.md
git add Quotation_KEKOREA/Presentation/README.md
git add Quotation_KEKOREA/AGENTS.md
git add Quotation_KEKOREA/contracts/ui.py
git add Quotation_KEKOREA/contracts/review_summary.py
git add Quotation_KEKOREA/tests/test_contract_review_summary.py
git add Quotation_KEKOREA/tests/test_readme_sync_guard.py
git add scripts/check_readme_sync.py
git add .githooks/pre-commit

git diff --cached --name-only
python .\scripts\check_readme_sync.py
테스트 통과 및 스테이징된 내용 확인 후:
git commit -m "Streamline contract review UI and synchronize all READMEs"
git push origin main
git commit에는 기본적으로 .githooks/pre-commit 자동 검사가 적용된다. 기존 hook 설정이 있다면 덮어쓰지 않고 적용 메시지를 표시한다. 자동으로 hook을 사용하려면 기존 hook과 충돌하지 않는지 확인한 뒤 git config core.hooksPath .githooks를 실행한다.
운영 확인
Streamlit 배포 반영 후 합성 계약을 열어 (1) 계약서 문장 클릭/수정 (2) 요약 그룹/원본 16개 보존 (3) 최종 내보내기 차단 검증 (4) 지급조건 저장/갱신을 확인한다. 인증되지 않은 공개 앱에서는 실제 계약자료를 사용하지 않는다.

참고: TASTE Skill은 본래 랜딩페이지/리디자인 중심이다. 이 패키지는 전문 업무용 Streamlit UI에 적용 가능한 정보 계층, 밀도, 간격, 버튼 동작 등의 원칙만 사용한다.