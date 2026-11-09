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
