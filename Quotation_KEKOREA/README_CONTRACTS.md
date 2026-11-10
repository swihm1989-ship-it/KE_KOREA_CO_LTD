# Contract workspace

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
- 미확정 조건이 있더라도 검토용 DRAFT PDF/DOCX는 생성할 수 있다. FINAL PDF/DOCX는 변경하지 않은 기존 `validate_rules(..., for_export=True)` 결과에 따라 차단될 수 있다. UI를 숨기거나 TBD를 선택하는 것이 법적/거래조건 확인을 의미하지는 않는다.
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
- DRAFT PDF/DOCX: 문장에 연결된 미확정 후보가 **값을 이미 보유한 경우** 중복 `[확인 필요]` 접두어 대신 미확정 부록과 DRAFT 경고로 관리한다. 실제 값이 빠진 연결 조항에는 계속 표시한다. 본문의 기존 `[서명 전 확인]`은 삭제하지 않는다.
- FINAL PDF/DOCX: 서명 전 확인/TBD 등 명시적 미확정 표시가 본문에 남으면 기존 필수조건 검증에 더해 차단한다. Supabase 저장·다운로드, 법률/결제 검증과 Revision 흐름은 변경하지 않는다.
- 수정사항 테스트: `Quotation_KEKOREA.tests.test_contract_integrity_fix`. 전체 회귀 및 실제 배포 파일 생성은 별개로 검증한다.

### 2026-11-09 신규 계약서 초안 품질 파이프라인

- 기존 BOX 1·2·3 화면, 버튼, 대화 흐름(`flow.py`), 문장별 메모·비교·승인·revision 저장, PDF/DOCX 및 FINAL 검증은 유지합니다. 기존 두 초안 생성 진입점의 내부 연결만 새 `contracts/drafting.py`로 교체합니다. 저장된 조항이 있는 계약은 자동 재작성하지 않습니다.
- 내부 순서: 거래조건 정리 → 계약 유형별 조항 목차/작성 기준 구성 → 조항별 참고자료 검색 → 상세 작성 → 누락·충돌 검사 → 필요 시 1회 보완·재검사 → 기존 화면에서 사용자 검토. 매매계약은 13개, 커미션 계약은 12개 주제의 기본 기준을 사용하며, 사용자가 명시적으로 승인한 준거법·분쟁 해결 제외 결정은 존중합니다.
- 선택한 첨부자료는 앞 12,000자에 한정하지 않고 전체 추출 텍스트에서 문단/페이지 경계를 잇는 구간을 검색합니다. 주제별 최대 3개 새 구간, 최종 발췌 합계 최대 100,000자로 제한합니다. 거래조건 분석 단계의 기존 12,000자 제한은 유지되며, 상세 초안 작성의 검색 범위만 확장됩니다.
- 공통 라이브러리는 기존 사용 선택을 따릅니다. 승인·활성·계약 유형 필터를 유지하고, 한 번 조회한 레코드에서 주제별 키워드 검색을 수행합니다. 이 추가 검색은 임베딩 API를 호출하지 않습니다. 비공개 원본이나 미승인 참고 메모를 공통 검색에 넣지 않습니다.
- 불가항력은 발생 요건·통지·완화 노력·이행 재개·장기화 시 처리를 포함하도록 지시합니다. 다른 조항에도 업무 범위, 지급, 기간, 해지, 책임, 비밀유지, 통지, 준거법, 분쟁 해결, 일반 조항 등의 구성요소 기준을 적용합니다. 계약 유형에 따라 인도·검수 또는 커미션 대상 거래·성공·증빙을 추가합니다.
- 별도 AI 품질 검사는 모든 계획 주제와 실제 생성된 모든 조항을 확인해야 합니다. 구성요소별 문장 ID·정확한 인용 근거를 검증합니다. 단순 제목이나 길이만으로 완성도를 판정하지 않습니다. 문장 근거가 없는 검사 결과나 허위 인용으로 완료 처리하지 않습니다.
- 보완은 지적된 조항과 완전히 빠진 주제로 한정합니다. 무관한 조항·기존 문장 ID·확정 거래조건을 보존하며 기본 커미션 지급 조항은 AI가 수정하지 않습니다. 최종 검사는 기존 지급정책 적용 후의 실제 본문을 대상으로 합니다. 남은 문제는 미확정 검토 항목으로 전달합니다.
- 신규 생성 내부의 생성/검사 API 호출은 보통 2회, 보완 시 최대 4회이며 보완 반복은 1회입니다. 요청별 타임아웃 최대 60초, 내부 경과시간 예산 180초를 적용합니다. 타임아웃·잘못된 검사 결과·허위 출처·범위 밖 수정은 중간 초안을 저장하지 않고 실패 처리합니다. 네트워크 시간 제한은 즉시 취소를 보장하는 UI 타이머가 아닙니다. 기존 거래조건 분석/검색 호출은 이 횟수와 별도입니다. 모델은 자동 변경하지 않습니다.
- 참고 계약의 금액·기한·책임한도·준거법은 합의값으로 자동 채택하지 않도록 작성/검사 지침을 둡니다. 미합의 항목은 확인 표시로 남깁니다. AI의 의미 판단과 법적 적정성을 결정적으로 보장하는 검증은 아니므로 최종 사용자 검토가 필요합니다.
- 검증: 가상 API 응답을 사용하는 새 핵심 테스트 15개 통과. 최종 전체 회귀 테스트 437개가 109.838초에 모두 통과했습니다(화면 테스트 포함, 생략 없음). `git diff --check`도 통과했습니다. 기존 Streamlit/PyMuPDF 경고는 남아 있습니다. 실제 모델 응답의 문장 품질·실제 Streamlit 배포·실제 거래자료 전송은 이번 로컬 검증에 포함하지 않습니다.


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
