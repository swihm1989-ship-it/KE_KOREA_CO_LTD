# KE KOREA Orchestration Demo 배포 안내

> 이 앱은 **샘플 데이터용 UI**입니다. 실제 메일, 문서 생성, AI API, Supabase에 연결하지 않습니다.
> 기존 KE KOREA 견적서 앱 및 원본 `render.yaml`은 건드리지 않습니다.

## 필수 선행
1. 코어 PR #31 → Mock UI PR #32 순으로 테스트 통과 및 main 병합.
2. GitHub에서 `main`의 `Quotation_KEKOREA/orchestration/ui/streamlit_page.py`를 확인.
3. 사용자 본인이 Render 또는 Streamlit Cloud의 GitHub 접근 권한을 연결해 신규 앱 생성을 승인. 현재 GitHub에 코드/설정 파일을 추가해도 **앱 생성/호스팅은 자동으로 이루어지지 않습니다**.

## 1. Streamlit Community Cloud (기존 앱과 별도)
1. https://share.streamlit.io 접속 후 **Create app**.
2. Repository: `swihm1989-ship-it/KE_KOREA_CO_LTD`
3. Branch: `main`
4. Main file path: `Quotation_KEKOREA/orchestration/ui/streamlit_page.py`
5. App URL은 서비스에서 사용 가능한 고유 이름을 지정(예: `ke-korea-orchestration-demo`, 예약/사용 가능 여부 미확인).
6. Deploy 후 브라우저에서 **메일함 → 업무 시작 → 문서 검토 → 발송 대기** 순으로 샘플 테스트.
7. 패키지는 진입점 폴더 `ui/requirements.txt`를 기준으로 설치. 실제 메일 서버 정보와 API 키를 입력하지 마세요.

**실제 URL:** Streamlit Cloud에서 생성 완료 후에만 확인 가능하며 README에 추측 주소를 기재하지 않습니다.

## 2. Render (기존 운영 서비스와 독립)
1. https://dashboard.render.com 접속 후 **New > Blueprint**.
2. 동일 GitHub 저장소를 연결.
3. Branch: `main` (PR 검증/병합 이후)
4. **Blueprint Path: `render-orchestration.yaml`** (반드시 정확히 입력; 기본 `render.yaml` 선택 금지).
5. 제시되는 신규 서비스가 `ke-korea-orchestration-demo` 하나이며 기존 `ke-korea-quotation` 서비스의 변경이 없는지 확인 후 승인.
6. Deploy Blueprint 완료 후 신규 `*.onrender.com` 주소 확인.
7. 이 Blueprint는 `autoDeployTrigger: off`로 명시하여 운영 중 기존 앱의 배포와 분리.
8. 실패 시 Render 이벤트/로그에서 Python 버전·패키지 설치·서버 시작 확인. 무료 플랜은 유휴 시 절전될 수 있음.

**주의:** 동일 Render 리소스를 여러 Blueprint로 관리하면 충돌 위험이 있습니다. 기존 `render.yaml`을 수정하거나 기존 `ke-korea-quotation` 서비스 이름을 재사용하면 안 됩니다.

## 3. 로컬 실행 (Windows VS Code)

현재 로컬 `main`만 있을 경우, PR #31/#32가 병합되지 않았다면 코드는 존재하지 않습니다. 병합한 이후 `git fetch origin`으로 확인한 뒤 별도 worktree에서 실행하면 됩니다.

```powershell
python -m pip install -r Quotation_KEKOREA/orchestration/ui/requirements.txt
streamlit run Quotation_KEKOREA/orchestration/ui/streamlit_page.py
```

Streamlit이 출력하는 로컬 주소(일반적으로 `http://localhost:8501`)로 접속합니다. 이미 8501 포트가 사용 중이면 `--server.port 8502`로 실행하세요.

## 4. 출시 범위/보안

- 메일함·가상 문서·검토·이메일 최종 승인 **모두 Mock**, 메일 발송 버튼 비활성.
- 세션 상태만 보존. 테스트 화면을 종료하면 작업 내역 보존이 보장되지 않음.
- 기존 `agent/`, `contracts/`, `app.py`, DB, 기존 Render 설정은 변경 없음.
- 실제 메일 연결·운영 데이터 사용은 별도 승인/인증/회귀 테스트 후에만 도입.


## 2026-11-11 · 오케스트레이션 검토용 파일 생성 (PR #36)

독립 `orchestration/workflows/draft_files.py`에서 기존 계약서 `contracts.draft_exports.export_draft`를 **그대로 호출**하여 이미 작성된 조항의 검토용 PDF/DOCX를 생성한다. PI/PO/CI/PL은 기존 `agent.trade_documents.validate_and_calculate` 결과가 차단 이슈 없이 확인된 경우 신규 **비직인·비공식 DRAFT DOCX 검토 시트**만 생성한다. 기존 `agent.pi_pdf.render_trade_document`는 회사 직인 파일을 필수로 요구하므로 **무역서류 PDF를 신규 UI에서 만들지 않으며** 직인·서명/최종 발행 절차를 우회하지 않는다. 신규 파일은 메모리에만 생성되며 다운로드 시 SHA-256 해시, DRAFT·비발행·발송불가가 명시되고, 입력값이 달라지면 기존 파일 다운로드를 노출하지 않는다. 신규 UI 의존성 `python-docx`, `reportlab`은 `orchestration/ui/requirements.txt`에만 추가했다. 기존 `app.py`, `agent/`, `contracts/`, 운영 `render.yaml`, DB, WHOIS POP3/SMTP는 변경하지 않았다. 별도 배포는 GitHub main 반영 후 다시 배포해야 새 기능을 볼 수 있다.


## 2026-11-11 · 독립 오케스트레이션 요청→문서→이메일 초안 통합 검토 (PR #37)

새 `Quotation_KEKOREA/orchestration/workflows/unified_review.py`와 별도 Streamlit UI의 **통합 업무 흐름** 화면에서 업무 지시문의 키워드를 기존 보수적 Router로 문서 종류로 분류하고, 사용자가 명시적으로 입력한 문서별 JSON 조건으로 기존 검증·검토용 DRAFT 파일 생성 엔진을 호출한다. **AI API/실메일 연동이 아닌 키워드·구조화 입력 기반**이다. 미확정 조건은 차단하고, 생성된 파일별 SHA-256 무결성 및 원본 조건의 해시를 확인해 문서별 DRAFT 검토를 기록한 뒤 이메일 초안 검토 단계로만 진행한다. 요청 조건 변경은 문서·메일 검토를 모두 취소하고 이메일 본문 변경은 메일 검토만 취소한다. 검토 완료 상태조차 `can_send=False`이며 실제 POP3/SMTP, 송신, 계약 FINAL, 직인, 저장/전송 작업은 없다. 실무 운영용 완전자동 생성이나 실계정 접근 기능으로 해석하지 않는다. 기존 `app.py`, `agent/`, `contracts/`, DB, 기본 `render.yaml`은 수정하지 않았다. 독립 `ui/streamlit_page.py` 배포 서비스는 `main` 병합 후 별도 재배포가 필요하다. 테스트: `orchestration/tests/test_unified_review.py`, `test_unified_ui.py`.
