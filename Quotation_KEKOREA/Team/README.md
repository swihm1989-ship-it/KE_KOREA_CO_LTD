# KE KOREA Quotation App — 팀 공유 안내

**기준일: 2026-11-05**  
이 문서는 현재 저장소의 코드와 테스트를 기준으로 구현, 데이터 흐름, 오류 개선 내역 및 새 에이전트의 연동 원칙을 요약합니다. 기존 [README.md](../README.md)는 설계·변경·검증의 상세 기록이며, 실제 변경 시에는 [AGENTS.md](../AGENTS.md)의 보호 규칙과 코드를 우선 확인하세요. 이 문서는 배포 상태나 외부 서비스의 현재 가동을 보증하지 않습니다.

## 1. 한눈에 보기

Streamlit 앱에서 사용자가 PO(구매주문서), PI(견적/Proforma Invoice), CI(Commercial Invoice), PL(Packing List), CIPL을 선택하고 텍스트 또는 이미지/PDF를 입력하면, 추출된 거래 초안을 검토·수정한 뒤 PDF/Excel 파일로 다운로드합니다. CIPL은 동일 거래 정보로 CI와 PL 초안을 함께 만듭니다.

```text
사용자 입력·첨부 → 파일 검증/PDF 페이지 처리 → OpenAI 구조화 추출
 → 근거·누락·충돌 검토 → 제품/거래처 확인 및 가격 조회
 → Decimal 기반 계산·필수 검토 → PDF/Excel 초안 다운로드
```

**자동 발주·송장 발행·이메일 발송은 하지 않습니다.** 결과는 검토용 초안이고, 문서 번호 발급이나 영구적인 배송/재고 시스템 연동도 구현 범위가 아닙니다.

## 2. 기능과 안전 장치

### 입력과 정보 추출

- 텍스트와 PNG/JPG/JPEG/WEBP/PDF를 지원합니다. 최대 5개, 파일당 10 MB, 합계 20 MB입니다.
- 사용자가 추출을 실행할 때 첨부 파일과 요청 문맥을 OpenAI Responses API에 전송하고 정해진 구조의 JSON 초안을 받습니다. 근거 인용, 미확인 필드, 충돌 정보를 함께 검토합니다.
- PDF는 PyMuPDF로 모든 페이지를 처리합니다. 페이지에 텍스트가 충분하면 텍스트도 추출하고, 텍스트가 적은 페이지는 이미지로 렌더링해 스캔 문서 인식에 보탭니다. 원본 PDF도 추출 요청에 포함합니다.
- 추출은 후보 초안을 만들 뿐입니다. 문서 내용은 지시로 실행하지 않으며, 필수 정보나 가격 근거가 부족하면 사용자가 확인할 때까지 내보내기를 막습니다.

### 상품·가격 식별

- [product_matching.py](../agent/product_matching.py)는 이름, SKU/코드, 용량·단위·입수량 등 식별 근거를 정규화해 유사 후보를 찾습니다. 유사도만으로 가격을 확정하지 않으며, SKU·제품 변형·용량 충돌은 자동 매칭을 막습니다.
- 유일하고 호환되는 후보가 90% 이상이면 가격 후보를 불러오되 **Double-check/확인**을 거쳐야 합니다. 68% 이상~90% 미만은 후보만 제시하고 자동 가격을 붙이지 않습니다. 그보다 낮거나 충돌하면 미확정으로 둡니다.
- 사용자는 미확정 제품명을 직접 입력할 수 있습니다. 해당 이름은 초안/출력에 보존하고, 카탈로그로 확인되지 않은 제품에는 카탈로그 가격을 임의로 적용하지 않습니다.
- 현재는 외부 벡터 DB/임베딩을 사용하지 않습니다. 작은 카탈로그의 SKU·용량 제약을 보존하는 결정론적 비교를 우선합니다. 향후 벡터 검색은 후보 제안에만 보조적으로 사용하고 가격 확정 근거를 대체하지 않아야 합니다.
- [pricing.py](../agent/pricing.py)는 문서 역할, 거래처, 제품 식별 및 통화를 함께 확인합니다. ECLADO 매입/PO와 Dear Glow 판매/PI·CI 가격은 구분되며, CI가 PI에서 가져온 거래이면 원본의 확정 거래 금액을 보존하고 재가격하지 않습니다. Supabase 오류나 잘못된 자격 증명에 오래된 가격을 성공처럼 적용하지 않습니다.

### 문서 계산·검토·출력

- [trade_documents.py](../agent/trade_documents.py)는 수량·단가·통화·금액 계산을 Decimal로 수행합니다. 비어 있는 수량과 명시적 0은 다릅니다. 명시된 0 수량은 행과 0 금액으로 유지합니다.
- [promotions.py](../agent/promotions.py)는 PI/PO 기존 행에 명시된 Buy-N-Get-M 행사를 적용합니다. 유상 수량·FOC 수량·출고 수량을 나누며, 증정분에 금액을 중복 부과하지 않습니다.
- 샘플 PI 행은 거래별 수동 입력이며 카탈로그 가격·일반 할인·행사로 덮어쓰지 않습니다.
- [packing_review.py](../agent/packing_review.py)는 공급처 포장 합계와 계산 합계를 비교합니다. 단위는 구분하고, 사용자가 승인하기 전에는 합계를 수정하지 않으며 컨테이너 정보를 추측하지 않습니다.
- [ci_import.py](../agent/ci_import.py)는 첨부 PI에서 CI 초안을 준비할 때 가격·수량 근거를 보존하고 은행/결제 정보를 제외합니다.
- 필수 누락, 근거 없는 값, 미확정 제품 및 계산 충돌은 검토 화면에서 해결해야 합니다. PI에만 KE KOREA 은행정보를 출력합니다.
- [renderers.py](../agent/renderers.py)와 [pi_pdf.py](../agent/pi_pdf.py)는 PDF/Excel 문서와 레이아웃을 생성합니다. HTML 렌더러도 코드에 있으나 앱 다운로드 선택지는 PDF/Excel입니다.

## 3. 코드 구조 및 데이터 경계

| 위치 | 책임 |
| --- | --- |
| [app.py](../app.py) | Streamlit 메뉴/UI, 추출·검토·내보내기 연결, Supabase 로딩, 세션 작업 관리 |
| [agent/attachments.py](../agent/attachments.py), [agent/extractor.py](../agent/extractor.py) | 파일 제한·PDF 전처리·OpenAI 입력 및 구조화 추출 |
| [agent/product_matching.py](../agent/product_matching.py), [agent/pricing.py](../agent/pricing.py) | 제품 후보와 역할·통화별 카탈로그 가격 |
| [agent/counterparties.py](../agent/counterparties.py), [agent/workflow_state.py](../agent/workflow_state.py) | 거래처 보완 정보 및 메뉴별 브라우저 세션 상태 |
| [agent/trade_documents.py](../agent/trade_documents.py), [agent/promotions.py](../agent/promotions.py), [agent/packing.py](../agent/packing.py), [agent/packing_review.py](../agent/packing_review.py) | 금액·행사·포장 계산 및 승인 |
| [agent/ci_import.py](../agent/ci_import.py), [agent/review_fields.py](../agent/review_fields.py) | PI→CI 준비 및 필수 항목 검토 |
| [agent/renderers.py](../agent/renderers.py), [agent/pi_pdf.py](../agent/pi_pdf.py), [agent/branding.py](../agent/branding.py), [agent/seal_storage.py](../agent/seal_storage.py) | 문서 파일·브랜드·비공개 회사 직인 |
| [supabase/migrations/](../supabase/migrations/), [supabase/README.md](../supabase/README.md) | Supabase 테이블, 접근 정책, 적용 및 검증 안내 |
| [tests/](../tests/) | 매칭·가격·계산·UI 상태·첨부·PDF·출력 회귀 테스트 |

Supabase 가격 테이블은 제품, 수입 스냅샷, 매입가 및 구매자 판매가를 분리합니다. 거래처 디렉터리는 별도 마이그레이션/로더를 사용합니다. 앱은 서버 측 키로 REST API를 호출합니다. 회사 직인은 비공개 Storage에서 내려받아 기대 SHA-256과 대조합니다. 실제 가격표/연락처/비밀키는 소스·공개 README·테스트에 복사하지 마세요. 자세한 SQL 적용·비공개 시드 절차는 [Supabase 안내](../supabase/README.md)를 따릅니다.

`workflow_state.py`의 초안 상태는 현재 브라우저 세션 범위이며 브라우저/서버 재시작을 넘어 영구 저장되지 않습니다. 메뉴 간 이동 시에는 각 문서의 입력·첨부·진행 중 작업을 분리해 보존합니다.

## 4. 오류를 어떻게 찾아 고쳤는가

아래는 저장소의 재현·수정 기록에서 확인되는 대표 사례입니다. **PDF의 특정 사용자 파일이 실패한 정확한 원인은 그 파일이 없어 확정하지 않았습니다.** 현재 추가된 PDF 경로는 해당 입력군을 보강한 것이며, 모든 스캔/손상/암호화 PDF의 인식을 보장하지 않습니다.

| 증상 | 확인한 원인 또는 한계 | 수정·오류 처리 | 회귀 검증 |
| --- | --- | --- | --- |
| 주문의 상품 가격이 다수 누락됨 | 일부 주문은 `Code` 열 값이 상품명 괄호에 붙어 있어 문자열 동일 비교가 실패했습니다. | 코드와 이름을 분리하고 구두점·공백·용량 표기를 안전하게 정규화했습니다. 불일치 행만 검토 대상으로 남깁니다. | `test_product_matching.py`, 가격 및 UI 테스트 |
| 한 행이 미확정일 때 맞는 행의 가격도 누락됨 | 제품 분류가 미확정인 PI/CI에서 부분 일치를 보완하지 않는 경로가 있었습니다. | 거래처·문서 역할·통화를 확인한 후 일치한 행만 가격 조회하고 나머지는 보류합니다. | `test_sale_partial_catalog.py` |
| 비슷한 오타 제품을 자동으로 잘못 확정할 위험 | OCR 유사도만으로는 다른 용량/SKU/제품 변형을 구분할 수 없습니다. | 호환성 제약과 점수 구간을 두고, 중간 점수는 후보만, 높은 점수도 사용자 확인 후 사용합니다. 직접 입력 제품명은 보존합니다. | `test_product_matching.py`, `test_product_matching_ui.py` |
| PDF 업로드에서 텍스트가 안 읽히거나 추출 오류 | PDF는 원본 파일 입력 경로가 있었지만 스캔 페이지 텍스트를 앱에서 별도 추출하는 경로가 부족했습니다. 특정 오류 파일은 확보하지 못해 과거 오류 원인을 단정할 수 없습니다. | PDF 헤더/크기 등 입력 검증, PyMuPDF 페이지별 텍스트 처리, 텍스트가 적은 페이지 이미지 렌더링, API 응답 제한 등의 구체적 오류 안내를 추가했습니다. | `test_pdf_inputs.py`, `test_extractor.py` |
| 메뉴를 이동한 뒤 입력/완료 작업이 사라지거나 오래된 결과가 덮어씀 | 공용 Streamlit 상태와 비동기 작업이 메뉴별 생명주기를 충분히 분리하지 못했습니다. | 메뉴별 상태와 작업 스냅샷을 분리하고 오래된 결과·중복 제출을 막으며 오류 후 재시도를 허용합니다. | `test_workflow_state.py`, `test_workflow_ui.py` |
| 수량이 0인데 계산이 막히거나 값이 누락됨 | `0`을 미입력으로 취급하면 유효한 명시적 0과 `None`을 구별하지 못합니다. | `None`만 미입력으로 처리하고 0 수량 행 및 0 금액을 보존합니다. | `test_trade_documents.py` 등 계산 테스트 |
| 공급처 PL 합계와 계산 합계가 다름 | 원본 합계와 정규화 계산을 자동으로 동일시하거나 단위/컨테이너를 추정하면 오기 위험이 있습니다. | 차이를 표시하고 사용자 승인 전 수정하지 않습니다. 단위를 분리하고 모르는 컨테이너 수는 생성하지 않습니다. | `test_packing_approval.py`, `test_packing_workflow.py` |
| 첨부 PI의 결제 정보가 CI로 넘어갈 위험 | PI와 CI는 은행정보 노출 규칙이 다릅니다. | PI→CI 변환에서 은행/계좌/SWIFT/결제 정보를 제거하고 원본의 가격·수량·근거는 보존합니다. | `test_ci_pi_import.py`, `test_ci_pi_import_ui.py` |
| Supabase·직인 연결 문제를 정상처럼 보이게 할 위험 | 누락된 테이블/잘못된 키/불일치 직인은 생성 실패로 처리해야 합니다. | 오류를 사용자에게 명시합니다. 자격 증명이 없는 경우에만 로컬 가격 스냅샷을 경고와 함께 선택할 수 있으며, API 실패를 조용히 오래된 데이터로 대체하지 않습니다. 직인은 비공개 경로와 해시를 확인합니다. | 카탈로그·거래처·직인 테스트 |

문서에 적힌 재현 정보는 해결 범위와 검증 방법을 설명합니다. 실제 배포에서 발생한 모든 오류나 특정 PDF의 오류 원인을 포괄하는 사후 분석은 아닙니다.

## 5. 팀원이 새 에이전트를 붙일 때

현재 앱은 하나의 Streamlit 오케스트레이션 경로이며 범용 에이전트 플러그인 API나 에이전트 간 메시지 버스는 없습니다. 아래는 **미래 연동을 위한 권장 계약**이지 이미 구현된 확장 API가 아닙니다.

1. 새 에이전트는 내부 가격 테이블에 직접 쓰지 말고 기존 `extract_trade_data` 초안 구조와 호환되는 거래 데이터 객체를 반환하도록 어댑터를 둡니다. 문서 종류, 당사자, 행별 품명/코드/용량/수량/단가/통화, 근거, 누락 필드, 충돌을 분리해 전달합니다.
2. 원문과 사용자 수정값을 보존합니다. 근거 없는 필드를 보완 사실처럼 만들거나, 유사도만으로 가격을 지정하거나, 문서 역할/통화를 바꾸지 않습니다.
3. Supabase 조회는 기존 가격/거래처 로더를 통합니다. 새 에이전트나 브라우저 코드에서 서비스 키를 직접 다루거나 DB에 주문·가격을 임의 기록하지 않습니다.
4. 공통 deterministic 검증·계산·사용자 확인·렌더러를 재사용합니다. 미확정 제품·금액·필수 필드는 기존 검토 UI의 생성 차단을 우회하지 않습니다.
5. 외부 발주/송장 발행/메일 전송 등 부작용은 별도 승인 설계 없이는 추가하지 않습니다. 새 동작은 격리된 테스트 픽스처로 오류/경계/역할별 회귀 테스트를 먼저 추가합니다.

## 6. 실행·테스트·운영 전 확인

저장소 루트 폴더에서 `uv`를 사용합니다. 앱 의존성은 `Quotation_KEKOREA/requirements.txt`에 선언되어 있습니다.

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt streamlit run .\Quotation_KEKOREA\app.py
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests
git diff --check
```

2026-11-05 작업에서 위 전체 테스트 명령으로 **193개 테스트가 통과**했습니다.

환경변수/Streamlit Secrets는 `OPENAI_API_KEY`, `OPENAI_MODEL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, 선택적 회사/은행 세부정보입니다. 실제 키는 `.env` 또는 호스팅 플랫폼의 서버 Secrets에만 보관합니다. UI의 추출 버튼을 누르면 입력 문서가 OpenAI에 전송됩니다. 외부 전송을 허용할 수 없는 문서를 업로드하지 마세요.

### Render 테스트 배포

저장소 루트의 [`.python-version`](../../.python-version)은 Render가 테스트된 Python 3.12 런타임을 사용하도록 하고, [`render.yaml`](../../render.yaml)은 기존 Streamlit 앱을 Singapore 리전의 Free 웹 서비스로 실행합니다. React 전환 설정은 아니며, 공개 URL에는 앱 로그인 기능이 없습니다. Render 대시보드에서 **New → Blueprint**를 선택하고 이 저장소의 `main` 브랜치를 연결하면 서비스를 생성할 수 있습니다.

Blueprint가 요청할 때 `OPENAI_API_KEY`와 `SUPABASE_SECRET_KEY`는 Render 대시보드에 직접 입력하세요. PI 생성을 쓰려면 6개의 `KEKOREA_USD_*` 은행정보도 Render Environment에 입력해야 합니다. 비밀키나 은행정보를 Git, 채팅, 로그에 입력하지 마세요. 첫 배포 성공 후에는 앱 URL에서 가상 자료로 파일 업로드·추출·검토·PDF/Excel 다운로드를 확인합니다.

Render Free는 절전 후 재기동될 수 있고 영구 디스크가 없습니다. 앱의 세션 메모리와 `outputs` 파일은 재시작/재배포 시 보장되지 않으므로 이 설정은 테스트용입니다. 장기 운영에는 유료 인스턴스, 영속 파일 저장, 세션 복구 및 접근 인증을 별도로 설계해야 합니다. 현재 코드는 로그인 없이 공개되므로 URL을 아는 사용자가 앱에 접근하고 OpenAI 요청을 발생시킬 수 있습니다.

**PyMuPDF 배포 전제:** PyMuPDF는 AGPL/상용 라이선스 선택이 필요한 듀얼 라이선스 패키지입니다. 사용자는 2026-11-05에 이 배포의 PyMuPDF 라이선스 확인을 완료했다고 답변했습니다. 상용 배포 전에 해당 라이선스의 증빙과 적용 범위를 팀에서 보관·확인하세요. LangChain은 PDF 파서가 아니므로 추가하지 않았습니다.

배포 URL은 기존 안내에서 `https://ke-korea.streamlit.app/`로 기록되어 있습니다. 이번 문서 작업에서 실제 서비스에 접속하거나 Supabase 실계정·최근 배포 코드를 확인하지 않았으므로, 현재 가용성 및 최신 배포 상태는 별도 확인 대상입니다. 이전 기록의 라이브 확인도 그 기록 날짜 범위에서만 유효합니다.

## 7. 관련 문서

- 상세 설계·기능 변경 이력: [README.md](../README.md)
- 유지해야 할 동작 및 수정 전 확인 절차: [AGENTS.md](../AGENTS.md)
- SQL 스키마·시드 적용·검증: [supabase/README.md](../supabase/README.md)
- 발표 스크립트: [Presentation/presentation_script_ko.md](../Presentation/presentation_script_ko.md)
