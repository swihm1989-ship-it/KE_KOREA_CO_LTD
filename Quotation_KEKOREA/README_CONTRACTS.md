# Contract workspace

> 현재 동작은 원격 코드 `f335e9e` 기준으로 대조했습니다. 문서 끝의 「2026-11-10 코드·README 대조 결과」를 우선 참고하세요. 이전 날짜의 테스트·패치 기록은 당시 상태이며 현재 운영 성공을 뜻하지 않습니다.

This document describes the contract-drafting feature added to the existing Streamlit application. The sidebar contains PI, PO, CI, PL and `계약서 만들기`. The contract label has no preparation suffix, and the separate commission-contract sidebar entry is removed. Commission implementation and stored records are retained. The PI, PO, CI and PL workflows are not replaced by this feature.

Deployment troubleshooting: a screen asking for `CONTRACT_ACCESS_PASSWORD` or `CONTRACT_ACCESS_PASSWORD_HASH` is running a different version from this checkout, which has no password gate. On Streamlit Cloud, check the deployed repository, branch and main file (`Quotation_KEKOREA/app.py`) and reboot after updating the deployed source. If retaining that older gated version, configure its access password in the app's server Secrets. This message does not indicate a missing SQL migration. Live deployment has not been verified for this menu change.

Historical menu verification (2026-11-06, before the subsequent regression fixes): the Streamlit navigation test passed with the five expected sidebar entries and preserved PI/PO/CI/PL state. The then-current requirements-based suite ran 233 tests with one product-annotation failure. This is not the current failure status: baseline `3991930` passed all 296 tests before this UI change. Use the complete requirements, including `python-docx`, for contract tests.

Classification/title verification (2026-11-06): all 37 contract tests pass with the complete requirements, including real Streamlit forms for investment-commission creation, opening all types, correcting an existing sale classification, preserving draft content for review, retaining user titles through AI drafting, and exact DOCX/PDF title text. The broader 240-test run reproduced the known product-annotation failure and initially exposed a PDF text-extraction ordering assumption in the new title test; that assertion was corrected and the 37 contract tests rerun successfully. No live records were edited and this change has not been deployed or verified against the live app.

Commission-policy verification (2026-11-06): the full requirements-based regression ran 248 tests with only the known `test_annotations_load_prices_without_bypassing_product_confirmation` failure. After adding explicit checks for repeated-AI bank redaction, changed server accounts, legal-review completion and rejecting N/A as legal evidence, all 27 selected policy/service/rules/workspace tests passed. The workspace assertion now reads the terms dataframe directly instead of relying on its truncated string representation. All fixtures use synthetic accounts and transactions. The source agreement was read locally only; no live OpenAI calls, document uploads, database changes or deployment were performed.

## What it does

- Commission drafting uses a generalized, non-verbatim reference brief from the user-supplied prior agreement. The original DOCX, transaction identities, commission percentages, bank data, guarantee signatures and negotiated periods are not copied into the repository or automatically inherited. Analysis and revision prompts consider balanced scope, proportionate non-circumvention, actual receipts, evidence, finite negotiated protection periods, confidentiality, tax and enforceability questions. Guarantees, governing law and dispute forums require explicit current instructions.
- **BOX 1 — chat:** `거래 내용과 AI 분석` retains conversation history, API consent, selected references and approved-clause RAG. The existing one-round, maximum-two-question guard and draft-first response remain unchanged. The latest 30 conversation messages accompany draft generation.
- **BOX 2 — manual details:** the terms and party editors are always available. UI states `확정 / AI 제안 / 확인 필요 / TBD 유지` map to existing confirmed/suggested/missing values; TBD preserves the supplied value without approving it. Existing term-reconciliation proposals and commission payment editing remain in this box. Confirming one finding never confirms unrelated structured values.
- **BOX 3 — document and notes:** a grey workspace surrounds a white, responsive paper preview. Sentence IDs remain stable; clicking a sentence highlights it and opens its saved note. Re-saving updates the note for that sentence and revision. `최종 수정 요청` collects current pending notes, generates proposals, compares them and requires approval before one revision commit. Old/deleted/superseded notes are shown separately and cannot be applied automatically. Direct single-sentence proposals, RAG risk review and revision restoration remain available.
- For investment/trade commissions, locally assembled payment sections default to D+7 calendar days after each confirmed trigger/tranche by TT, while explicitly confirmed custom deadlines can be used; payment completion is actual credit, not a transfer instruction. These sections take precedence over conflicting timing/default-interest wording. The server inserts only the configured KE KOREA USD corporate account when the confirmed payee and currency match. Missing/mismatched configuration blocks export. The six `KEKOREA_USD_*` bank variables are never substituted into another company's or another currency's receiving account. They are not API credentials, but are still not logged or committed. Protected account sections are stripped from AI snapshot payloads and assembled after AI generation.
- Default interest runs as daily simple interest on unpaid principal from the day after the due date; the edit form accepts an explicitly negotiated annual percentage while legal validity remains a separate review requirement. It refers to the highest rate legally applicable to the specific commission obligation in the Payer's country, subject to any lower mandatory limit under the governing/enforcement laws, with a lawful-default-interest fallback if no applicable maximum exists. No numeric cap is guessed. Lending ceilings are not treated as commission default rates, and a selected governing law does not automatically override local mandatory law. This is a drafting policy, not automated foreign-law research or certification.
- Before FINAL export, explicitly confirm the payer country, trigger, currency and payee in BOX 2, then record `late_interest_legal_review` and `late_interest_source` with the applicable-law assessment, supporting law/review document and review date. AI extraction cannot confirm these for the user. `수수료 지급조건 수정` → `지급조건 저장 및 조항 갱신` revises the trigger, deadline, payer country and negotiated annual late-interest rate, using the existing payment policy. The policy guard detects missing/edited payment clauses, changed triggers and changed server bank settings. Calendar-day counting and special-trigger rules remain unchanged. DRAFT may be exported while these checks remain unresolved, with explicit provisional labels and an unresolved-items appendix.
- The single contract workspace opens every supported contract type. New contracts require an explicit sale, trade-commission or investment-commission selection; the menu no longer defaults every contract to sale. Type is separate from title and controls the required terms and party roles.
- The saved-contract selector and workspace heading display the user's title without type labels or revision suffixes. AI drafting preserves that title, and DOCX/PDF headings use the same title. Revision information remains in a separate caption.
- Existing misclassified contracts can be corrected in `계약 정보 수정` → `현재 계약 유형` → `계약 정보 저장`. Title edits are also available there. Changes create a revision with concurrency checking, preserving terms, clauses and references. Changing type on an existing draft adds a review issue and blocks export until that review is resolved; old proposals are cleared.
- Drafts sale, trade-intermediary commission and investment-commission contracts in Korean or English from natural-language transaction notes and a structured terms table.
- Stores contract revisions, conversation messages, annotations, approved clause preferences, references and export metadata in Supabase. Revision commits use an expected-revision check to prevent overwriting a concurrent edit.
- Extracts text from PDF and DOCX references locally. Scanned PDF OCR is optional and requires a separate explicit consent before page images are sent to the configured OpenAI API. Extracted reference text is treated as data, and AI source quotations are checked against the selected material.
- Lets the user open and edit several sentence notes alongside their sentences, then save and send them together in one AI request. The separate optional single-sentence action remains available. Reported note conflicts, duplicate/missing sentence changes and protected payment changes reject the proposal without changing the contract. Different-sentence semantic conflicts still require explicit human consistency review; AI is not a legal reconciliation guarantee. Only approved changes are saved once through the existing revision RPC.
- **Review outputs:** `검토용 초안 PDF` and `검토용 초안 DOCX` require actual clauses. They preserve original wording but explicitly qualify unresolved text, add an unresolved-items appendix, and omit signature pages. PDF has a DRAFT watermark/header on every page; DOCX has a repeating DRAFT header. These are not signing copies.
- **Final outputs:** `최종 계약서 PDF` and `최종 계약서 DOCX` use the existing renderer and are enabled only after `validate_rules(..., for_export=True)` passes. No required term, bank check, legal check or AI review severity is relaxed. Both modes retain private Storage and export records, distinguished by `exports/draft/` versus `exports/final/` in their paths; legacy exports retain their existing paths.

The app does not send, sign, issue or automatically seal contracts. It does not implement BIPV construction agreements. The DOCX/PDF layout and Korean font rendering still need visual verification in the deployment environment.

## Configuration

Set these values only in the local ignored `.env` file or the hosting provider's server-side Secrets:

| Variable | Requirement |
| --- | --- |
| `OPENAI_API_KEY` | Required for analysis, drafting, revisions and consented OCR. Never expose it to browser code. |
| `OPENAI_MODEL` | Required default model. |
| `CONTRACT_OPENAI_MODEL` | Optional contract-specific model override. |
| `SUPABASE_URL` | Required Supabase project HTTPS URL. |
| `SUPABASE_SECRET_KEY` | Required server-only Supabase key. Do not use the publishable key for this feature. |

**The contract UI has no login or password gate.** Anyone who can reach the app URL can view, edit, export and delete stored contracts and reference materials through the app. Do not store confidential agreements or deploy this app publicly unless that exposure is acceptable. The Supabase bucket is private at the storage layer, but the app's server-side secret can access it on behalf of every visitor.

## Supabase setup

1. Review `supabase/migrations/202611050001_contracts.sql`.
2. Apply it manually in the intended Supabase project's SQL Editor using an administrator account. It creates private contract tables, a non-public Storage bucket, and revision/create/delete RPC functions. It does not populate contract records.
3. Configure `SUPABASE_URL` and `SUPABASE_SECRET_KEY` as server-side environment variables.
4. Verify the migration's table grants, RLS status, RPC execution grants and bucket privacy in that project before storing real contract data.

The migration has **not** been applied or verified against the live Supabase project. Do not treat database privacy, grants, or persistence as production-verified until those checks are completed. The server secret key bypasses ordinary RLS and must never be exposed in a client, public log, or repository.

## Local run and verification

From the repository root (`KE_KOREA_CO_LTD`), install the app requirements and start Streamlit:

```powershell
uv run --with-requirements Quotation_KEKOREA\requirements.txt streamlit run Quotation_KEKOREA\app.py
```

Run contract tests:

```powershell
uv run --with-requirements Quotation_KEKOREA\requirements.txt python -m unittest discover -s Quotation_KEKOREA\tests -p "test_contract_*.py"
```

Run the complete app regression suite:

```powershell
uv run --with-requirements Quotation_KEKOREA\requirements.txt python -m unittest discover -s Quotation_KEKOREA\tests
git diff --check
```

The tests use synthetic contract content and fake API/database clients. They do not call the live OpenAI API or Supabase project.

## Current rollout status

The code and local tests are present, but this feature has not been deployed. The Supabase migration, deployed secrets, live database persistence, external OCR/API behavior and production document layout remain unverified. The UI is intentionally unauthenticated. Keep real agreements, signatures, account details and keys out of test fixtures and source control.

## 2026-11-06 TASTE 계약서 UI 및 README 동기화

### Current drafting and review flow

- **Draft first:** Users enter a natural-language transaction, respond to at most a small number of initial clarifying questions, and generate a complete working draft. Draft generation and sentence edits remain possible while legal details are unresolved.
- **Sentence revisions:** Select multiple sentences in BOX 3 to keep their adjacent note fields open simultaneously. Typing is retained in the browser session; with BOX 1's API consent, `최종 수정 요청` saves all notes then sends one joint AI request. Compare and approve selected changes, including the explicit cross-sentence consistency check. Saved notes survive session reload; unsaved notes do not. Earlier-revision notes can be viewed but must be explicitly edited or saved again. Existing pending term proposals are preserved and must be applied or dismissed before a batch request. The existing payment editor remains the route for protected payment sentences.
- **Review UI:** `contracts/review_summary.py` deduplicates display cards by category/field and labels them required, recommended, legal-review or TBD-allowed-in-draft. The explicit review-language selector defaults to Korean and is separate from output language. Conservative category labels do not pretend to translate every legal nuance; company names, amounts and original evidence remain verbatim in a collapsed details area. Original findings and validation state are retained.
- **Final validation:** `contracts/rules.py` and payment policy checks remain authoritative for FINAL. Changing a previously reviewed issue to TBD reopens that issue; saving unchanged review choices creates no revision and does not invalidate notes. A summary itself cannot change confirmation, evidence, bank settings or signature readiness.
- **Commission editor:** The payment trigger, payer country, due period and optionally negotiated late-interest rate may be edited. Bank details and enforceability must be verified before final export; no guessed addresses or numeric rates.
- **RAG risk assessment:** Optional, source-grounded risk review based on approved sample clauses. Its AI suggestions do not modify a contract until the user explicitly applies them.
- **Rollout:** Work resumed from fetched `main` at `3991930`, newer than the requested `e20fcb6`, with 296 baseline tests passing. This three-box UI remains a local change; it has not been pushed or deployed. Historical smaller test runs above describe earlier stages.

Final local verification (2026-11-06): **320 tests passed, 0 failures, exit code 0**, including all 296 existing tests and 24 new helper/Streamlit interaction tests; `git diff --check` passed. No existing test was removed or weakened. Synthetic multi-page Korean/English DRAFT PDFs were rendered and inspected, including Korean original evidence in English output. Actual browser visual/responsive verification was blocked by Windows browser-URL detection; Word rendering and live OpenAI/Supabase/deployment behavior remain unverified. Existing Streamlit-width and PyMuPDF import deprecation warnings remain distinct from failures.

### Scope and privacy

No change to PO/PI/CI/PL or ECLADO pricing logic. The current contract page is not authenticated; do not use live confidential agreements on an internet-accessible instance until access control is added and tested. Never put bank account data or API keys in a README.

## 2026-11-06 commission payment wording compatibility

The default 7-calendar-day English payment clause prints `seven (7) calendar days` (D+7); confirmed alternative periods retain their numeric value. This existing wording correction was included in the passing 296-test baseline and is untouched by the UI change.

## 2026-11-06 CI regression scope

The document-export safeguard is document-specific: PO/PI product-annotation confirmation blocks PDF/Excel generation; a CI preserving attached-PI transaction prices may produce an explicitly marked DRAFT with unresolved product matching warnings. This CI rule does not relax contract-export validation or change commission clauses.

### 2026-11-06 문장 옆 인라인 메모 UI 보완
BOX 3에서는 문장과 우측 메모 영역이 모든 행에 고정 배치된다. 문장을 누르면 해당 행 오른쪽에 입력란이 열리며 다른 메모가 자동으로 닫히지 않는다. 메모 버퍼·일괄 AI 요청·검토와 승인 동작은 그대로 유지한다. 운영 브라우저 시각 QA는 별도 검증이 필요하다.

## 2026-11-06 AI 위험 검토 페이지·추천안 확장

contracts/risk_review_workspace.py는 기존 contracts/review.py의 검증을 유지한 채 전체 조항을 분할해 위험 결과를 모으고 페이지당 5개로 보여준다. 추천안은 선택 위험에서 사용자 요청 시 3개 생성되며, 변수 이름·값은 모델 결과를 검증한 뒤 편집한다. contracts/risk_review_ui.py는 추천 3개 중 선택, 가변정보 수정, 문장 편집, 수정 미리보기 및 기존 proposal 승인 경로를 제공한다. 적용은 DB에 즉시 저장하지 않으며, 이미 저장된 메모·커미션 지급정책·FINAL 출력을 자동 변경하지 않는다. 기존 위험 검토 함수의 단일 호출 5건 제한과 전체 검토 묶음 방식은 구별된다.

### 2026-11-06 · 계약서 위험 검토 미리보기 표시 보강

- `추천 문장 적용`은 기존 계약서 조항을 즉시 확정 저장하지 않으며, 같은 revision의 BOX 3 문장에만 임시 수정 문구를 표시한다.
- BOX 3 상단에 미저장 위험 검토 수정안 개수와 `선택한 수정안 비교·승인` 경로를 명시하고, 변경된 각 문장에 미리보기 상태를 표시한다.
- 비교·승인 및 revision 저장·PDF/DOCX 최종 검증 로직은 그대로 유지한다. 실제 Streamlit 운영 브라우저의 반영 여부는 별도 검증이 필요하다.


### 2026-11-06 계약서 내보내기 UI 간소화 (검증 규칙 변경 없음)

- BOX 3에서 문서 다운로드(DRAFT/FINAL)를 먼저 표시하고, 길게 반복되는 서명 전 검토 목록은 `고급 검토 기록 · 확정 근거 확인 (선택)` 접힌 영역으로 이동했다. 검토 기록·원문·확인 근거 입력 기능은 유지한다.
- 미확정 조건이 있어도 검토용 DRAFT는 생성할 수 있습니다. FINAL은 현재 문서의 명시적 동의·승인·직인·당사자 검증 규칙을 따릅니다. TBD 유지가 거래조건 확정을 뜻하지 않습니다.
- 계약서 UI 외의 ECLADO·PO/PI/CI/PL, 지급정책, 수정 엔진, 저장·승인 로직은 수정하지 않는다. 실제 Streamlit 운영 화면과 전체 회귀 테스트는 사용자 PC에서 별도로 검증한다.

### 2026-11-06 계약서 메모 revision 복구 UX 보완

계약서 BOX 3에서 현재 revision에 유효한 메모가 0개이지만 이전 revision의 메모가 존재하면, 기존 메모를 **명시적으로 현재 revision으로 가져오기** 버튼으로 재사용할 수 있습니다. 다른 계약 또는 삭제된 문장에 연결된 메모는 가져올 수 없습니다. 이전 메모를 자동 확정하거나 적용하지 않으며, AI 전송 동의와 기존 수정안 충돌 검사를 유지합니다. `최종 수정 요청` 비활성 상태에는 현재 revision 메모가 필요한 이유를 안내합니다. 계약서 데이터 모델·지급 정책·FINAL 검증·ECLADO/PO/PI/CI/PL 기능은 변경하지 않았습니다. 이 기능의 실제 Streamlit 검증은 전체 테스트를 통해 확인해야 합니다.

### PDF/DOCX 렌더링과 비공개 저장 실패 처리
렌더링 성공/비공개 파일 업로드 성공/출력 이력 저장 성공을 구별한다. 렌더링은 성공했으나 `ContractRepositoryError`가 발생한 경우 기존 롤백 후 세션 내 **직접 다운로드 (서버 미저장)** 링크를 제공한다. 저장소에 없는 결과를 저장 성공이라고 주장하지 않는다. 렌더링 자체가 실패하면 다운로드 버튼을 만들지 않는다. FINAL 검증이나 계약조건 상태를 변경하지 않는다.

### 2026-11-09 · BOX 3 긴 문장 전체 보기
- 계약서 BOX 3의 문장 클릭 버튼을 줄바꿈 가능한 가변 높이로 변경하여 긴 문장도 생략 없이 표시합니다. 폰트 크기는 6pt 이하로 줄이지 않습니다.
- 180자 초과 문장은 마우스 오버 또는 키보드 포커스에서 전체 문장을 보여주는 보조 말풍선을 지원합니다. 커서를 치우거나 포커스를 옮기면 숨깁니다. 말풍선 본문은 HTML escape 처리합니다.
- sentence ID, 문장 클릭, 문장별 메모, AI 수정 미리보기, 수정 승인, DRAFT/FINAL 및 계약·무역 로직은 변경하지 않습니다.
- 적용 스크립트가 문법 검사와 이전 코드 패턴 검증을 수행합니다. 전체 Streamlit 테스트·실제 배포 확인은 별도로 진행해야 합니다.


### 2026-11-09 통합 최종 수정 요청 UI
- BOX 3의 문장 메모, 이전·제외 메모, AI 핵심 위험 검토 이후 최종 수정 요청을 배치한다.
- 최종 수정 요청은 현재 revision의 메모와 AI 위험 검토 추천안을 충돌 검사 후 하나의 수정안으로 모으며, 비교·승인 전에는 원본 계약서를 수정하지 않는다.
- 같은 문장을 두 경로로 수정하면 조정을 요구하고, 빈 메모라도 위험 검토 선택안이 있으면 통합 요청할 수 있다.
- 사용자 승인 뒤에만 새 revision을 저장한다. 기존 필수 검증·DRAFT/FINAL 출력과 ECLADO·PO/PI/CI/PL 기능은 변경하지 않는다.
- 운영 Streamlit 배포는 별도 검증이 필요하다.

- **2026-11-09 OCR JSON 400 오류 수정:** 스캔 PDF 참조자료 OCR의 OpenAI Responses API 요청에서 `json_object` 출력 형식을 사용할 때 `input_text`에 JSON 응답 요청을 명시했습니다. 기존 OCR 상단 78% 범위, 사용자 전송 동의, 필드 검증 및 실패 처리 방식은 유지합니다.

### KE KOREA 공통 참고자료 승격 / 2026-11-09
- 계약별로 비공개 저장된 참고 PDF/DOCX는 그대로 유지한다. 관리 키 인증을 마친 관리자만 현재 계약의 기존 참고자료를 회사 공통 샘플 라이브러리에 명시적으로 등록할 수 있다.
- 원본 해시 및 현재 계약 소속을 확인하여 Supabase 비공개 `kekorea-contracts` 라이브러리 경로에 별도 등록하고, 공통 레코드는 `kekorea_contract_references`에서 `contract_id=NULL`, `library_pending`으로 보관한다. 다른 계약의 원본 파일을 자동으로 공개하거나 이전하지 않는다.
- 원본 등록만으로 AI 장기기억 또는 자동학습이 되는 것이 아니다. 관리자 검토 후 개인정보·회사명·거래 금액·계좌 등을 제거한 익명화 참고 메모를 명시적으로 승인해야 검색·RAG에서 계약 유형에 맞춰 재사용한다.
- 기존 `library.py`/`repository.py`/`service.py`, 계약의 PDF/Word 생성, ECLADO 및 PO/PI/CI/PL 기능은 변경하지 않는다. 인증되지 않은 운영 공개화면에서 원본을 공유해서는 안 된다.

### BOX 3 문장 정렬 보정 (2026-11-09)
계약서 미리보기의 모든 문장 버튼과 내부 텍스트 래퍼를 동일한 왼쪽 기준선으로 정렬한다. 짧은 문장/긴 문장의 시작점이 일치하며, 기존 자동 줄바꿈·문장 호버 전체보기·문장별 메모·AI 수정과 계약서 저장/출력 검증은 변경하지 않는다. 수정 파일: `Quotation_KEKOREA/contracts/ui.py` (CSS만).

### BOX 3 문장 왼쪽 정렬(본문/클릭영역 분리)

- 계약서 문장 표시를 Streamlit 버튼의 기본 텍스트 정렬과 분리해, 짧거나 긴 문장 모두 왼쪽 기준선에서 시작합니다.
- 기존 문장 클릭 키/메모·AI 위험 검토·revision 처리와 긴 문장 전체 보기 기능은 유지합니다.
- 기능 변경은 `Quotation_KEKOREA/contracts/ui.py`의 BOX 3 문장 렌더링과 CSS에만 한정됩니다.


### 2026-11-09 · 본문 조건 후보 연결 및 DRAFT 문장별 표시
- BOX 2에서 계약서 본문을 AI로 재분석하여 값이 비어 있는 구조화 조건과 당사자 필드에 미승인 후보를 불러옵니다. 기존 비어 있지 않은 값은 보존하고 사용자 승인과 본문 영향 비교 절차를 유지합니다.
- 검토용 PDF/DOCX는 미확정 조건과 직접 연결된 문장에만 추가 표시를 붙이고, 미확정 전체 목록은 부록에 유지합니다. DRAFT 워터마크와 FINAL 검증은 변경하지 않습니다.

### 2026-11-09 루트 작업 파일 정리

- 과거 오류 수정 패키지는 루트 `archive/bugfixes/`의 UI·PDF·언어·거래조건·참고자료·위험 검토·워크플로·OCR·테스트·문서 폴더로 모았습니다. 독립 백업은 `archive/backups/`, 루트 테스트 로그는 `logs/tests/`로 이동했습니다.
- 현재 실행 코드, 공식 테스트(`Quotation_KEKOREA/tests`), 배포 설정 및 비공개 데이터 경로는 유지합니다. 보관 패키지 내부의 보조 테스트와 내장 백업은 해당 패키지와 함께 보존합니다.
- 상세 위치는 루트 `archive/README.md`, 이전·새 경로와 파일 해시는 `archive/move_manifest_2026-11-09.json`에서 확인합니다. 과거 적용 스크립트는 재사용 전 경로·코드 버전 검토가 필요합니다.
- 이동 무결성: 34개 항목, 145개 파일의 개수와 SHA-256 일치를 확인했습니다. 정리 후 전체 회귀 테스트 403개가 모두 통과했습니다(116.182초, 생략 없음). `git diff --check`도 통과했습니다. 기존 Streamlit/PyMuPDF 경고는 남아 있습니다. 운영 배포는 이번 정리 범위에 포함하지 않습니다.

## 2026-11-09 다국어 계약 조건 추출 키 정규화

- BOX 2 본문 후보 추출 시 한국어·영어·인도네시아어 입력을 동일한 내부 snake_case 조건 키에 대응한다. 제품/단가/수량/인도/지급조건을 임의의 새 키로 중복 등록하지 않도록 주요 별칭을 정규화한다.
- buyer/seller는 당사자 별도 표에서 확인하며 값·단위·통화 원문을 보존한다. AI 추출은 `suggested` 후보이며 사람이 `확정`해야만 confirmed가 된다. 기존 비어 있지 않은 값은 덮어쓰지 않는다.
- 서로 다른 값이 하나의 표준 키에 충돌하면 첫 후보만 미승인으로 제시하고 경고를 표시한다. 자동 해결/기존 확정값 변경은 하지 않는다.
- DRAFT/FINAL 출력 및 법적 최종 검증은 변경하지 않는다. 로컬 회귀 테스트와 실제 Streamlit 배포 검증은 별개이다.

## 2026-11-09 거래조건 동의어 확장 및 문맥 분류

- BOX 2에서 한국어·영어·인도네시아어의 400개 이상 정확 별칭을 계약조건 표준 키로 정규화한다. price·qty·volume·harga satuan·jumlah 등 표시가 달라도 공통 항목에 제안한다. MT·KG는 수량 자체가 아닌 단위(unit)이고 value·amount는 총액일 수 있어 문맥이 불확실한 경우 경고를 남긴다.
- buyer/seller는 당사자 별도 표에서 확인하며 값·단위·통화 원문을 보존한다. AI 추출은 `suggested` 후보이며 사람이 `확정`해야만 confirmed가 된다. 기존 비어 있지 않은 값은 덮어쓰지 않는다.
- 서로 다른 값이 하나의 표준 키에 충돌하면 첫 후보만 미승인으로 제시하고 경고를 표시한다. value·rate 등 모호한 키를 함부로 unit_price로 강제하지 않으며 기존 확정값을 변경하지 않는다.
- DRAFT/FINAL 출력 및 법적 최종 검증은 변경하지 않는다. 로컬 회귀 테스트와 실제 Streamlit 배포 검증은 별개이다.

## 2026-11-09 계약조건 추출·충돌 비교·FINAL 검증 강화

- BOX 2 AI 추출은 한국어·영어·인도네시아어 표준 키 정규화를 유지하되 통화·단위·숫자·인도조건의 의미를 별도로 비교한다. **4와 5는 충돌**하나 `5`와 `5.00`은 수치가 같을 수 있으며, EXW 인도조건과 일정 협의 절차는 상호 배타적인 조건이 아니다. 근거가 불확실하면 미확정 후보로 남긴다.
- 거래조건은 `AI 제안(suggested)`으로 표시하며 사용자가 승인하기 전까지 확정으로 승격되지 않는다. 기존 확정 조건은 자동 덮어쓰기하지 않는다. `$`만으로 USD를 가정하지 않는다.
- DRAFT PDF/DOCX는 저장 본문을 검토용으로 출력하며 별도의 미확정 부록을 자동 추가하지 않습니다. 본문 자체의 미확정 문구를 합의된 조건으로 바꾸지 않습니다.
- FINAL은 현재 저장 revision의 본문 승인과 직인 권한·원본 SHA-256 검증을 요구합니다. 임시 확인 문구는 기본 차단하지만, 사용자가 미확정 본문 그대로 내보내기에 별도로 동의하면 문구를 보존해 출력할 수 있습니다. 이 동의는 거래조건 확정이나 법률 검증을 뜻하지 않으며, 미반영 조건 변경·본문 부재·KE KOREA 및 매매 당사자 누락 검증은 유지합니다. BOX 2 전 항목 확정이나 AI 위험 추천안 전부 선택은 필수가 아닙니다.
- 수정사항 테스트: `Quotation_KEKOREA.tests.test_contract_integrity_fix`. 전체 회귀 및 실제 배포 파일 생성은 별개로 검증한다.

### 2026-11-09 신규 계약서 초안 품질 파이프라인

- 기존 BOX 1·2·3 화면, 버튼, 대화 흐름(`flow.py`), 문장별 메모·비교·승인·revision 저장, PDF/DOCX 및 FINAL 검증은 유지합니다. 기존 두 초안 생성 진입점의 내부 연결만 새 `contracts/drafting.py`로 교체합니다. 저장된 조항이 있는 계약은 자동 재작성하지 않습니다.
- 내부 순서: 거래조건 정리 → 계약 유형별 조항 목차/작성 기준 구성 → 조항별 참고자료 검색 → 상세 작성 → 누락·충돌 검사 → 필요 시 1회 보완·재검사 → 기존 화면에서 사용자 검토. 매매계약은 13개, 커미션 계약은 12개 주제의 기본 기준을 사용하며, 사용자가 명시적으로 승인한 준거법·분쟁 해결 제외 결정은 존중합니다.
- 선택한 첨부자료는 앞 12,000자에 한정하지 않고 전체 추출 텍스트에서 문단/페이지 경계를 잇는 구간을 검색합니다. 주제별 최대 3개 새 구간, 최종 발췌 합계 최대 100,000자로 제한합니다. 거래조건 분석 단계의 기존 12,000자 제한은 유지되며, 상세 초안 작성의 검색 범위만 확장됩니다.
- 공통 라이브러리는 기존 사용 선택을 따릅니다. 승인·활성·계약 유형 필터를 유지하고, 한 번 조회한 레코드에서 주제별 키워드 검색을 수행합니다. 이 추가 검색은 임베딩 API를 호출하지 않습니다. 비공개 원본이나 미승인 참고 메모를 공통 검색에 넣지 않습니다.
- 불가항력은 발생 요건·통지·완화 노력·이행 재개·장기화 시 처리를 포함하도록 지시합니다. 다른 조항에도 업무 범위, 지급, 기간, 해지, 책임, 비밀유지, 통지, 준거법, 분쟁 해결, 일반 조항 등의 구성요소 기준을 적용합니다. 계약 유형에 따라 인도·검수 또는 커미션 대상 거래·성공·증빙을 추가합니다.
- 별도 AI 품질 검사는 모든 계획 주제와 실제 생성된 모든 조항을 확인해야 합니다. 구성요소별 문장 ID·정확한 인용 근거를 검증합니다. 단순 제목이나 길이만으로 완성도를 판정하지 않습니다. 문장 근거가 없는 검사 결과나 허위 인용으로 완료 처리하지 않습니다.
- 보완은 지적된 조항과 완전히 빠진 주제로 한정합니다. 무관한 조항·기존 문장 ID·확정 거래조건을 보존하며 기본 커미션 지급 조항은 AI가 수정하지 않습니다. 최종 검사는 기존 지급정책 적용 후의 실제 본문을 대상으로 합니다. 남은 문제는 미확정 검토 항목으로 전달합니다.
- 신규 초안은 생성→품질검토→필요 시 1회 보완→재검토 순서입니다. 각 검토에서 잘못된 인용만 1회 재검증할 수 있어 생성/검사 API는 통상 2회, 최대 6회입니다. 요청별 소켓 타임아웃은 최대 150초, 내부 파이프라인 경과시간 예산은 600초입니다. 별도의 거래조건 분석은 180초이며 검색·임베딩 호출은 이 횟수에서 제외합니다. 이는 즉시 취소를 보장하는 UI 타이머가 아닙니다. 모델·품질검증을 자동 완화하지 않습니다.
- 참고 계약의 금액·기한·책임한도·준거법은 합의값으로 자동 채택하지 않도록 작성/검사 지침을 둡니다. 미합의 항목은 확인 표시로 남깁니다. AI의 의미 판단과 법적 적정성을 결정적으로 보장하는 검증은 아니므로 최종 사용자 검토가 필요합니다.
- 검증: 가상 API 응답을 사용하는 새 핵심 테스트 15개 통과. 최종 전체 회귀 테스트 437개가 109.838초에 모두 통과했습니다(화면 테스트 포함, 생략 없음). `git diff --check`도 통과했습니다. 기존 Streamlit/PyMuPDF 경고는 남아 있습니다. 실제 모델 응답의 문장 품질·실제 Streamlit 배포·실제 거래자료 전송은 이번 로컬 검증에 포함하지 않습니다.


### 2026-11-09 계약 PDF 출력 정책 개선 (로컬 패치, 배포 미확인)
- 계약서 DRAFT PDF/DOCX는 BOX 3에서 저장한 제목·조항을 출력하며, 검토용 워터마크/머리글은 유지하지만 자동 `[확인 필요]` 접두사, 미확정 부록, AI 검토 원문은 출력하지 않는다. 원래 조항 자체에 작성자가 적은 미확정 문구는 임의 삭제하지 않는다.
- FINAL은 현재 저장 revision의 본문 승인과 직인 권한·원본 SHA-256 검증을 요구합니다. 임시 확인 문구는 기본 차단하지만, 사용자가 미확정 본문 그대로 내보내기에 별도로 동의하면 문구를 보존해 출력할 수 있습니다. 이 동의는 거래조건 확정이나 법률 검증을 뜻하지 않으며, 미반영 조건 변경·본문 부재·KE KOREA 및 매매 당사자 누락 검증은 유지합니다. BOX 2 전 항목 확정이나 AI 위험 추천안 전부 선택은 필수가 아닙니다.
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

## Authenticated UI test isolation and AI review issue schema (2026-11-09)
- Existing Streamlit AppTest suites simulate a signed-in test session **only within each test method**; production login remains mandatory.
- The server-side Auth gate is unchanged, and separate authentication/security tests continue to test real 12-hour signed-token validation.
- AI review issues provided as text remain unconfirmed, while malformed opaque issues fail closed and preserve user notes.
- Legacy error messages retain the original invalid severity for audit and compatibility.
- Run full regressions before deployment; no login bypass environment variable is introduced.

### 2026-11-09 번역 숫자 검증 오탐 보정
- 한국어/영어 계약서 버전 번역 시 `30일`처럼 한글에 붙은 숫자도 추출합니다. `1,000`/`1000`/`1000.00` 등 값이 같은 표기만 정규화하고 비율(`30%`/`30`) 및 실제 금액·기한의 불일치는 계속 차단합니다. 불일치가 있으면 조항 위치, 숫자 차이, 원문·번역문을 알려주고 원본은 보존합니다. 새 계약서가 정상 생성된 것은 번역의 법률적 정확성까지 보증하지 않습니다.

### 2026-11-09 영어 계약서 날짜 번역 숫자 검증 보완

- 한국어 `2026년 11월 10일`과 영어 `November 10, 2026`의 달 표기를 같은 값으로 비교합니다. 날짜 맥락의 영어 월 이름/약어만 숫자로 정규화합니다.
- 원래 금액·수량·비율·날짜의 실제 값 변경은 계속 차단하고, 불일치 시 원문/번역문과 차이를 보여줍니다. 원본 계약은 보존됩니다.
- 회귀 테스트: `Quotation_KEKOREA/tests/test_contract_translation_month_names.py`. 실모델 응답·운영 Streamlit은 별도 검증이 필요합니다.

### 2026-11-10 Source-reference deployment repair

- Fixed a Python string quoting error in the analysis citation instructions introduced by `5f5e0e6`; the service can import again. No other runtime behavior was changed by this repair.
- Source-reference recovery retains the upstream handling of null/single-object/prose citations and continues to reject fabricated quotes. Existing transaction, pricing, translation, export and authentication behavior is unchanged.
- Verification: 18 source-reference/service tests and all 498 tests in the full suite passed (130.277 s, no skips) with app requirements installed and the existing local private catalog fixture available. Compile checks and git diff --check passed. The initial minimal-dependency run failed because python-docx/pydantic and the private fixture were absent; no application code was changed to address those setup failures. Production health returned HTTP 200; deployed contract-analysis behavior remains unverified.

### 2026-11-10 Contract analysis timeout handling

- Trade-condition analysis now allows a 180-second socket timeout instead of 90 seconds. The reported approximately 90-second failure matches the previous limit; production transport logs were unavailable, so the underlying server/network delay is not confirmed.
- Direct timeouts and URL-wrapped timeouts now display a distinct timeout message with the request limit. Connection errors retain their existing message. Other operations keep their existing timeout values; model selection, business terms, translation, pricing, exports and authentication were not changed.
- Tests cover the analysis timeout, unchanged input snapshot, unchanged default for other calls, and safe timeout/connection messages. Existing citation validation remains enabled. Verification: all 501 tests passed in 139.103 seconds with app requirements and the existing local catalog fixture, no skips. Compile and diff checks passed. A synthetic analysis using local configured API credentials succeeded in 19.41 seconds; that does not validate production credentials or latency. Production contract-analysis verification remains pending.

## 2026-11-10 코드·README 대조 결과

**대조 기준:** 원격 `main`의 `f335e9e`. 이번 점검에서 `97a6199` 이후 코드 변경 16개가 다섯 README에 기록되지 않은 것을 확인해 보완했다. 아래는 코드 확인 결과이며, 운영 화면 검증 완료를 뜻하지 않는다.

| 근거 커밋 | 구현과 사용자에게 보이는 동작 |
| --- | --- |
| `c173bac` | 계약 초안 생성·품질검토 요청 제한을 호출당 최대 150초, 파이프라인 예산 600초로 조정. 중간 미검증 초안은 저장하지 않음. |
| `c06cd2c` | AI가 같은 조건을 다국어 키로 반복 추출하면 키를 정규화하고 충돌을 미확정 검토 항목으로 남김. |
| `b359cd4` | 계약 분석·검토 초안만 LangGraph의 추출/생성·검증 노드로 실행. 기존 중복 키 계약은 미리보기 후 사용자 승인으로 새 revision에 복구하며 열기만으로 쓰지 않음. `langgraph>=1.0,<2` 의존성 추가. |
| `a317bdc` | 계약 생성·검사·보완 단계를 화면에 표시. |
| `fbbdc16` | 무조건적인 문장 전체 확인 표시를 줄이고 실제 누락 사실에만 표시하도록 작성 지침 보완. 미확정 문구를 보존한 FINAL 출력은 별도 사용자 동의로 허용하며 기존 승인·직인·당사자 검증 유지. |
| `fd20d88` | 선택적인 AI 일괄 문장 정리: 문장 전체 확인 포장 문구만 수정 후보로 제안. 숫자·실제 미확정 사실·보호 문장은 보존하고, 위험 검토·메모 편집을 대체하거나 자동 저장하지 않음. |
| `0e353b1` | 품질검토의 인용이 실제 문장과 맞지 않을 때 동일 초안으로 1회 재검증. 그 외 검증은 완화하지 않음. |
| `11fa92b` | 번역의 통화·단위·Incoterms 등 보호 코드 불일치 문장만 1회 재번역하고 숫자·코드 검증 재수행. 계속 불일치하면 원본 보존. |
| `39bb6eb` | 계약 AI 완료 단계별 소요 시간을 표시. 계약 원문·계정 비밀을 시간 표시 데이터에 넣지 않음. |
| `8beb6c7` | `제3자`/`third party`를 수량 3과 구분하되 법률 표현의 출현 횟수를 별도로 비교해 삭제·추가를 차단. 실제 금액·기한 검증 유지. |
| `ddf4822` | 저장 계약 목록에 언어 표시 `[KR]`/`[EN]` 등을 붙이되 법적 제목은 변경하지 않음. 문장 삭제는 AI 호출 없이 수정안 생성→비교·승인→새 revision 순서이며 기본 커미션 지급 문장은 보호. |
| `da754b7` | FINAL 서명란을 한 번만 출력하고 당사자·대표자·직책·계약 날짜를 저장값에서 구성. 중복 서명 요약만 제외하며 실질 조항은 보존. 직인은 개인 서명을 대체하지 않음. |
| `321e1a7` | 한국어 중복 서명 요약 처리, 제목/조항/본문 18/12/10pt 및 비율을 유지한 10cm 폭 직인 배치. |
| `2f7825e` | PDF/DOCX 글꼴·굵기·간격·정렬 및 서명란 페이지 배치 개선. `packages.txt`에 `fonts-nanum` 추가; 실제 사용 글꼴은 호스트 설치 상태에 따름. |
| `b59f648` | 알려진 대표자 직책만 계약 출력 언어에 맞춰 표기. 임의로 CEO를 추정하지 않고 알 수 없는 직책은 사용자 입력 보존. |
| `f335e9e` | 새 매매 초안의 당사자·브랜드·제품/수량·가격·인도·결제 명세를 저장 조건에서 구성. 제안값은 미확정 표시하고 브랜드·100% 선결제를 추정하지 않음. 품질 보완 때 고정 명세를 보존하며 기존 계약을 자동 재작성하지 않음. |

**앞선 오류 수정 기록:** 출처 형식 복구 `5f5e0e6`, 안내 문자열 문법 수정 `987fd16`, 거래조건 분석의 90→180초 제한 및 시간 초과 메시지 구분 `97a6199`도 포함한다. null/단일 객체를 처리하고 검증 불가 문자열 인용은 확인 이슈로 남기며, 허위 인용은 계속 거부한다.

**로컬 작업본과의 차이:** 이번 점검 당시 사용자 작업본 `a314818`은 원격 기준과 분기되어 있다. 사용자가 추가한 번역 약어 차이 상세 메시지는 그 로컬 커밋의 변경이며, 이 대화에서 관련 19개 테스트와 USD→KRW 차이 표시·원본 보존을 확인했다. 원격에는 이후의 보호 코드 1회 재번역 경로가 있으므로 두 동작을 같은 구현으로 설명하지 않는다. 이번 작업은 문서만 정리하며 실행 코드를 병합하거나 변경하지 않는다.

**검증 범위:** `987fd16`의 498개 및 `97a6199`의 501개 전체 테스트 통과는 각 커밋에서 수행한 과거 결과다. 현재 코드 전체 테스트를 이번 문서 점검에서 다시 실행한 것으로 기록하지 않는다. 원격 `f335e9e`의 GitHub Actions 성공은 확인했다(`42749663125`); 이는 자동 검사 결과이며 배포 완료·운영 계약 분석·최종 날인 화면 성공을 증명하지 않는다. 해당 운영 검증은 미확인이다. 이번 문서 검증은 다섯 README의 변경 범위, 코드/커밋 근거, 링크 대상 및 `git diff --check` 대조로 한정한다.

동기화 보호의 한계: `scripts/check_readme_sync.py`와 로컬 pre-commit 훅은 파일 포함 여부만 검사한다. 훅을 실행하지 않는 원격 작업의 문서 누락이나 내용의 정확성까지 보장하지 않는다. 이번 보완은 누락 이력을 현재 문서에 추가한 것이며 과거 커밋의 동시 갱신 규칙 위반을 소급해 없애지는 않는다.

### 2026-11-10 팀 설명·발표 자료 재점검

- 팀 README에 3분 입문 안내, 쉬운 기술 용어, 가상 거래의 처리 과정과 인수인계 역할을 추가했다. 발표 README에 LangGraph 설명, 준비 계약 중심 5분 시연 순서, FAQ 및 지연 시 대체 순서를 정리했다.
- 발표 대본의 문장 중간에 섞인 Git 명령을 제거하고 현재 계약·무역문서 기능 기준 5분 대본으로 교체했다. 로그인 미구현·437개가 최신 테스트라는 구식 설명 및 임시 서버 가동 주장을 바로잡았다.
- 문서만 수정했다. 발표용 계약·캡처·파일 준비, 실제 낭독 시간 및 운영 시연 성공은 미확인이다. 준비 자료: [팀 안내](Team/README.md), [발표 안내](Presentation/README.md), [발표 대본](Presentation/presentation_script_ko.md).

### 2026-11-10 출처 문자열 복구 최소 수정 (로컬 검증, Push 안 함)

- `analyze_trade()`의 최상위 `source_refs` 문자열은 출처로 인정하지 않고 `[]`로 정규화하며 `unverified_ai_source_ref`/`confirm` 검토사항을 추가한다. `None`과 빈 문자열은 경고 없이 `[]`로 처리한다. 단일 객체는 목록으로 변환한 뒤 원문 인용·문서 ID 검증을 유지한다.
- 문자열을 복구하라는 테스트와 문자열도 예외 처리하라는 기존 테스트의 충돌을 수정 전 보고했다. 문자열 사례는 빈 배열·경고·원본 보존을 검증하는 별도 테스트로 분리했다. 리스트 내부 문자열/None, 허위 인용문, 없는 문서 ID의 ValueError 검증은 유지한다.
- 실행 코드 변경은 출처 문자열 처리 분기로 제한했다. 계약 작성·번역·검토·PDF 경로는 변경하지 않았다. 지정한 두 테스트 파일의 21개 테스트 및 Python 138개 파일의 문법 검사는 통과했다. 전체 `test_contract*.py` 361개(69.003초)와 전체 회귀 586개(168.699초)가 모두 통과했다. 실패·오류·생략은 없으며 기존 Streamlit/PyMuPDF 경고는 남아 있다. GitHub Push와 운영 검증은 수행하지 않았다.


## 2026-11-11 · 개인 후이즈 오케스트레이션 1단계 (별도 PR, 기존 앱 미연동)

[독립 오케스트레이션 README](orchestration/README.md)에 따라 신규 `Quotation_KEKOREA/orchestration/` 내부에 **수동 드라이런** 기반 문서 종류 분류, 별도 Master LangGraph, 기존 PI/PO/CI/PL/계약을 호출하기 전의 어댑터 인터페이스, 검토 첨부 SHA-256 검증, 이메일 재승인 판단의 순수 함수와 격리 테스트를 추가했다. 기존 앱 화면·계약/무역 처리·DB·배포는 변경하지 않았으며 새 코드는 **어떤 메일도 수신·발송하거나 문서 최종 생성/승인하지 않는다**. 실제 후이즈 연결, 문서 어댑터 본연동, SMTP 및 영속 승인 기록은 미구현이다. 테스트 결과는 PR CI를 확인해야 하며 운영 동작으로 오해하면 안 된다.


## 2026-11-11 · 독립 오케스트레이션 Mock UI (후속 브랜치, 미병합)

독립 `orchestration/ui/streamlit_page.py`에서 Streamlit **메일함, 업무 대시보드, 자연어 요청 Mock 라우팅, 문서별 가상 검토/수정, 이메일 초안/승인, 실행 기록** 화면을 구현한다. `workflows/mock_workflow.py`는 샘플 주소 `example.test`만 사용하는 메모리 내 불변 데이터 모델이며 문서 수정 시 이전 승인, 이메일 변경 시 이메일 승인을 무효화한다. **실제 후이즈 POP3/SMTP, 기존 agent/contracts 호출, 실문서 PDF 생성, DB 저장/발송은 모두 미구현**이다. 기존 앱/설정/DB/실거래 경로는 수정하지 않았으며, 해당 독립 화면은 기존 `app.py` 메뉴에 나타나지 않는다. 이 설명은 별도 UI 브랜치가 승인·병합되기 전까지 운영 기능이 아니다.

실행: 저장소 루트에서 `streamlit run Quotation_KEKOREA/orchestration/ui/streamlit_page.py` (Streamlit 설치 환경). 격리 테스트: `python -m unittest discover -s Quotation_KEKOREA/orchestration/tests -v` (Master LangGraph 시험은 langgraph 설치 필요). 실제 Streamlit 화면 렌더링 및 현재 GitHub Actions 실행 결과는 별도로 검증 필요.


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

### 2026-11-11 · MASTER GRAPH 누락정보 입력 위치 및 필드명 오타 보완 (PR #42, 검증 대기)

- 독립 MASTER GRAPH의 AI 업무 요청 화면에서 AI 추출 직후, 조건표보다 먼저 Buyer/Seller 등 부족정보 입력칸을 표시하도록 조정했습니다. 입력은 기존 PI/계약서 후보에 반영하며 이전 검토용 초안은 무효화합니다.
- `buyr`/`byuer`/`seler`/`quantiy` 등 명시적 `항목: 값` 필드 라벨을 보수적으로 정규화하고, AI가 제안한 `buyr` 역할도 Buyer로 인식합니다. 회사명·금액·수량 값은 자동 수정하지 않습니다.
- 코드는 PR 브랜치에 있으며 전체 회귀 테스트·CI·실제 Streamlit 운영 확인 및 병합/배포는 아직 완료되지 않았습니다. 기존 KE KOREA 문서 앱, 직인, 저장된 계약서 및 이메일 발송 기능은 변경하지 않았습니다.

### 2026-11-11 · MASTER GRAPH 로그인 후 시장 뉴스 홈 (PR #42, 검증 대기)

- 로그인 후 첫 화면에 태양광·데이터센터·원자재·증시/거시경제 네 카테고리의 공개 RSS 뉴스 제목과 링크를 제공합니다. KST 오후 6시를 기준으로 이전 18:00부터 로그인 시각까지의 발행시간을 필터링하며 카테고리별 5개씩 최대 5페이지를 제공합니다.
- Google News 공개 RSS 검색 인덱스를 사용합니다. Bloomberg/PV Insights/PV Tech/Investing.com의 직접 구독 API를 연동한 것은 아니며 특정 매체 기사 노출은 보장하지 않습니다. 기사 전문을 저장하거나 재게시하지 않습니다.
- 네트워크 오류 시 빈 결과 대신 오류 안내를 표시합니다. 테스트 코드는 추가했으나 실제 외부 RSS, CI, Streamlit 배포 검증은 아직 수행하지 못했습니다.

## 2026-11-11 MASTER GRAPH 기존 문서 렌더러 연결 (검증 대기)

MASTER GRAPH AI 업무 요청 화면에서 PI/PO/CI/PL의 기존 `agent.trade_documents.validate_and_calculate`, `agent.ci_import.ci_render_data`, `agent.renderers.render_files` 및 `agent.branding.resolve_company_seal`을 직접 호출하여 PDF/XLSX/HTML DRAFT 다운로드를 제공한다. 기존 업무 에이전트로 이동하는 링크는 제거했다. 기존 PDF의 직인 검증, 페이지 분할, PI 은행정보 6항목 및 문서별 필수정보 차단은 유지한다. 계약서 검토용 PDF/DOCX는 기존 `contracts.draft_exports.export_draft` 경로를 유지한다. 계약서 FINAL 내보내기는 기존 승인·법률 검증을 우회해 제공하지 않는다. MASTER 전용 연결 파일은 `orchestration/workflows/legacy_document_exports.py`, UI는 `orchestration/ui/ai_intake_page.py`, 테스트는 `tests/test_master_legacy_exports.py`이다. 이 변경은 코드 구현이며 실제 Streamlit 실행·전체 회귀·운영 배포 검증을 완료했다는 뜻이 아니다.


## 2026-11-13 · Master 실행 로그 및 AI 모니터링

Master 관리자 모니터링 메뉴에 JSON 실행 로그, 모델별 호출/응답시간/성공·실패율/입출력 토큰/예상 USD 비용/오류 및 기존 재시도 집계를 추가했습니다. 메일·계약 내용, 개인정보와 비밀키는 수집하지 않습니다. 기존 계약서 및 PI/PO/CI/PL 서식·직인·메일 동작은 유지하며 Audit Log는 추가하지 않습니다. Supabase 서버 전용 테이블에 30일 보관하고 매시간 만료 기록을 삭제합니다. 저장 장애는 기존 업무를 중단하지 않으며 임시 데이터/누락을 화면에 표시합니다.

구현/검증/배포 범위는 [운영 안내](../docs/master-observability-20261113.md)를 참조하세요. 운영 로그인 화면은 확인했으며 배포 후 관리자 실화면 확인은 인증 만료로 아직 미확인입니다.

검증: 외부 통신을 차단한 전체 851개 테스트(계약/무역문서 677 + Master 174) 통과, 신규 모니터링 27개 포함. 비공개 자료는 커밋에서 제외했습니다.


## 2026-11-13 · 선택 메일에서 문서 준비

메일함의 **AI로 거래조건 추출·문서 준비** 버튼으로 선택 메일 제목·본문과 직접 선택한 첨부를 처리하고 AI 업무 요청으로 이동해 문서 후보를 채웁니다. 기존 복사 전용 버튼도 유지합니다. PI/견적서·PO·계약서·CIPL(CI+PL)을 인식하고 전체 품목·포장 데이터를 보존하며 누락 사실을 보완할 수 있습니다. 원본 PI·수량·출하·배송지·검토 규칙과 기존 서식/직인을 유지합니다. 열람·동기화만으로 AI 실행이나 실제 발송/최종 발행을 하지 않습니다.

160개 가상 메일과 가상 AI HTTP 응답으로 연결/원문/금액 검증 테스트를 추가했습니다. 실제 모델 정확도 시험과 운영 실화면 확인은 구분하며, Google 인증이 차단된 운영 검증은 미확인입니다. 상세 내용: `docs/master-mail-document-intake-20261113.md` (저장소 루트 기준).

검증: 외부 통신을 차단한 전체 1,030개 테스트 통과(계약/문서 678 + Master 352, 실패/스킵 0). 160개 가상 메일은 가상 AI HTTP 응답으로 전달·원문·계산·보호 규칙을 검증한 것이며 실제 모델 성능 수치를 뜻하지 않습니다.


### 2026-11-13 · Master 메일 MoU 인식 및 수동 문서 종류 선택
- BIPV MoU/M.O.U./Memorandum of Understanding/양해각서(줄바꿈 포함)를 기존 CONTRACT 후보 추출로 연결합니다. MoU 전용 법률 문서 생성기는 추가하지 않았으며, AI 원문은 정규화하지 않고 그대로 전달합니다.
- 자동 분류가 실패해도 본문이 있는 메일은 사용자가 메일 화면에서 PI/PO/CI/PL/CONTRACT를 선택해 AI 업무 요청에 전달할 수 있습니다. 추출은 명시적인 버튼·동의가 있어야 실행되며 자동 발송·승인은 없습니다.
- M.O.U.의 끝 마침표는 부정 명령과 다음 문서 요청을 분리하도록 보존합니다. 과거 인용 메일을 새 문서 요청으로 취급하지 않습니다.
- 관련 테스트: `Quotation_KEKOREA/orchestration/tests/test_mail_mou.py`. 합성 데이터 테스트/CI와 운영 화면의 사용자 인증·실제 AI 응답 검증은 별개입니다.
- 기존 계약서·PI/PO/CI/PL 서식, 직인, 가격·수량 및 최종 승인 검증 규칙은 수정하지 않았습니다.


### 2026-11-13 · Master 메일 POP3 RETR 조회 오류 복구
- 후이즈 POP3에서 본문 RETR 조회가 실패하면 실패 메일의 UID를 한 번만 새 TLS 로그인 세션에서 재조회합니다. 재접속 후 UIDL·LIST를 갱신해 변경된 POP3 메시지 번호를 잘못 사용하지 않습니다.
- RETR 실패를 발신자·제목·본문 없는 가짜 메일로 표시하거나 기존 정상 캐시를 덮어쓰지 않습니다. 모두 실패하면 원문/비밀번호를 노출하지 않는 안내를 표시하고 마지막 정상 메일을 보존합니다.
- 실제 메일 삭제·변경, 자동 발송·AI 실행, 인증·권한 정책, PI/PO/CI/PL/계약서 서식·직인·검증 규칙은 변경하지 않았습니다.
- 합성 POP3 서버 응답과 Streamlit 캐시 회귀 테스트를 추가했습니다. 실제 후이즈 RETR 실패 원인은 운영 서버 응답 코드·로그 없이 확정하지 않습니다. GitHub CI 성공은 로그인된 운영 앱의 실제 수신 성공을 의미하지 않습니다.


### 2026-11-13 · POP3 수신계정 확인 및 0건 원인 진단
- 로그인된 회사 메일함 소유자에게만 현재 `WHOIS_POP_USERNAME` 설정값을 표시하고, 요청한 `david.ihm@ke-korea.com`과 일치하는지 안내합니다. 실제 비밀번호와 서버 원문은 표시하지 않습니다.
- 소유자가 누르는 읽기 전용 POP3 상세 진단은 UIDL 메일 건수, LIST 건수, 최신 메일 RETR 성공·거부·타임아웃 구분 및 크기 정책만 표시합니다. 실제 메일 본문/UID/첨부는 표시·저장·로그하지 않으며 발송·삭제하지 않습니다.
- '마지막 조회 성공'의 모호한 문구를 동기화 완료 시간과 표시 가능한 메일 건수로 구분하고, 0건이면 상세 진단을 안내합니다. 로그인 인증 성공만으로 본문 수신 성공을 보증하지 않습니다.
- 외부 후이즈 서버 원인과 실제 Secrets의 계정 설정값은 운영 인증 화면에서만 확인 가능합니다. 합성 테스트와 GitHub CI는 실제 운영 메일 수신 검증을 대신하지 않습니다.


### 2026-11-13 · POP3 상세 진단 ImportError / Streamlit Hot Reload 복구
- Streamlit 프로세스가 오래된 후이즈 메일 어댑터를 캐시에 유지할 때 SMTP 버전뿐 아니라 POP3 진단 버전과 `probe_pop_diagnostics` 함수 존재 여부를 검증하고 필요할 때만 모듈을 다시 로딩합니다.
- 진단 함수가 여전히 없다면 ImportError로 전체 메일함을 중단하지 않고 앱 재시작 안내를 표시합니다. 메일 계정·비밀번호·인증 정보는 변경하거나 출력하지 않습니다.
- 수신계정 `david.ihm@ke-korea.com`은 운영 화면에서 설정 문자열이 확인되었으며 실제 POP3 RETR 성공은 진단 실행으로 별도 확인해야 합니다. 계약서·PI/PO/CI/PL/직인/승인 규칙은 변경하지 않습니다.
- 회귀 테스트는 오래된 POP3 버전 및 진단 함수 누락 상황의 모듈 재로딩을 검증합니다. 실제 운영 화면/후이즈 서버 연결은 별도로 확인해야 합니다.


### 2026-11-13 · POP3 본문 거부 교차 진단 (실서버 결과와 분리)
- PR #74 이전과 PR #76 직후의 수신 메서드를 대조해 `_pop`, `UIDL`, `LIST`, `RETR`, `QUIT` 흐름에 직접적인 변경이 없음을 확인했습니다. #74는 `mail.collect` 로깅 데코레이터만 추가했고, #75~#76의 메일 변경은 UI·AI 요청 연결 위주입니다. #77부터 재접속·재시도 로직이 변경되었습니다.
- UIDL/LIST 성공과 RETR 거부를 구분하기 위해 소유자 클릭으로만 실행되는 POP3 교차 진단을 추가했습니다. 최신·중간·오래된 최대 3개 메일을 각자 새 TLS 세션에서 번호 재조회 후 RETR 본문 및 선택적인 TOP 헤더 조회만 검사합니다. 서버 응답·UID·본문·첨부·계정 비밀번호를 표시·저장·로그하지 않습니다.
- POP3 TOP 지원은 선택사항이며 TOP 거부가 RETR 실패를 뜻하지 않습니다. 새 진단의 합성 테스트 통과는 실제 후이즈 서버 테스트가 아닙니다. 설정 변경·메일 전송·삭제·AI 자동 실행·기존 문서서식 변경은 없습니다.


### 2026-11-13 · 최근 메일 RETR 거부 시 정상 메일 복구
- 운영 화면에서 POP3 UIDL/LIST 18건, 최신 메일 RETR `server_rejected`, 중간·오래된 메일 RETR `success` 확인. 특정 최신 메일의 본문 조회 거부가 전체 수신함 장애를 뜻하지 않으며 구체적 서버 거부 사유는 아직 미확인입니다.
- 메일 자동 수신은 첫 5개에서 전부 실패할 경우 오래된 정상 메일을 조회하지 않는 구조였으므로, 기존 최근 메일 조회를 우선 유지하되 실패 UID 재접속에서는 오래된 메시지부터 확인하도록 조정했습니다. 최근 5건이 모두 불가할 때만 최대 3개의 더 오래된 UID를 각각 독립 TLS 연결로 확인해 복구합니다. 정상 본문 없이 성공했다고 표시하지 않습니다.
- 복구 조회는 UIDL 재확인 후 RETR만 수행하고 메일 삭제·변경·발송을 하지 않으며 원문/UID/서버 예외/비밀번호를 로그나 GitHub에 기록하지 않습니다. 합성 POP3 회귀 테스트로 최신 메일 거부 및 오래된 메일 복구를 검증합니다.
- POP3 설정·Google OAuth·기존 계약서/PI/PO/CI/PL 서식·직인·가격/수량·승인 규칙 변경 없음. 실제 후이즈 수신 성공과 운영 화면 반영은 별도 확인이 필요합니다.


### 2026-11-13 · POP3 최신 수신 코드 핫리로드 검증
- PR #81에서는 최신 메일 RETR가 실패할 때 이전 정상 메일을 조회하는 `fetch_messages`가 변경되었지만 어댑터 버전 `POP_DIAGNOSTIC_REVISION`이 v3 그대로여서, Streamlit의 유지 중인 Python 세션에서는 기존 함수를 그대로 재사용할 수 있었습니다.
- 버전을 v4로 올리고 `POP_FETCH_REVISION = pop-fetch-older-fallback-20261113-v1`을 추가해 모듈 캐시 검사에 포함했습니다. 실행 중 UI에는 POP3 모듈 버전·수신 함수 버전·함수 연결 상태가 표시됩니다.
- 오래된 모듈이면 재로딩하고 수신 함수를 다시 연결하되 계정·비밀번호·Google OAuth·메일 데이터와 기존 문서 서식·직인·승인 규칙은 변경하지 않습니다.
- 모듈 교체를 검증하는 합성 테스트와 GitHub CI는 운영 후이즈 서버의 RETR 성공을 보장하지 않습니다. 교차 진단에서 최신 메일 1건의 RETR 거부는 여전히 발생할 수 있으며, 메일함 동기화 결과를 따로 확인해야 합니다.


### 2026-11-13 · 메일함 AI 업무 요청 버튼의 화면 전환 복구
- 메일함 `@st.fragment(run_every='60s')` 내부에서 `on_click` 콜백으로 사이드바 `master_page` 라디오 값을 변경해도 전체 Streamlit 앱이 리런되지 않아 'AI로 거래조건 추출·문서 준비' 및 '이 메일로 AI 업무 요청 작성' 버튼을 눌러도 화면이 전환되지 않을 수 있었습니다.
- 이제 두 버튼은 Fragment에서 메일 원문·선택한 문서 종류·선택 첨부를 세션 상태에 기록하고, 이동 의사를 임시 플래그로 남긴 다음 `st.rerun(scope='app')`으로 앱 전체를 다시 실행합니다. 전체 앱 시작 시 사이드바 라디오가 만들어지기 **전**에 플래그를 한 번 소비해 'AI 업무 요청'으로 이동합니다. 기존 메일 동기화의 60초 Fragment는 유지합니다.
- 자동 추출 버튼은 기존 동의·모델 설정·문서 검증을 거쳐 요청을 한 번만 처리하며, '이 메일로 AI 업무 요청 작성' 버튼은 동의를 자동으로 허용하거나 AI 호출을 시작하지 않습니다. 기존 PI/PO/CI/PL/계약서 템플릿, 직인, 가격·수량, 승인 규칙은 변경하지 않았습니다.
- 외부 AI 호출은 실제 사용자 동의/운영 모델 설정이 필요하고 GitHub UI 테스트는 합성 메일만 사용합니다. AI 모델의 실제 정확도/실서버 처리 성공은 자동 테스트만으로 보장되지 않습니다.


### 2026-11-13 · Streamlit 메일 → AI 전환 후 ImportError 긴급 복구
- PR #83에서 앱 시작 시 새 `consume_mail_navigation` 함수를 필수 import했지만 Streamlit이 이전 `mail_intake` 모듈을 캐시하면 ImportError로 Master 전체가 열리지 않았습니다. 이번 변경은 해당 시작 단계 의존성을 없애고, 세션 이동 플래그를 `master_page` 라디오 생성 전에 직접 소비합니다.
- 메일함 버튼 클릭 때만 `queue_handoff`의 `navigate` 지원 여부를 확인하고, 구버전이면 모듈을 갱신해 재연결합니다. 갱신이 불가능하면 비밀정보를 포함하지 않는 안내를 표시하고 전체 앱을 중단하지 않습니다. 실패 시 AI 자동 호출이나 페이지 강제 이동을 실행하지 않습니다.
- 합성 UI 회귀 테스트에 구버전 함수 누락 상태의 앱 시작과 구버전 콜백 재로딩을 추가했습니다. 실제 메일·첨부·OAuth/SMTP/POP3 Secret, 문서 서식·직인·가격·승인 정책은 변경하지 않습니다.


### 2026-11-13 · 메일함 AI 업무 요청 버튼 통합
- 메일함의 `AI로 거래조건 추출·문서 준비`와 `이 메일로 AI 업무 요청 작성` 두 버튼을 `AI 업무 요청으로 이동` 하나로 통합했습니다. 메일 제목·본문, 사용자가 선택한 문서 종류(PI/PO/CI/PL/CONTRACT), 명시적으로 선택한 첨부만 같은 세션의 AI 업무 요청 화면으로 전달하며, 이동만으로 외부 AI를 호출하거나 AI 동의를 자동으로 승인하지 않습니다.
- AI 업무 요청 화면에서는 `AI 자동 분석`과 `직접 수정 후 분석`을 선택합니다. 기본값은 `직접 수정 후 분석`이며 메일 본문을 수정할 수 있습니다. 자동 분석 모드는 요청 입력창을 읽기 전용으로 두고, 두 모드 모두 기존 동의 체크박스와 명시적인 실행 버튼이 있어야 AI 분석을 시작합니다.
- 문서 종류 미인식 메일도 AI 업무 요청으로 이동해 문서 종류를 사용자가 선택할 수 있습니다. MoU는 기존 CONTRACT 후보로 전달되며 MoU 전용 생성기는 새로 추가하지 않습니다. 이전 버전의 자동 실행 예약 토큰은 소비만 하고 자동 AI 호출하지 않습니다.
- 메일 POP3 수신/동기화, Google OAuth, 계약서·PI·PO·CI·PL 서식, 직인, 가격/수량 검증, 승인/발송 정책은 변경하지 않았습니다. CI 테스트는 합성 메일/가상 모델만 사용하고 실제 메일과 개인정보를 외부 테스트 API나 GitHub로 보내지 않습니다.


### 2026-11-13 · AI 업무 요청 단일 거래정보 입력과 미확정 PDF 다운로드
- 실제 메일로부터 AI가 분석한 후보의 Buyer/Seller 이름·주소·통화 등이 세 군데(미확정 정보 보완, 거래조건 직접 수정, PDF 필수정보 입력)로 나뉘고 서로 다른 상태를 갱신하던 중복 UI를 제거했습니다. `AI 업무 요청`의 한 입력 카드에서 회사명·주소·통화·인도/결제조건·문서번호·품목별 수량/단가·선적/원산지 등을 변경하면 Enter/포커스 이동에 `apply_answer`로 PI/PO/CI/PL 및 계약서 후보에 동기화하고, 변경 즉시 오래된 검토 파일·PDF 다운로드를 무효화합니다. 추가 품목도 동일 입력 영역에서 수정하며, 원본 AI 추출정보와 검증 경고는 별도 접힌 참고 영역에 표시합니다.
- 수정된 거래조건은 고급 JSON 편집의 기본값, 문서 후보 미리보기, 기존 KE KOREA 문서 렌더러의 입력에 동일하게 사용됩니다. 문서번호나 값을 모를 경우 빈칸으로 두어도 되고, 명시적으로 지운 수량은 0으로 간주하거나 오래된 유료수량에서 되살리지 않도록 처리합니다. 숫자·상대방 확인이 끝난 것처럼 자동 승인하지 않습니다.
- PDF 생성 버튼은 발행 검증을 통과하면 기존 로고·직인·은행정보·페이지 분할을 포함한 기존 DRAFT 양식을 사용합니다. 한 항목이라도 미확정이거나 직인/은행정보 검증에 실패하면, 기존 정식 양식/최종 발행을 우회하는 대신 **미확정 사항이 눈에 띄게 표시된 직인 없는 별도의 내부 검토용 PDF 파일**을 제공합니다. 이는 내려받을 수 있는 PDF이지만 FINAL 발행본, 결제청구서, 계약 체결본이 아니며 `final=False`, `sendable=False`입니다. 확인되지 않은 금액은 0.00으로 계산하지 않고 미입력으로 표시합니다.
- Google OAuth, POP3/SMTP 메일 수신·발송, 기존 검증·승인 규칙, 직인 저장소, 원본 템플릿 파일은 변경하지 않았습니다. 모든 테스트 입력은 합성 자료이며 실메일/고객정보/첨부를 CI에 제공하지 않습니다. 실제 운영 Streamlit 화면은 별도 확인이 필요합니다.


### 2026-11-13 · Master AI 업무 요청 AttributeError 긴급 복구 (Buyer/Seller 데이터 타입)
- PR #86 이후, AI 후보 또는 기존 Streamlit 세션에서 `seller`/`buyer`가 `{'legal_name', 'address'}` 객체가 아닌 회사명 문자열이나 비정상 타입일 때 `validate_and_calculate(...).get()` 호출이 `AttributeError`로 중단되는 문제가 확인됐습니다.
- 오케스트레이션 데이터 정규화 단계에서 `seller`/`buyer` 문자열은 실제 입력된 회사명으로만 보존하고 주소는 비워 둡니다. 누락/비문자 형태는 확인되지 않은 값으로 남겨 기존 발행 검증에서 차단합니다. 사용자가 단일 입력창을 수정할 때에도 전체 문서 후보를 안전하게 정규화합니다.
- 이전 배포에서 남은 세션의 PI/PO/CI/PL 후보는 렌더링·검증·PDF 생성 전에 in-memory 교정하여 앱이 중단되지 않도록 했습니다. 이때 미확정 정보를 임의 승인하거나 직인/은행정보 검증을 우회하지 않습니다. 추가 UI 방어에서 잘못된 필드 형식은 검토 안내로 표시됩니다.
- 합성 데이터 회귀 테스트에 문자열 Seller/Buyer, 여러 문서에 서로 다른 당사자 타입, 주소 보완 반영, 이전 세션 복구와 미확정 PDF 다운로드를 추가했습니다. OAuth/POP3/SMTP, 원본 PI·PO·CI·PL 렌더러, 계약서 엔진, 발행 정책은 변경하지 않았습니다. 운영 실화면 검증은 별도입니다.
