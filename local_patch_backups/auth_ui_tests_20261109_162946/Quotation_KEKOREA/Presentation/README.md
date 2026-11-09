# KE KOREA AI 문서·계약서 에이전트 — 발표용 README

기준일: **2026-11-09**. 실제 저장소 구현을 기준으로 설명합니다. 최신 코드의 로컬 자동 테스트와 실제 모델 품질·운영 배포는 구분합니다. 상세 구현/설정은 [팀 README](../Team/README.md)에 있습니다.

## 1. 핵심 메시지

> 거래 설명과 참고자료를 구조화하고, 회사의 승인된 조항을 검색해 초안을 작성한 뒤, 사람이 조건과 수정안을 검토·승인하는 문서 지원 시스템입니다.

가격 계산·필수조건·수정 이력은 코드와 DB가 관리하고, AI는 추출·작성·검토를 담당합니다. 실제 계약 서명·발주·송신·결제까지 자동 실행하는 서비스로 소개하지 않습니다.

## 2. 기능과 실제 구현 기술

| 발표 주제 | 실제로 구현한 방식 | 설명 시 구분할 점 |
| --- | --- | --- |
| 에이전트 화면 | Streamlit, BOX 1 대화 / BOX 2 조건 / BOX 3 본문 | 기존 UI·승인 흐름 유지 |
| 거래정보 이해 | OpenAI Responses API 구조화 추출 + 조건 키 정규화 | 추출한 후보는 사용자 확정 전 미승인 |
| LangChain | 미사용. Python으로 추출·검색·검사 연결 | LangChain 기반이라고 발표하지 않음 |
| MCP | 앱에 MCP 서버/클라이언트 미구현 | DB는 서버에서 REST/RPC로 호출. 개발 도구의 MCP와 구분 |
| 장기기억 저장소 | Supabase PostgreSQL 계약/대화/revision + 비공개 파일 Storage | 영속 저장이며 모델의 자동학습이 아님 |
| 공통 지식/RAG | 관리자가 승인한 익명화 참고 메모 검색 → 모델 입력 | 원본을 업로드했다고 즉시 모든 계약에 재사용하지 않음 |
| 임베딩 검색 | 기본 512차원 벡터를 JSONB에 저장하고 Python에서 유사도 계산 | pgvector·FAISS 등 전용 벡터 인덱스 없음 |
| 조항별 품질 개선 | 작성 기준 → 주제별 검색 → 상세 작성 → 누락/충돌 검사 → 1회 보완 | 단순히 글자 수를 늘리는 기능이 아님 |
| 사람이 통제하는 수정 | 문장 메모·위험 추천 → 비교 → 승인 → 새 revision | 미리보기와 저장 승인은 별개 |
| 문서 출력 | 계약 PDF/DOCX, 무역 PDF/Excel | DRAFT와 FINAL의 검증 경로 구분 |

## 3. 계약서가 만들어지는 과정

```mermaid
flowchart TD
  A[사용자 거래 설명과 선택한 참고자료] --> B[거래조건 후보 정리]
  B --> C[계약 유형별 조항 목차·작성 기준]
  C --> D[첨부 전체 구간·승인 메모에서 조항별 검색]
  D --> E[상세 초안 작성]
  E --> F[모든 생성 조항의 누락·충돌·문장 근거 검사]
  F --> G[필요 조항만 최대 1회 보완·재검사]
  G --> H[기존 BOX 3에서 사용자 검토]
  H --> I[수정안 비교·승인과 revision 저장]
  I --> J[DRAFT 또는 기존 FINAL 검증 후 파일 출력]
```

- 매매계약 13개, 커미션 계약 12개 기본 주제의 작성 기준을 사용합니다. 명시적 제외 결정은 존중합니다.
- 불가항력 예시: **발생 요건 → 통지 → 영향 완화 → 이행 재개 → 장기화 시 처리**를 확인합니다. 임의의 통지일수·해지기간을 합의된 사실처럼 채우지 않습니다.
- 참고 문서의 앞부분뿐 아니라 뒤쪽 조항도 검색합니다. 인접 문단/페이지를 연결해 제목과 실제 의무를 함께 가져옵니다. 모델에는 선택된 발췌문을 제한해 전달합니다.
- 신규 초안 내부는 보통 2회, 보완 시 최대 4회 AI 호출입니다. 기존 분석/검색 호출은 별도이며 실제 비용·응답 시간은 입력과 모델에 따라 달라집니다.
- 이미 저장된 계약서는 이 기능으로 자동 덮어쓰지 않습니다. 실패한 중간 결과는 초안으로 저장하지 않습니다.

## 4. 장기기억/RAG 설명용 그림

```text
계약별 기록                           회사 공통 참고 지식
────────────                         ────────────────────
계약·대화·조건·본문                    비공개 원본 등록
       ↓                                      ↓
Supabase revision 저장                관리자 익명화 메모 검토·승인
       ↓                                      ↓
계약을 다시 열어 조회·복구              승인·활성·계약 유형 필터 검색
                                              ↓
                                      참고 근거와 함께 새 초안 작성
```

발표 멘트: “모델이 회사의 계약서를 스스로 학습하는 구조가 아니라, 승인된 참고 지식을 저장해 필요한 순간에 찾아 제공하는 구조입니다.”

기존 공통 검색은 임베딩·키워드를 혼합하고, 새 초안의 조항별 추가 검색은 키워드를 사용합니다. 상품/SKU 매칭은 별도의 규칙·문자열 유사도 방식입니다. 이 세 가지 검색을 같은 기능으로 설명하지 않습니다.

## 5. 무역 문서 기능도 함께 구현

| 기능 | 사용 가치 | 적용한 통제 |
| --- | --- | --- |
| PO/PI/CI/PL 텍스트·이미지·PDF 입력 | 반복 입력과 문서 전환 작업 감소 | 문서별 입력/작업 상태 분리 |
| 제품·가격 조회 | SKU·용량에 맞는 가격 근거 확인 | 유사 후보 사용자 확인, PO/PI/CI 가격 역할 분리 |
| 수량·금액·행사·샘플 | 수기 계산 오류 감소 | Decimal 계산, 명시적 0 유지, FOC/유상 구분 |
| 첨부 PI → CI | 실제 거래가격 재사용 | 카탈로그로 덮어쓰지 않음, 은행정보 제외 |
| PL 합계·PDF 페이지 | 포장 합계와 출력 안정성 | 원본 보존·수정 승인·단위 분리·하단 묶음 보존 |

자동 발주·전자 송장 발행·재고/배송 시스템 연동·이메일 발송은 구현 범위가 아닙니다.

## 6. 5분 발표 순서

| 시간 | 내용 | 화면/자료 |
| --- | --- | --- |
| 0:00–0:40 | 반복 입력, 짧고 불완전한 조항, 수정 이력 관리 문제 | 문제 사례; 실제 고객 자료 대신 합성 예제 |
| 0:40–1:30 | 기능별 구현 기술과 저장소 | 이 문서 2·4절의 기술 표/그림 |
| 1:30–3:20 | 계약 설명 → 조건 후보 → 상세 초안 | BOX 1·2·3. 응답이 길면 미리 준비한 가상 계약을 병행 |
| 3:20–4:10 | 불가항력 구성요소와 수정 승인 | 요건·통지·완화·재개 확인, 메모/비교/승인 |
| 4:10–4:40 | 무역 문서의 가격·수량 통제 | 가상 주문의 검토 화면과 PDF/Excel |
| 4:40–5:00 | 테스트 결과와 현재 한계 | 구현·검증·운영 반영을 구분 |

## 7. 임시 화면에서 시연하기

이번 세션의 로컬 임시 주소는 **http://127.0.0.1:8502**입니다. 이 PC에서만 접속하도록 바인딩했으며 서버 종료/PC 재시작 후에는 다시 실행해야 합니다.

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m streamlit run .\Quotation_KEKOREA\app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
```

**현재 로컬 화면은 사용자가 선택한 기존 Supabase DB를 공유합니다.** 임시 주소라고 데이터까지 분리된 것은 아닙니다. 테스트 계약 제목은 `[TEST]`로 시작하고 합성 데이터만 사용하세요. 기존 계약을 수정·삭제하거나 실제 고객 파일을 전송하는 시연은 하지 않습니다. 별도 팀 공개 시연은 인증된 테스트 환경과 독립 DB를 준비하는 것이 적합합니다.

준비할 합성 예제:

- 계약 제목: `[TEST] 샘플 물품공급계약`.
- 가상 회사 A/B, 실제 계좌·연락처 없는 물품·수량·가격 조건.
- 불가항력·검수·해지 문단이 있는 공개 사용 가능/자체 작성 참고자료.
- 미합의 기한은 비워 두고 확인 표시가 남는 모습을 보여줍니다.
- 기존 승인 자료를 공통 검색에 쓰려면 샘플 관리 설정과 승인 상태를 담당자가 확인합니다. 업로드만으로 RAG 등록 완료라고 설명하지 않습니다.

## 8. 실제 확인한 것과 아직 확인하지 않은 것

| 항목 | 상태 |
| --- | --- |
| 최신 전체 자동 테스트 | **437개 통과 / 생략 없음 / 109.838초**, Streamlit AppTest 포함 |
| 새 품질 파이프라인 테스트 | 가상 API 응답 기반 핵심 15개 포함 |
| 코드 공백 검사 | `git diff --check` 통과한 기록 있음 |
| 임시 서버 | 이번 세션 health 200/ok 확인. 브라우저 자동화의 URL 확인 제한으로 시각 확인 미완료 |
| 실제 모델의 상세 조항 품질 | 대표 계약/조항으로 별도 검증 필요. 자동 테스트 통과와 동일하지 않음 |
| Render·Streamlit 운영 반영 | 이번 변경의 실제 운영 배포·생성 결과 미확인 |
| 새 기술 도입 | LangChain·LangGraph·MCP·fine-tuning은 미구현 |

근거: [테스트 로그](../../logs/tests/drafting_quality_2026-11-09.log), [품질 테스트](../tests/test_contract_drafting.py), [앱 연결 테스트](../tests/test_contract_library_ui.py). 기존 경고는 남아 있으며 과거 실패 로그는 당시 코드의 실행 기록입니다.

## 9. 발표에서 반드시 설명할 한계

- 현재 앱 전체에 사용자 로그인/사용자별 계약 권한 분리가 없습니다. 샘플 관리 키와 비공개 DB/Storage만으로 공개 앱 사용자 접근이 제한되는 것은 아닙니다.
- AI의 완성도·충돌 판단과 참고자료의 적합성을 법적 유효성 보증으로 소개하지 않습니다. FINAL 검증 통과는 전자서명이나 법률 검토 완료가 아닙니다.
- 참고 계약 OCR은 상단 78%를 처리하므로 하단 조항이 누락될 수 있습니다. OCR·추출의 완전성을 주장하지 않습니다.
- 장기 기록과 공통 승인 메모는 저장되지만, 세션 작업 상태의 재시작 복구나 모든 대화의 전역 자동 기억은 보장하지 않습니다.
- 승인 샘플 수·다양성, 검색 정확도, 실제 모델 누락률·비용·지연·동시 사용자 성능은 이번 테스트로 측정하지 않았습니다.
- 운영 배포·독립 staging DB·인증·모니터링·백업/복구는 구현/운영 담당자의 별도 확인 대상입니다.

## 10. 마무리 멘트와 참고 위치

“AI가 초안과 검토 근거를 만들고, 코드가 계산과 변경 경계를 지키며, 사람이 최종 조건과 수정안을 결정합니다.”

- 구현 설명/실행/설정: [팀 README](../Team/README.md)
- 계약 상세 및 변경 기록: [README_CONTRACTS](../README_CONTRACTS.md), [프로젝트 README](../README.md)
- 실제 코드: [drafting.py](../contracts/drafting.py), [library.py](../contracts/library.py), [repository.py](../contracts/repository.py)
- 과거 수정본/백업 위치: [보관함 안내](../../archive/README.md)
- 과거 [발표 스크립트](presentation_script_ko.md)는 이 문서의 최신 구현/검증 상태와 대조한 뒤 사용합니다.


### 2026-11-09 계약 PDF 출력 정책 개선 (로컬 패치, 배포 미확인)
- 계약서 DRAFT PDF/DOCX는 BOX 3에서 저장한 제목·조항을 출력하며, 검토용 워터마크/머리글은 유지하지만 자동 `[확인 필요]` 접두사, 미확정 부록, AI 검토 원문은 출력하지 않는다. 원래 조항 자체에 작성자가 적은 미확정 문구는 임의 삭제하지 않는다.
- FINAL PDF/DOCX는 현재 revision의 본문을 사용자가 명시적으로 승인한 뒤 생성한다. BOX 2의 제안·법률 검토사항은 화면에서 경고하지만 전부 확정하도록 강제하지 않는다. 본문에 `[서명 전 확인]` 등의 임시 표시가 남았거나 당사자/본문이 명백히 누락되면 최종 생성을 막는다.
- FINAL에는 검증된 회사 직인을 KE KOREA 서명란에만 넣는다. Streamlit Secrets의 `CONTRACT_FINAL_SEAL_PASSWORD` 관리자 암호가 필요하며 원본 이미지는 기존 비공개 Supabase 저장소 또는 SHA-256이 같은 로컬 이미지에서 읽는다. 이미지·비밀번호는 코드나 저장소에 기록하지 않는다. DRAFT에는 직인을 넣지 않는다.
- 코드 패치가 전체 테스트나 운영 Streamlit 검증을 의미하지 않는다. 적용 후 테스트 및 실제 PDF 시각 검증이 필요하다.


### 2026-11-09 조건표 중복 및 계약 PDF 회귀 수정 (로컬 패치·운영 미확인)
- BOX 2 buyer/seller 등 당사자 역할을 조건표에서 중복 표시하지 않고 `parties` 표만 원본으로 사용한다. 수량 행에 KG/월 등이 명시된 경우 `unit`에 KG 후보를 보여주며 사용자 승인 전에는 확정하지 않는다. 매매계약의 `payment_trigger` 표시는 `매매대금 지급 조건`으로 바꾼다. `$`를 USD로 자동 확정하지 않는다.
- 계약서 DRAFT PDF/DOCX의 자동 미확정 부록·검토 원문 출력은 폐지된 정책이므로 관련 회귀 테스트의 기대값을 변경한다. 내부 검토 이력은 DB/앱에 보존한다.
- FINAL UI 테스트는 현재 revision 승인, 관리자 직인 사용 암호, KE KOREA 서명 당사자를 준비한 뒤 생성 경로를 검증한다. 실제 직인/Streamlit 배포 검증과는 별도다.
- 기존 계약/조건표/메모/직인 원본은 수정하지 않는다. 모든 테스트를 통과하기 전에는 배포하지 않는다.


### 2026-11-09 BOX 2·계약파일 한 번 다운로드 경로 보완 (로컬 패치, 배포 미확인)
- Buyer/Seller 등 역할은 `parties` 표에서만 표시하고 조건표에 빈 중복 행을 생성하지 않는다. `quantity.unit`의 KG/월에서 `unit`의 KG를 미확정 후보로 제안하며 사용자 확인 없이 확정하지 않는다. 매매계약 지급조건 명칭을 수수료 지급 트리거와 구별한다. `$` 표기만으로 통화를 USD로 확정하지 않는다.
- 검토용 DRAFT PDF/DOCX는 현재 저장된 BOX 3 제목·조항만 포함해 서버 업로드 없이 한 번 클릭으로 내려받는다. Supabase Storage 400은 DRAFT 다운로드에 영향을 미치지 않는다. revision·본문이 달라지면 다운로드 데이터를 재생성한다. 검토 이력은 화면에 보존한다.
- FINAL은 BOX 3 현재 revision 확인, 관리자 직인 사용 인증, 명시적 본문 미확정 표시 및 당사자 검증에 따라 출력한다. BOX 2의 모든 빈칸을 억지로 채우게 강제하지 않지만, 가격·인도장소 차이 등 실제 위험은 사용자 검토를 필요로 한다. PDF 자동 날인은 비공개 SHA-256 검증 이미지만 사용한다.
- 기존 PO/PI/CI/PL, RAG/메모/revision 기능을 변경하지 않는다. 새 직접 다운로드 흐름에 맞춰 관련 구식 업로드 테스트를 수정했다. 사용자 PC의 전체 테스트 및 운영 환경에서의 PDF 시각 검증은 별도 수행이 필요하다.


### 2026-11-09 최신 대화 명령과 계약 revision 동기화 (로컬 통합 패치, 배포 미검증)
- 서명용 계약의 원본은 마지막으로 **승인 후 저장된 revision**이다. 기존 계약서가 있을 때 최근 사용자의 명시적 수정 요청만 현재 revision과 비교한다. 과거 대화 전체의 조건을 뒤섞어 부산/서울 등의 인도장소를 다시 덮어쓰지 않는다.
- 대화 요청은 즉시 계약서를 변경하지 않는다. 변경값을 확인하고 '선택 후보로 본문 영향 수정안 만들기'→'선택한 변경을 하나의 revision으로 적용'으로 저장한다. 이 승인 후 해시가 revision에 기록되어 페이지를 다시 열어도 이전 명령의 중복 경고를 최소화한다.
- 페이지를 다시 열었을 때 아직 승인되지 않은 최근 명시적 수정 요청이 있으면 재검토·재적용 기능을 제공한다. 사용자의 직전 발언이 임의로 법적 효력을 가지지 않으며, 저장된 계약 본문과 상충하면 사용자가 비교·승인한다.
- 기존 DRAFT 직접 다운로드, BOX 2 중복 행 제거, FINAL 직인 인증, PO/PI/CI/PL은 이전 기능 그대로 보존한다. 이 패치에 대한 실제 DB/웹 배포와 전체 회귀 테스트는 별도 검증이 필요하다.


### 2026-11-09 계약서 동일조건 복사·한국어/영어 전체 번역 (로컬 패치, 배포 미확인)
- 저장·복사·언어 버전 메뉴의 복사 기능은 마지막 저장된 revision의 거래조건, 당사자, 본문 조항을 새 계약에 복제한다. 원본 계약과 자료는 변경되지 않으며, 원본 계약에 귀속된 참고자료 인용은 복사하지 않는다.
- 한국어/영어 새 버전 만들기는 사용자가 AI 전송에 명시 동의했을 때 현재 계약 조항과 설명형 조건을 번역하고, 숫자/금액/표준단위/Incoterms 코드 변화가 발생하면 새 계약 생성을 중지한다. 변환 직후 BOX 3에서 본문을 검토·수정할 수 있다.
- 회사 법인명·품목코드·원본 출처를 추측하거나 변조하지 않는다. 실제 사용/최종 날인 전 양국어 법률 문구를 사용자/전문가가 대조해야 한다. DB 연결/전체 회귀 테스트/운영 배포는 별도 검증 필요.

## Contract PDF and FINAL export integration (2026-11-09)

- DRAFT PDF/DOCX exports use the saved BOX 3 contract clauses without automatically adding unresolved-item appendices.
- DRAFT files are review copies, separate from FINAL contracts.
- FINAL export uses dedicated checks in contracts/final_policy.py rather than requiring all BOX 2 fields to be confirmed.
- FINAL export requires explicit approval and authorized KE KOREA company-seal verification.
- PDF/DOCX changes are implemented in contracts/draft_exports.py and contracts/exports.py.
- Regression tests cover draft formatting, final authorization, and export behavior.
- Rendered contracts must be reviewed before signing.

## 2026-11-09 AI contract note review format recovery

- In `contracts/service.py`, AI issue lists containing plain nonempty text are normalized into explicit, unconfirmed review issues; invalid/empty content fails closed rather than disappearing.
- In `contracts/workspace.py`, the model receives clearer issue-structure instructions. Original sentence validation, conflict detection, and atomic revision approval remain unchanged.
- The BOX 3 final-revision-request error path explains that the contract has not changed and existing note drafts remain available.
- `tests/test_contract_review_issue_recovery.py` checks mixed/invalid issues, unmodified snapshots on failure, and correct proposal creation. FINAL still requires current-revision approval and existing placeholder/seal-authority checks.

## 2026-11-09 BOX 3 note revision preview reliability

- `contracts/service.py`: preserve nonempty free-text AI review issues as unconfirmed review items, while rejecting malformed/empty issue data without accepting or discarding risks.
- `contracts/workspace.py`: explicitly request structured AI issue objects; keep the revision and user notes unchanged until review/approval.
- `contracts/ui.py`: display entire proposed contract in the existing revision-comparison panel, and the full saved contract immediately after approval. Keep approval/commit and FINAL seal authorization separate; display a helpful message on proposal errors.
- `tests/test_contract_issue_preview_recovery.py`: cover recoverable AI issues, invalid issues, proposal preview integrity and unchanged source revision.

## Auth and contract review integration (2026-11-09)

- Auth/gate.py protects the entire Streamlit UI before sidebar, database and AI use. Streamlit Secrets configure one admin login; a signed cookie expires 12 hours after initial login, even across refresh.
- Auth/session.py provides HMAC-signed time-limited tokens. The CookieController is a JavaScript-cookie component (not HttpOnly), appropriate only for a limited demo; production access needs stronger authentication and rate limiting.
- BOX 3 AI review issue objects and text issues normalize into explicit unconfirmed review items. Unknown AI issue structures fail safely without changing existing contract text or notes.
- Proposed revisions require human comparison/approval and atomic revision saving. The UI provides the full approved preview and displays all remaining FINAL blockers.
- Logged-in admin no longer retypes the FINAL seal password. Direct standalone contract module retains a legacy password fallback for compatibility; explicit final approval and verified seal still apply.
- Dependencies: streamlit-cookies-controller==0.0.4. Credentials and session signing secret belong in private Streamlit Secrets, never in Git.
- The uploaded four Python files were the direct source for this repair, rather than a historical GitHub or ZIP patch version.
