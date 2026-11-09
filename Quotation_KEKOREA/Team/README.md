# KE KOREA Quotation App — 팀 공유 안내

**기준일: 2026-11-06**
이 문서는 현재 저장소의 코드와 테스트를 기준으로 구현, 데이터 흐름, 오류 개선 내역 및 새 에이전트의 연동 원칙을 요약합니다. 기존 [README.md](../README.md)는 설계·변경·검증의 상세 기록이며, 실제 변경 시에는 [AGENTS.md](../AGENTS.md)의 보호 규칙과 코드를 우선 확인하세요. 이 문서는 배포 상태나 외부 서비스의 현재 가동을 보증하지 않습니다.

## 1. 한눈에 보기

Streamlit 앱에서 사용자가 PO(구매주문서), PI(견적/Proforma Invoice), CI(Commercial Invoice), PL(Packing List)을 각각 선택하고 텍스트 또는 이미지/PDF를 입력하면, 추출된 거래 초안을 검토·수정한 뒤 PDF/Excel 파일로 다운로드합니다. CI와 PL은 별도 메뉴와 별도 문서로 생성합니다.

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
- [pricing.py](../agent/pricing.py)는 문서 역할, 거래처, 제품 식별 및 통화를 함께 확인합니다. PO는 원본 문서의 판매자·통화·가격과 무관하게 제품명/용량을 대조해 ECLADO의 검증된 KRW 매입가를 적용하고 가격 기준도 주문 수량 단위(예: PCS)로 정규화하며, 일치가 불확실하거나 가격이 없으면 해당 행을 검토 대상으로 남깁니다. PI는 Dear Glow 판매가격을 사용합니다. CI는 반드시 첨부 PI의 거래가격을 보존하며, PI가 없으면 카탈로그 가격으로 대체하지 않고 생성을 막습니다. CI와 PL은 제품명·용량 매칭 및 Double-check만 수행하고 ECLADO 카탈로그 단가는 적용하지 않습니다. PL은 가격 없는 포장명세서로 유지됩니다. Supabase 오류나 잘못된 자격 증명에 오래된 가격을 성공처럼 적용하지 않습니다.

### 문서 계산·검토·출력

- [trade_documents.py](../agent/trade_documents.py)는 수량·단가·통화·금액 계산을 Decimal로 수행합니다. 비어 있는 수량과 명시적 0은 다릅니다. 명시된 0 수량은 행과 0 금액으로 유지합니다.
- [promotions.py](../agent/promotions.py)는 PI/PO 기존 행에 명시된 Buy-N-Get-M 행사를 적용합니다. 유상 수량·FOC 수량·출고 수량을 나누며, 증정분에 금액을 중복 부과하지 않습니다.
- 샘플 PI 행은 거래별 수동 입력이며 카탈로그 가격·일반 할인·행사로 덮어쓰지 않습니다.
- [packing_review.py](../agent/packing_review.py)는 공급처 포장 합계와 계산 합계를 비교합니다. 단위는 구분하고, 사용자가 승인하기 전에는 합계를 수정하지 않으며 컨테이너 정보를 추측하지 않습니다.
- [ci_import.py](../agent/ci_import.py)는 첨부 PI에서 CI 초안을 준비할 때 가격·수량 근거를 보존하고 은행/결제 정보를 제외합니다. 원문 행에 할인 표기가 없으면 누락 할인율을 0%로 처리하고, 할인 표기가 있으나 값이 누락된 경우는 재확인합니다. CI에 PI가 첨부되지 않으면 transaction price를 임의로 채우지 않고 차단합니다. CI/PL 상품은 ECLADO 이름·용량만 확인하며 PL에 가격은 적용하지 않습니다.
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

이전 2026-11-05 검증에서는 위 전체 테스트 명령으로 193개 테스트가 통과했습니다. 이후 검증 결과와 현재 배포 기준은 아래 최신 작업 요약을 참고하세요.

환경변수/Streamlit Secrets는 `OPENAI_API_KEY`, `OPENAI_MODEL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, 선택적 회사/은행 세부정보입니다. 실제 키는 `.env` 또는 호스팅 플랫폼의 서버 Secrets에만 보관합니다. UI의 추출 버튼을 누르면 입력 문서가 OpenAI에 전송됩니다. 외부 전송을 허용할 수 없는 문서를 업로드하지 마세요.

### Render 테스트 배포

저장소 루트의 [`.python-version`](../../.python-version)은 Render가 테스트된 Python 3.12 런타임을 사용하도록 하고, [`render.yaml`](../../render.yaml)은 기존 Streamlit 앱을 Singapore 리전의 Free 웹 서비스로 실행합니다. React 전환 설정은 아니며, 공개 URL에는 앱 로그인 기능이 없습니다. Render 대시보드에서 **New → Blueprint**를 선택하고 이 저장소의 `main` 브랜치를 연결하면 서비스를 생성할 수 있습니다.

Blueprint가 요청할 때 `OPENAI_API_KEY`와 `SUPABASE_SECRET_KEY`는 Render 대시보드에 직접 입력하세요. PI 생성을 쓰려면 6개의 `KEKOREA_USD_*` 은행정보도 Render Environment에 입력해야 합니다. 비밀키나 은행정보를 Git, 채팅, 로그에 입력하지 마세요. 첫 배포 성공 후에는 앱 URL에서 가상 자료로 파일 업로드·추출·검토·PDF/Excel 다운로드를 확인합니다.

Render Free는 절전 후 재기동될 수 있고 영구 디스크가 없습니다. 앱의 세션 메모리와 `outputs` 파일은 재시작/재배포 시 보장되지 않으므로 이 설정은 테스트용입니다. 장기 운영에는 유료 인스턴스, 영속 파일 저장, 세션 복구 및 접근 인증을 별도로 설계해야 합니다. 현재 코드는 로그인 없이 공개되므로 URL을 아는 사용자가 앱에 접근하고 OpenAI 요청을 발생시킬 수 있습니다.

2026-11-05 Render에 배포해 `COMPANY AUTOMATION_Project`의 `Production` 환경으로 이동했습니다. [Render 앱](https://ke-korea-quotation.onrender.com/)은 HTTP 200을 반환했고 UI에서 ECLADO 카탈로그 157개 상품 연결을 확인했습니다. 실제 주문 추출 및 PDF/Excel 생성은 이 배포 확인에서 실행하지 않았습니다. Render GitHub 저장소 연결 목록에 이 저장소가 없어 공개 Git 저장소 URL로 초기 배포했으며, Render가 자동 배포 미지원 상태라고 안내했습니다. 새 커밋 반영 시 Blueprint 수동 동기화/서비스 수동 배포가 필요합니다. 자동 배포를 원하면 Render의 GitHub 계정 설정에서 이 저장소 접근을 연결한 뒤 확인하세요.

**PyMuPDF 배포 전제:** PyMuPDF는 AGPL/상용 라이선스 선택이 필요한 듀얼 라이선스 패키지입니다. 사용자는 2026-11-05에 이 배포의 PyMuPDF 라이선스 확인을 완료했다고 답변했습니다. 상용 배포 전에 해당 라이선스의 증빙과 적용 범위를 팀에서 보관·확인하세요. LangChain은 PDF 파서가 아니므로 추가하지 않았습니다.

기존 Streamlit 앱 주소는 `https://ke-korea.streamlit.app/`입니다. Render와 Streamlit은 서로 별도로 배포되며, 한쪽 변경이 다른 쪽에 자동 반영되지 않습니다. Render 배포 시 Supabase의 현재 가격 스냅샷이 보이는 것은 확인했지만, 실제 DB 데이터의 계약상 최신성이나 양쪽 서비스의 향후 동기화는 별도 확인 대상입니다.

### 2026-11-05 최신 변경 및 유지보수 기준

- **사이드바 메뉴는 현재 상태로 유지합니다.** 메뉴 목록, 라벨, 선택/전환 동작 및 메뉴별 워크플로 연결 코드는 팀의 명시적인 사전 승인 없이 수정·삭제·재구성하지 않습니다. 다른 기능의 수정도 메뉴 동작에 영향을 주지 않도록 분리하고 관련 회귀 테스트로 확인합니다.
- CIPL 통합 메뉴와 CI+PL 동시 생성 경로를 제거했습니다. 현재는 PI, PO, CI, PL을 각각 선택해 개별 문서를 만듭니다. CI·PL 개별 흐름은 유지하며 앱 UI에서 CI 및 PL 메뉴가 보이고 CIPL 메뉴가 없는 것을 배포 후 확인했습니다.
- 메뉴를 전환해도 같은 브라우저 세션 안에서는 각 문서의 입력, 첨부, 추출 초안, 검토/수정 상태 및 생성 파일 상태가 메뉴별로 보존됩니다. 추출/생성 작업은 전환 후에도 계속 진행되고, 완료 결과는 해당 메뉴로 돌아왔을 때 확인할 수 있습니다. 이는 세션 메모리 상태이며 새로고침, 세션 종료, 서버 재시작 또는 재배포를 넘어 보존되는 저장 기능은 아닙니다.
- 변경 커밋 `54a6fdd` (**Remove combined CI and PL workflow**)는 Render 배포 `dep-dbm3rll9fdbs73bp7gg0`에 성공했고, `https://ke-korea-quotation.onrender.com/`에서 메뉴 구성을 확인했습니다. 이 확인은 실제 거래 추출 및 PDF/Excel 파일 생성까지 수행한 배포 검증은 아닙니다.
- 변경 관련 CI/PL·사이드바·업로드·포장 워크플로 집중 테스트 **50개 통과**. 전체 테스트는 **203개 중 202개 통과, 1개 실패**였으며, 실패는 PO 상품 Double-check UI 기대값 관련으로 CIPL 제거 변경 경로와 무관합니다. 전체 테스트가 모두 통과한 것으로 간주하지 마세요.

### 계약 자동화 추가 (로컬 구현)

- 기존 사이드바의 두 계약 메뉴 라벨과 메뉴 목록은 그대로 두고, 해당 메뉴를 매매계약/커미션 계약 UI에 연결했습니다. PI/PO/CI/PL 코드는 계약 저장소와 분리되어 있습니다.
- 자연어 거래 분석, 당사자·조건표, 한국어/영어 초안, 문장별 메모·수정안·revision 복구, 참고 PDF/DOCX 및 사용자 승인 선호 조항, DOCX/PDF 내보내기를 `Quotation_KEKOREA/contracts/`에 분리했습니다.
- 계약 화면은 사용자 요청으로 비밀번호 없이 공개 접근하도록 변경했습니다. 앱 URL에 접근 가능한 누구나 계약 및 참고 파일을 열람·수정·삭제할 수 있으므로, 비공개/민감 계약을 저장하지 마세요. Supabase Storage 버킷은 비공개지만 앱은 서버 `SUPABASE_SECRET_KEY`로 파일을 대신 제공합니다. 스캔 PDF OCR은 별도 동의를 요구합니다.
- 구현 설정·테스트 명령·운영 전 확인사항은 [README_CONTRACTS.md](../README_CONTRACTS.md)에 기록했습니다. 새 테이블/Storage 버킷은 [계약 migration](../supabase/migrations/202611050001_contracts.sql) 적용 전에는 운영에서 사용할 수 없습니다.
- **현재 상태:** 코드와 합성 데이터 로컬 테스트는 추가됐지만 Supabase migration 적용, 실제 비밀 설정, 실제 DB 권한/RLS 검증, 앱 배포 및 운영 문서 시각 검증은 완료되지 않았습니다. 이를 배포 완료로 표현하지 마세요.

## 7. 계약서 목록 오류 수정 및 인수인계 (2026-11-06)

### 목적 및 영향

- **문제:** 저장된 계약이 하나 이상 있을 때 `render_contract_page()`의 삭제 확인 분기가 정의되지 않은 `options` 변수를 참조하여 `NameError`를 발생시킬 수 있었습니다. 이 오류가 나면 계약 목록과 대화 History 확인도 중단됩니다.
- **수정:** `records`에서 ID를 문자열로 정규화한 `options` 사전을 생성합니다. 삭제 요청 ID가 실제 목록에 포함되는 경우에만 계약 제목과 확인창을 표시합니다. 메뉴 구성, 견적서 가격 계산, 계약 revision 및 Supabase 데이터 구조는 변경하지 않습니다.
- **대화 History:** `repo.list_messages(contract_id)`에서 계약별 대화를 읽어 `st.chat_message`에 표시하는 기존 기능을 유지합니다. 화면이 열리지 않던 원인을 제거한 것이며, 과거 메시지가 실제 DB에 존재하는지나 운영 서버에서 정상 노출되는지는 별도 검증이 필요합니다.
- **삭제 흐름:** 목록의 X → 확인/취소. 실제 삭제는 기존 Supabase RPC 및 Storage 처리 경로를 사용합니다. 확인 없이 삭제하지 않습니다. 실제 DB·파일을 대상으로 파괴적 테스트를 수행하지 않습니다.

### 적용 및 테스트

```powershell
# 저장소 최상위 폴더에서, 수정 패치 적용 후
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_contract_workspace_ui
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests
git diff --check
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt streamlit run .\Quotation_KEKOREA\app.py
```

화면에서 (1) 저장 계약 2건 조회 (2) 삭제 취소 (3) 삭제 확인 (합성·테스트 저장소만) (4) 다른 계약을 열 때 History가 섞이지 않는지 확인합니다. 이전 상품 주석 실패 기록은 과거 이력이며 이번 작업 시작 전 `3991930`의 전체 296개 테스트는 통과했습니다. 새 실패가 발생하면 배포하지 않습니다.

**당시 조사 이력:** 계약 목록 오류를 조사했던 이전 세션에서는 GitHub 연결 쓰기 권한 부족으로 HTTP 403이 발생했고 전체 검증을 완료하지 못했습니다. 현재 기준으로 해당 목록 보호 테스트는 296개 통과한 작업 시작 전 검사에 포함돼 있습니다. 이번 UI의 로컬 검증과 실제 운영 적용 여부는 별도로 기록합니다.

### 보안 및 운영 확인

계약 화면은 비밀번호 없이 공개 접근됩니다. 민감 계약/개인정보 저장은 접근 제어가 마련되기 전까지 피해야 합니다. Supabase migration, Secrets, RLS, 실제 계약·파일 삭제 및 PDF/DOCX 시각 검증은 별개입니다. 배포 후 앱에서 확인하지 않고 단순 GitHub 반영을 운영 성공으로 표시하지 않습니다.

## 8. 관련 문서

- 상세 설계·기능 변경 이력: [README.md](../README.md)
- 계약 자동화 구현·설정·미검증 항목: [README_CONTRACTS.md](../README_CONTRACTS.md)
- 유지해야 할 동작 및 수정 전 확인 절차: [AGENTS.md](../AGENTS.md)
- SQL 스키마·시드 적용·검증: [supabase/README.md](../supabase/README.md)
- 발표 스크립트: [Presentation/presentation_script_ko.md](../Presentation/presentation_script_ko.md)

## 2026-11-06 TASTE 계약서 UI 및 README 동기화

### 계약서 워크스페이스 운영 및 유지보수

- 메뉴는 PO/PI/CI/PL과 **계약서 만들기**로 구분한다. 기존 견적서 계산과 가격 정책은 변경하지 않는다.
- **BOX 1** 자연어 거래 입력·AI 대화·기존 질문 제한·참고자료 → **BOX 2** 상세조건과 당사자 수동 입력·지급조건 갱신 → **BOX 3** 문서형 초안·문장별 메모 → `최종 수정 요청` → 비교·승인·단일 revision 저장 순서다. 위험 검토·이전 revision 복원·복사·삭제 기능은 보조 영역에 유지한다.
- 검토 요약은 `contracts/review_summary.py`에서 중복을 묶고 필수/권장/법률/TBD로 안내한다. 한국어가 기본이며 검토 언어를 별도로 선택한다. 원문·항목별 근거는 접힌 메뉴에 보존한다. 확인 해제는 해당 이슈만 다시 미확정으로 바꾸며 관련 없는 필드를 자동 확정하지 않는다.
- `검토용 초안 PDF/DOCX`는 실제 조항이 있으면 미확정을 표시해 비공개 저장한다. 최종본은 기존 규칙을 그대로 통과해야 한다. 출력 기록은 경로의 `draft/final`로 구분하며 DB 마이그레이션은 추가하지 않는다.
- 문장 옆에 여러 메모를 동시에 열어 입력하고 `최종 수정 요청`에서 함께 저장·단일 AI 요청한다. BOX 1의 AI 전송 동의가 필요하며, 기존 조건 수정안은 먼저 적용·취소해야 한다. AI가 보고한 충돌과 중복·누락·보호된 지급조항 수정은 차단한다. 서로 다른 문장 간 의미 충돌은 비교 화면에서 사용자가 명시적으로 확인한다. 이전 revision 메모는 재저장 없이 적용하지 않는다. 기존 단일문장 AI 호출·지급정책·법률검증·revision 엔진과 거래 문서 코드는 유지한다.
- 커미션 지급조건은 기본 D+7·TT에서 출발하지만 사용자가 지급기한과 서면합의 연체이율을 편집할 수 있다. 계좌/법률 정보는 AI가 임의 확정하지 않는다.
- `contracts/library.py`, `review.py` 등의 승인된 샘플 검색(RAG)은 **계약서 관련** 기능이다. 상품·가격 매칭은 별도의 SKU/용량 규칙을 계속 사용하며, 위에서 설명한 '상품에 벡터 DB 미사용' 규칙과 충돌하지 않는다.
- 과거 README의 74개 테스트·상품 주석 실패 등은 당시 기록이다. 이번 작업 시작 전 전체 296개 테스트는 통과했다. 운영 DB/API·실제 배포는 이번 작업에서 확인하지 않았으며, Windows 브라우저 URL 확인 제한으로 실제 브라우저 시각 검수도 미완료다.
- 코드 변경·삭제 시 루트/프로젝트/계약/Team/Presentation README를 동일 변경에서 갱신한다. `scripts/check_readme_sync.py`의 staged guard를 통과시키고 기존 기능 설명이 남아 있지 않은지 확인한다.

**이번 최종 로컬 검증:** 2026-11-06 전체 320개 테스트 통과, 실패 0개, 종료 코드 0(기존 296개 + 신규 24개). `git diff --check` 통과. 합성 자료·가짜 API/DB와 Streamlit AppTest로 검증했고 기존 보호 테스트는 변경하지 않았다. 운영 데이터 수정, GitHub 푸시, 배포는 수행하지 않았다. DRAFT PDF의 다중 페이지·혼합 언어는 렌더링으로 확인했으며 브라우저·Word의 실제 시각 검수는 별도다.

## 2026-11-06 회귀 테스트 보완

상품 주석 확인 미완료 시 PO/PI PDF 및 Excel 생성 버튼은 차단됩니다. 투자/무역 커미션 계약의 기본 7일 영문 문구는 `seven (7) calendar days`를 사용하며 사용자 지정 기한은 유지합니다. 두 동작은 296개 통과한 기준 소스에 포함되어 있으며 이번 UI 작업에서 수정하지 않았습니다.

## 2026-11-06 CI DRAFT 출력 보존

PO/PI의 확인 전 생성 차단과 달리, CI는 첨부 PI 거래가격을 변경하지 않고 상품 매칭 미확정 경고 및 DRAFT 상태를 유지해 검토용 PDF/Excel 출력을 허용합니다. 관련 회귀 테스트는 `test_product_matching_ui.py`와 `test_review_ui.py`이며 둘 다 통과해야 합니다.

### 계약서 UX 업데이트 (2026-11-06)
BOX 3 문장/댓글은 고정된 두 열로 렌더링하여 클릭 전후에 레이아웃이 이동하지 않는다. 수정 전후 비교·수동 승인·revision 동작은 동일하다. 기존 거래 문서 영역 및 위험 통제는 수정하지 않았다.

## 2026-11-06 AI 위험 검토 페이지·추천안 확장

팀 시연: BOX 3 > AI 핵심 위험 검토 > 전체 위험 검토 > 1/2/3 페이지 이동 > 항목 선택 > 추천안 3개 생성 > 가변값·문장 직접 편집 > 추천 문장 적용 > BOX 3 미리보기 확인 > 선택한 수정안 비교·승인. 관련 코드는 risk_review_workspace.py 및 risk_review_ui.py. 기존 PO/PI/CI/PL·ECLADO 및 법률 검증 엔진은 변경하지 않았다.

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

### 계약서 출력 장애 시
DRAFT/FINAL 모두 렌더링 단계와 비공개 저장 단계를 구분한다. 저장 실패만 발생했으면 브라우저 세션의 직접 다운로드로 확인하고, Supabase Storage 버킷 `kekorea-contracts` 및 exports 테이블 권한/설정을 점검한다. FINAL 필수검증은 유지한다.

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
