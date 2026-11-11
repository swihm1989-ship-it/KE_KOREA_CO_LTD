# KE KOREA 개인 프로젝트 — 후이즈메일 멀티에이전트 오케스트레이션 설계

> **상태: 설계 전용 / 미구현 · 2026-11-11**
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
