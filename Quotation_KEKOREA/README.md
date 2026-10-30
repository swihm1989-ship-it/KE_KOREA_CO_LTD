# KE KOREA 무역 문서 생성 AI Agent 설계안

작성일: 2026-10-30 (Asia/Seoul)  
상태: ECLADO 가격 SQL과 로컬 텍스트 프롬프트 기반 초안 Agent가 준비되어 있으며, 앱에 Supabase REST 카탈로그 조회를 연결했다. 실제 Supabase/Cloud 연결은 아직 확인되지 않았다. 업무 서식 재현·첨부자료 판독·발행 절차는 미완료이며 모든 출력은 검토용 초안이다.

## 1. 이해한 목표

KE KOREA CO. LTD의 실제 거래 정보를 받아 제품군에 맞는 Purchase Order(PO), Proforma Invoice(PI), Commercial Invoice(CI), Packing List(PL)를 생성한다. CI와 PL은 개별 파일 또는 하나의 CIPL PDF로 제공한다.

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
- 실제 가격 seed와 원본 분석 보고서는 Git에서 제외했다. 목표 프로젝트는 `jusozufdsnpdxezxptfp`이며 아직 연결·적용하지 않았다.

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
- KE Korea default profile: `KE Korea Co. LTD`, `#1510, 157 Yangpyung Ro, Yungdeungpo Gu, Seoul, South Korea`, `Representative: DAVID, SEOKWON IHM`. Transaction-specific company details take priority. Solar PI uses `assets/company_logo.png` in the header and the private seal from `private/company_seal.png`; never commit the private seal.
- `agent/pricing.py`: Supabase REST API에서 최신 `kekorea_catalog_imports` ID, ECLADO 제품, 해당 import의 매입가·판매가를 서버에서 조회한다. ECLADO 공급 PO에는 매입가만, Dear Glow 판매 PI/CI에는 해당 구매처 판매가만 exact match로 적용한다. 구매처·공급처/통화가 다르면 해당 가격을 쓰지 않는다.
- Supabase 신형 `SUPABASE_SECRET_KEY`는 HTTPS REST 요청의 `apikey` 헤더로만 전달한다. 브라우저 코드, URL, 로그에 키를 노출하지 않는다. Secret key는 전체 DB 접근 권한이 있으므로 Streamlit 앱 공개 범위를 반드시 비공개로 설정한다.
- Supabase 연결 설정이 없으면 개발용 로컬 seed를 사용할 수 있으나, Cloud에서는 seed를 Git에서 제외하므로 Supabase 비밀 키가 필요하다. Supabase 조회 실패 시 오래된 로컬 가격으로 조용히 대체하지 않는다.
- `agent/trade_documents.py`: Decimal 계산, 할인·FOC 분리, 거래 역할·통화·가격 기준·포장 검증. 필수값 누락/충돌이면 DRAFT 상태로 막는다.
- `agent/renderers.py`: English PDF/XLSX/HTML review drafts. Solar PI uses the corporate-blue header with the company logo and PI-only bank details.

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
SUPABASE_URL = "https://jusozufdsnpdxezxptfp.supabase.co"
SUPABASE_SECRET_KEY = "새로 발급한 Supabase Secret key"
```

앱 접근 범위는 **Only specific people can view this app**로 제한한다. Supabase Secret key는 RLS를 우회하는 서버 전용 키이며 공개 Streamlit 앱에 두면 안 된다. 로컬 `.env`와 `private/` 가격 seed는 Git에서 제외한다.

### 검증과 미완료 사항

- Python `unittest`에서 SQL importer·계산·렌더러·OpenAI 모의요청·Supabase REST 모의요청 검증을 실행한다. 모의 테스트는 실제 Supabase 인증이나 실제 테이블 상태를 증명하지 않는다.
- 앱이 실제 Supabase에 연결되면 화면에 최근 catalog import 시각과 제품 수를 표시한다. “No ECLADO catalog import”는 테이블은 있어도 seed rows가 없을 때, HTTP 401/403은 키 또는 권한 문제, 404는 API 노출/테이블명 문제를 뜻한다.
- 실제 Supabase key, DB row, Streamlit Cloud Secrets로 라이브 연결은 아직 확인하지 않았다. 이 환경에서는 외부 Supabase endpoint에 접속하지 않고 비밀 키 없이 모의 응답으로만 검증한다.
- Order screenshots are supported. PDF/XLSX order uploads, final numbering/issuance, and CI/PL shipping integration are not connected. Generated files remain review drafts.
- PDF 화면 렌더링과 Excel 앱 검증은 미완료다. 회사 템플릿에 맞춘 편집 전 시각 검수가 필요하다.


## Buyer order image input and cosmetics money display

The Streamlit form accepts up to five PNG/JPG/JPEG/WEBP order screenshots (10 MB each, 20 MB total) alongside buyer/company details. On Extract, the prompt and images are sent to OpenAI for structured extraction. The app keeps the resulting document as a DRAFT and flags image-derived item details for visual review before download. OpenAI image inputs use billable tokens; upload only transaction images that are appropriate to send to the configured API.

For cosmetics, the final unit price is rounded before extending the line amount: KRW to whole won (`KRW 15,000` in English documents) and USD to two decimal places (`$10.57`). Totals, PI/PO/CI line items, spreadsheet outputs, and the app total display use the same rounding rule. Other product families retain their existing unit-price precision.


## PI corporate branding

The solar PI header displays the supplied company logo in a white brand panel. The faint body watermark was removed because the white party panels and pricing table obscured it. The former charcoal/gold fills and rules now use the logo's navy and blue palette.


## Brand assets and Cloud secrets

- The solar PI displays the supplied logo in a white header area. Navy and blue replace the previous charcoal and gold theme. No body watermark is used.
- `assets/company_logo.png` is tracked. `private/company_seal.png`, `.env`, generated outputs, and catalog seed data are excluded from Git.
- Streamlit Cloud uses `KEKOREA_COMPANY_SEAL_BASE64` for the private seal and the six `KEKOREA_USD_*` variables for PI bank details. Generate the seal value in PowerShell from the repository root with:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes('.\Quotation_KEKOREA\private\company_seal.png')) | Set-Clipboard
```

Copy the resulting value into Streamlit Cloud Secrets. Bank details appear on PI only.


## Shared document handling and document names

PI, PO, CI, PL, and CIPL use the same extraction, verified ECLADO catalog lookup, quantity synchronization, discount parsing, Decimal calculation, English translation checks, explicit REMARK handling (`N/A` when omitted), and branded PDF/XLSX renderer. PO uses ECLADO purchase prices when the supplier is ECLADO; sale documents use the Dear Glow price list only for Dear Glow buyers. Other cosmetic buyers require a separately approved price.

The Streamlit sidebar offers separate PI, PO, CI, PL, and CIPL workflows. CI creates a Commercial Invoice only; PL creates a Packing List only; CIPL creates both CI and PL using the same transaction data. PI alone includes KE KOREA's USD bank details. CIPL is recognized as a paired document request; PI/Proforma Invoice, PO/Purchase Order, CI/Commercial Invoice, and PL/Packing List aliases are accepted when the prompt explicitly requests creation. If the named document conflicts with the selected menu, extraction stops and tells the user which menu to choose.

Field extraction accepts common equivalent labels instead of requiring exact schema wording: Qty/Q'ty/ordered units/Volume for quantities; Item/Product/Goods/Description for product names; Unit Price/Rate/Price per unit for prices; Shipping Terms/Terms of Shipping/Ship Conditions/Delivery Terms for Incoterms; and Payment Conditions/Terms of Payment/Settlement Terms for payment. SET, BOX, CARTON, CTN, PALLET, and similar terms are retained as units or package descriptors based on context, never converted to another unit. If a quantity uses ambiguous `Volume` or a bare package-count label such as `Box: 10`, the review screen asks the user to confirm the interpretation before enabling PDF/XLSX downloads. Cubic/package volume and delivery dates are kept distinct from ordered quantity and Incoterms.

The shared PDF renderer preserves the source quantity unit on PI, PO, and CI lines (including PC/PCS/KG) and shows the unit separately in PL. It formats total quantities with thousands separators and groups different units instead of adding incompatible units together. CI/PI/PO amount boxes center both label and amount. Every PDF type requires and embeds the company seal below `KE KOREA CO. LTD` in its signature panel; if the seal asset is unavailable, downloads are blocked. Local generation uses `private/company_seal.png`; Streamlit Cloud must provide the top-level `KEKOREA_COMPANY_SEAL_BASE64` secret.

### Automatic document fields

- The issue date is always generated from the current date in `Asia/Seoul` and displayed in English (for example, `30 October 2026`). Dates copied from an order or email are not used as the issue date. This rule applies to PI, PO, CI, PL, CIPL, PDF, Excel, and HTML outputs.
- The PDF title badge shows the document identifier without a `DRAFT | NO.` prefix: PI and CI use `INVOICE #`, PO uses `PO #`, and PL uses `PACKING LIST #`. Draft status remains visible in the footer.
- `SHIP TO` contains only a specifically stated delivery destination, recognized from labels such as `Ship To`, `Delivered To`, `Delivery To`, `Delivery Address`, `Destination`, or equivalent supported-language labels. The buyer address, seller address, origin country, and EXW/FOB named place are not used as a destination. If no specific destination is provided, the document displays `N/A`.
