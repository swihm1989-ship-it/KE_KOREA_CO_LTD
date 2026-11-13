# KE KOREA 무역 문서 생성 AI Agent 설계안

> 현재 동작은 원격 코드 `f335e9e` 기준으로 대조했습니다. 문서 끝의 「2026-11-10 코드·README 대조 결과」를 우선 참고하세요. 이전 날짜의 테스트·패치 기록은 당시 상태이며 현재 운영 성공을 뜻하지 않습니다.

작성일: 2026-10-30 (Asia/Seoul)  
최종 갱신: 2026-11-06 (Asia/Seoul)

상태: Streamlit 배포, Supabase 카탈로그 조회, 비공개 직인 다운로드 및 초안 PDF 생성·다운로드를 확인했다. 모든 출력은 사용자 검토용 초안이며 실제 발주·발송은 자동 수행하지 않는다. 아래 초기 설계 기록보다 다음 현재 동작 및 변경 보호 기준을 우선한다.

2026-11-05 업데이트: 통합 CI+PL 메뉴와 생성 경로를 제거했다. Commercial Invoice(CI)와 Packing List(PL)는 사이드바의 개별 메뉴에서 따로 생성한다.

계약 자동화 기능의 구현 범위·설정·DB migration 및 검증 상태는 [README_CONTRACTS.md](README_CONTRACTS.md)를 참조한다. 계약 코드는 GitHub `main`에 반영되었지만 Supabase migration 적용·운영 데이터 저장·실제 Streamlit 경로의 동작은 별도로 검증해야 한다.

현재 계약서 화면은 **BOX 1 계약조건 입력·AI 대화, BOX 2 상세조건 수동 입력, BOX 3 문서형 미리보기**로 구성한다. BOX 2의 확정/AI 제안/확인 필요/TBD 유지는 기존 confirmed/suggested/missing 상태에 대응하며, 조건 변경은 기존 본문 영향 검토·승인 절차를 따른다. BOX 3에서 여러 문장을 클릭하면 각 문장 옆에 메모가 동시에 열린다. 메모별 저장을 누르지 않아도 `최종 수정 요청` 한 번으로 모두 저장하고 한 번의 AI 요청으로 수정안을 만든다. 승인 전에는 본문이 바뀌지 않고, 승인한 변경은 기존 revision RPC 한 번으로 저장한다.

계약서 출력은 검토용 DRAFT와 최종 계약서로 구분한다. DRAFT는 실제 조항이 필요하며 미확정 상태의 본문에 `[확인 필요]`/`[TBD / UNCONFIRMED]` 표시와 미확정 부록을 붙인다. PDF에는 매 페이지 DRAFT 워터마크, DOCX에는 반복 DRAFT 머리글을 넣고 서명 페이지를 생성하지 않는다. 최종 PDF/DOCX는 기존 `validate_rules(..., for_export=True)`를 통과해야 한다. 두 경로 모두 기존 비공개 Storage·revision·내보내기 기록을 사용하며 경로의 `exports/draft/`와 `exports/final/`로 구분한다.

## 현재 동작 및 변경 보호 기준 — 2026-11-02

배포 앱: https://ke-korea.streamlit.app/ (사용자가 2026-11-03 확인한 현재 주소). 이전 `kekoreacoltdgit-69eu27cywmml3jfwtdsappb.streamlit.app` 주소는 접속 확인 시 404였다.

배포 소스: GitHub `main`, 진입점 `Quotation_KEKOREA/app.py`

향후 작업 지침: [AGENTS.md](AGENTS.md)

| 수정 사항 | 현재 동작 | 회귀 검증 |
| --- | --- | --- |
| 회사 직인 저장 | `kekorea-private-seal` 비공개 Supabase 버킷에서 서버 전용 키로 읽고 PNG SHA-256을 검증한다. 다운로드는 15분간 캐시한다. 큰 Base64 Secret은 필요하지 않으며 선택적인 이전 방식의 대체 경로만 남아 있다. | `tests/test_branding.py`, 실제 배포 PDF의 직인 픽셀 대조 |
| PDF 페이지 분할 | 상품 행은 실제 남은 공간이 부족할 때만 다음 페이지로 이동한다. 하단 영역 때문에 마지막 상품 하나를 강제로 옮기지 않는다. 합계·REMARK·계좌정보·회사 명판/직인 묶음이 들어가지 않으면 묶음 전체를 다음 페이지로 이동한다. | `tests/test_pdf_pagination.py`, 배포 앱의 20개 상품 PI PDF |
| PDF 원문 추출 (로컬 구현) | PyMuPDF로 텍스트 PDF의 페이지별 텍스트를 추출해 원본 PDF와 함께 모델에 전달한다. 텍스트가 없는 스캔 페이지는 이미지로 렌더링해 시각 추출을 돕는다. LangChain은 PDF 파서가 아니므로 추가하지 않는다. PyMuPDF는 AGPL/상용 이중 라이선스이므로 상용 라이선스 확인 전 배포하지 않는다. | `tests/test_pdf_inputs.py`, `tests/test_extractor.py`; 배포 검증 전 |
| 누락 정보 입력 | `Not provided`/`TO BE CONFIRMED` 등으로 남을 값은 검토 화면에서 입력한다. 필수 정보는 입력 전 PDF/Excel 생성을 막고, 선택 정보는 사용자가 `N/A`를 명시할 수 있다. | `tests/test_review_fields.py`, `tests/test_review_ui.py`, 배포 앱의 배송·결제조건 입력 후 PDF |
| 입력값 유지와 새 파일 생성 | 메뉴를 이동해도 보완 입력값을 유지한다. 새 주문 추출 또는 명시적 JSON 정정 시 이전 입력을 초기화한다. 내용 수정 시 기존 다운로드를 무효화한다. | `tests/test_review_ui.py` |
| 문서별 동시 작업 (로컬 구현) | PI/PO/CI/PL의 주문 입력·첨부·초안·검토값·승인·다운로드를 메뉴별로 보관한다. 메뉴를 이동해도 실행 중 추출/생성은 계속되며 결과는 시작한 메뉴에 저장한다. | `tests/test_workflow_state.py`, `tests/test_workflow_ui.py`; 배포 검증 전 |
| 주문수량 0 | 숫자 `0`, 문자열 `"0"`, `"0.0"`을 정상 수량으로 인정한다. 행은 삭제하지 않으며 해당 행 금액은 0이다. 빈 값·음수·비숫자·NaN/Infinity는 계속 오류다. 단가의 양수 검증은 별도 유지한다. | `tests/test_trade_documents.py`, `tests/test_review_ui.py`, 배포 PO의 0+5 수량/금액 표시 |
| 문서별 가격 구분 | ECLADO PO는 정확한 제품·용량의 검증된 KRW 매입가격을 사용한다. PI는 Dear Glow 판매가격을 사용한다. CI는 첨부 PI의 거래가격을 그대로 사용하며 PI가 없으면 카탈로그 가격으로 대체하지 않고 생성을 막는다. CI/PL은 ECLADO 제품명·용량 매칭만 수행하고, 가격 없는 PL에 카탈로그 가격을 적용하지 않는다. | `tests/test_supabase_catalog.py`, `tests/test_ci_pi_import.py`, `tests/test_product_matching.py` |
| ECLADO 공급처 별칭 | `eclado`, `ECLADO CO. LTD`, `에끌라도`, `에끌라두`를 대소문자·공백·구두점 차이 없이 같은 공급처로 인식한다. 원래 법인명 필드는 그대로 보존한다. 화면에 인식 여부와 카탈로그 매입가격 적용 상품 수를 표시한다. | `tests/test_supabase_catalog.py`, `tests/test_review_ui.py` |
| OCR 상품명 유사 매칭 및 직접 수정 (로컬 구현) | 정확한 상품명 일치가 없을 때만 문자열 유사도를 이용해 ECLADO 카탈로그 후보를 찾는다. 유사도 90% 이상이며 SKU·용량·제품 구분에 충돌이 없는 단일 후보는 카탈로그 가격을 불러오되 `Double-check this product` 확인 전에는 문서 생성을 막는다. 68% 이상 90% 미만은 가격을 자동 적용하지 않고 후보를 제시한다. 후보가 없거나 직접 수정한 상품명은 사용자가 입력한 그대로 견적에 표시하며 가격은 별도 입력/확인한다. 벡터 검색은 사용하지 않는다. | `tests/test_product_matching.py`, `tests/test_product_matching_ui.py`, `tests/test_workflow_state.py`; 배포 검증 전 |
| 거래처 정보 DB (데이터 저장 완료, 자동 반영 코드는 로컬) | Supabase 비공개 `kekorea_counterparties`에 등록된 거래처의 법인명·주소·담당자·명시적 기본 배송지를 누락 필드에 적용한다. 주문에 명시한 값과 N/A가 우선한다. | `tests/test_counterparties.py`, `tests/test_counterparties_api.py`, `tests/test_counterparties_ui.py` |
| PL 합계 수정 승인 | 원본 합계와 항목별 계산 합계를 비교표로 보여준다. `합계를 수정할까요?`를 승인하면 원본은 보존하면서 계산된 합계를 PDF/Excel에 적용한다. PCS/KG 등 다른 단위는 따로 유지한다. 품목/원본 합계 변경 시 승인을 취소한다. 잘못된 행 값·단위 충돌·컨테이너 수는 승인으로 우회하지 못한다. | `tests/test_packing_approval.py`, `tests/test_review_ui.py` |
| 통화와 반올림 | Decimal 계산을 유지한다. 화장품 KRW는 원 단위, USD는 소수점 두 자리로 단가를 반올림한 뒤 행 금액을 계산한다. 단위가 다른 수량은 별도로 표시한다. | `tests/test_trade_documents.py`, `tests/test_packing_workflow.py` |

### 최근 변경 이력

- `46ab479`: 비공개 Supabase 직인 로딩 및 검증.
- `dbb50ba`: 상품 공간 우선 배치, 하단 정보 묶음의 페이지 분할 방지.
- `0e107d7`: 누락 정보 입력, 수정 반영, 입력 상태 유지, 오래된 다운로드 제거.
- `ab2bf1f`: 명시적 주문수량 0 허용, 누락·음수 오류 구분, 포장 편집기의 숫자 0 보존.
- `d75417c`: ECLADO 영문·한글 별칭 인식과 일부 상품 미일치 시 일치 상품의 가격 조회 유지.
- 2026-11-02 PL 보완: 합계 비교·명시적 수정 승인, 단위가 붙은 원본 합계와 컨테이너 규격 입력 파싱, 수정 후 승인 초기화.

### 검증 명령과 유지 규칙

저장소 루트에서 다음 명령을 실행한다. `--with streamlit`을 포함해야 화면 회귀 테스트가 건너뛰어지지 않는다.

```powershell
uv run --with streamlit --with pymupdf python -m unittest discover -s Quotation_KEKOREA/tests
git diff --check
```

2026-11-03 문서별 동시 작업 검증의 최신 테스트 수와 범위는 아래 해당 변경 기록을 따른다. 테스트 수는 이후 정당한 회귀 테스트 추가에 따라 증가할 수 있다. 검토 화면 테스트는 외부 API를 모킹하며, 실제 배포 검증과 구분한다. 실제 배포 검증에는 가상 입력을 우선 사용하고, 사용자의 주문 이미지 재전송이 필요하면 외부 전송 승인을 먼저 확인한다.

### 2026-11-03 메뉴 이동 시 초기화 및 작업 중단 방지 (로컬 구현)

원인: 기존 화면은 `trade_draft`와 생성 파일 상태 한 벌을 공유했다. 다른 문서의 추출 결과가 이를 덮어썼고, 메뉴를 떠날 때 Streamlit이 숨겨진 입력 위젯 상태를 정리했다. 긴 API 호출과 파일 생성도 화면 스크립트에서 실행되어 메뉴 이동에 따른 재실행과 충돌할 수 있었다.

`agent/workflow_state.py`의 세션별 `DocumentWorkspaces`가 PI/PO/CI/PL의 입력 문구, 첨부 이미지, 초안, 공급처 입력, 누락 정보 보완, 적용 전 JSON 편집, 포장 행, 확인/합계 승인, 생성 파일을 별도 보관한다. 준비 중 메뉴를 경유해도 기존 문서 작업은 유지한다. 업로더와 표 편집기의 읽기 전용 상태를 강제로 복원하지 않고, 첨부 바이트와 실제 편집 행을 따로 보존한다. 보관된 첨부는 미리보기로 확인하고 `첨부 이미지 모두 지우기`로 제거할 수 있다.

자료 추출과 파일 생성은 세션당 최대 3개 작업 스레드로 실행한다. 같은 메뉴의 실행 중 작업은 중복 제출하지 않으며, 다른 메뉴에서는 새 작업을 시작할 수 있다. 작업자는 입력 복사본으로 실행하고 Streamlit 화면/세션 상태에는 접근하지 않는다. 결과는 화면 스레드가 시작한 메뉴에만 반영한다. 사이드바에 진행 중 작업과 보관 중 초안을 표시하고, 실행 중에는 1초 간격의 상태 확인으로 완료 결과를 갱신한다. 관련 Streamlit API: [fragment 공식 문서](https://docs.streamlit.io/1.41.0/develop/api-reference/execution-flow/st.fragment).

각 생성 작업은 세션/작업별 고유 출력 폴더를 사용한다. 생성 중 문서 내용이 바뀌면 이전 내용으로 생성한 파일은 다운로드에 연결하지 않는다. 새 추출 성공/JSON 정정은 해당 메뉴의 이전 보완값과 포장 편집 상태를 초기화한다. 다른 메뉴의 자료는 건드리지 않는다. 기존 수량 0, 가격·통화, 프로모션, 합계 승인 취소, 직인, PDF 서식 규칙은 유지한다. CI와 PL은 개별 메뉴와 파일로 생성한다.

유지 범위는 **동일 브라우저 연결의 Streamlit 세션**이다. 브라우저 새로고침/새 세션, 서버 재시작에 대한 영구 저장은 구현하지 않았다. 외부 API 호출 시간제한과 오류는 기존대로 표시하며 자동 재요청하지 않는다. 실제 발주나 발송은 수행하지 않는다. 배포 앱 반영 및 실제 OpenAI 호출을 이용한 동시 작업 검증은 아직 수행하지 않았다.

재발 방지: `tests/test_workflow_state.py`는 메뉴별 상태 분리, 실제 작업 스레드의 PI/PO 동시 실행, 원래 메뉴로 결과 반영, 오래된 생성 결과 폐기, 중복 제출 차단, 오류 후 재시도, 입력 복사본과 세션 분리를 검증한다. `tests/test_workflow_ui.py`는 다섯 메뉴 및 준비 중 메뉴 왕복, 입력·파일·공급처·미적용 JSON·첨부 유지/제거, 추출/생성 도중 이동, PL 승인 유지 및 원본 수정 후 승인 취소를 검증한다. 외부 서비스와 렌더링 지연은 가상 자료/제어 가능한 대기 작업으로 대체하며 실제 계산·검토 화면은 실행한다.

검증 결과: 수정 전 화면 테스트에서 메뉴 왕복 시 입력 소실 및 비동기 작업 관리자 부재를 재현했다. 수정 후 `uv run --offline --with streamlit python -m unittest discover -s Quotation_KEKOREA/tests`로 **101개 테스트가 모두 통과했다(화면 테스트 포함, 생략 없음)**. 작업 폴더의 uv 캐시를 사용했으며 테스트 임시 파일 권한을 허용한 실행으로 확인했다. `git diff --check`도 통과했다. Streamlit의 기존 위젯 API 경고는 남아 있다. 독립 코드 검토에서 중요한 결함은 보고되지 않았다.

### 2026-11-03 Code 열이 있는 주문의 상품명·용량 표기 보완 (로컬 구현)

추가로 제공된 JSON은 24개 상품이 `NK-CX Core Ampoule (NK-CX)`, `Respiration Toner (E173A)`처럼 추출되어 있었다. 이 주문에는 미확정 토너 25번째 행이 없었다. 기존 문자열 동일 비교 때문에 코드가 붙은 24개 이름 모두 가격 조회에 실패했다. 코드 없는 주문 사진과의 차이는 해상도가 아니라 상품명에 합쳐진 Code 열이었다.

`agent/product_matching.py`가 완전한 카탈로그 이름을 인식하고, `agent/pricing.py`는 기존 공급처·매입/판매 가격·통화 정책으로 가격을 조회한다. 원래 추출 이름과 출처를 덮어쓰지 않는다. 추출 스키마에는 `product_code`를 추가하여 앞으로 코드와 이름을 따로 받으며, 숫자의 출처가 이름 한 부분만으로 축약되지 않도록 이미지의 전체 행을 `source`에 인용하게 한다. 기존 JSON처럼 코드가 이름에 합쳐진 입력도 계속 처리한다.

지원하는 표기에는 대소문자, 공백/줄바꿈, 전각 문자, 보이지 않는 공백, 하이픈·구두점·인용부호, 괄호/대괄호/일부 CJK 괄호, 영어/한글 제품명·코드 라벨, 코드의 구두점/공백 변형이 포함된다. 이름 앞뒤와 단어 사이의 검증된 괄호 코드도 처리한다. 긴 코드 `E-20-8`을 `E-20`으로 잘라 인식하지 않는다. `&`와 `and`, `50.0 G`/`50 grams`, `ml`/`millilitres`, `x`/`X`/`×`/`*`, 단순 묶음 `2×25g`/`25g×2`를 같은 표기로 비교한다. 용량 단위를 환산하거나 합산해서 다른 포장을 같은 제품으로 취급하지 않는다.

완전한 상품명이 유일하게 확인되지만 임의의 추가 설명이 남으면 검증된 가격 후보를 불러오고 `Confirm product annotation ...` 확인란을 표시한다. 사용자는 설명이 실제 동일 제품을 뜻하는지 확인한 뒤 문서를 생성한다. 이는 가격을 추측하거나 단가를 다시 입력하게 하는 방식이 아니다. 의미를 알 수 없는 모든 단어를 무조건 무시하지 않는다.

잘못되거나 충돌한 SKU, 서로 다른 두 제품명, 생략/오타로 불완전한 이름, 용량·단위·입수량 충돌, 복합 용량 일부 누락, 샘플/테스터/리필/미니/Plus 등 다른 제품 변형, SPF/PA 등급의 숫자 또는 `+` 개수 차이는 자동 확정하지 않는다. 카탈로그 이름 자체에 포함된 변형 단어는 보존한다. 중복 상품과 정규화 후 충돌하는 이름은 모호한 상태로 남긴다. 기존 카탈로그 가격을 받은 행이 상품명/코드 변경으로 미일치가 되면 그 카탈로그 단가와 제품 ID를 제거한다. 사용자가 별도로 확정한 거래 가격 정책은 유지한다.

검증: 제공된 최신 24개 행을 로컬 카탈로그로 재검사하여 **24/24 가격 연결과 KRW 적용**을 확인했다. 연락처·실제 주문 수량·비공개 단가를 테스트 코드에 복사하지 않았다. 전체 카탈로그 이름/용량의 재인식 결과는 표준 제품 131개 일치, 용량 없는 중복 후보 26개 모호 상태로 기존 구분을 보존했다. `tests/test_product_matching.py`는 정상 표기·코드/용량/세트 충돌·SPF/PA·코드 접두부·설명 확인·중복·원본 보존을 검증한다. 화면 테스트는 단가 입력 요구가 사라지고 상품 설명 확인만 남는지 확인한다. 실제 배포 반영과 원본 이미지의 OpenAI 재추출 검증은 아직 수행하지 않았다.

최종 회귀 검증: `uv run --offline --with streamlit python -m unittest discover -s Quotation_KEKOREA/tests`로 **116개 테스트가 모두 통과했다(화면 테스트 포함, 생략 없음)**. 작업 폴더 uv 캐시와 테스트 임시 파일 권한을 허용한 실행을 사용했다. `git diff --check`도 통과했다. 독립 검토에서 확인한 긴 코드의 접두부 충돌, SPF/PA 기호 소실, 붙여 쓴 곱셈 용량, 설명이 붙은 불완전 복합 용량은 실패 테스트로 재현한 후 수정했다. 추가 설명 속 `mg`/`g`/`ml` 등 단위 충돌도 차단한다. 기존 Streamlit 위젯 API 경고는 남아 있다.

### 2026-11-03 PI/CI 부분 상품 미일치 가격 조회 보완 (로컬 구현)

상품명 부가 표기 인식은 PO/PI/CI가 같은 함수를 사용한다. 앞서 제공된 24개 상품 JSON을 PI로 바꾸고 구매자를 Dear Glow로 지정한 로컬 검증에서는 24/24 상품이 USD 판매가격에 연결되었다. 구매자가 비어 있거나 다른 구매자이면 Dear Glow 전용 판매가격을 자동 적용하지 않는다. 이 경우는 이미지 인식 실패와 구분한다.

추가로 재현한 오류: 구매자가 Dear Glow로 확인되어도 제품 분류가 미확정/`other`이고 일부 행이 미일치하면, PO에만 있던 부분 인식 보완이 PI/CI에는 적용되지 않아 일치 상품의 가격까지 건너뛰었다. `agent/pricing.py`의 분류 보완 조건을 PI/CI의 확인된 거래처에도 적용한다. 일치한 행만 해당 구매자의 판매가격을 조회하고 미일치 행은 확인 대상으로 남긴다. 명시된 통화를 변경하거나 PO의 KRW 매입가격을 PI/CI에 대입하지 않는다.

이후 CI 가격 정책을 명확히 분리했다. PI 생성 시 Dear Glow 판매 카탈로그를 사용할 수 있지만, CI는 반드시 첨부된 PI의 거래 단가를 보존하며 첨부 PI가 없으면 CI 내보내기를 차단한다. CI와 PL의 ECLADO 제품명·용량 매칭은 카탈로그 식별에만 사용하고 가격은 변경하지 않는다. PL에는 가격을 적용하지 않는다.

회귀 검증은 `tests/test_sale_partial_catalog.py`에서 PI/CI 분류 미확정+일부 미일치, 구매자 누락/타 구매자 보호, KRW 명시 시 매입가격 대체 금지, 실제 검토 화면의 미일치 행 단가 입력 요구를 다룬다. 이후 제공된 실제 PI JSON은 구매자 `dear glow`, 분류 `cosmetics`, 괄호 코드가 붙은 24개 상품이었다. 따라서 이 주문의 문제는 구매자 누락이나 `other` 분류가 아니다. 아래 배포 검증 결과를 따른다.

최종 검증: 수정 전 PI/CI의 `other` 분류 재현 테스트가 실패했고, 수정 후 화면 테스트를 포함한 **120개 테스트가 모두 통과했다(생략 없음)**. 실행 명령은 `uv run --offline --with streamlit python -m unittest discover -s Quotation_KEKOREA/tests`이며 작업 폴더 캐시 및 테스트 임시 파일 권한을 허용했다. `git diff --check`도 통과했다. 기존 Streamlit API 경고는 유지된다.

2026-11-03 실제 배포 재현: `https://ke-korea.streamlit.app/`의 독립 세션에 실제 사용자 주문 대신 가상의 Dear Glow PI 한 행을 사용했다. `Cell Memory Cream`, `50g`, 수량 1은 USD 판매가격에 연결됐다. 같은 초안의 이름을 `Cell Memory Cream (E-165)`로 정정하고 단가를 비운 뒤 적용하면 가격 연결이 실패했다. 새 추출 결과에도 최신 스키마의 `product_code` 필드가 없었다. 단가 원문과 연락처는 검증 로그에 출력하지 않았다. `tmp/verify_live_pi_matcher.py`가 이 검증을 재현한다.

배포 소스 정보 조회에서는 저장소 `swihm1989-ship-it/ke_korea_co_ltd`, 브랜치 `main`, 진입점 `Quotation_KEKOREA/app.py`를 확인했다. 같은 시점 GitHub main의 `pricing.py`에는 새 `match_product` 호출이 있고 `extractor.py`에는 `product_code` 스키마가 있었다. 즉 저장소의 수정과 실제 실행 중인 앱 사이의 버전 불일치가 확인됐다. 정확히 어떤 배포/프로세스 캐시 단계가 갱신되지 않았는지는 아직 확정하지 않았다. 브라우저 연결 호스트가 없어 관리자 재부팅은 수행하지 못했다. 앱 Reboot/재배포 후 동일한 괄호 코드 검증이 통과하기 전까지 배포 문제가 해결됐다고 기록하지 않는다. 이 증상을 새 상품명 오류로 단정하고 매칭/가격 정책을 추가 완화하지 않는다.

재부팅 후 실제 배포 검증: 사용자가 Reboot 완료를 알린 뒤 같은 독립 가상 PI 검증을 재실행했다. 새로 추출된 한 행에 `product_code` 필드가 포함됐고 USD 판매가격이 연결됐다. 이어 그 행을 `Cell Memory Cream (E-165)`/`50g`로 정정하고 단가를 비운 뒤 적용해도 `master_price=true`와 USD 판매가격 연결이 유지되는 것을 확인했다. 따라서 재부팅 전 실패했던 괄호 코드의 PI 가격 연결은 현재 배포 앱에서 정상화됐다. 제공된 24개 상품 전체는 로컬에서 검증한 범위이며, 재부팅 후 실제 배포 검증은 가상 한 행이다. 실제 주문 이미지 재전송, PDF 발행, 주문/발송은 하지 않았다. 첫 재검증은 검증 스크립트의 대기 시간이 짧아 결과를 받기 전에 종료됐으므로 이를 제품 오류로 집계하지 않았다. 충분한 대기 후 검증 스크립트가 성공 종료했다.

### 2026-11-03 비공개 거래처 디렉터리

사용자가 제공한 Dear Glow 정보를 `public.kekorea_counterparties`에 저장했다. `DEAR_GLOW` 키로 법인명과 `Dear Glow`/`Dearglow` 별칭, 담당자, 회사 주소, 별도로 명시한 배송지와 배송지 전화 N/A를 보관한다. 회사 전화·이메일은 제공되지 않았으므로 추측하거나 N/A로 바꾸지 않는다. 개인 연락처와 배송지 원문은 Git/README/테스트에 복사하지 않는다. 원본은 Git에서 제외된 `private/counterparties/companies.sqlite3`에도 준비해 두었다.

초기 테이블 생성은 `supabase/migrations/202611030001_counterparties.sql`을 사용자가 SQL Editor에서 실행했다. 이 대화의 Supabase SQL 도구는 노출되지 않았으므로 SQL 실행을 에이전트가 했다고 기록하지 않는다. 테이블에 RLS를 활성화하고 PUBLIC/anon/authenticated 접근을 회수했으며, 서버 역할에 SELECT/INSERT/UPDATE만 부여한다. 저장 명령은 `python Quotation_KEKOREA/scripts/save_company_profile.py --company-key DEAR_GLOW`다. 기존 회사 행의 미제공 필드는 유지하며 다른 회사 행은 수정하지 않는다. 저장 응답과 독립 GET으로 내용 일치를 검증했고, 공개 키의 조회는 HTTP 401로 거부됐다.

`agent/counterparties.py`는 법인명/등록 별칭을 식별하여 PI/CI/PL에서는 구매자, PO에서는 공급처 정보를 채운다. 대상 이름이 비어 있을 때만 명령문의 유일한 등록 거래처명을 보조 근거로 사용한다. 다른 거래처가 명시되거나 별칭이 중복되면 임의로 적용하지 않는다. 등록 주소를 배송지로 추측하지 않으며, 명시적으로 등록한 기본 배송지만 판매 문서에 사용한다. PO의 배송지는 공급처 배송지로 대체하지 않는다. 기존 KE KOREA 정보, 가격·통화·상품·수량·포장 검증은 유지한다.

DB 데이터는 추출 후 서버에서 적용하며 저장된 연락처를 AI 프롬프트에 추가해 보내지 않는다. 주문에 명시된 주소/담당자/배송지와 N/A는 DB 기본값보다 우선한다. DB가 채운 필드는 출처를 추적하여 거래처 변경 시 다른 회사 자료가 남지 않게 한다. DB 조회 장애가 나더라도 이미 검토 중인 동일 거래처의 저장 정보와 사용자가 직접 입력한 법인명은 지우지 않는다. 회사 레코드는 60초 캐시한다. 테이블/연결 장애 시에는 경고하고 직접 입력 경로를 유지한다.

검증: 당시 가상 회사 정보만 사용하는 **134개 전체 테스트가 통과했다(화면 테스트 포함, 생략 없음)**. DB 저장/재조회, 별칭 명령 자동 입력, PI/PO/CI 검토 화면, 명시 값 우선, 거래처 변경/중복/미일치, 회사 주소와 배송지 분리, DB 장애 시 문서 보존, 기존 기능을 검증한다. 독립 검토에서 지적된 DB 장애 시 법인명 소실은 실패 테스트로 재현 후 수정했고, Windows SQLite 연결을 명시적으로 닫는 것도 검증했다. `git diff --check`를 함께 실행한다.

배포 상태: 거래처 **데이터는 실제 Supabase에 저장 완료**했지만 자동 입력 코드의 커밋/배포 및 실제 배포 앱 자동 입력 검증은 아직 하지 않았다. DB의 비공개 권한과 앱 화면의 접근 제어는 별개다. 현재 앱은 로그인 없이 접속되므로, 연락처/배송지 자동 조회 기능을 배포할 때에는 앱 이용 대상과 접근 제한을 먼저 확인해야 한다. 저장 성공만으로 배포 앱의 자동 입력이 동작한다고 안내하지 않는다.

### PO에 `Cannot calculate`가 표시될 때

1. `Items to confirm`의 실제 오류를 확인한다. 수량, 단가, 할인율, 통화 오류를 구분한다. 일반 정보 누락으로 파일 생성이 막히는 것과 수치 계산 오류를 혼동하지 않는다.
2. 0 수량은 유효하다. 수량 0만을 이유로 `Quantity required`/`Cannot calculate`가 표시되면 회귀 오류다.
3. ECLADO PO는 매입가격과 KRW를 확인한다. 명시된 다른 통화를 몰래 KRW로 바꾸거나 판매가격으로 대체하지 않는다.
4. 상품명과 용량의 추출 결과를 원본 및 카탈로그와 대조한다. 확정되지 않은 상품/용량의 가격은 추측해서 채우지 않는다.
   - 알려진 ECLADO 공급처의 제품 분류가 미확정/`other`인 경우, 정확히 일치한 상품이 있으면 화장품으로 재분류하고 일치한 행부터 매입가격을 적용한다. 나머지 상품의 미일치 오류는 유지한다. 다른 한글 공급처를 공급처 누락으로 취급하지 않는다.
5. 오류가 남으면 해당 행의 추출값과 오류 문구를 확인한 뒤 수정한다. 계산이 되게 하려고 검증 전체를 끄지 않는다.

배포 PO에서 가상의 수량 0과 5를 합산하고 KRW 금액을 정상 표시하는 것을 확인했다. 로컬 회귀 테스트는 PO 매입가격, 0 행의 금액, 명시된 통화 유지까지 함께 검증한다. 이는 사용자의 현재 브라우저 세션에서 어떤 값이 추출됐는지까지 증명하지 않는다.

## 1. 이해한 목표

KE KOREA CO. LTD의 실제 거래 정보를 받아 제품군에 맞는 Purchase Order(PO), Proforma Invoice(PI), Commercial Invoice(CI), Packing List(PL)를 각각 별도 파일로 생성한다.

- PO: KE KOREA가 구매자로서 공급처에 보내는 발주서.
- PI: KE KOREA가 판매자로서 구매처에 보내는 거래 조건·대금 안내 문서.
- CI / PL: 실제 선적 자료를 반영하는 통관 제출용 상업송장·포장명세서.
- 주력 제품: ECLADO 화장품, Polysilicon, Wafer, Solar Cell, Solar Module.
- 기타 제품도 제품 분류와 서식 프로필을 추가하여 지원한다. 미등록 제품에 기존 서식을 무조건 적용하지 않는다.
- 입력: 직접 타이핑, 이메일 복사·붙여넣기, 거래처 대화 캡처, PDF 및 향후 허용하는 첨부 파일.
- 출력 추천: 발송·인쇄용 PDF와 수정 가능한 Excel(XLSX). 지원 형식은 구현 전에 확정한다.
- 소스 코드와 서식 정의는 Git에서 관리한다. 실제 거래 자료와 발행 결과물은 별도 보관한다.
- **모든 업무 산출물은 영문이다.** 중국어·인도네시아어·한국어·영어 거래 입력을 GPT가 해석하여 번역하고, 문서의 제목·표·날짜·조건·REMARK·금액을 영어로 작성한다. 중국어 회사명과 주소만 `中文原文 (English translation)` 형식으로 원문을 병기한다. 번역은 원문 근거와 함께 검토하며, 등록 영문 법인명이라고 추측하지 않는다.
- 원자재는 제품명·가격·선적 조건을 거래별로 입력하고 확인한다. 화장품은 제공된 가격표를 기준 마스터로 사용하고, 선택한 할인·행사 조건을 거래별로 적용한다.

### ECLADO 가격표 및 SQL 준비 현황 (2026-10-30)

- 두 XLSX의 본품·장비/부속품 포함 카탈로그 131개와 별도 샘플 26개, 총 157개를 읽었다. 제품별 구매가 157건과 Dear Glow 기준 판매가 157건을 SQL 데이터로 준비했다.
- 매입가는 KRW 파일의 `UNIT Price(\\)` 열(N), 본품 판매가는 바이어용 파일의 KE KOREA → OLIVIA 가격 열(N)을 사용한다. KRW 파일의 `Dear Glow Price` 열(P)과도 대조했다. 소매가·도매가·환율 환산 매입가와 구분한다.
- 본품 판매가는 USD, `Sample` 시트의 판매가는 KRW다. 샘플 용량은 원본에 없으므로 본품 용량을 복사하지 않는다.
- 10% 할인 열은 기준가 × 0.9와 일치했다. 10%를 영구 적용하지 않고, 거래에서 선택한 할인율을 기준 판매가에 한 번 적용한 가격이 최종 청구 단가가 된다.
- 2+1·3+1 자동 계산 및 향후 인보이스 반영은 가능하다. `무상 수량 = floor(유상 수량 / 구매 기준 수량) × 증정 수량`, `실제 선적 수량 = 유상 + 무상`으로 분리한다. 할인과 행사 중복 적용은 명시적으로 선택하며, 다른 제품 증정·품목 혼합 행사는 별도 규칙이 필요하다.
- 무료 증정품은 영문 `Free of Charge (FOC)` 행으로 구분하고 PL 수량에는 포함한다. CI의 신고가액은 청구액과 분리된 확인값으로 관리한다. 현재는 산식과 설계 및 SQL 예시까지이며, 행사 엔진·인보이스 렌더러가 구현된 상태는 아니다.
- 코드 `73568`은 서로 다른 Toner와 Cream에 중복된다. 코드·제품명·용량·본품/샘플 구분으로 별도 제품 ID를 생성했다. 코드만으로 병합하지 않는다.
- `MK-2`의 포장 중량·박스 크기에는 비정상 계산값이 있어 `needs_review`로 표시했다. 가격표 포장 정보는 참고값이며 실제 선적·포장 정보로 자동 확정하지 않는다.
- [SQL 적용 순서·테이블 설명·검증 안내](supabase/README.md), [스키마 SQL](supabase/migrations/202610300001_eclado_catalog.sql), [비공개 실제 가격 데이터 SQL](private/eclado/002_eclado_catalog_seed.sql).
- 실제 가격 seed와 원본 분석 보고서는 Git에서 제외했다. 목표 프로젝트는 `YOUR_PROJECT_REF`이며 아직 연결·적용하지 않았다.

## 2. 현재 확인한 프로젝트

실제 참고 폴더명은 `07_function_calling-main/SeokwonIhm`이다. 사용자 표현의 SeokwonIHm 폴더에 해당한다. `Quotation_KEKOREA`는 확인 당시 비어 있었으며 새 업무용 프로젝트의 위치로 사용한다. 학습 자료 원본은 수정하지 않는다.

Python 함수 호출, LangChain 도구 연결, Pydantic 검증, MCP 연동, 요청별 분기와 비동기 작업 예제가 있다. 기존 `pyproject.toml`에는 Python 3.12 이상과 관련 패키지가 선언되어 있다. 선언된 의존성을 새 프로젝트의 검증된 실행 환경으로 간주하지 않으며, 업무용 의존성은 별도로 선정·고정한다. 이번에는 학습 코드의 외부 API를 실행하지 않았다.

| 참고 위치 | 확인한 기법 | 업무용 적용 계획 |
| --- | --- | --- |
| `01_tool_intro/03_return_tool_result.py` | 도구 요청, 실제 함수 실행, 호출 ID에 연결한 결과 반환 | 모델이 파일 생성을 말하는 것과 실제 생성 성공을 구분 |
| `02_tool_contracts/03_validate_tool_call.py` | 입력·결과의 엄격한 Pydantic 검증 | 수량·단가·통화·문서 유형 및 거래 ID 검증 |
| `03_tools_and_api/03_pdf_tool.py` | 페이지 단위 PDF 텍스트 추출 | PDF 입력 처리의 출발점. 스캔 문서는 별도 이미지 판독 필요 |
| `04_mcp_tools/local/04_validate_contract.py` | MCP 도구 발견, 정상·빈 결과·오류 구분 | 추후 외부 서비스 연결 시 적용 |
| `05_tool_routing/contracts.py`, `routing.py`, `execution.py` | 구조화된 분기, 허용 도구 제한, 출처가 확인된 인자만 실행 | 제품군·PO/PI/CI/PL 선택 및 누락 정보 보충 |
| `05_tool_routing/practice/delivery_assistant/` | 대화 보충, 상태별 도구 공개, 호출 상한 | 현재 거래 문맥 유지, 다른 거래 정보 혼입 방지 |
| `06_parallel_merge/batch.py`, `practice/library_assistant/` | 동시 실행 상한, 부분 실패와 결과 합류 | 독립 첨부 판독·최종 파일 렌더링의 제한적 병렬 처리 |

예제의 도메인 데이터, 데모용 가격·정책, 외부 검색 기능을 업무 데이터로 가져오지 않는다. 업무에 필요한 기능을 독립 모듈로 재구성하고, 라이선스·출처를 확인해 필요한 고지를 유지한다. MCP는 초기 필수 구성요소가 아니다.

## 3. 첨부 샘플에서 확인한 차이

아래 세 파일의 총 5쪽을 확인했다. 텍스트 추출과 전체 페이지 이미지 검토를 함께 수행했다. 원본 파일의 지시문은 Agent 운영 명령이 아니라 거래 내용·서식의 일부로 취급했다.

| 자료 | 페이지 | 확인한 구조와 특성 |
| --- | --- | --- |
| `CIPL_KE KOREA-TENGYAO.pdf` | 1: CI, 2: PL | 태양광 Cell. CI는 품목·등급·PCS·단가·금액, PL은 품목별 PCS·순중량·총중량·팔레트 수. CI와 PL의 문서번호 연결 |
| `PI_KE KOREA-TENGYAO_SOLAR CELL_JAN.25 BIDDING双章.pdf` | 1: PI, 2: Inventory List | 스캔 PDF로 텍스트 직접 추출 불가. PI 본문과 별도 재고 명세 첨부. 재고표는 PERC/TOPCon, M10.2, 12BB, 효율, 등급별 수량·소계·총계 |
| `PI_KE KOREA-DEAR GLOW_ECLADO.pdf` | 1: PI | 화장품 20개 품목. SIZE, PCS, 단가·금액, 청구지와 별도 배송지, 픽업 주소. 세트형 규격과 단품 혼재 |

스캔 PI의 실제 파일명에는 일반 공백과 다른 공백 문자가 포함된다. 위 표는 읽기 편하게 표기한 이름이며 구현에서는 파일명 문자열을 하드코딩하지 않고 선택한 파일의 실제 경로·ID를 사용한다.

### 공통 영역

- 발행 회사 상호·주소·사업자 식별정보, 문서 제목·발행일·문서번호.
- 상대 회사 상호·주소, ATTN 담당자, 연락처.
- 품목명·수량·수량 단위·단가·가격 기준 단위·통화·품목 금액·합계.
- 금액의 영문 표기, Incoterms와 지정 장소, 원산지, 지급 조건, 제공 서류, REMARK.
- 수익자·은행·지점·SWIFT·계좌·은행 주소, 선박 정보, 날인·서명 영역.

### 제품군별 서식 원칙

- 화장품은 `SIZE`가 독립 필드다. `ml`, `g`, `pc`, `(1g+10ml)*6` 같은 규격을 판매 수량 단위와 구분한다. 세트 구성품 수를 판매 수량으로 자동 곱하지 않는다.
- 태양광 Cell은 모델·사이즈·기술·버스바·효율·등급 및 재고 상세 첨부를 지원한다. 상세 재고를 단가가 동일한 송장 품목으로 묶는 규칙은 명시적으로 관리한다.
- 태양광 서식을 Polysilicon, Wafer, Module에 그대로 복제하지 않는다. 각각 순도·형태, 두께·사이즈, 출력·모델·시리얼 등 제품 프로필을 별도로 설계한다. 이 세 제품의 상세 서식은 이번 샘플에서 확인되지 않은 제안이다.
- PL은 실제 포장 단위, 순중량·총중량, 박스·팔레트 구성을 관리한다. 샘플의 품목별 요약 외에 필요한 포장 상세를 확장할 수 있어야 한다.
- 긴 주소·다품목·긴 REMARK는 자동 줄바꿈·페이지 나눔을 처리하고, 후속 페이지의 품목 헤더와 합계·서명 영역이 겹치지 않게 한다.

### 그대로 복사하면 안 되는 샘플 정보

- 같은 TENGYAO 거래에서 PI는 `EXW KOREA`, CI/PL은 `FOB BUSAN, SOUTH KOREA`다. 문서 단계별 실제 조건을 저장하고 차이를 표시한다. 어느 문서가 맞는지 AI가 임의로 결정하지 않는다.
- 태양광 PI의 보증금은 소수 셋째 자리까지 기재되어 있고 CI에는 다른 정밀도의 보증금·잔금이 있다. 통화 표시 자릿수와 결제 분할 반올림을 분리하고 차이는 확인 대상으로 남긴다.
- 송장 본문의 등급 `RMW`와 Inventory List의 `RWM` 표기가 다르다. 원문과 정규화 후보를 모두 보존하고 사용자가 확인한 매핑만 적용한다.
- 상대방의 ATTN 담당자가 법적 대표자라는 근거는 없다. 담당자와 대표자를 별도로 저장한다.
- 샘플에 없는 전화번호·이메일·대표자·HS Code·실제 운송 정보는 추측하지 않는다.
- 샘플의 원산지·은행 계좌·주소·과거 단가·선적 조건은 새 거래의 자동 확정값이 아니다. 승인된 회사·제품 마스터의 후보값으로만 등록한다.
- 과거 문서의 도장·서명을 새 거래 문서에 자동 복사하지 않는다. 승인된 별도 자산과 사용 절차를 정한 뒤 적용한다.
- PO 샘플 및 화장품 CI/PL 샘플은 제공되지 않았다. 해당 문서는 요구사항 기반 초안을 만든 뒤 사용자 서식 검토가 필요하다.

원본 위치: 사용자가 지정한 `Y2026/2026년/1~2분기/Deal 1_Hanwha Cell Auction_Tengyao/` 및 `Y2026/2026년/3분기/Deal 6_ECLADO-DEAL GLOW/`. 원본 PDF나 전체 거래처·계좌 정보는 이 README에 복제하지 않았다.

## 4. 사용 방식 비교와 추천

| 방식 | 사용자 경험 | 장점 | 고려할 점 |
| --- | --- | --- | --- |
| VS Code의 대화형 코딩 도우미 + 문서 생성 엔진 | 자료를 주고 생성 요청, 생성 파일 열기 | 초기 서식·계산 검증이 빠르고 별도 UI 개발 없이 시작 가능 | 개발 도구와 실행 환경에 의존. 업무 기록·입력 수정·반복 사용 화면은 별도 설계 필요 |
| 로컬 브라우저 UI + 동일 엔진 | 아이콘 실행 → 붙여넣기/파일 선택 → 추출값 확인 → 다운로드 | 비개발자 반복 업무에 적합. 외부 서버 운영 없이 시작 가능 | PC에서 앱 실행 필요. 이미지 판독에 외부 모델을 쓰면 입력 일부는 API로 전송됨 |
| 로그인 가능한 사내 웹 앱 | 브라우저 접속, 거래 이력·공동 작업 | 여러 직원·기기 사용에 유리 | 인증·권한·서버·백업·동시 편집 등 운영 범위 확대 |

**추천안:** 먼저 VS Code에서 동일 엔진으로 샘플 재현·검증을 하고, 일상 업무에는 1인용 로컬 브라우저 UI를 제공한다. UI 초기 후보는 Python 기반 Streamlit이다. 업로드, 표 수정, 다운로드 위젯을 지원해 기존 Python 자료와 연결하기 좋다. 이는 이번 설계자의 추천이며 사용자 선택 완료를 뜻하지 않는다.

VS Code에서도 필요한 생성 코드를 구현하고 실행하여 PDF/XLSX를 작업 폴더에 저장하고 파일 경로로 전달할 수 있다. VS Code 편집기 자체가 송장 생성 기능을 제공하는 것은 아니며, 생성 엔진·서식·실행 환경이 필요하다. 이 구조로 만들면 UI가 바뀌어도 같은 문서 생성 로직을 사용할 수 있다.

초기 사용 범위 제안은 Windows PC의 단일 사용자다. 여러 직원의 동시 사용·휴대전화 접속은 이후 사내 웹 앱 단계로 분리한다. 로컬 UI는 로컬 처리 전용 AI를 의미하지 않는다. 사용할 모델과 외부 전송 허용 범위는 구현 시작 전에 정한다.

공식 기능 참고(2026-10-30 확인): [Streamlit 파일 업로드](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader), [입력·표 편집 위젯](https://docs.streamlit.io/develop/api-reference/widgets), [파일 다운로드](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button).

## 5. 사용 흐름

1. 새 거래 또는 기존 거래를 선택한다. 제품군과 생성할 문서 종류를 선택하거나 AI의 추천을 확인한다.
2. 이메일·대화 내용을 붙여넣고 캡처/PDF를 첨부한다. 한 거래에 여러 입력을 추가할 수 있다.
3. AI가 구조화된 거래 초안을 만든다. 각 값의 출처, 원문, 파일·페이지 또는 이미지 위치, 불확실 여부를 함께 보관한다.
4. 화면에서 거래 당사자, 품목·가격, 결제·선적, 포장 정보를 확인·수정한다. 누락·상충 항목을 질문으로 모은다.
5. 프로그램이 단위·금액·수량·문서 간 일치 여부를 계산·검증한다. 수정 시 이전 확인 상태를 해제한다.
6. 초안 PDF/XLSX를 생성하여 미리 확인한다. 불완전한 초안은 DRAFT 상태와 누락 항목을 표시한다.
7. 필요한 정보와 검증을 완료한 뒤 사용자가 확정한다. 확정본은 데이터·서식 버전과 함께 저장하고 다운로드한다.
8. 수정 발행은 새 리비전으로 보존하며 기존 확정본을 덮어쓰지 않는다.

예: “첨부한 이메일과 캡처로 ECLADO PI 초안을 만들어줘” → 제품과 수량·가격 추출 → 배송지 누락 질문 → 사용자 보충 → 금액 검증 → 미리보기 → PDF/XLSX 제공.

이메일 전송, 세관 시스템 제출, 주문 실행, 인터넷에서 거래 조건 자동 채우기는 초기 범위에 포함하지 않는다. 파일 생성 성공과 상대방 전달·통관 완료를 구분한다.

## 6. 공통 데이터 설계

| 데이터 묶음 | 필드 |
| --- | --- |
| 거래 및 문서 | 내부 거래 ID, 구매/판매 구분, 문서 유형, 문서번호, 발행일, 개정번호, 상태, 연결 PO/PI/CI/선적 ID, 서식 ID·버전, 출력 언어 `en` 고정 |
| 회사·사람 | 법인 상호, 주소, 국가, 사업자 식별번호, 대표자, 담당자, 전화, 이메일. 구매자·판매자·수하인·청구지·배송지·픽업지·필요 시 통지처를 별도 역할로 저장 |
| 품목 | 내부 제품 ID, 제품군, 브랜드, 제품명, 규격, 모델, 등급, 수량, 수량 단위, 단가, 가격 기준 단위, 통화, 원산지, 확인된 경우 HS Code |
| 화장품 상세 | 용량·규격, SKU, 세트 구성, 필요 시 LOT·제조일·유효기간·포장당 입수량 |
| 태양광 상세 | 재료·기술·규격, 등급, 순도/두께/효율/출력 등 제품별 속성, 필요 시 LOT·시리얼·재고 명세 첨부 |
| 금액·지급 | 품목 금액, 할인, 운임, 보험, 기타 비용, 적용되는 세금, 최종 총액, 금액 영문 표기, 선금·잔금·기일·지급 조건, 수익자 및 은행 프로필 |
| 운송 | Incoterms 규칙·버전(확인 시)·지정 장소, 선적지·도착지, 운송 수단, 예정/실제 일자 구분, 선박·항차, B/L 또는 AWB, 컨테이너, 픽업 일자·주소 |
| 포장 | 포장 ID·형태·번호, 박스/팔레트 계층, 품목별 포장 배분 수량, 순중량·총중량·단위, 크기·부피·단위, Shipping Marks |
| 기타·출처 | REMARK 원문, 제공 문서, 승인된 날인 자산 참조, 출처 ID·페이지·원문, 추출 상태, 사용자 확인 기록 |

필드가 존재한다고 모든 문서의 필수 항목인 것은 아니다. 제품군·문서 유형·목적지·거래 조건별 요구 프로필로 필수성을 결정한다. 초기 프로필은 업무상 검증 규칙이며 국가별 법규 준수의 자동 판정을 의미하지 않는다.

### 방향과 가격을 분리

- PO는 KE KOREA가 구매자, 공급처가 판매자다. 공급처의 매입 단가·결제 조건·필요한 수취 계좌를 사용한다.
- PI/판매 CI는 KE KOREA가 판매자다. 구매처에 제시한 매출 단가·조건과 KE KOREA의 승인된 수취 계좌를 사용한다.
- 같은 프로젝트라도 구매와 판매는 별도 거래 데이터로 연결한다. 매입 가격이나 공급처 내부 조건이 판매 문서에 섞이지 않게 한다.
- Buyer와 Consignee가 다를 수 있다. 샘플의 CONSIGNEE 표제를 모든 거래의 구매자 역할로 강제하지 않는다.
- 발행 시점의 회사·제품·은행 정보를 스냅샷으로 남겨 마스터 수정이 과거 발행본에 영향을 주지 않게 한다.

### 문서별 초안과 확정 조건

| 문서 | 초안 작성의 중심 입력 | 확정 전 확인 사항 |
| --- | --- | --- |
| PO | 공급처, 제품·규격, 매입 수량·가격·통화, 납품·결제 조건 | 공급처/구매자 역할, 발주 번호·납기·인도 장소·추가 비용 |
| PI | 구매처, 판매 품목·수량·가격·통화, 결제·선적 조건 | 청구지/배송지, 수익자, 유효기간 필요 여부, 누락된 조건 |
| CI | 연결 거래·선적, 실제 출고 품목·수량·가격, 확정 조건 | PI와 달라진 수량·금액·조건, 적용 프로필의 운송·원산지 정보 |
| PL | 실제 품목·출고 수량, 포장 수·순중량·총중량 | 품목별 포장 배분, 무게·단위, CI 수량·선적·수하인 일치 |

일부 선적을 지원하기 위해 거래 1건에 선적 N건을 연결한다. 각 CI/PL은 특정 선적의 동일한 데이터 스냅샷을 사용하고, 누적 출고량과 미출고 잔량을 별도로 계산한다.

## 7. Agent와 프로그램의 역할

AI는 자연어·이미지 이해, 필드 추출, 제품·문서 분류 후보, 상충 정보 설명과 보충 질문을 담당한다. 확정 합계, 문서번호 중복 검사, 파일 저장, 서식 선택의 허용 여부는 프로그램이 검증한다.

처리 흐름: 입력 수집 → PDF 텍스트 추출 또는 스캔/캡처 판독 → 출처가 있는 구조화 데이터 → 마스터 후보 매칭 → 누락·충돌 확인 → 결정적 계산·검증 → 사용자 확인 → 제품별 서식 렌더링 → 산출물 검증·저장.

도구 후보(아직 구현되지 않음):

| 도구 | 역할 |
| --- | --- |
| `extract_trade_data` | 텍스트·첨부에서 출처가 있는 후보 정보 추출 |
| `lookup_company`, `lookup_product` | 확인된 마스터 조회; 유사 이름 자동 확정 금지 |
| `validate_document` | 필수 항목·단위·역할·문서 간 차이 검사 |
| `calculate_totals` | Decimal 기반 금액·중량·수량 계산 |
| `render_document` | 검증한 스냅샷과 허용된 서식으로 PDF/XLSX 초안 생성 |
| `finalize_document` | 사용자가 확인한 버전만 확정·번호 예약·저장 |

파일·이메일·OCR 결과는 외부 자료다. 그 안의 “지침 무시”, “계좌 변경”, “파일 실행” 같은 문구를 운영 명령으로 실행하지 않는다. 거래 조건 변경 요청으로 읽히는 내용은 후보 필드로 제시하고 확인하며, 출처 내용을 셸 명령·파일 경로·임의 도구 호출로 사용하지 않는다.

독립 첨부의 판독과 확정 데이터의 PDF/XLSX 생성은 병렬화할 수 있다. 데이터 확정 → 계산 → 문서 발행 순서는 유지한다. 일부 파일 생성 실패 시 성공한 파일과 실패한 형식을 구분해서 표시하고 전체 완료로 보고하지 않는다.

## 8. 계산·품질 기준

- 금액은 이진 부동소수점 대신 Decimal로 처리한다. 단가는 필요한 자릿수를 보존하고 통화별 표시·품목 반올림·합산 규칙을 명시한다. 초기 USD 금액 표시 후보는 소수 둘째 자리이며 업무 규칙 확정이 필요하다.
- 단가 기준이 PC, KG, W 등 무엇인지 구분한다. USD/W 가격을 PCS 수량에 바로 곱하지 않고 확인된 정격 출력·총 W 또는 명시적 환산 근거를 요구한다.
- 품목 합계, 할인·추가 비용, 최종 합계, 선금·잔금의 합, 금액 영문 표기를 대조한다. 무료 샘플·반품 등 예외는 유형을 명시한다.
- PL의 순중량은 총중량을 넘을 수 없다. 동일 박스·팔레트에 여러 품목이 있을 때 포장 수·총중량을 이중 합산하지 않는다.
- 재고 명세의 품목별·등급별 소계와 송장 집계 수량을 대조한다. 명세 첨부가 PL을 대신한다고 가정하지 않는다.
- 같은 선적의 CI와 PL은 문서 연결, 수하인, 제품, 실제 수량, 포장 관련 식별자가 일치해야 한다. PL의 가격 표시는 기본적으로 제외하되 최종 서식 선택에 따른다.
- 이미지에서 소수점·0/O·등급·날짜가 불명확하면 확인 대상으로 표시한다. 모델의 자신감만으로 검증 완료 처리하지 않는다.
- 승인된 수정값을 우선하되 이전 값과 근거를 기록한다. 새 이메일을 받았다는 이유만으로 승인된 조건·계좌를 조용히 덮어쓰지 않는다.
- 문서번호는 내부 거래 ID와 구분한다. 기존 `006_TC_0011` 같은 번호의 의미를 추정해 자동 증가시키지 않는다. 초기에는 수동 입력+중복 확인, 이후 승인한 자동 채번 정책으로 확장한다.
- 재실행 시 동일 확정 요청에 문서번호·발행본이 중복 생성되지 않게 한다. 발행본과 개정본은 구분한다.
- PDF는 폰트 포함 여부·누락·잘림·페이지 나눔을 시각 검토한다. XLSX와 PDF는 동일 스냅샷·동일 계산 결과를 사용한다.

## 9. 프로젝트와 저장 구조 제안

아래는 향후 구현 구조이며 이번에 이 폴더들을 생성했다는 의미는 아니다.

```text
Quotation_KEKOREA/
  README.md
  pyproject.toml / lock file
  .env.example                  # 변수명만, 실제 키 없음
  app/                          # 로컬 브라우저 UI 또는 CLI
  agent/                        # 추출·분류·대화·도구 호출
  domain/                       # 데이터 스키마·계산·검증·상태 전이
  tools/                        # 조회·판독·문서 생성 도구
  templates/
    cosmetics/                  # PO / PI / CI / PL
    solar/                      # 제품 하위 프로필 및 문서별 서식
    registry.*                  # 제품군·문서 유형·서식 버전 매핑
  renderers/                    # PDF / XLSX, UI와 독립
  tests/fixtures/               # 익명화한 합성 검증 자료
  private/                      # 실제 입력·마스터·거래 DB, Git 제외
  outputs/                      # 생성 문서·발행 스냅샷, Git 제외
```

추천 기술 구성: Python + Pydantic + Supabase PostgreSQL의 제품·가격 마스터 + PDF/XLSX 렌더러 + 구조화된 모델 추출. 사용자가 Supabase 프로젝트를 지정하여 기존 로컬 마스터 제안을 변경했다. PDF 생성은 ReportLab 등, Excel 생성은 openpyxl 등으로 구현 가능하며 렌더링 품질을 보고 최종 선정한다. UI는 Streamlit 후보, 모델 제공자·모델·요금·버전은 아직 미선정이다. 불필요한 웹 검색·다중 Agent를 초기 기본 흐름에 넣지 않는다.

제품·가격 마스터는 Supabase에 저장할 SQL을 준비했다. 거래·문서 상태까지 Supabase로 통합할지, 로컬 캐시를 함께 사용할지는 구현 단계에서 정한다. 발행본은 데이터 스냅샷·서식 버전·파일 해시·생성 시각을 함께 저장한다. 저장은 트랜잭션과 임시 파일 후 이동을 사용하고, 실패한 생성 상태를 복구할 수 있게 한다.

Git에는 코드, 익명화한 서식, 합성 테스트, 설정 예시, 문서를 저장한다. 실제 회사·거래처 연락처, 은행 계좌, 거래 단가, 대화 캡처, 원본 PDF, 도장·서명 자산, DB, 생성물, API 키·`.env`, 로그는 추적 대상에서 제외한다. 구현 시작 시 `.gitignore`를 먼저 설정하고 기존 추적 여부도 확인한다. 과거 자료를 테스트에 쓰려면 별도 비공개 보관과 접근 범위를 정한다.

API 기반 판독을 선택하면 어떤 자료가 외부로 전송되는지 표시한다. 원문·계좌·연락처를 진단 로그에 그대로 남기지 않고, 모델 호출 타임아웃·횟수 상한을 둔다. 발행 문서와 DB는 별도 백업·복원 절차가 필요하다. OneDrive의 자동 동기화만을 데이터베이스 일관성 백업으로 간주하지 않는다.

## 10. 구현 순서와 검증 기준

1. **회사·서식 기준 확정:** 회사/은행 프로필, 실제 사용할 출력 형식, PO 및 화장품 CI/PL 초안, 채번·금액 규칙을 정한다. 원본 XLSX 등 편집 가능한 샘플이 있으면 재사용 가능성을 확인한다.
2. **문서 엔진 우선:** AI 없이 구조화된 입력으로 ECLADO PI와 태양광 PI·CI·PL을 생성한다. VS Code에서 실행하여 PDF 레이아웃과 계산을 검증한다.
3. **공급처 PO와 제품 프로필 확장:** 구매·판매 역할 분리, Polysilicon/Wafer/Module 프로필, 포장 계층·부분 선적을 검증한다. 새 서식은 초안으로 시작해 확인 후 사용한다.
4. **AI 입력 추가:** 붙여넣기, 캡처, 스캔 PDF를 연결하고 출처·상충·누락 확인 대화를 검증한다.
5. **로컬 UI 추가:** 업로드·수정·미리보기·다운로드와 재발행 이력을 연결한다. 사용자 관점의 실제 거래 시나리오로 검증한다.
6. **운영 확장:** 필요할 때 공동 사용·권한·서버 운영·외부 업무 시스템 연동을 설계한다.

구현 시 통과해야 할 핵심 시나리오:

- ECLADO의 20개 품목, 세트 규격, 별도 배송지·픽업지를 손실 없이 생성.
- 태양광 PI의 스캔 판독, Inventory List 집계와 RMW/RWM 충돌 표시.
- PI와 CI의 선적·결제 조건 차이를 보존하고 사용자에게 제시.
- 수량·단가·통화/가격 기준 단위 누락, 소수점 오독, 영문 금액 불일치 탐지.
- PO 매입가격·공급처 계좌가 판매 PI에 섞이지 않음.
- 실제 포장·중량 없는 PL은 확정본으로 발행하지 않음.
- 다품목·긴 주소·한글/영문 혼합 입력에서도 PDF 잘림·XLSX 인쇄 영역 오류 없음.
- 부분 선적의 CI/PL 수량 일치, 공유 팔레트 이중 집계 방지, 누적 출고량 검사.
- 수정 이후 재확인, 중복 발행 방지, 부분 실패·재시도·개정본 보존 확인.
- 외부 자료에 포함된 운영 지시를 실행하지 않고 거래 자료로만 처리.

현재 문서는 요구사항 분석과 설계이며, 위 검증이 통과했다는 보고가 아니다. 구현 후에는 합성 자료의 자동 검증과 승인된 실제 샘플의 비공개 시각 검토를 구분해 기록한다.


## 11. 사용자가 확정할 사항

- 초기 운영은 본인 PC의 단일 사용자로 시작한다.
- 결과물은 PDF+Excel을 우선 제공한다.
- 이미지·이메일 내용을 OpenAI API에 보내기 전에 화면에서 고지한다.
- 회사 서식, 은행 정보, 날인 자산, 자동 채번 정책은 확인 전까지 추측하지 않는다.

## 12. 1차 구현과 Supabase 연결 상태 (2026-10-30)

### 구현 범위

- `app.py`: Streamlit screen for typed transaction details and buyer order-image uploads. Users review extracted JSON, resolve blocking issues, and download PDF/XLSX/HTML drafts.
- `agent/extractor.py`: OpenAI Responses API structured extraction from transaction text and attached order screenshots. Prompt and images are sent only after the user clicks Extract.
- 입력 언어: 중국어·인도네시아어·한국어를 GPT가 해석해 영문 필드로 정리한다. 중국어 회사명·주소는 중국어 원문 뒤에 영문 번역을 괄호로 병기하고, 나머지 중국어는 영문만 남긴다. PDF는 중국어 글리프용 CID 폰트 인코딩으로 병기 이름·주소를 보존한다.
- KE Korea default profile for PI, PO, CI, and PL documents: `KE Korea Co. LTD`, `#1510, 157 Yangpyung Ro, Yungdeungpo Gu, Seoul, South Korea`, `Representative: DAVID, SEOKWON IHM`, phone `CONTACT_PHONE_CONFIGURED_IN_SERVER`, and email `CONTACT_EMAIL_CONFIGURED_IN_SERVER`. The profile is seller by default and buyer on PO; transaction-specific company details take priority. Documents use `assets/company_logo.png` in the header and the complete private seal image from `assets/image.png` in the signature area.
- `agent/pricing.py`: Supabase REST API에서 최신 `kekorea_catalog_imports` ID, ECLADO 제품, 해당 import의 매입가·판매가를 서버에서 조회한다. ECLADO 공급 PO에는 매입가만, Dear Glow 판매 PI/CI에는 해당 구매처 판매가만 exact match로 적용한다. 구매처·공급처/통화가 다르면 해당 가격을 쓰지 않는다.
- Supabase 신형 `SUPABASE_SECRET_KEY`는 HTTPS REST 요청의 `apikey` 헤더로만 전달한다. 브라우저 코드, URL, 로그에 키를 노출하지 않는다. Secret key는 전체 DB 접근 권한이 있으므로 Streamlit 앱 공개 범위를 반드시 비공개로 설정한다.
- Supabase 연결 설정이 없으면 개발용 로컬 seed를 사용할 수 있으나, Cloud에서는 seed를 Git에서 제외하므로 Supabase 비밀 키가 필요하다. Supabase 조회 실패 시 오래된 로컬 가격으로 조용히 대체하지 않는다.
- `agent/trade_documents.py`: Decimal 계산, 할인·FOC 분리, 거래 역할·통화·가격 기준·포장 검증. 필수값 누락/충돌이면 DRAFT 상태로 막는다.
- `agent/renderers.py`: English PDF/XLSX/HTML review drafts. Solar PI uses the corporate-blue header with the company logo and PI-only bank details.

### Supplier packing-list images

PL 검토·승인 로직은 `agent/packing_review.py`, 기존 합계 계산은 `agent/packing.py`로 분리한다. 검토 화면은 명시적 숫자 뒤의 단위(`100 PCS`, `10 kg`, `0.1 CBM`)와 `수량 x 규격FT Containers` 형식을 분리해 읽는다. 컨테이너 개수와 규격을 곱하거나 팔레트 수에서 컨테이너 수를 추측하지 않는다. 단위가 서로 충돌하면 수정을 요청한다.

합계가 다르거나 원본 합계가 비어 있고 행별 합계를 계산할 수 있으면 비교표와 `합계를 수정할까요?` 승인란을 표시한다. 승인은 계산된 합계에만 적용하며 원본 값을 `_packing_original_totals`에 보존한다. 다른 단위의 수량은 `_packing_approved_quantities`에 별도로 보존한다. 단가·상업송장 품목 수량·포장 행 자체는 변경하지 않는다. 승인 후 PDF 생성에는 나머지 필수 정보와 행 검증도 통과해야 한다. 원본 합계나 품목을 다시 수정하면 이전 승인과 이전 다운로드를 무효화한다.

2026-11-02 실제 배포 검증: 가상 PL 두 행에서 승인 전 PDF 생성 차단, 승인 후 계산된 CBM과 단위별 수량·컨테이너 수가 반영된 PDF 다운로드, 원본 합계 수정 시 승인 취소 및 기존 다운로드 제거를 확인했다. 다운로드 PDF를 이미지로 렌더링하여 표·합계·직인 배치도 확인했다.

The standalone PL workflow accepts up to five supplier document images and extracts each product's quantity and unit, package type and count, net and gross weight, and CBM. Printed totals and the explicit container count are stored separately from calculated row sums; containers are never inferred from pallet counts or volume. The review table and printed-total fields are editable. Quantities and package types are not added across incompatible units, and fractional pallet allocations are allowed. When complete row values differ from printed totals, the PL draft uses the calculated row totals, preserves the source values for review, and requires the user to confirm the extracted values before download. Invalid values and inconsistent package types still block download. Missing values remain unconfirmed. PL output does not require a price or currency. PDF, Excel, and HTML include the packing fields.

For a cosmetics PO with no seller name, each exact catalog match can supply a verified ECLADO purchase-price candidate independently. An unresolved row must not suppress prices for other matched rows. The user must confirm that price source; the supplier's legal name and address remain separate fields. A different specified supplier does not receive ECLADO catalog prices. Explicit transaction currencies remain unchanged.

### 2026-11-03 PO 단가 전체 누락 재발 방지

사용자가 제공한 추출 JSON에서 이미지의 24개 상품은 상품명·용량이 카탈로그와 일치했지만, 별도 문구 `Melaser Whitening Toner는 3+1이야.`가 용량·수량 없는 25번째 행으로 추가되어 있었다. 공급처 법인명도 비어 있었다. 기존의 “모든 행이 일치해야 공급처 미입력 PO의 가격 후보를 조회” 조건 때문에 이 한 행이 정상 24개 행의 단가와 통화 조회까지 막았다. 이미지 해상도나 응답 길이 제한으로 확인된 문제가 아니다.

수정 범위는 `agent/pricing.py`의 공급처 미입력 PO 가격 후보 조회 조건뿐이다. 정확히 일치하고 ECLADO 매입가격이 있는 행은 개별 조회하고, 미일치·모호한 행은 가격을 추측하지 않는다. 공급처 확인, 법인명·주소 입력, 명시된 통화, 수량 0, 프로모션 계산, 다른 공급처, PI/CI/PL/CIPL 및 PDF 서식 규칙을 유지한다. 해당 토너는 용량과 실제 주문수량을 확인해야 하며 자동 삭제하거나 다른 상품에 3+1을 적용하지 않는다.

재발 방지 테스트: `tests/test_po_partial_catalog.py`는 24개 정상 행+미확정 프로모션 행, 공급처/통화 보호, 전 행 미일치, 재실행 시 중복 확인 방지를 검증한다. `tests/test_review_ui.py`는 화면에서 24개 단가 입력 요구가 사라지고 미확정 25번째 행과 공급처 확인이 유지되며 PDF 생성은 계속 차단되는지 검증한다. 실제 주문과 개인 연락처·비공개 단가를 테스트에 저장하지 않고 가상 자료를 사용한다. README 기록만으로 재발을 방지한다고 간주하지 말고 이 테스트를 유지한다.

검증: 수정 전 회귀 테스트에서 통화 `null`로 실패하는 것을 확인했고, 수정 후 `uv run --offline --with streamlit python -m unittest discover -s Quotation_KEKOREA/tests`로 화면 테스트를 포함한 90개 테스트가 모두 통과했다(생략 없음). 기존 Streamlit 경고는 남아 있다. 기본 uv 캐시/임시 파일 권한 및 네트워크 제한 때문에 작업 폴더 캐시와 오프라인 실행을 사용했고, PDF 임시 파일 권한을 허용한 실행에서 전체 통과를 확인했다. 이 변경의 실제 배포 앱 검증은 아직 수행하지 않았다.

### 로컬 실행

저장소 최상위 폴더에서:

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt streamlit run .\Quotation_KEKOREA\app.py
```

또는 `Quotation_KEKOREA/` 폴더에서 `python -m pip install -r requirements.txt` 후 `streamlit run app.py`를 실행한다. API 키는 `.env`에만 둔다.

### Streamlit Community Cloud 설정

메인 파일은 `Quotation_KEKOREA/app.py`로 두고, 앱이 연결된 GitHub 브랜치에 코드 변경을 push한다. Manage app → Settings → Secrets에 다음 값을 비밀로 등록한다. 실제 키는 이 채팅에 보내지 않는다.

```toml
OPENAI_API_KEY = "새로 발급한 OpenAI 키"
OPENAI_MODEL = "gpt-6-luna"
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "새로 발급한 Supabase Secret key"
```

앱 접근 범위는 **Only specific people can view this app**로 제한한다. Supabase Secret key는 RLS를 우회하는 서버 전용 키이며 공개 Streamlit 앱에 두면 안 된다. 로컬 `.env`와 `private/` 가격 seed는 Git에서 제외한다.

### 검증과 미완료 사항

- Python `unittest`에서 SQL importer·계산·렌더러·OpenAI 모의요청·Supabase REST 모의요청 검증을 실행한다. 모의 테스트는 실제 Supabase 인증이나 실제 테이블 상태를 증명하지 않는다.
- 앱이 실제 Supabase에 연결되면 화면에 최근 catalog import 시각과 제품 수를 표시한다. “No ECLADO catalog import”는 테이블은 있어도 seed rows가 없을 때, HTTP 401/403은 키 또는 권한 문제, 404는 API 노출/테이블명 문제를 뜻한다.
- 2026-11-02: 배포 앱의 실제 Supabase 카탈로그 연결과 비공개 직인 다운로드를 확인했다. 키 자체는 코드·문서·로그에 기록하지 않는다.
- Image and PDF order uploads are supported in the current source. PyMuPDF extracts selectable PDF text page by page and renders text-poor pages as images for vision extraction; original PDFs are also sent as source files. This local-source implementation has not been revalidated against the live deployment. PyMuPDF licensing must be cleared before commercial deployment. Final numbering/issuance and persistent CI/PL shipping integration are not connected. Generated files remain review drafts.
- PDF 렌더링과 직인·페이지 배치는 로컬 및 배포 앱 생성 파일로 검증했다. Excel 데스크톱 앱 자체의 시각 검수는 별도이며, 실제 거래 문서는 발송 전에 사용자가 검토한다.


## Buyer order image input and cosmetics money display

The Streamlit form accepts up to five PNG/JPG/JPEG/WEBP order screenshots (10 MB each, 20 MB total) alongside buyer/company details. On Extract, the prompt and images are sent to OpenAI for structured extraction. The app keeps the resulting document as a DRAFT and flags image-derived item details for visual review before download. OpenAI image inputs use billable tokens; upload only transaction images that are appropriate to send to the configured API.

For cosmetics, the final unit price is rounded before extending the line amount: KRW to whole won (`KRW 15,000` in English documents) and USD to two decimal places (`$10.57`). Totals, PI/PO/CI line items, spreadsheet outputs, and the app total display use the same rounding rule. Other product families retain their existing unit-price precision.


## PI corporate branding

The solar PI header displays the supplied company logo in a white brand panel. The faint body watermark was removed because the white party panels and pricing table obscured it. The former charcoal/gold fills and rules now use the logo's navy and blue palette.


## Brand assets and Cloud secrets

- The solar PI displays the supplied logo in a white header area. Navy and blue replace the previous charcoal and gold theme. No body watermark is used.
- `assets/company_logo.png` is tracked. The complete seal image `assets/image.png` is used automatically in local runs; the seal images, `.env`, generated outputs, and catalog seed data are excluded from Git.
- The GitHub repository is public, so keep the company seal out of Git. Streamlit Cloud loads the seal from the private Supabase Storage bucket `kekorea-private-seal`, using the top-level `SUPABASE_URL` and server-only `SUPABASE_SECRET_KEY` secrets. Keep the six `KEKOREA_USD_*` variables for PI bank details. Upload the local seal from the repository root with:

```powershell
python Quotation_KEKOREA/scripts/upload_company_seal.py
```

The uploader uses local credentials, creates a private bucket if necessary, and verifies the uploaded image by downloading it. The app checks the PNG's SHA-256 and caches the download for 15 minutes. `KEKOREA_COMPANY_SEAL_BASE64` is an optional legacy fallback and can be removed after storage is configured. Never publish the seal or the server key. Bank details appear on PI only.


## Shared document handling and document names

PI, PO, CI, and PL use the same extraction, quantity synchronization, Decimal calculation, English translation checks, explicit REMARK handling (`N/A` when omitted), and branded PDF/XLSX renderer. Product matching can use ECLADO names and capacities across PO, CI, and PL; uncertain matches require review. PO uses verified ECLADO KRW purchase prices. PI may use the Dear Glow sale price list. CI must preserve transaction prices from its attached PI and is blocked without that source; it is never repriced from the ECLADO purchase catalog. PL remains price-free and uses product matching only.

The Streamlit sidebar offers separate PI, PO, CI, and PL workflows. CI creates a Commercial Invoice only; PL creates a Packing List only. Generate each document from its own menu. PI alone includes KE KOREA's USD bank details. PI/Proforma Invoice, PO/Purchase Order, CI/Commercial Invoice, and PL/Packing List aliases are accepted when the prompt explicitly requests creation. If the named document conflicts with the selected menu, extraction stops and tells the user which menu to choose.

Field extraction accepts common equivalent labels instead of requiring exact schema wording: Qty/Q'ty/ordered units/Volume for quantities; Item/Product/Goods/Description for product names; Unit Price/Rate/Price per unit for prices; Shipping Terms/Terms of Shipping/Ship Conditions/Delivery Terms for Incoterms; and Payment Conditions/Terms of Payment/Settlement Terms for payment. SET, BOX, CARTON, CTN, PALLET, and similar terms are retained as units or package descriptors based on context, never converted to another unit. If a quantity uses ambiguous `Volume` or a bare package-count label such as `Box: 10`, the review screen asks the user to confirm the interpretation before enabling PDF/XLSX downloads. Cubic/package volume and delivery dates are kept distinct from ordered quantity and Incoterms.

The shared PDF renderer preserves the source quantity unit on PI, PO, and CI lines (including PC/PCS/KG) and shows the unit separately in PL. It formats total quantities with thousands separators and groups different units instead of adding incompatible units together. CI/PI/PO amount boxes center both label and amount. Every PDF type embeds the full `assets/image.png` company seal below `KE KOREA CO. LTD` in its signature panel; if that image is unavailable, downloads are blocked. Streamlit Cloud retrieves the matching image from private Supabase Storage using its server-side secrets.

### Automatic document fields

- The issue date is always generated from the current date in `Asia/Seoul` and displayed in English (for example, `30 October 2026`). Dates copied from an order or email are not used as the issue date. This rule applies to PI, PO, CI, PL, PDF, Excel, and HTML outputs.
- The PDF title badge shows the document identifier without a `DRAFT | NO.` prefix: PI and CI use `INVOICE #`, PO uses `PO #`, and PL uses `PACKING LIST #`. Draft status remains visible in the footer.
- `SHIP TO` contains only a specifically stated delivery destination, recognized from labels such as `Ship To`, `Delivered To`, `Delivery To`, `Delivery Address`, `Destination`, or equivalent supported-language labels. The buyer address, seller address, origin country, and EXW/FOB named place are not used as a destination. If no specific destination is provided, the document displays `N/A`.

### PO/PI 행사 계산 보완 (2026-11-03)

PO/PI의 행사 명령은 기존 주문 행에 적용합니다. `전체 제품 3+1 행사`는 전체 행에, `Melaser Whitening Toner 3+1 행사`는 해당 제품에 적용합니다. 같은 이름의 다른 용량이 있으면 용량을 함께 지정합니다. `Buy 3, get 1 free`, 한국어 구매/증정 표현, 전각 숫자와 더하기 기호도 숫자형 행사로 정규화합니다. 서로 충돌하거나 제외/취소가 섞인 명령은 확인 전 생성을 막습니다.

주문 수량은 유상 수량이며, 증정 수량은 `floor(유상 수량 / 구매 기준) × 증정 기준`, 출고 수량은 `유상 + 증정`입니다. 금액은 유상 수량에만 단가를 곱합니다. 용량이나 포장 내부 개수는 행사 배수가 아닙니다. 수량을 검토 화면에서 나중에 입력하거나 변경해도 다시 계산합니다. PDF에는 유상 수량과 `+ 증정 수량 FOC`를 표시하여 증정분을 중복 표시하지 않습니다.

| 행사 | 유상 수량 | 증정 수량 | 출고 수량 |
| --- | ---: | ---: | ---: |
| 1+1 | 10 | 10 | 20 |
| 2+1 | 10 | 5 | 15 |
| 3+1 | 10 | 3 | 13 |
| 4+1 | 10 | 2 | 12 |
| 4+3 | 10 | 6 | 16 |
| 3+2 | 10 | 6 | 16 |

기존 `apply_promotion` 산식은 유지했습니다. 변경 범위는 PO/PI 행사 명령 연결, 재계산, 행사 오류 생성 차단, 행사 행의 PDF 수량 표시입니다. 가격 정책, 제품 매칭, 거래처 DB, 메뉴별 작업 보관, CI/PL/CIPL 동작은 이번 수정 대상이 아닙니다. 회귀 테스트는 `tests/test_order_promotions.py`, `tests/test_order_promotions_ui.py`에 추가했습니다. 실제 모델/API 추출과 배포 앱 반영 여부는 로컬 테스트와 별도로 확인해야 합니다.

로컬 검증: `uv run --offline --with streamlit python -m unittest discover -s Quotation_KEKOREA/tests` 전체 151개 통과(기존 134개 + 신규 17개, Streamlit AppTest 포함). 여섯 행사 각각 PO/PI의 PDF/XLSX 생성과 유상 수량 기준 금액을 확인했습니다. 운영 앱에는 아직 배포하지 않았습니다.

### PI 샘플 수동 입력 (2026-11-03)

PI 요청에 `샘플` 또는 대소문자 구분 없는 `sample`이 있으면 **샘플 수동 입력** 영역을 표시합니다. `SAMPLE도 있어`처럼 한국어 조사가 붙어도 인식합니다. 예: `Dearglow에 PI 작성해줘. 샘플도 있어`. 샘플 품명·용량·수량·단위·단가를 직접 입력하고, **샘플 행 추가**로 여러 행을 추가할 수 있습니다. 필요 없는 행은 해당 행의 **include in invoice**를 해제합니다. 수량과 단가는 미리 추측하지 않으므로 직접 입력해야 하며, 단가 `0`도 유효합니다. 음수·비숫자·NaN·Infinity 등 잘못된 값은 파일 생성을 막습니다.

샘플은 해당 PI 안에만 저장하는 거래별 행이며 SQL 상품/가격 테이블에 등록하지 않습니다. 카탈로그에 같은 이름이 있어도 수동 단가를 덮어쓰지 않습니다. 새 샘플 행의 품명은 빈칸으로 시작하며, 사용자가 입력한 실제 제품명을 그대로 PDF/Excel에 출력합니다. `SAMPLE`로 고정하거나 `(SAMPLE)`을 자동으로 붙이지 않습니다. 샘플 여부는 내부 `is_sample` 정보로 관리하므로 품명을 바꿔도 수동 입력값은 유지됩니다. 수량은 전체 수량에 포함하고, 금액은 `수량 × 직접 입력한 단가`를 전체 금액에 합산합니다. 예: 일반 상품 10개/20 USD와 샘플 5개/단가 0 USD는 총 15개/20 USD, 샘플 단가를 0.25 USD로 입력하면 총 15개/21.25 USD입니다. 샘플에는 일반 상품의 행사·할인을 자동 적용하지 않습니다.

입력값은 기존 메뉴별 초안 보관 경로를 사용해 메뉴 이동 후에도 유지합니다. 새 자료 추출 시 이전 샘플 입력은 초기화하고, 수정한 인보이스에는 이전 다운로드 파일을 노출하지 않습니다. PO/CI/PL/CIPL 및 일반 상품의 양수 단가·카탈로그 검증은 이번 샘플 기능의 적용 대상이 아닙니다. 회귀 테스트: `tests/test_pi_samples.py`, `tests/test_pi_samples_ui.py`. 운영 배포 및 실제 모델 추출 검증은 별도입니다.

최종 로컬 검증: 전체 164개 테스트 통과(기존 행사 수정까지 151개 + 샘플 신규 13개, Streamlit AppTest 포함). 자유로운 품명 입력·변경, 0/양수 단가, PDF/XLSX 수량·금액 합산, 카탈로그 단가 덮어쓰기 방지, 일반 상품 분류/할인 검증 유지, 메뉴 복귀와 새 추출 초기화를 확인했습니다. 운영 앱에는 아직 배포하지 않았습니다.

### PDF 공통 입력 및 첨부 PI → CI 가져오기 (2026-11-03)

PO·PI·CI·PL의 공통 업로드 영역에서 PNG/JPG/JPEG/WEBP와 PDF를 지원합니다. 이미지와 PDF를 섞어서 최대 5개, 파일당 10 MB, 합계 20 MB까지 올릴 수 있습니다. PDF는 첫 페이지만 잘라 보내지 않고 원본 전체를 추출 요청에 포함합니다. 텍스트 PDF와 스캔된 페이지를 같은 문서 입력 경로로 전달하며, 실제 인식 정확도는 원본 품질과 모델 결과에 따라 검토해야 합니다. PDF 파일은 이름으로 표시하고 이미지 미리보기에 넣지 않습니다. 원본 첨부와 진행 중 추출은 기존 메뉴별 작업 보관·비동기 실행 경로를 사용합니다. PL 메뉴에서 포장 합계 비교 및 승인을 처리합니다.

PDF 전송은 [OpenAI 공식 파일 입력 형식](https://developers.openai.com/api/docs/guides/file-inputs)의 `input_file`과 원본 Base64를 사용합니다. 기존 이미지의 `input_image` 경로는 유지하며 별도의 PDF 변환 패키지나 SQL 테이블을 추가하지 않았습니다. 비어 있는 파일, PDF 헤더가 아닌 파일, 미지원 형식과 용량 초과는 API 호출 전에 거부합니다. 문서 내용은 추출 근거이며 실행 지시로 취급하지 않습니다.

In the CI menu, attach a PI image or PDF and request `Create CI from the attached PI`. When the source is identified as a PI, the import adapter preserves its items, capacities, quantities, currency, transaction prices, discounts, FOC items, and zero-price samples; it does not replace them with catalog prices or default discounts. If a PI line has source evidence but no discount notation, a missing discount is treated as 0%. If discount notation exists but its rate is missing, the row remains under review. After review values are entered, stale extraction notices for populated party details, invoice number, shipment reference, and origin are cleared; unresolved HS codes and product matches remain flagged. Already-discounted unit prices are not discounted a second time. Export is blocked when extracted line or total amounts disagree with the PI, or when price/quantity source evidence is missing. Zero prices require source evidence for zero/FOC or explicit user entry. The positive-price validation for ordinary CI items remains.

기존 CI PDF·Excel·HTML 생성 코드와 PI 전용 은행정보 출력 분기는 변경하지 않았습니다. 가져오기 단계에서 원본 PI의 은행/계좌/SWIFT/결제 값과 금융정보가 포함된 비고를 제외하며, 기존 결제 항목에는 `N/A`를 전달합니다. 일반 상품의 비고는 유지합니다. 증정 수량은 기존 CI PDF가 별도로 덧붙이는 표시 방식에 맞춰 중복되지 않게 전달하고, 실제 출고 수량과 Excel의 증정 행은 보존합니다. PI의 발행일을 복사하는 대신 기존 공통 규칙에 따라 CI 발행일은 현재 Asia/Seoul 날짜를 사용합니다. 선적 참조번호·원산지 등 원본에 없는 기존 CI 필수 항목은 검토 화면에서 직접 입력해야 합니다. 원본이 PI가 아닌 일반 CI 입력에는 기존 카탈로그·할인 처리를 계속 적용합니다.

회귀 테스트: `tests/test_pdf_inputs.py`, `tests/test_pdf_upload_ui.py`, `tests/test_ci_pi_import.py`, `tests/test_ci_pi_import_ui.py`. API 요청 형식은 가짜 응답으로 검증하고 실제 문서 생성·Streamlit 화면은 합성 자료로 검증합니다. 실제 고객 자료 외부 전송, 운영 앱 배포 및 실제 모델 OCR 정확도 검증은 이번 로컬 검증에 포함하지 않습니다.

최종 로컬 검증: 전체 182개 테스트 통과(기존 164개 + 신규 18개, Streamlit AppTest 포함), 종료 코드 0. 모든 문서 메뉴의 PDF 전달, 혼합 첨부·파일 제한·메뉴 보관, PI 이미지/PDF의 CI 변환, 원본 금액 불일치 차단, 실제 CI PDF/XLSX/HTML의 은행·결제 값 제외를 확인했습니다. 기존 PDF/Excel/HTML 렌더러, 가격 정책 모듈, 거래처/제품 매칭, 작업 상태 보관, 의존성 목록은 변경하지 않았습니다. 운영 앱에는 아직 배포하지 않았습니다.

### 2026-11-06 TASTE 계약서 UI 및 README 동기화

- **현재 코드 기준:** `contracts/flow.py`는 반복 질문을 줄이고 초안 작성 요청에 따라 초안을 만든다. 질문 응답과 계약서 본문 언어는 별개로 관리한다.
- **지급조건:** `contracts/commission_policy.py`와 UI에서 커미션 지급기한 및 서면합의 연체이율을 반영한다. 초기 D+7을 사용자가 변경할 수 있으며, 계좌 및 법률 검증의 미확정 상태는 유지한다.
- **RAG:** 승인된 참고 조항 검색 결과를 위험 검토에 활용하지만, 자동 승인을 하지 않는다. 참고 자료는 거래 당사자·금액 등을 확정하는 근거로 자동 승격하지 않는다.
- **TASTE 기반 검토 UI:** 기존 KE KOREA 색상을 유지한 회색 작업 배경·흰색 문서형 미리보기와 3개 작업 박스를 사용한다. 미확정 이슈는 화면에서 중복을 묶고 필수 확인/권장 확인/법률 검토 권장/초안에 TBD 허용으로 안내한다. 원문과 항목별 근거는 접힌 메뉴에 보존한다. 최종 검증 엔진은 변경하지 않는다.
- **검증 이력:** 이번 작업 시작 시 로컬과 원격 `main`은 `3991930`으로 일치했고 기존 296개 테스트가 통과했다. 아래 이전 테스트 수·실패 기록은 당시 이력이다. 이번 계약 UI 변경은 운영 배포하지 않았으며, 로컬 테스트와 실제 운영 검증을 구분한다.
- **문서 동기화:** 5개 README에 기능 변경·변경된 설명·제거한 기능을 함께 반영한다. `scripts/check_readme_sync.py` 및 `.githooks/pre-commit` 검사 포함. 자세한 계약 동작은 [README_CONTRACTS.md](README_CONTRACTS.md) 참조.

### 2026-11-06 전체 테스트 실패 2건 수정

- 계약 커미션 기본 7일 기한을 영문 `seven (7) calendar days`로 표기해 법률 문서의 기존 기본 문구와 테스트를 일치시켰습니다. 7일이 아닌 명시적 사용자 지급기한은 그대로 반영합니다.
- 상품명 주석 확인(`Confirm product annotation` 및 `Double-check this product`)이 남은 PO/PI에서는 PDF/Excel 생성 버튼을 차단합니다. 체크박스 확인 후에만 생성을 허용합니다. 가격 자동 조회 및 상품명 원문 보존 규칙은 변경하지 않았습니다.
- 회귀 검사: `tests/test_commission_policy.py`, `tests/test_product_matching_ui.py`. 이번 UI 작업 시작 전 전체 296개 테스트에서 이 보호 동작을 포함해 통과했다.

### 2026-11-06 CI 검토용 DRAFT 출력 회귀 보완

PO/PI에서 확인이 필요한 상품 주석은 문서 생성 전에 확인해야 합니다. CI는 기존처럼 첨부 PI의 실제 거래가격을 유지하고 상품명 매칭이 미확정이면 경고 및 DRAFT 상태를 표시한 채 검토용 PDF/Excel 생성을 허용합니다. `test_review_ui.py::test_unconfirmed_ci_product_match_allows_draft_pdf`와 `test_product_matching_ui.py`의 동작을 함께 유지합니다. 해당 거래 문서 코드는 이번 계약 UI 작업에서 수정하지 않았으며, 최종 발행·전송을 자동 수행하지 않습니다.

### 계약 UI 전용 조정 계층과 제한

`contracts/workspace.py`는 현재 계약·revision·sentence ID에 맞는 메모를 하나의 AI 요청으로 전달하고 결과의 대상·원문·중복·누락·삭제 여부·보호 지급조항을 검사한다. AI 전송에는 BOX 1의 전송 동의가 필요하다. AI가 메모 간 충돌을 보고하면 계약 본문을 변경하지 않고 조정을 요청한다. `apply_proposal()`로 적용 가능성을 검증하며, AI가 모든 법률적·의미적 충돌을 발견한다고 보장하지 않으므로 사용자가 금액·기한·역할을 확인해야 한다. 일부 변경만 승인하면 나머지 메모는 이전 revision의 기록으로 남는다. 열려 있는 미저장 메모는 브라우저 세션에 보관되며 `최종 수정 요청` 또는 개별 저장 시 DB에 저장된다. 이전 revision 메모는 확인용으로 불러올 수 있지만 명시적으로 다시 수정·저장해야 요청에 포함된다.

`contracts/draft_exports.py`는 최종 렌더러를 변경하지 않는 별도 검토용 출력 경로다. 미확정이 있으면 본문 전체를 미승인으로 표시하고 원문 근거를 부록에 보존한다. `contracts/rules.py`, `commission_policy.py`, `service.py`, `editing.py`, 저장 스키마와 PO/PI/CI/PL·ECLADO 코드는 보존했다. 로컬 PDF 다중 페이지·혼합 언어 렌더링을 확인했으나 실제 브라우저의 반응형·시각 검수와 Word 렌더링, 운영 DB/API/배포 검증은 미완료다. Windows 브라우저 URL 확인 제한으로 컴퓨터 제어가 중단됐다.

최종 로컬 검증(2026-11-06): 요구사항 전체 의존성으로 `python -m unittest discover -s Quotation_KEKOREA/tests -v`를 실행해 **320개 통과, 실패 0개, 종료 코드 0**(89.580초)을 확인했다. 기존 296개를 삭제·수정하지 않고 신규 24개를 추가했다. 신규 검증은 3박스 순서, 수동 입력 상태, AI 후보의 기존 초안 보존, 문장 메모 재호출·분리, 일괄 승인과 충돌, 미확정 재개, 빈 revision 방지, DRAFT 저장 실패 정리, FINAL 차단/정상 생성, 혼합 언어 PDF를 포함한다. `git diff --check`도 통과했다. 기존 `use_container_width` 및 `fitz` 경고는 테스트 실패와 구분한다.

### 2026-11-06 BOX 3 댓글 배치 보완
문서형 초안의 각 문장을 7:3 고정 행으로 렌더링해 메모를 열기 전후에도 문장 정렬을 유지한다. 우측의 댓글 입력란은 선택한 문장에만 표시되고 다른 문장 메모는 동시에 유지된다. 기존 DB 저장, 일괄 AI 요청, revision 승인 및 출력 규칙은 변경하지 않았다.

## 2026-11-06 AI 위험 검토 페이지·추천안 확장

계약서 위험 검토 개선: 전체 조항을 10문장 이하 묶음으로 기존 출처 검증 위험 검토에 전달하고 최종 결과는 5건씩 페이지 표시한다. 선택한 위험에 대해 모델에서 추천 문장 3개를 생성한다. 숫자·법인명은 검증된 가변 템플릿으로만 변경할 수 있다. 사용자가 선택한 문장은 BOX 3에서 즉시 미리보기로 표시하되 기존 revision/FINAL 검증은 유지한다.

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

### 계약서 PDF/Word 저장 실패 구분
계약서 파일 렌더링이 성공했지만 Supabase 비공개 저장 또는 export 기록 저장이 실패하면, 기존 부분 업로드 정리를 유지하면서 현재 브라우저 세션에 한해 직접 다운로드 버튼을 제공한다. 파일 생성 실패와 서버 저장 실패를 구분해 안내한다. 최종 계약서는 기존 `validate_rules(..., for_export=True)` 조건을 통과해야 한다.

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


### 2026-11-13 · AI 단일 입력 / PDF 생성 캐시 충돌 긴급 수정
- 운영 화면에서 `apply_answer() got an unexpected keyword argument 'allow_blank'` 및 `render_incomplete_trade_pdf` ImportError를 확인했습니다. 두 함수는 GitHub `main`에는 있으나 Streamlit 프로세스에 이전 Python 모듈 객체가 남으면 새 UI가 이전 함수를 호출하는 문제가 있었습니다.
- AI 업무 요청 진입 시 화면 모듈의 실행 버전을 검사하고, 이전 버전이면 오류를 외부에 노출하지 않고 재로딩합니다. 거래정보 수정은 변경 시점에 `intake_followups.apply_answer`의 `allow_blank` 지원 여부를 검사한 후 필요하면 실제 모듈을 다시 불러오며, PDF 생성 버튼은 `legacy_document_exports`의 검토용 PDF 함수/버전을 확인해 필요 시 재로딩합니다. 새 함수명을 앱 시작 시 필수 import하지 않아 전체 앱 부팅 오류를 방지합니다.
- 모듈 갱신이 어려운 경우 입력값이나 세션에 저장된 문서 후보를 제거하지 않고, 민감한 서버 예외 대신 안전한 재시작 안내를 표시합니다. 미확정 필드가 있어도 검토용 PDF 다운로드 경로는 유지하고, 기존 직인·은행·금액·승인 검증과 정식 발행 정책은 변경하지 않습니다.
- 합성 데이터 테스트에 이전 `apply_answer` 함수 시그니처, 누락된 `render_incomplete_trade_pdf`, 갱신 실패 시 비밀 원문 미노출, 구버전 AI 화면 모듈 재로딩을 추가했습니다. POP3·SMTP·Google OAuth·실메일·첨부·계약서 양식은 변경하지 않습니다. 실제 운영 검증은 별도입니다.


### 2026-11-13 · PI 정식 양식 보류 사유 구분 및 AI 잔여 기록 확인
- 기존 PDF 생성 화면은 검증기에서 반환한 거래조건 누락/충돌, PI 은행정보 6항목 미설정, 검증된 회사 직인 없음 및 PDF 렌더러 오류를 모두 동일한 '정식 양식 발행 보류' 문구로 표시했습니다. 사용자가 Buyer/Seller·주소·수량·단가를 다 입력해도 다른 서버 설정 또는 최초 AI 추출의 `missing_fields`·`conflicts` 메모가 남으면 정식 서식은 보류될 수 있습니다.
- 이제 PDF 생성 시 거래조건 문제와 PI 은행정보, 직인, CI 원본 PI, 문서 타입, 알 수 없는 렌더러 오류를 **안전한 범주별 문구**로 보여줍니다. 계좌번호/암호/서버 오류 원문/실제 메일은 출력·전송·로그에 남기지 않습니다. 입금계좌 Secret의 실제 값은 표시하지 않으며 미설정 항목 개수만 안내합니다.
- 동일한 '거래정보 입력 · 수정 (한 번만)' 카드 안에서 AI가 과거 추출한 미확정·충돌 기록을 열람하고, 사용자가 실제 원문과 대조하여 개별적으로 '해소 확인'할 수 있습니다. 이는 과거 AI 기록만 갱신하고 문서별 필수 입력·수량/금액·은행정보·원본 PI·직인 검증을 우회하지 않습니다. 자동으로 충돌을 삭제하거나 근거가 없는 내용을 입력하지 않습니다. 확인 시 기존 PDF·검토 상태는 무효화됩니다.
- 기존 PI/PO/CI/PL 양식과 엄격한 발행 검증, AI 모델 사용 동의, POP3/SMTP/OAuth, 저장된 개인 메일 및 직인 파일은 변경하지 않습니다. 합성 자료로 UI와 데이터 불변성을 테스트하며 운영 환경의 실제 보류 원인은 배포 후 안전한 진단 화면에서 확인해야 합니다.


### 2026-11-13 · MASTER 계약서 FINAL을 기존 KE KOREA 양식으로 통일
- Master `AI 업무 요청`의 CONTRACT 문서에 새 **기존 KE KOREA 계약서 FINAL 양식 · PDF / Word** 출력 단계를 추가했습니다. 최종 출력은 기존 `contracts.exports.export_contract`를 그대로 사용하며, 글꼴·제목/소제목/본문 18/12/10pt, 계약 본문, 조항 순서, 서명란, 페이지 번호, 직인 배치는 원본 렌더러에서 처리합니다. 원본 PI/PO/CI/PL 엔진과 기존 계약서 DRAFT 렌더러는 수정하지 않았습니다.
- Master의 한 거래정보 입력 카드 안에 계약서 전용 필수 조건(계약일, 준거법, 분쟁 해결, 결제 시점 등)과 당사자 확인 기능을 추가했습니다. AI가 추출한 당사자/거래조건은 `suggested` 상태를 유지하고, 사용자가 원문과 대조해 항목별로 **확정**해야 합니다. 조건 변경 시 기존 AI 작성 조항과 이전 FINAL 다운로드 상태는 무효화됩니다. 누락된 필수정보를 허위 기재하거나 자동 승인하지 않습니다.
- FINAL 발행 시 원본 `contracts.final_policy.final_document_blockers`, `contracts.rules.validate_snapshot(for_export=True)`, `contracts.models.validate_snapshot`을 실행하고, 미확정 AI 제안/조항/당사자 및 거래조건을 차단합니다. 모든 조항의 현재 해시와 연결된 명시적 사용자 승인 및 기존 관리자 로그인 또는 `CONTRACT_FINAL_SEAL_PASSWORD` 검증이 필요합니다. 기존 `contracts.ui._verified_contract_seal`의 PNG 및 SHA-256 검증을 거친 회사 직인만 사용하며, 실제 출력 바이트는 기존 `contracts.exports.export_contract`에서 생성됩니다.
- 서명된 계약 체결, 이메일 자동 발송, 최종 계약서의 Supabase 영구 저장은 수행하지 않습니다. 출력은 로그인 세션에서 직접 다운로드합니다. 고급 JSON 편집으로 조건이 바뀌면 후보에 명시적으로 반영하고 모든 당사자/조건을 다시 확인해야 합니다.
- 합성 당사자와 임시 합성 PNG로 PDF/Word 원본 엔진 출력 일치, 승인·직인 권한 미확보 차단, 거래조건 변경 시 이전 승인 무효화, 기존 UI 흐름을 테스트합니다. 실제 계약서·메일·직인·Secrets를 CI/GitHub에 업로드하지 않습니다. 운영 두 앱의 실출력 PDF 시각 비교는 별도 검증 사항입니다.

- 최종 검토 보완: AI 분석이 남긴 `severity=confirm` 미확인 이슈도 FINAL을 차단합니다. Master의 동일 계약정보 입력 영역에서 원문과 대조한 개별 확인 이슈만 사용자가 '확인 완료' 할 수 있으며, `severity=block` 이슈는 확인 버튼만으로 해제할 수 없습니다. 모든 상태 변경은 계약서 FINAL 승인 해시를 변경합니다.


### 2026-11-13 · 승인 RAG 참고 메모 임베딩 백필 및 의미 검색
- 서버 관리자 인증을 마친 후 **공통 샘플 라이브러리 관리 → 승인 참고 조항의 누락 임베딩 생성**으로 기존 승인·활성 참고 메모의 누락된 벡터를 생성한다. `OPENAI_API_KEY`가 서버에 필요하며 버튼 클릭 시 API 비용이 발생할 수 있다. 관리 대상 원본·계약서·서명·계좌는 임베딩 API로 전송하지 않는다.
- `contracts/library.py`의 `backfill_library_embeddings`는 저장된 승인 메모의 **topic + text**만 배치 전송(요청당 최대 64개), 512차원 유한 벡터 검증 후 동일 레코드의 JSONB manifest에서 임베딩과 revision만 갱신한다. 데이터가 미승인이거나 비활성인 경우 제외하며 오류 시 재시도 가능하다. 현재 최초 수집 시 만든 일반 참고 메모는 조항 원문 발췌와 다르므로, 내용 품질은 별도 검토가 필요하다.
- 계약서 신규 초안의 주제별 검색(`search_library_topics`)은 승인 문서와 호환 가능한 벡터가 있을 경우 **한 번의 배치 임베딩 호출**로 의미+키워드 혼합 검색을 수행한다. 모델 설정 불일치, 외부 API 장애, 벡터 누락 시 키워드 검색을 유지한다. 기존 계약서 승인, DRAFT/FINAL, PO/PI/CI/PL 출력 정책은 변경하지 않는다.
- 기존 143개 승인 지식 청크 중 최초 확인된 35개만 벡터가 있었으며 신규 108개는 미적용이었다. **코드 변경이 실제 108개 벡터 생성 완료나 운영 배포 성공을 의미하지 않는다.** 관리자 백필 실행 후 Supabase 내 벡터 수량 및 실제 모델 검색 결과를 검증해야 한다.


### 2026-11-13 · 원문 검증형 계약서 RAG 2.0 (다중 계약서 교차 비교)
- \`contracts/contextual_rag.py\`: Supabase private 원본을 SHA-256 검증 → PDF/DOCX/HWP 텍스트 추출 → 조항별 private parent index(최대 96개, 문맥/위치 포함)로 보관. 미추출 스캔본, XLSX는 자동 승인하지 않는다.
- 관리 키를 가진 사용자가 **공통 샘플 라이브러리 관리**에서 일괄 인덱싱한 후 원문 앞뒤를 검토하고, 비식별화된 문구를 명시적으로 승인해야 \`source_section_id\`로 RAG에 연결된다. 기존 108개 일반 메모는 원문 근거 조항으로 자동 간주하지 않는다.
- 신규 계약서 초안의 승인된 조항별 검색에서 **서로 다른 원문 문서 2개 이상**의 근거가 확인되면 AI 1회로 조항 비교, 선택 이유와 충돌 확인. 선택된 조항의 **승인된** 앞뒤 문맥을 함께 제공하고 기존 전체 계약 감사로 재검증한다. AI가 근거 없는 ID를 생성하면 무시, 실패 시 일반 검색으로 복귀한다.
- 현재 확정 거래조건/정책이 과거 사례보다 우선하고 과거 개인·거래처·금액·수수료율·기한을 자동 상속하지 않는다. 기존 PDF 서식, PI/PO/CI/PL, 계약 revision/승인 흐름은 변경하지 않는다.
- 구현과 데이터의 구분: 운영 데이터 20개 원문 추출·승인, 신규 임베딩 백필과 실제 AI 생성·배포는 각기 별도 검증해야 한다. 세부 내용: Contract RAG 2.0 (저장소 루트 docs/contract-contextual-rag-v2-20261113.md) (하위 폴더 README에서는 저장소 루트의 해당 파일을 참조).

### 2026-11-13 · ZIP 기존 OCR/텍스트 저장 누락 복구
- 관리자 인증 후 **공통 샘플 라이브러리 관리 → 기존 ZIP에서 추출했던 원문 텍스트 복구**: 기존 `contracts.zip`에서 복원한 비공개 JSON 20개를 읽는다. 저장 전에 레코드 내용 해시와 Supabase Storage 원본 바이트 SHA-256을 모두 검증한다.
- `restore_private_extraction_bundle()`는 비어 있는 `extracted_text`만 채운다. 기존 승인 청크·기존 본문·계약 revision·원본 버킷은 보존하며 `private_text_extraction_v1` 출처/미추출 페이지/검토 필요 정보를 남긴다.
- 그 다음 **원본 계약서 조항 인덱스 · 관리자 검증**을 실행하면, 기존 추출 텍스트의 페이지/문서 위치를 재사용해 비공개 계층형 조항 인덱스를 생성한다. 기존 PDF를 무조건 새로 OCR하지 않는다.
- OCR 글자 인식 오류, 스캔 미추출 페이지, 편집 누락, 서식 깨짐은 자동으로 법적 검증되지 않는다. 원문 확인과 **원문 조항 개별 승인** 없이는 새 계약서에 원본 텍스트를 제공하지 않는다.
- 이전 데이터 점검: 승인 문서 23개 중 20개가 `extracted_text`가 공란이었으며, 원본 ZIP의 이전 추출 자료에는 그 20개에 대한 텍스트가 남아 있었다. DB에 실제 입력되었는지 여부는 운영 복원 후 재검증해야 한다.

### 2026-11-13 · 운영 데이터 원문 복구 및 조항 위치 검증 (완료된 데이터 작업)
- Supabase `public.kekorea_contract_references`에서 기존 본문 누락 **20개**를 `contracts.zip`에서 검증된 원문 추출 결과로 직접 복구했다. SHA-256 20개 모두 원본 ZIP 및 기존 DB 해시가 일치했다. `private_text_extraction_v1`을 사용해 이전 OCR에서 미추출된 페이지와 수동 검토 필요 여부를 유지했다.
- 기존 승인 문서 3개까지 합쳐 공통 승인 **23/23개 `extracted_text` 보유**, **23/23개 `private_clause_hierarchy_v1` 비공개 인덱스 생성**. 총 원문 인덱스 **233개**, 모든 조항 ID 고유하고 조항 SHA256 검증 불일치 0개, 원본 해시 불일치 0개.
- 이 작업은 원문 저장 및 비공개 계층 인덱스 복원이다. **원문 233개가 모두 공통 AI 프롬프트로 승인된 것은 아님**. 원문 비교를 이용하려면 원문 앞뒤 맥락을 확인하고 익명화 참고 문구를 관리자 승인해야 한다.
- 기존 공통 승인 참고 메모 143개/임베딩 35개라는 별도 현황은 변경되지 않았다. 승인 참고 메모의 누락 벡터 생성과 실제 AI 비교 품질 및 Streamlit 운영 화면 배포 검증은 별도 확인 대상이다.
