# KE KOREA 개인 프로젝트 — 후이즈메일 멀티에이전트 오케스트레이션 설계

> **초기 설계 기록 · 2026-11-11. 현재 구현은 아래 2026-11-13 변경 이력 참조.**
>
> 개인 저장소 `swihm1989-ship-it/KE_KOREA_CO_LTD`에 기존 Streamlit 무역문서/계약서 에이전트를 **손대지 않고** 별도 오케스트레이션 시스템을 추가하기 위한 README. 이 파일을 추가했다고 수신·발송·계약서 연동이 작동하는 것은 아니다.
>
> 작업 보호 원칙: 기존 `Quotation_KEKOREA/app.py`, `agent/`, `contracts/`, `tests/`, `supabase/`, 설정/배포/DB 마이그레이션, 기존 저장 문서와 `main`의 동작은 절대 수정하지 않는다. 이 계획이 승인되기 전 구현·패키지 추가·메일 연결·발송 금지. 회사 **팀 저장소** `encore-ai-campus/aio-03-p2-team3`도 수정하지 않는다.

## 1. 목표와 기존 코드 기준선

후이즈메일에서 사용자가 받은 문의·발주 이메일/첨부를 **읽기 전용으로** 가져오고, AI가 어떤 업무인지 분류하여 **기존 PI, PO, CI, PL 및 계약서 엔진**을 이용해 검토용 초안을 준비한다. 사람이 **문서 자체를 먼저 검토/승인**하고, 이어 수신자/제목/본문/첨부가 확정된 **발송용 이메일을 별도로 승인**한 경우에만 후이즈 SMTP로 발송하는 흐름을 목표로 한다.

기존 개인 저장소에서 확인한 항목:
- **Streamlit 진입:** `Quotation_KEKOREA/app.py` (무역 문서 생성), `contracts/ui.py` (계약서 BOX 1/2/3).
- **무역 문서:** `agent/trade_documents.py` (PO/PI/CI/PL 금액·수량 계산과 검증), 기타 기존 `agent/` 업무 모듈. 기존 PDF/Excel 출력·회사 설정·가격/단위 규칙 **변경 금지**.
- **계약:** `contracts/ai_graph.py`의 LangGraph 계약 초안 그래프, `contracts/drafting.py`, `contracts/repository.py`, `contracts/exports.py` 및 검토 승인/revision/FINAL 게이트. 계약 AI는 사용자 확정 전에 거래조건을 제안값으로 취급하며 검토 오류가 있으면 FINAL 제한. 기존 계약 화면의 보안 경고와 접근 통제 문제 해결 여부는 운영 전 별도 확인 필요.
- **현재 시스템에 없는 기능(이 설계의 대상):** 후이즈메일 받은편지함 동기화·SMTP 발송, 기존 문서/계약 엔진을 조정하는 새 Master Orchestrator, 첨부 묶음 고정과 **이메일 전송 별도 승인**. 아직 구현됐다고 주장하지 않는다.

## 2. 후이즈메일 기술 선택 — 검증된 사항 vs 확인 필요

후이즈 공식 문서에서는 메일 클라이언트용 **POP3/SMTP**를 안내한다. 제품 유형에 따라 서버 주소와 포트/보안 설정이 달라질 수 있다.

- 공식 참고: [후이즈메일 상품](https://email.whois.co.kr/v2/webmail.php), [후이즈 Outlook 안내](https://m.whois.co.kr/mail_wmail.php?act=outlook), [후이즈 일반 설정 안내](https://m.whois.co.kr/mail_wmail.php?act=process).
- 문서에 POP3 포트 **995** 및 SMTP **587** 사례가 안내되어 있다. 다른 후이즈 설정 페이지에는 POP 110과 SMTP 25/587도 있으므로 **우리 계정의 실제 서비스 상품별 설정**을 후이즈 관리자/고객센터에서 확인해야 한다. 서버명을 `mail.w.<도메인>`으로 고정하지 않는다.
- **IMAP·Webhook·후이즈메일 공개 API를 사용할 수 있는지는 미확인.** Gmail Pub/Sub/History API와 달리, 후이즈 POP3 기본 방식은 일반적으로 **정기 Polling**이 필요하다. API/IMAP이 실제 지원된다는 근거가 확보되면 어댑터만 교체하는 설계를 유지한다.
- **POP3 수신은 읽기 전용:** 가능한 `UIDL` 기준으로 신규 메시지를 식별하고 `RETR`로 가져오며, `DELE` 호출 금지. UIDL이 없거나 일관성 보장 불가하면 메일 원문 헤더/해시와 서버별 식별자를 병용하고 자동 처리하지 않는 예외 정책 필요.
- POP3는 Gmail의 스레드/메일함 API와 같지 않다. `Message-ID`, `In-Reply-To`, `References`로 연결관계를 추정하되 **메일 헤더 누락·중복 가능성**을 검증한다. 자기 발신 메일 루프·자동응답·스팸은 별도 정책으로 걸러야 한다.
- SMTP는 인증 및 TLS 설정 확인 후에만 사용. 암호 없는 로그인/평문 발송 금지. SMTP timeout은 실제 전송 여부 불확실 상태일 수 있어 **무조건 재전송 금지**.
- 후이즈 웹메일의 대용량 첨부 기능이 곧 외부 SMTP의 첨부 한도라는 뜻은 아니다. 실계정에서 **허용 용량·첨부 수·초당/일일 발송 제한·보낸편지함 기록 가능 여부**를 확인해야 한다.
- 비밀번호·앱 비밀번호·계정주소·거래처 실데이터는 **환경변수/시크릿 저장소**에만 둔다. README, Git, 테스트 fixture, AI 프롬프트/실행 로그에 기록 금지.

## 3. 추천 폴더 분리 (VS Code 프로젝트는 그대로, 신규 코드만 별도)

```text
KE_KOREA_CO_LTD/                      # 기존 개인 GitHub 저장소
├── README.md                         # 기존 안내: 필요시 문서 링크만 추가
└── Quotation_KEKOREA/
    ├── app.py                        # [PROTECTED] 기존 Streamlit 앱
    ├── agent/                        # [PROTECTED] 기존 PI/PO/CI/PL 엔진
    ├── contracts/                    # [PROTECTED] 기존 계약서/LangGraph/RAG/승인
    ├── tests/                        # [PROTECTED] 기존 테스트
    ├── supabase/                     # [PROTECTED] 기존 DB/마이그레이션
    ├── Team/                         # 기존 팀 안내
    ├── Presentation/                 # 기존 발표 안내
    └── orchestration/                # [NEW] 미래 신규 기능 격리 폴더
        ├── README.md                 # [NOW] 설계만 추가됨
        ├── master_graph.py           # [FUTURE] 독립 LangGraph Master
        ├── state.py                  # [FUTURE] 기존 계약 State와 분리
        ├── router.py                 # [FUTURE] 요청 유형 분류
        ├── adapters/                 # [FUTURE] 기존 기능에 대한 보호된 연결 계층
        │   ├── whois_pop3.py         # 수신 전용
        │   ├── whois_smtp.py         # 승인 후 전송 전용
        │   ├── trade_adapter.py      # 기존 trade 업무 인터페이스
        │   └── contract_adapter.py   # 기존 계약 업무 인터페이스
        ├── workflows/                # [FUTURE] 문서 의존 순서/검토 흐름
        │   ├── document_tasks.py
        │   └── email_draft.py
        ├── approval/                 # [FUTURE] 이메일 전체 최종 승인
        │   └── send_gate.py
        ├── security/                 # [FUTURE] 수신자·첨부 해시·정책
        │   └── attachment_manifest.py
        ├── persistence/              # [FUTURE] 새로운 실행 이력/멱등성
        │   └── run_repository.py
        └── ui/                       # [FUTURE] 초기에는 독립 화면
            └── streamlit_page.py
```

**중요:** 위 `[FUTURE]` 파일과 폴더는 이번 README에 설명한 **예정 구조**이지 실제 생성된 파일이 아니다. 기존 `agent/`, `contracts/`를 이동·이름 변경·복사하지 않는다.

**VS Code에서 작업하는 방법:** 같은 저장소이되 `git worktree` 또는 별도 개발 브랜치/작업 폴더로 분리. 기존 Streamlit 페이지에 메뉴를 붙이기 위해 `app.py`를 수정해야 한다면 **현재 보호 조건에 따라 통합하지 않고**, 별도의 독립 Streamlit 실행 진입점을 이후 새 파일로 만드는 방안을 우선 고려. 기존 앱 메뉴 통합은 사용자로부터 **별도 명시적 수정 승인**을 받은 뒤에만 검토.

**DB:** 기존 Supabase 계약/무역 테이블은 불변. 신규 `mail_orchestration_runs`, `mail_processed_messages`, `mail_document_links`, `mail_approval_envelopes`, `mail_send_intents` 등의 **신규 전용 테이블만 별도 마이그레이션으로 제안**. 이번 README 작업에서는 DB를 생성하지 않음.

## 4. 전체 아키텍처와 실행 원칙

```text
후이즈 POP3 읽기 전용 Poller
   ↓  UIDL/헤더 기반 중복 제거 · 원문/첨부 파싱 · 사용자 계정 확인
Master LangGraph (독립 state/checkpointer; 기존 코드 호출만)
   ├─ Intent Router → 계약 문의 / 발주 / PI / PO / CI / PL / 단순 답장
   ├─ Trade Adapter → 기존 무역문서 엔진의 검증된 공개 인터페이스
   ├─ Contract Adapter → 기존 계약 엔진(approval/revision 규칙 보존)
   └─ Validation Gate → 누락·출처·계산·문서 간 일치 확인
   ↓
사용자 문서별 검토 → 문서별 승인/개정 버전 확정
   ↓
승인 문서 PDF/XLSX/DOCX의 실제 bytes SHA-256 및 파일 manifest 고정
   ↓
메일 초안: 수신자/CC/BCC/제목/본문/Reply headers/첨부
   ↓
사용자 최종 메일 승인 (manifest+envelope hash 고정)
   ↓
Whois SMTP Sender: **승인된 SendIntent만** 1회 전송 시도
   ↓
sent / send_unknown / failed 분리 기록, 발송 원문/파일 감사 이력
```

- **AI는 추출·분류·문안 작성**만. 금액·수량·환산·상품·승인·서명/직인·최종 발송은 기존 계산/검증 코드와 사용자 결정으로 처리.
- 기존 계약서 `suggested/confirmed/missing` 상태·revision·FINAL 차단을 우회하지 않는다.
- CI는 관련 승인 PI의 특정 버전·가격 근거에 의존하도록 설계하고, PL은 포장 수량 검토를 먼저 완료한다. 개인 프로젝트의 실제 CI/PL 승인 인터페이스를 개발 전에 재확인하고 차이가 있으면 기존 로직을 강제로 바꾸지 않는다.
- 여러 문서 동시 요청 시 **독립 항목은 병렬**, PI→CI 등 의존 항목은 순차. 어느 한 문서라도 승인되지 않으면 그 파일을 발송하지 않으며, 원칙적으로 **묶음 발송 전체를 보류**(정책 변경은 사용자 결정).
- **문서 승인 ≠ 메일 승인**: 최종 발신자·to/cc/bcc·제목·본문·Reply headers·첨부 ID/버전/해시 모두 사용자가 별도 확인. 승인 뒤 변경되면 무효화하고 재승인.

### 제안 상태·데이터 계약

```text
MailRun: run_id, mailbox_id, pop_uidl, header_message_id,
         source_hash, status, retry_count, error_code
DocumentTask: run_id, kind, snapshot_id, revision, proposal_id,
              document_status, approval_status, file_ids
AttachmentManifest: file_id, owner_id, revision, filename, mime_type,
                    byte_length, sha256, approved_at
EmailEnvelope: from, to, cc, bcc, subject, body,
               in_reply_to, references, attachment_manifest_ids,
               envelope_sha256, approved_by, approved_at
SendIntent: run_id, envelope_sha256, idempotency_key, status,
            smtp_attempt_at, smtp_acceptance_id, last_error
```

상태: `received→classified→needs_input|drafting→awaiting_document_approval→awaiting_email_approval→sending→sent`; 장애 `failed|send_unknown|cancelled`. 실행 기록은 신규 DB 또는 영속 체크포인터에 저장(초기 개발 단계에서는 `InMemorySaver`만 사용하여 운영 복구가 완료됐다고 표시하지 말 것).

**발송 멱등성:** SMTP에는 Gmail API의 메시지 ID 기반 완전한 exactly-once 보장이 없으므로, 먼저 **DB에서 전송 의도를 단 한 번 claim**하고 SMTP 시도한다. SMTP 수락 후 연결이 끊긴 경우에는 `send_unknown`으로 정지하고 관리자/사용자 확인. 전송된 편지함에 접근 가능한지/SMTP Message-ID를 매칭할 수 있는지는 후이즈 서비스 상품에서 별도 확인해야 한다.

## 5. 기존 기능 보호 정책 / 충돌 레지스터

| ID | 위험 | 강제 대응 |
|---|---|---|
| P01 | `app.py`·계약/무역 UI를 새 코드 때문에 수정 | **금지**. 신규 독립 UI 사용, 메뉴 통합은 별도 승인 |
| P02 | 기존 계약 revision/FINAL 또는 무역 계산 변경 | **금지**. 기존 공개 서비스 인터페이스와 테스트 결과 재사용 |
| P03 | 후이즈 POP3 수신 후 메일 삭제/중복 처리 | `DELE` 금지, UIDL·메일 헤더/해시로 중복 제거, 읽기 전용 |
| P04 | IMAP/API/Push를 Gmail처럼 가정 | 금지. 후이즈 상품별 POP3/SMTP 실사용 확인 전 임의 URL·포트 고정 금지 |
| P05 | SMTP timeout·중복 클릭으로 이중 발송 | 원자적 SendIntent claim + `send_unknown`/수동 확인, 자동 재전송 금지 |
| P06 | 계약 초안·PI 등 문서 미승인 상태에서 첨부 | 파일 승인+revision+SHA256 검증 전 SMTP 호출 금지 |
| P07 | 이메일의 악성 프롬프트가 승인·지급조건을 변경 | 수신 본문은 비신뢰 데이터. 시스템/도구/권한 지시로 처리 금지 |
| P08 | 개인 기밀/계좌/서명/직인/실메일 유출 | 실제 자료 공개 저장소·AI 모델 테스트 입력 금지, 최소 저장/권한 분리 |
| P09 | 다른 업무 에이전트와 코드·DB 공유 중 충돌 | 새 실행 테이블/상태/테스트 전용. 기존 API 변경이 필요하면 **구현 보류 후 보고** |

**불변 조건 점검:** 이 구현을 위해 기존 파일의 수정이 조금이라도 필요한 경우 자동 패치하지 말고, `(1) 왜 필요한지 (2) 새 파일만으로 우회 가능한지 (3) 어떤 동작이 바뀌는지 (4) 승인 필요한 기존 파일`을 사용자에게 보고한다. 사용자 승인 전 변경하지 않는다.

## 6. 구현 전에 확인해야 할 후이즈 설정 체크리스트

- [ ] 현재 사용하는 후이즈메일 상품명/메일 서버 호스트/로그인 방식/POP 활성화 경로
- [ ] POP3 TLS 연결과 서버 인증서 검증 방식, UIDL 지원/안정성 확인
- [ ] SMTP 587 STARTTLS/인증 방식과 첨부파일 제한·발송 제한
- [ ] POP3가 수신 후 서버 메일을 보존하는 옵션 및 메일 삭제 방지 확인
- [ ] 테스트 계정 1개(실제 거래 메일이 없는 계정), 발신/수신 테스트 주소
- [ ] 자동 회신·보낸편지함 확인 가능 여부(중복 발송 감사 방법)
- [ ] 기존 Supabase 사용자 권한·암호화 시크릿 저장/백업·보존 정책
- [ ] 메일·계약서 원문을 외부 AI API에 보낼 때의 개인정보·기밀 처리 기준

**환경변수 예시 (값 넣지 않음):** `WHOIS_POP_HOST`, `WHOIS_POP_PORT`, `WHOIS_POP_USERNAME`, `WHOIS_POP_PASSWORD`, `WHOIS_SMTP_HOST`, `WHOIS_SMTP_PORT`, `WHOIS_SMTP_USERNAME`, `WHOIS_SMTP_PASSWORD`, `WHOIS_MAIL_FROM`, `MAIL_POLL_INTERVAL_SECONDS`, `ORCHESTRATION_ENABLED=false`. 특정 호스트/비밀번호는 계정 관리자 확인 후에만 사용한다.

## 7. Superpowers 방식의 향후 구현 로드맵 — 모든 작업 미착수

**원칙:** 이 단계는 설계이며 아직 코드 변경 허가가 아니다. `brainstorming→writing-plans→TDD→code-review→verification` 순서로, 한 기능=한 브랜치/PR. **기존 메인/현재 배포 보호**, 반드시 별도 worktree에서 구현.

| 단계 | 설계·향후 개발 과제 | 완료 기준 |
|---|---|---|
| 0 | 기존 코드/테스트/PDF 출력 기준선 고정 | 기존 계약·PI/PO/CI/PL 가상 시나리오 출력 동일, rollback/변경 금지 파일 목록 |
| 1 | 후이즈 POP3/SMTP 설정 검증 및 읽기 전용 Poller **분리** | UIDL 중복 제거, 삭제 0건, 서버오류 복구, 비밀정보 로그 없음 |
| 2 | 독립 Master LangGraph·Router (메일 읽기만) | 기존 Streamlit·DB 동작 그대로; 라우팅만 테스트 |
| 3 | TradeAdapter / ContractAdapter 기존 함수·저장 경계 확정 | 기존 금액/조건/revision/승인/출력 결과 동일 |
| 4 | 문서 작업 의존성·누락 항목 처리·승인 대기 | 미확정·누락 정보에 대해 임의 확정 없음 |
| 5 | PDF/DOCX/XLSX 첨부 manifest + 이메일 미리보기 | 승인 문서 파일 SHA256 불변, 변경 시 재승인 |
| 6 | **별도** 사람 이메일 승인 게이트 + SMTP 단발 송신 | 명시적 승인 없이는 네트워크 발송 0회, 중복 클릭에도 1개 intent |
| 7 | 실패 복구·보안·권한·성능·운영 모니터링 | POP/SMTP 네트워크 장애, 이중발송, 서버 재시작, 권한·기밀 테스트 |
| 8 | 테스트 계정에서 E2E 검증 → 선택적 앱 통합 결정 | 테스트/코드 리뷰 통과 후 사용자 승인; 기존 앱 UI 통합 별도 승인 |

### 필수 테스트

- 기존: 기존 테스트 전부 통과 + 계약서/무역서류 PDF·DOCX·Excel 내용과 revision·승인 결과 비교.
- 메일: UIDL 중복 조회/중복 폴링/서버 메일 보존, Message-ID 없는 메일, 첨부 파일명/인코딩, 빈·손상 파일, 송수신자 스푸핑, 인젝션.
- 거래: 가격/수량 미정은 재확인, PI→CI 가격·수량 일치, PL 합계 검증, 계약서 조항 근거·보안/승인.
- 최종 승인: 문서 승인 후 이메일 발송 승인 별도, 수신자/본문/첨부/revision/파일 바이트 변경 시 재승인.
- 발송: SMTP 실패/timeout/응답 유실, 동시 클릭, 서버 재시작, 중복 intent, `send_unknown`에서 자동 재발송 금지.
- 비활성: `ORCHESTRATION_ENABLED=false`면 기존 Streamlit 화면과 기존 계약/무역 경로는 결과 변화 없어야 함.
- 검증 결과는 **실제 실행 후에만** 통과라 표기하며, 현재는 모두 미실행이다.

## 8. 다음 단계에 Codex/Superpowers에 줄 프롬프트 (지금은 실행 금지)

```text
KE_KOREA_CO_LTD 개인 저장소의 Quotation_KEKOREA/orchestration/README.md를 먼저 읽고,
Superpowers brainstorming/writing-plans 기준으로 [단계 번호] 하나를 검토해줘.
기존 Quotation_KEKOREA/app.py, agent/, contracts/, tests/, supabase/,
개인 기존 실행/배포 설정과 encore-ai-campus 팀 저장소는 수정하지 마.
동등 기능이 존재하면 중복 구현 금지; 필요한 새 기능은 orchestration/ 내부로 분리.
기존 모듈을 바꿔야 한다면 구현을 중단하고 충돌·대안·승인 필요 파일을 보고해.
테스트 계정과 가상 데이터만 사용하고, 메일 송신은 사람이 최종 승인하기 전 절대 금지.
현재는 설계안만 작성한 상태이며, 추후 명시적인 구현 허가가 있어야 실행해.
```

## 9. 이번 문서의 범위 요약

- **저장소:** 개인 `swihm1989-ship-it/KE_KOREA_CO_LTD`
- **새 README 경로:** `Quotation_KEKOREA/orchestration/README.md`
- **변경 내용:** 폴더 분리·후이즈 POP3/SMTP·Master LangGraph·기존 PI/PO/CI/PL/계약 재사용·사람 승인·회귀 테스트 로드맵.
- **현재 구현 여부:** 새 mail orchestration 코드 **미구현**, 메일 계정 연결/발송 **미수행**, 기존 앱/DB/설정 **수정 없음**.


## 10. 실제 1단계 구현 상태 (2026-11-11 · 별도 PR, 아직 main 미병합)

**앞선 1~9절은 원래 목표/미래 폴더 구조를 설명한 설계 기록이다. 그 안의 `[FUTURE]` 문구는 최초 작성 시점 기준이며 아래 구현 현황을 우선 적용한다.** 현재 구현된 것은 메일 수신기가 아니라 **기존 앱과 연결되지 않는 독립 코어**이다.

| 파일 | 현재 수준 |
| --- | --- |
| `__init__.py`, `state.py`, `router.py` | 패키지, 독립 State, PI/PO/CI/PL/CONTRACT 보수적 분류 |
| `master_graph.py` | `classify → prepare → END` 독립 LangGraph. 결과는 `needs_input`에서 정지 |
| `adapters/trade_adapter.py`, `adapters/contract_adapter.py` | **인터페이스 자리만 준비**. 기존 문서 생성/저장 함수를 아직 호출하지 않음 |
| `security/attachment_manifest.py` | 검토 바이트에 대한 SHA-256 생성/검증 |
| `approval/send_gate.py` | 수신자·제목·본문·첨부 지문을 포함한 이메일 승인 무효화 판단만 구현; **SMTP 권한/승인/전송 미구현** |
| `tests/test_master.py` | 분류, 해시변조, 승인 무효화 및 LangGraph가 승인/발송하지 않는지 테스트 |

**실행 (개발자, 실제 메일 연결 없음):**

```powershell
python -m unittest discover -s Quotation_KEKOREA/orchestration/tests -v
python -c "from Quotation_KEKOREA.orchestration.master_graph import run_dry_run; print(run_dry_run('PI and Contract', 'Please review'))"
```

테스트 실행 환경에는 프로젝트 의존성 `langgraph` 설치가 필요하다. 해당 패키지가 없다면 `master_graph` 경로가 실행되지 않으며 테스트 하나가 skip된다. 테스트 **전체 통과/기존 회귀 결과는 PR CI 확인 전까지 미확인**이다. 기존 `app.py` 실행으로 이 기능이 자동 표시되지는 않는다.

**코어 코드는 네트워크 접근을 하지 않음:** POP3/SMTP 호스트 및 비밀번호 사용 안 함, 사용자 데이터 추출/계약 생성 안 함, 메일 발송 절대 안 함. 다음 단계에서는 기존 함수의 실제 호출 방식/승인 상태를 별도로 검증한 뒤, 어댑터 추가와 독립 Streamlit UI를 각각 작은 PR로 진행할 것. 실계정 연결은 마지막에 별도 동의와 테스트를 거친다.


## 2026-11-11 · 독립 오케스트레이션 Mock UI (후속 브랜치, 미병합)

독립 `orchestration/ui/streamlit_page.py`에서 Streamlit **메일함, 업무 대시보드, 자연어 요청 Mock 라우팅, 문서별 가상 검토/수정, 이메일 초안/승인, 실행 기록** 화면을 구현한다. `workflows/mock_workflow.py`는 샘플 주소 `example.test`만 사용하는 메모리 내 불변 데이터 모델이며 문서 수정 시 이전 승인, 이메일 변경 시 이메일 승인을 무효화한다. **실제 후이즈 POP3/SMTP, 기존 agent/contracts 호출, 실문서 PDF 생성, DB 저장/발송은 모두 미구현**이다. 기존 앱/설정/DB/실거래 경로는 수정하지 않았으며, 해당 독립 화면은 기존 `app.py` 메뉴에 나타나지 않는다. 이 설명은 별도 UI 브랜치가 승인·병합되기 전까지 운영 기능이 아니다.

실행: 저장소 루트에서 `streamlit run Quotation_KEKOREA/orchestration/ui/streamlit_page.py` (Streamlit 설치 환경). 격리 테스트: `python -m unittest discover -s Quotation_KEKOREA/orchestration/tests -v` (Master LangGraph 시험은 langgraph 설치 필요). 실제 Streamlit 화면 렌더링 및 현재 GitHub Actions 실행 결과는 별도로 검증 필요.


## 11. UI 검증 자동화 (2026-11-11 · PR #32 브랜치)

기존 계약서 회귀 테스트는 UI 신규 경로를 검증하지 않기 때문에 **독립 GitHub Actions 워크플로** `.github/workflows/orchestration-mock-ui.yml`과 `tests/test_streamlit_ui.py`를 추가했다. `python -m unittest discover -s Quotation_KEKOREA/orchestration/tests -p 'test_*.py' -v`에서 Router, Mock 승인 상태, 실제 Streamlit AppTest 화면 렌더링, 가상 업무 시작, 비활성화된 SMTP 발송 버튼을 테스트한다. 기존 배포 파이프라인 및 기존 앱 파일은 변경하지 않는다. **실제 브라우저 수동 검증·후이즈 실계정·실제 문서 어댑터/발송은 여전히 미검증/미구현**이며, GitHub 검사 결과가 나오기 전에는 통과라고 선언하지 않는다.


## 2026-11-11 · 오케스트레이션 읽기 전용 기존 엔진 사전검증 (PR #34)

신규 `Quotation_KEKOREA/orchestration/adapters/engine_bridge.py`에서 **기존** `agent.trade_documents.validate_and_calculate`(PI/PO/CI/PL) 및 `contracts.models.validate_snapshot`, `contracts.rules.validate_snapshot`(계약) 함수를 **새 데이터 복사본으로 호출**하여 누락 정보·차단 조건을 표시한다. 독립 Streamlit UI의 **엔진 사전검증** 메뉴에서는 테스트용 JSON을 입력해 결과를 볼 수 있다. 호출 결과는 발송/최종 확정 권한이 아니며 기존 Streamlit 앱·계약 저장소·문서 발행·PDF 생성·Supabase·후이즈 POP3/SMTP는 호출하지 않는다. 기존 업무 에이전트 파일과 배포 설정을 변경하지 않았다. 실제 문서 자동 생성/승인 연동은 후속 단계다. 신규 테스트는 `orchestration/tests/test_engine_bridge.py`, `test_engine_preflight_ui.py`이며 PR CI 통과 전까지 미검증이다.


## 2026-11-11 · 독립 오케스트레이션 문서 초안 미리보기 (PR #35)

신규 `Quotation_KEKOREA/orchestration/workflows/document_preview.py` 및 독립 UI의 **문서 초안 미리보기** 메뉴에서 기존 PI·PO·CI·PL 계산·검증 결과를 문서형 테이블로 확인하고, 기존 계약 스냅샷에 **이미 작성된** 조항만 읽기 전용으로 표시한다. 기존 문서 엔진과 검증 규칙을 호출하되, 입력 객체는 복사하며 기존 앱의 저장/수정/승인/PDF/직인과 SMTP는 호출하지 않는다. 기존 무역 PDF 출력은 비공개 직인 파일 필수 조건이 있어 우회하지 않으며, 계약 문구를 AI가 자동 생성하는 기능도 이번 PR 범위가 아니다. 따라서 **최종 발행 문서가 아닌 DRAFT 구조화 미리보기**이다. 원본 `app.py`, `agent/`, `contracts/`, 기존 Render 설정, DB는 수정하지 않는다. 단위 테스트는 `orchestration/tests/test_document_preview.py`, UI AppTest는 `test_document_preview_ui.py`이며 CI 검증 결과에 따라 병합한다.


## 2026-11-11 · 오케스트레이션 검토용 파일 생성 (PR #36)

독립 `orchestration/workflows/draft_files.py`에서 기존 계약서 `contracts.draft_exports.export_draft`를 **그대로 호출**하여 이미 작성된 조항의 검토용 PDF/DOCX를 생성한다. PI/PO/CI/PL은 기존 `agent.trade_documents.validate_and_calculate` 결과가 차단 이슈 없이 확인된 경우 신규 **비직인·비공식 DRAFT DOCX 검토 시트**만 생성한다. 기존 `agent.pi_pdf.render_trade_document`는 회사 직인 파일을 필수로 요구하므로 **무역서류 PDF를 신규 UI에서 만들지 않으며** 직인·서명/최종 발행 절차를 우회하지 않는다. 신규 파일은 메모리에만 생성되며 다운로드 시 SHA-256 해시, DRAFT·비발행·발송불가가 명시되고, 입력값이 달라지면 기존 파일 다운로드를 노출하지 않는다. 신규 UI 의존성 `python-docx`, `reportlab`은 `orchestration/ui/requirements.txt`에만 추가했다. 기존 `app.py`, `agent/`, `contracts/`, 운영 `render.yaml`, DB, WHOIS POP3/SMTP는 변경하지 않았다. 별도 배포는 GitHub main 반영 후 다시 배포해야 새 기능을 볼 수 있다.


## 2026-11-11 · 독립 오케스트레이션 요청→문서→이메일 초안 통합 검토 (PR #37)

새 `Quotation_KEKOREA/orchestration/workflows/unified_review.py`와 별도 Streamlit UI의 **통합 업무 흐름** 화면에서 업무 지시문의 키워드를 기존 보수적 Router로 문서 종류로 분류하고, 사용자가 명시적으로 입력한 문서별 JSON 조건으로 기존 검증·검토용 DRAFT 파일 생성 엔진을 호출한다. **AI API/실메일 연동이 아닌 키워드·구조화 입력 기반**이다. 미확정 조건은 차단하고, 생성된 파일별 SHA-256 무결성 및 원본 조건의 해시를 확인해 문서별 DRAFT 검토를 기록한 뒤 이메일 초안 검토 단계로만 진행한다. 요청 조건 변경은 문서·메일 검토를 모두 취소하고 이메일 본문 변경은 메일 검토만 취소한다. 검토 완료 상태조차 `can_send=False`이며 실제 POP3/SMTP, 송신, 계약 FINAL, 직인, 저장/전송 작업은 없다. 실무 운영용 완전자동 생성이나 실계정 접근 기능으로 해석하지 않는다. 기존 `app.py`, `agent/`, `contracts/`, DB, 기본 `render.yaml`은 수정하지 않았다. 독립 `ui/streamlit_page.py` 배포 서비스는 `main` 병합 후 별도 재배포가 필요하다. 테스트: `orchestration/tests/test_unified_review.py`, `test_unified_ui.py`.


## 2026-11-11 · MASTER GRAPH OIDC 인증 및 기존 저장 계약서 읽기 전용 연동 (PR #38)

독립 `Quotation_KEKOREA/orchestration/ui/streamlit_page.py`의 **모든 메뉴**에 Streamlit OIDC 로그인·`email_verified`·명시적 사용자 이메일 allowlist를 통과해야 하는 인증 게이트를 적용한다. 인증 설정/허용 목록이 없으면 기본 접근 차단. **저장된 계약서** 메뉴에서 기존 `contracts.repository.ContractRepository`의 `list_contracts/load_contract`를 통해 기존 Supabase 계약서의 목록·검색·한국어/영어 필터·리비전·조항·원래 저장된 이슈를 **읽기 전용**으로 확인할 수 있다. 기존 계약 검증 규칙에 의한 확인사항은 신규 AI 법률 의견이 아니라 결정적 사전 점검으로 표시한다. 실제 기존 저장소 조회는 OIDC 설정과 동일 Supabase의 서버 전용 접속 키를 별도 MASTER GRAPH 호스팅 서비스에 설정해야 하며 **아직 이 저장소에 인증 자격정보를 기록하지 않았다**. 기존 계약서/문서 발행 앱, `agent/`, `contracts/`, 원본 `render.yaml`, DB 스키마는 변경하지 않는다. MASTER GRAPH의 읽기 전용 코드도 서버 비밀 키 자체의 DB 권한을 제한하지는 못하므로 최소권한 백엔드 적용 검토가 필요하다. 자세한 설정은 `Quotation_KEKOREA/orchestration/AUTH_AND_LIBRARY.md` 참조.


## 2026-11-11 · AI 거래조건 자동 추출 + 저장 계약서 참고 + 검토용 문서 생성 (PR #39)

독립 MASTER GRAPH 인증 후 메뉴 **AI 거래조건 추출**을 제공한다. 사용자가 입력한 자연어 거래조건만 명시적 동의 후 기존 `contracts.service.analyze_trade` AI 엔진에 전송한다. **저장된 계약서 내용은 AI API로 전송하거나 새로운 계약에 자동 복사하지 않으며**, 별도 읽기 전용 참고 패널에서만 열람한다. 결과의 법인명/단가/수량/거래조건은 모두 **suggested (AI 제안, 미확정)** 상태로 생성된다. 사용자는 문서별 JSON 입력값을 직접 수정·확인한 뒤 기존 PI/PO/CI/PL 검증과 DRAFT 파일 생성 경로로 전달할 수 있으며, 원문이 바뀌면 파일 재생성을 요구한다. 계약서 조항 생성은 별도 명시적 동의 및 OpenAI 서버 키 설정 뒤 기존 `contracts.ai_graph.generate_contract_draft_graph`의 검토용 신규 초안 경로에서만 실행하며, 기존 저장소/샘플 라이브러리 자동 조회·쓰기·SMTP 발송·최종 승인/발행은 없다. UI 서버에는 `OPENAI_API_KEY`와 `OPENAI_MODEL` (선택: `CONTRACT_OPENAI_MODEL`)을 별도 Streamlit Cloud Secrets로 설정해야 실제 AI를 사용할 수 있다. 모델 비용과 기밀 데이터 외부 전송에 유의. 기존 계약 작성 앱 `app.py`, `agent/`, `contracts/`, 원본 `render.yaml` 및 DB 스키마는 수정하지 않는다. 상세 추가 테스트 `orchestration/tests/test_ai_intake.py`, `test_ai_intake_ui.py`.


## 2026-11-11 · AI 업무 요청 메뉴 통합 및 부족정보 직접입력 (PR #40)

MASTER GRAPH 독립 UI의 `AI 업무 요청` 메뉴는 이제 기존 `AI 거래조건 추출` 실제 분석 화면을 직접 제공하며, 중복된 `AI 거래조건 추출` 사이드바 메뉴 및 사용자용 Mock 요청 폼을 제거한다. 내부 `mock_workflow`/샘플 메일 테스트는 유지된다. AI 거래조건 추출 후 Buyer/Seller 법인명·주소·국가, 상품명·수량·단가·단가출처 및 필수 무역 조건이 누락된 경우 **별도 텍스트 입력칸**이 표시된다. 사용자가 해당 칸에 입력하고 Enter를 누르거나 포커스를 이동하면 Streamlit rerun으로 최신 문서 후보(JSON, 화면 거래 요약)에 반영되며, 동일한 거래조건을 PI/PO/CI/PL과 계약서 후보에 동기화한다. 기존 DRAFT 파일과 검토 상태는 즉시 무효화하고, 조건이 바뀐 기존 AI 계약서 조항도 폐기하여 재생성을 요구한다. 기존 문서 엔진 규칙에 따라 정확한 법인명/주소/지급조건을 사람이 검증해야 하며 **AI/인간 입력을 자동으로 confirmed로 승격하지 않는다**. 안전한 발행·발송 승인 기능은 아직 분리되어 있다. 상세 테스트 `orchestration/tests/test_intake_followups.py` 및 `test_ai_intake_ui.py`.

### 2026-11-13 · MASTER 문서 생성 전 누락 연락처 입력 보완 (PR #94 당시 동작)
- 기존 앱의 `agent.review_fields.missing_review_fields`를 MASTER 입력·회사 양식 출력 검증에도 연결했습니다. Buyer/Seller 담당자·대표자, 전화번호, 이메일과 배송지, 문서별 표시 항목, 품목별 할인율을 입력할 수 있습니다. `Not provided`, `TBD` 등 임시 문구는 누락으로 처리하고, 선택 항목의 `N/A`는 사용자가 직접 입력해야 합니다.
- PI/PO의 상대 회사가 다르면 연락처 입력칸을 구분합니다. 연락처 수정은 같은 정확한 법인명인 회사에만 반영하며, PO 구매자와 PI 판매자가 같은 회사인 경우에도 연결합니다. 다른 회사의 연락처를 덮어쓰지 않습니다. 계약서 담당자는 `representative`에 반영하고 다시 확인할 상태로 유지합니다.
- 이미 확인된 회사명·주소를 누락된 문서/계약서에도 적용하려면 해당 입력칸의 **현재 값으로 누락 항목에도 반영**을 누를 수 있습니다. 이 버튼은 비어 있는 대상만 채우며 다른 문서에 이미 입력된 회사명·주소를 덮어쓰지 않습니다.
- 여러 문서 중 뒤쪽 문서에만 있는 추가 품목도 입력할 수 있습니다. 앞 문서에 값이 있어도 뒤 문서의 누락을 숨기지 않습니다. 연락처를 포함한 변경은 이전 PDF·검토·FINAL 다운로드를 무효화합니다.
- 원본 회사 양식·직인·은행정보·가격 검증은 유지합니다. 표시할 정보의 확인이 끝나지 않으면 회사 양식 출력을 보류하고, 기존 내부 검토용 PDF 경로를 유지합니다. 입력한 연락처는 기존 PDF/HTML 및 내부 검토용 PDF에 반영됩니다. 기존 앱의 렌더러·페이지 서식은 수정하지 않았습니다.
- 검증: 최신 RAG 변경 병합 후 기존 계약·문서 694개와 MASTER 418개, 총 1,112개 테스트 통과(실패·스킵 0). 합성 자료로 누락/임시 문구/N/A, PO·PI 회사 구분, 추가 품목, 입력 반영·다운로드 무효화 및 실제 PDF/HTML 연락처 출력을 검사했습니다. 기존 로컬 가격 카탈로그는 Git에 추가하지 않고 테스트에만 사용했습니다. 운영 MASTER는 Google 로그인 화면까지만 확인했으며 로그인 후 신규 입력창·PDF·배포 코드 일치는 미확인입니다.

### 2026-11-13 · MASTER 입력 상태 동기화 및 승인 후 공란 유지 FINAL 출력

- **사용 흐름:** `AI 업무 요청`의 한 거래정보 입력창에서 수정 → `최종 PDF · 기존 KE KOREA 양식`에서 문서별 누락/오류 확인 → 현재 내용의 최종 출력 승인 → `PI/PO/CI/PL 최종 PDF 생성` → `PDF FINAL 다운로드`. 같은 단계에서 XLSX/HTML도 받습니다. 문서번호 자동 생성은 선택 사항입니다.
- **누락과 오류 구분:** 누락된 회사/연락처/거래조건, 과거 AI 미입력 메모는 확인 목록으로 표시하며 승인 후 공란으로 출력할 수 있습니다. 미확정 값을 N/A·TBD·Not provided 또는 0으로 채우지 않습니다. 사용자가 직접 입력한 선택 항목 N/A와 실제 수량 0은 유지합니다. 부족한 수량·가격·할인율·통화에 의존하는 금액과 불완전한 합계는 공란입니다.
- **현재 입력값 일치:** 입력이 잘못되어 적용할 수 없으면 화면에 그 값을 유지하고 오류를 표시하며 이전 파일·승인을 즉시 무효화합니다. 메뉴를 이동해도 오류 입력을 보존합니다. 고급 JSON 적용 시 기본 입력창도 갱신하고, 미적용 JSON 또는 미해결 입력 오류로 이전 문서를 출력하지 않습니다. 승인 해제/내용 변경 후에는 이전 FINAL 다운로드가 사라집니다.
- **기존 양식:** 같은 PDF/HTML/XLSX 렌더러에 명시적인 `final=True`를 전달합니다. FINAL은 DRAFT 표시가 없고 기존 표·페이지·은행정보/직인 묶음 배치를 유지합니다. 기본 DRAFT 경로의 기존 검증은 유지합니다. 승인한 FINAL에서 빈 은행정보는 공란이며 실제 금액/조건 충돌, 음수·비숫자·NaN/Infinity, 단위 불일치, CI의 원본 PI 거래가격 요건과 검증된 회사 직인 요건은 계속 확인합니다.
- **브라우저 입력 상태:** 고급 JSON 반영·AI 재추출 등으로 후보를 교체할 때 입력창도 새 상태로 연결합니다. 이전 화면의 DRAFT/빈 단위/빈 할인율이 뒤늦게 전송돼 새 후보를 덮어쓰는 현상을 막고, 같은 회사의 PI/PO 연락처 변경도 실제 화면에 갱신합니다. 잘못 입력한 값의 원문, 메뉴 왕복 상태와 재승인 절차는 유지합니다.
- **자연어 AI 추출 호환성:** 기존 계약 AI가 정상적으로 반환하는 `missing` 조건을 잘못된 형식으로 거절하던 연결부를 수정했습니다. 비어 있는 조건은 미입력으로 유지하며, AI가 `confirmed` 상태를 임의로 지정하는 것은 계속 차단합니다. PI와 계약 후보 모두 최신 연결 모듈을 사용해 운영 앱의 이전 모듈 캐시에서도 같은 동작을 적용합니다.
- **문서별 검증과 갱신:** 다른 문서나 CONTRACT의 누락은 정상 PI 승인을 막지 않습니다. Streamlit이 예전 모듈을 보유한 경우 입력·검토·어댑터와 공통 렌더러/PDF 의존성을 순서대로 갱신해 `final` 인자 불일치를 방지합니다.
- **계약서와 RAG:** 이번 공란 출력 경로는 PI/PO/CI/PL에 적용합니다. 기존 CONTRACT FINAL 승인/직인 권한과 최근 RAG 구현은 별도로 유지합니다. 파일 생성은 자동 이메일 발송·실제 발주·계약 체결을 수행하지 않습니다.
- **검증 결과:** 최종 코드로 기존 문서·계약 707개와 MASTER 472개, 합계 1,179개 테스트가 모두 통과했습니다(실패·건너뜀 0). 합성 자료의 PDF 텍스트/다중 페이지 시각 검사, 수량 0, 누락·오류 구분, 입력/승인/다운로드 무효화 및 이전 모듈 재로딩도 확인했습니다.
- **운영 확인:** PR #95 배포 후 인증된 MASTER에서 누락값이 있는 자연어 요청의 편집창 진입, 직접 입력한 주소·이메일의 PDF 반영, 수량·합계 공란 FINAL과 수량 0/합계 $0.00 FINAL의 실제 다운로드를 확인했습니다. 입력 변경 시 이전 승인·다운로드도 해제됐습니다. 이 과정에서 발견한 고급 JSON의 브라우저 상태 덮어쓰기는 후속 보완했으며, 최신 배포의 재확인 결과는 [PR #95](https://github.com/swihm1989-ship-it/KE_KOREA_CO_LTD/pull/95)에 함께 기록합니다.


### MASTER PDF archive and sidebar workflow (2026-11-17)

MASTER sidebar now shows: 시장 뉴스, 메일함, AI 업무 요청, 통합 업무 흐름, 문서 검토, 발송 대기, 저장된 계약서. The old sample dashboard, execution log, admin monitoring, draft preview, and engine preflight are hidden from the menu (underlying diagnostics and original engines remain untouched). Successful MASTER DRAFT PDF generation archives the exact PDF to the private Supabase bucket `kekorea-master-pdfs`, with owner-scoped metadata in `kekorea_master_pdf_archive`; FINAL PDFs are likewise archived. Saved lists show filenames, KST dates and times, click-to-preview and download. The 발송 대기 screen requires a new user approval (and the original seal authorization for contracts) before converting the immutable draft snapshot into a new PDF using the original KE KOREA rendering engine. Converted drafts leave the pending list, retaining the historical record. No automatic SMTP send. The original KE KOREA contracts database and document renderer are unchanged. New archive records require server-only Supabase credentials and a private bucket. GitHub merge is not by itself proof of live Streamlit deployment; verify the deployed menus and a fresh DRAFT -> FINAL workflow on the running app.


### 2026-11-18 · 승인형 메일 회신 (PR #128 대체)
문서 요청이 있는 메일은 메일함 → AI 업무 요청 → 기존 PI/PO/CI/PL/계약서 작성과 기존 PDF 승인·발행 흐름을 그대로 따른다. 문서 요청이 없는 메일은 AI 업무 요청에서 비공개 Supabase 'kekorea_master_mail_outbox'로 저장한 뒤 발송 대기 메뉴의 이메일 영역으로 이동한다. 사용자 동의 후 OpenAI가 세 가지(간결/친근/상세) **추천 초안**을 만들고 사용자가 받는 사람·제목·본문·기본 서명(한국어/영어)을 직접 수정한다. 수신자의 국적은 추측하지 않고 메일 언어를 초기값으로 사용한다. **실제 발송은 최종 문구 해시와 연동된 확인 발송 전 승인 버튼 + 발송 버튼 클릭 후에만** 수행한다. 서버는 상태를 draft→sending→sent/send_unknown으로 원자적 변경하여 중복 발송 및 전송 결과 불확실시 재전송을 방지한다. 백그라운드/cron/메일 수신/AI 호출 중 자동 SMTP 발송은 없다. 기존 후이즈 POP3 리더와 PDF 발행 검증·기존 문서 엔진은 유지한다. 운영 SMTP 테스트·Streamlit 배포 검증은 별도이다.


### 2026-11-18 · 기업형 이메일 서명(2번 디자인)
수신 언어에 맞춰 이름(한글/영문), 직함, 얇은 구분선, KE KOREA 공식 company_logo.png, 회사명 및 주소, 마지막 `www.ke-korea.co.kr` 링크를 표시한다. 한국어 회사명은 `(주)케이이코리아`, 직함은 `대표이사 (Managing Director)`이다. 영문 서명은 기존 영문 이름·직함·회사명·주소를 유지하고 사이트 URL만 추가한다. 회사 로고는 기존 앱 assets/company_logo.png를 Pillow로 리사이즈하여 이메일 Content-ID 인라인 이미지로 첨부한다. SMTP는 multipart/alternative(일반 텍스트+HTML) 방식으로 발송되며 외부 로고 호스트는 필요 없다. Streamlit 발송 전 미리보기 역시 같은 로고·레이아웃을 데이터 URI로 표시한다. 메일 편집/발송 승인/중복 방지 및 수동 발송 전용 규칙은 변경하지 않았다.


### 2026-11-18 · AI 회신 장애 시 발송 대기 복구
메일함 → AI 업무 요청에서 AI 회신 생성이 실패하더라도 DB 저장 성공 시 기존 DRAFT를 유지하고 '발송 대기'로 이동한다.
email_reply_handoff.prepare_email_handoff는 DRAFT를 먼저 저장한 뒤 AI 회신 후보 3개를 생성하며, HTTP 400/401/403/404/429/5xx 및 네트워크 오류를 민감 정보 없이 구분해 표시한다.
저장된 메일의 후보가 비어 있으면 발송 대기에서 AI 회신을 다시 생성하거나 사용자가 직접 회신을 작성할 수 있다.
AI 회신 모델은 기존 계약서 엔진과 동일하게 CONTRACT_OPENAI_MODEL을 우선 사용한다.
AI 후보 유무와 무관하게 SMTP 송신은 명시적 발송 전 승인 버튼 + 발송 버튼 이후에만 실행된다. 자동 발송, 백그라운드 발송, AI 실패 시 자동 대체 발송 기능은 없다.
실제 OpenAI API 인증 및 사용량/모델 권한은 운영 서버 상태에 따라 확인해야 하며, 모델 응답 원문이나 API 키는 화면에 표시하지 않는다.

### 2026-11-18 · MASTER UI 회신 장애 재발 방지·진단
Streamlit Cloud의 지속 실행 Python 프로세스는 화면을 새로고침해도 이미 import된 회신 생성/전달 모듈을 유지할 수 있다. email_reply_runtime.py에서 모듈 리비전 + 실제 파일 mtime을 비교해 최신 코드로 재로드하며, 이전 함수 객체가 handoff 기본 인자로 남는 문제는 호출 시점 인자로 덮어쓴다.
발송 대기 → AI 연결 상태 진단은 서버 키의 설정 여부·모델 이름·실행 코드 버전만 보여 준다. 사용자가 명시적으로 동의하고 버튼을 누르면 가상 문장만 OpenAI Responses API에 보내 HTTP 상태와 안전한 오류 code/param만 안내한다. 원본 메일, 거래처 정보, API 키, provider 메시지 원문은 진단에 전송하거나 표시하지 않는다. AI 진단은 소량의 API 비용을 사용할 수 있다.
AI 실패 시 기존 발송 대기 초안은 보존하고 직접 작성할 수 있다. 송신은 오직 사용자가 최종 승인 버튼을 누른 후 발송 버튼을 누른 경우로 제한. UI·회신 런타임·DB 중복전송 회귀 테스트는 orchestration/tests 하위에서 자동 실행.
실제 로그인된 Streamlit Cloud 브라우저 조작·실계정 SMTP 송신·운영 OpenAI 응답의 성공은 CI만으로 입증할 수 없으며 별도 운영 테스트가 필요하다.

브라우저 자동 클릭 검사에서 편집 직후 체크박스가 초기화되는 문제가 확인되어, 수정 후 발송 승인은 별도의 '이 내용으로 발송 전 승인' 버튼으로 통일했다. 승인 당시 주소·제목·본문·서명 해시가 기록되며 이후 어떤 수정에도 승인 취소, 사용자가 '발송' 버튼을 누르기 전까지 전송 없음.

### 2026-11-18 · OpenAI 회신 HTTP 400 대응 (schema-v2)
실운영에서 후보 생성 시 HTTP 400이 발생한 것이 확인됨. 이전 코드는 HTTP 숫자만 표시하고 오류 code/param을 버려 원인 파악이 불가능했음.
OpenAI Responses API 권장 `text.format.type=json_schema`(strict)로 변경하고, 세 개의 후보를 클라이언트에서도 다시 검증. 선택된 모델이 구조화 출력 형식 자체를 거부할 때만 **동일 모델·동일 승인된 메일 입력·`store=false`를 유지**하여 `text.format.type=text`로 1회 재시도. 다른 HTTP 400, 인증 실패, 모델/사용량 문제는 재시도하지 않음.
provider error의 HTTP 번호와 영숫자 code/param만 표시하며, error.message 원문·거래처 이메일·API 키는 UI/로그에 노출하지 않음. 진단 탭 역시 가상 문장만 사용하고 동일한 구조화 출력→텍스트 호환 검사를 수행.
Streamlit 배포 후 잔존 런타임 모듈을 메인 페이지·AI 업무요청·발송 대기에서 version check 후 갱신. 자동 메일 발송 없음. DRAFT 보존, 수동 작성 및 '이 내용으로 발송 전 승인'→'발송' 2단계 유지.
회귀 테스트: HTTP400 형식 불일치 시 안전한 재시도 1회, 모델 파라미터 오류 시 재시도 금지, 비밀 원문 비노출, JSON schema, 모델 호환 진단, 코드 펜스 결과 정규화, 기존 UI·문서·계약 회귀.
한계: 실운영 OpenAI API 키/모델의 응답과 Streamlit Cloud 실제 배포는 테스트 환경의 가상 응답만으로 확인할 수 없음. 직접 입력할 새 API 키는 필요하지 않음.


### 2026-11-18 · 발송 승인 후 결과 확인 화면 오류 (발송 전 단계)
운영 화면에서 '발송 결과 확인에 실패했습니다. 보낸편지함을 확인...' 메시지를 확인. 실제 Supabase `kekorea_master_mail_outbox`의 해당 메일은 DRAFT, `send_started_at`/`sent_at`/`approved_sha256`가 모두 NULL이고 AI 후보 3개는 보존됨. **현재 전송 코드상 SMTP는 DRAFT → sending 원자적 claim 이후에만 호출**, 따라서 이 시도의 DB 증거는 전송 시작 전 예외를 가리킴.
기존 Streamlit은 UI 모듈만 갱신하고 `email_outbox.send_approved`를 정적 import로 유지해 오래된 함수가 `signature_text`/`language` 키워드를 받지 못하는 `TypeError`가 발생할 가능성이 있었음. UI 발송 버튼에서 전송 함수의 소스 수정 시각, 런타임 리비전, 함수 파라미터를 확인하고 필요할 때만 모듈을 안전하게 재로드하도록 수정.
사용자 직접 발송 클릭 후 오류가 생기면 **DB를 읽기 전용으로 재조회**하여 DRAFT/전송 시작 전과 sending/sent/send_unknown 상태를 별도로 표시. 내부 예외 메시지·SMTP 비밀번호·거래처 메일 본문은 노출하지 않고 안전한 예외 종류만 표시. 오류 시 기존 발송 승인 상태를 해제하고, 자동으로 다시 보내지 않음.
실제 전송이 시작된 상태로 조회된다면 중복 발송을 금지하고 보낸편지함 확인을 안내. AI 회신·서명·기존 문서 PDF 엔진·Supabase 스키마·메일 자동발송 금지 원칙은 유지. 새 테스트는 구형 함수 캐시 재로드, 오류 시 DB DRAFT 판별, 발송 후 상태 불확실 시 재발송 금지, Streamlit UI 모의 버튼, Chromium 브라우저 검증을 포함.
운영 후이즈 SMTP에 대한 라이브 송신은 실제 사용자 수신자에게 자동으로 테스트하지 않으며, 운영 UI의 외부 계정 로그인 검증 여부와 구분한다.


### 2026-11-18 · 원본 메일별 FINAL PDF → 발송 대기 첨부 연동
- 메일함에서 가져온 특정 메일로 AI 업무 요청에서 FINAL PI/PO/CI/PL/CONTRACT PDF를 생성하면 기존 `kekorea-master-pdfs` / `kekorea_master_pdf_archive`에 저장한다. 기존 **저장된 계약서** 목록·미리보기·삭제 UI는 수정하지 않는다.
- 완료된 PDF와 원본 메일의 비공개 발송함 DRAFT를 `kekorea_master_mail_pdf_links`로 연결한다. 동일 메일에서 여러 FINAL을 생성하면 여러 첨부를 표시한다. 다른 원본 메일의 파일을 섞지 않는다.
- AI 회신 후보 자동생성은 별도 체크박스에 동의한 경우에만 호출하고, 실패해도 연결된 DRAFT/첨부를 유지한다. 발송 대기 메뉴에서 AI 후보를 생성하거나 본문을 직접 편집 가능하다.
- 첨부 내용은 SMTP 직전 owner-scoped PDF 다운로드와 SHA-256 검증을 다시 수행한다. 선택한 메일의 수신인·제목·본문·첨부 식별자와 해시가 모두 동일해야 사용자 승인 상태가 유효하다.
- 메일 송신은 발송 대기 화면의 `이 내용으로 발송 전 승인` + `발송` 버튼으로만 수행한다. 자동 SMTP 없음. 기존 SENT 기록은 그대로 두고 재발송 시 별도 DRAFT를 생성한다.
- 스키마: `supabase/migrations/20261118084000_master_mail_pdf_links.sql`. 기존 계약서·RAG·문서 렌더러 변경 없음. 운영 서버에서는 PDF를 실제 발행하고 UI에서 첨부 및 발송을 확인해야 한다.

### 2026-11-18 · PDF 저장·다운로드·메일첨부 공통 파일명
- PI/PO/CI/PL(각각 CI·PL 포함)과 계약서 PDF 저장 파일명을 `문서종류_문서번호_KE-KOREA_거래처명_제품명(물량).pdf` 규칙으로 표시한다. 없는 정보는 임의 생성하지 않고 해당 파일명 구간만 생략한다. 예: `PI_PI-2601_KE-KOREA_DEARGLOW_M10 Cell(1000 PCS).pdf`, 모든 거래정보가 없으면 `PI_KE-KOREA.pdf`.
- PO 상대방은 공급사(Seller), PI/CI/PL 상대방은 구매자(Buyer)를 우선 사용한다. 여러 상품은 첫 상품과 나머지 종류 수를 요약하고, 물량은 원문에서 검증된 첫 행의 수량·단위만 사용한다.
- 같은 문서번호, 같은 거래처·제품·물량을 여러 번 사용해도 생성 가능하다. 파일명은 UI/다운로드/메일첨부용 **표시 이름**일 뿐이며, 비공개 실제 파일 경로와 문서 메타데이터 PK는 독립된 UUID로 유지한다.
- 기존 저장된 계약서의 조회·미리보기·삭제 코드는 변경하지 않으며, 기존에 저장된 문서의 파일명도 소급 변경하지 않는다.
