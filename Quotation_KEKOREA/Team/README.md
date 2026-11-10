# KE KOREA — 팀 공유 및 구현 안내

> 현재 동작은 원격 코드 `f335e9e` 기준으로 대조했습니다. 문서 끝의 「2026-11-10 코드·README 대조 결과」를 우선 참고하세요. 이전 날짜의 테스트·패치 기록은 당시 상태이며 현재 운영 성공을 뜻하지 않습니다.

기준일: **2026-11-10**. 저장소 코드·SQL·의존성·로컬 테스트 기록을 기준으로 작성했습니다. 코드 구현, 실제 DB 적용, 로컬 실행, 운영 배포는 서로 구분합니다. 이 문서는 현재 구조를 설명하며 과거 변경 이력은 [프로젝트 README](../README.md)를 참고하세요.

## 처음 합류한 팀원을 위한 3분 안내

이 앱은 거래 내용을 문서로 정리하고 사람이 검토하도록 돕는다. AI가 내용을 추출·작성·검토하고, Python 코드가 숫자·출처·변경 범위를 검사하며, 사용자가 수정안을 승인한다.

읽는 순서: **아래 용어와 예시 → 3절 업무 흐름 → 4절 저장/RAG → 7절 실행 → 8절 검증 상태**. 발표 담당자는 [5분 발표 안내](../Presentation/README.md)와 [읽을 대본](../Presentation/presentation_script_ko.md)을 이어서 본다.

| 용어 | 쉬운 설명 | 이 앱에서 하는 일 |
| --- | --- | --- |
| API | 앱이 외부 기능에 요청하고 결과를 받는 통로 | OpenAI에 추출·작성·검토 요청 |
| LangGraph | 처리 단계와 순서를 연결하는 실행 도구 | 계약 분석의 추출→검증, 신규 초안의 준비→생성·검토→최종 구조 검증 |
| 장기기억 | 다시 열어 볼 수 있도록 남기는 기록 | Supabase의 계약·대화·메모·수정 이력. LangGraph 자체에 영속 기억을 둔 것은 아님 |
| RAG | 필요한 참고 지식을 찾아 AI에게 함께 제공 | 승인·활성 상태의 참고 메모를 유형에 맞춰 검색 |
| 임베딩 | 문장의 의미를 검색에 쓸 숫자로 표현 | 승인 메모의 의미 검색에 사용. 상품 가격을 생성하거나 확정하지 않음 |
| revision | 저장된 계약의 버전 번호 | 수정안 승인 후 새 버전 저장. 이전 버전과 충돌하면 적용 차단 |
| snapshot | 한 버전에 들어 있는 계약 데이터 묶음 | 당사자·조건·조항·검토사항 등을 함께 보관 |
| MCP | AI 도구 연결을 위한 별도 규약 | 이 운영 앱에는 아직 미구현. 개발 환경에서 쓰는 MCP와 구분 |

예시: 가상 물품 100 PCS, 단가 USD 2, EXW 조건을 입력하면 AI가 조건 후보를 만든다. 사용자는 BOX 2에서 확인하고 BOX 3의 초안을 검토한다. 문장 메모로 수정을 요청해도 즉시 원문은 바뀌지 않는다. 수정 전후를 비교·승인한 뒤 새 revision으로 저장된다. 다시 계약을 열 때 조회하는 기록과, 다른 계약 작성에 참고하는 승인 RAG 지식은 별도다.

```mermaid
flowchart LR
  A[거래 설명] --> B[LangGraph 계약 분석과 검증]
  B --> C[조건 후보와 사용자 확인]
  C --> D[LangGraph 신규 초안 생성과 품질검토]
  R[승인된 참고 메모 검색] --> D
  D --> E[본문 검토와 수정안 비교·승인]
  E --> F[새 revision 저장]
  F --> G[Supabase에서 다시 열기]
```

이 도식은 단계 설명이다. 모든 단계를 하나의 LangGraph나 하나의 자동 저장 작업으로 묶은 것은 아니다. 거래조건 분석 그래프와 신규 초안 그래프가 따로 있으며, DB 저장·승인은 기존 애플리케이션이 담당한다.

### 팀 인수인계 때 확인할 네 가지

| 담당 역할 | 확인할 자료 | 전달할 결과 |
| --- | --- | --- |
| 기능 설명 담당 | BOX 1→2→3과 가상 계약 | 후보·미리보기·저장 승인을 구분해 설명 |
| 개발 담당 | `ai_graph.py`, `drafting.py`, `repository.py` | 호출 흐름과 revision 충돌 처리 위치 설명 |
| 데이터 담당 | 승인 참고 메모와 DB/Storage 설정 | 실제 승인 샘플 유무, 검색 가능 여부, 시연 DB 확인 |
| 발표 담당 | 발표 대본과 가상 계약·검토용 파일 | 네트워크 없이도 설명할 화면/파일 준비 |

## 1. 먼저 알아야 할 구현 현황

| 기능/기술 | 현재 구현 | 근거 및 설명 |
| --- | --- | --- |
| 사용자 화면 | Streamlit | [app.py](../app.py), [contracts/ui.py](../contracts/ui.py). React/Next.js 앱이 아님 |
| AI 추출·작성 | OpenAI Responses API 직접 호출 | Python `urllib.request`로 요청하고 JSON을 검증. [extractor.py](../agent/extractor.py), [service.py](../contracts/service.py) |
| LangChain / LangGraph | 계약 전용 LangGraph 도입 | `contracts/ai_graph.py`, `requirements.txt`. 계약 분석·초안 검증 노드만 사용하며 일반 거래문서는 기존 경로 유지 |
| MCP | 앱 런타임에 구현되지 않음 | MCP 서버/클라이언트, 도구 등록·발견 및 MCP를 통한 DB 호출 없음. 개발 환경에서 제공되는 도구와 배포 앱의 기능은 별개 |
| 에이전트 오케스트레이션 | 계약 전용 LangGraph + 기존 Python 규칙 | 상태 없는 계약 분석/작성 그래프와 기존 거래문서 작업 관리. 여러 자율 에이전트의 협업 시스템은 아님 |
| 장기 저장소 | Supabase PostgreSQL + Storage | 계약·대화·revision·메모·참고자료·출력 기록 영속 저장. 아래 저장소 표 참고 |
| 공통 지식 재사용/RAG | 승인된 참고 메모 검색 후 프롬프트에 전달 | 임베딩/키워드 혼합 검색과 신규 초안용 조항별 키워드 검색. [library.py](../contracts/library.py) |
| 벡터 저장 방식 | JSONB manifest 안의 숫자 배열 | 기본 512차원 임베딩. pgvector 인덱스·FAISS·Chroma·Pinecone 미사용 |
| 자동학습 / fine-tuning | 구현되지 않음 | 계약 저장이나 파일 업로드만으로 모델 가중치를 학습하지 않음 |
| 외부 실행 | 사용자 검토용 문서 생성 | 실제 발주·송신·이메일·전자서명·결제 자동 실행 없음 |

## 2. 기능별 폴더 지도

```text
KE_KOREA_CO_LTD/
├─ Quotation_KEKOREA/
│  ├─ app.py                 # 앱 진입점·메뉴·거래 문서 연결
│  ├─ agent/                 # PO/PI/CI/PL 추출·상품/가격·계산·PDF/Excel
│  ├─ contracts/             # 계약 작성·검색·검토·수정·저장·PDF/DOCX
│  ├─ tests/                 # 공식 회귀 테스트와 Streamlit AppTest
│  ├─ supabase/              # DB 마이그레이션·가격 SQL·적용 안내
│  ├─ scripts/               # 샘플 등록·회사 정보·직인·가격 시드 관리
│  ├─ assets/                # 공개 로고 등 문서 자산
│  ├─ private/               # Git 제외 비공개 자료·설정용 자료
│  ├─ outputs/               # Git 제외 생성물; 영속 저장소로 보장하지 않음
│  ├─ Team/                  # 이 문서
│  └─ Presentation/          # 발표용 README 및 기존 발표 스크립트
├─ archive/bugfixes/         # 과거 수정 패키지; 실행 앱과 구분
├─ archive/backups/          # 과거 소스·문서 백업
├─ logs/tests/               # 테스트 실행 기록
├─ logs/preview/             # 로컬 임시 서버 로그
├─ docs/superpowers/plans/   # 구현 계획·작업 범위 기록
├─ scripts/                 # README 동기화 검사
└─ render.yaml              # Render 배포 설정
```

과거 폴더의 이전/현재 위치는 [보관함 안내](../../archive/README.md)와 [이동 명세](../../archive/move_manifest_2026-11-09.json)에 있습니다. `archive`의 보조 테스트는 과거 수정본과 함께 보존한 기록물입니다. 현재 테스트는 `Quotation_KEKOREA/tests`에서 실행합니다. 과거 적용 스크립트는 당시 경로·코드 형태를 가정하므로 현재 소스에 재실행하지 마세요.

## 3. 계약서 에이전트 구현

### 3.1 화면과 역할

- **BOX 1:** 거래 설명·참고자료 선택·AI 전송 동의·조건 분석·초안 생성.
- **BOX 2:** 조건 및 당사자 직접 입력·상태 확인·본문 조건 후보 추출·지급조건 관리.
- **BOX 3:** 문장별 미리보기·메모·위험 검토·수정안 비교/승인·DRAFT/FINAL 다운로드.
- 계약 유형은 `sale`, `trade_commission`, `investment_commission`; 출력 언어는 한국어/영어입니다. 한국어·영어·인도네시아어 조건 이름은 표준 키로 정규화하지만 인도네시아어 계약서 출력 모드를 제공하는 것은 아닙니다.
- [flow.py](../contracts/flow.py)는 초안 요청 의도와 초기 질문 수를 제어합니다. LangGraph 상태 그래프가 아닙니다. 계약 전용 실제 LangGraph 실행은 `contracts/ai_graph.py`가 담당합니다.

### 3.2 거래조건과 본문은 별도 데이터

[models.py](../contracts/models.py)의 snapshot은 `parties`, `terms`, `clauses`, `issues`, `reference_ids`, `omissions`, `revision` 등을 보관합니다.

- 조건 상태: `suggested`는 미승인 후보, `confirmed`는 사용자 확정, `missing`은 미정입니다. AI 추출은 자동 확정하지 않습니다.
- 본문에 숫자가 있다고 조건표가 자동 확정되는 것은 아닙니다. [clause_terms.py](../contracts/clause_terms.py)로 본문 근거를 다시 추출해 후보를 채우고 사용자가 확인합니다.
- [normalize_terms.py](../contracts/normalize_terms.py)는 조건 이름의 명시적 별칭을 정규화하고 수치·통화·단위·Incoterm 문맥을 비교합니다. 단가와 총액, 수량과 단위, 인도조건과 통지/일정 문구를 구분합니다.
- 기존 값과 충돌하는 후보는 조용히 덮어쓰지 않습니다. `4`와 `5`는 다르며 `5`와 `5.00`은 같은 수치일 수 있습니다. `$`만으로 USD를 확정하지 않습니다.

### 3.3 신규 초안 품질 파이프라인

```mermaid
flowchart LR
  A[거래조건 정리] --> B[조항 목차와 작성 기준]
  B --> C[선택 자료와 승인 메모에서 주제별 검색]
  C --> D[상세 초안 작성]
  D --> E[누락·충돌·문장 근거 검사]
  E --> F{보완 필요}
  F -->|예| G[해당 조항만 1회 보완 후 재검사]
  F -->|아니오| H[기존 화면에서 사용자 검토]
  G --> H
```

[새 drafting.py](../contracts/drafting.py)는 기존 두 생성 진입점에서 호출합니다. 화면·버튼·대화 흐름·저장/승인 절차는 유지합니다.

- 기본 작성 기준은 매매계약 13개, 커미션 계약 12개 주제입니다. 업무 범위·지급·기간·해지·책임·불가항력·비밀유지·통지·준거법·분쟁 해결·일반 조항과 유형별 인도/검수 또는 커미션 범위를 포함합니다. 명시적으로 승인된 준거법·분쟁 해결 제외 결정은 존중합니다.
- 불가항력은 사건 요건, 통지, 영향 완화, 이행 재개, 장기화 시 처리를 확인합니다. 다른 조항도 조건·의무·절차·효과를 작성하도록 지시하며 문장 길이만으로 품질을 평가하지 않습니다.
- 선택 첨부자료 전체에서 문단/페이지를 연결한 구간을 검색합니다. 주제별 최대 3개 새 구간, 발췌 합계 최대 100,000자입니다. 거래조건 분석의 기존 앞 12,000자 제한과 상세 작성용 검색은 별도입니다. 원문 전체를 모델에 무제한 전송하는 방식은 아닙니다.
- 모든 계획 주제의 구성요소와 실제 생성된 모든 조항에 검사 결과를 요구합니다. 문장 ID·인용 문구가 실제 본문에 존재하는지 확인합니다. 이 검증은 의미/법적 정당성의 결정적 증명이 아닙니다.
- 문제가 있으면 해당 조항만 1회 보완하고 다시 검사합니다. 무관한 조항·기존 문장 ID·확정 조건·보호된 커미션 지급 조항을 보존합니다. 남은 문제는 미확정 검토 항목으로 전달합니다.
- 신규 초안은 생성→품질검토→필요 시 1회 보완→재검토 순서입니다. 각 검토에서 잘못된 인용만 1회 재검증할 수 있어 생성/검사 API는 통상 2회, 최대 6회입니다. 요청별 소켓 타임아웃은 최대 150초, 내부 파이프라인 경과시간 예산은 600초입니다. 별도의 거래조건 분석은 180초이며 검색·임베딩 호출은 이 횟수에서 제외합니다. 이는 즉시 취소를 보장하는 UI 타이머가 아닙니다. 모델·품질검증을 자동 완화하지 않습니다.
- 잘못된 응답·허위 인용·범위 밖 수정·시간 초과는 중간 초안을 저장하지 않습니다. 이미 조항이 저장된 계약은 자동 재작성하지 않습니다. 모델을 자동 변경하지 않습니다.

### 3.4 수정·위험 검토·승인

| 기능 | 구현 및 경계 |
| --- | --- |
| 문장별 수정 | [editing.py](../contracts/editing.py), [service.py](../contracts/service.py): 기존 문장 ID와 원문을 기준으로 수정안을 검증 |
| 메모 일괄 수정 | [workspace.py](../contracts/workspace.py): 계약·문장·base revision이 유효한 메모만 모음 |
| AI 핵심 위험 검토 | [review.py](../contracts/review.py), [risk_review_workspace.py](../contracts/risk_review_workspace.py): 전체를 최대 10문장 단위로 검토, 묶음당 최대 5개 소견, 결과는 5건씩 표시 |
| 위험별 추천안 | 균형형·권리 보호형·보수적 협의형 3안; 편집 가능한 변수와 미리보기. 적용 버튼은 영구 저장 승인이 아님 |
| 통합 최종 수정 요청 | [final_merge.py](../contracts/final_merge.py): 메모와 위험 추천안의 같은 문장 충돌을 검사한 뒤 비교·승인 경로로 전달 |
| revision 저장 | [repository.py](../contracts/repository.py)와 DB RPC: 기대 revision 확인·행 잠금·새 snapshot 저장으로 동시 수정 충돌 방지 |
| 이전 메모 복구 | 이전 revision 메모는 자동 재적용하지 않음. 현재 계약/문장의 유효성을 확인하고 명시적으로 가져옴 |
| 지급 정책 | [commission_policy.py](../contracts/commission_policy.py): 트리거·지급기한·계좌·검토 근거를 분리. 기본 D+7 제안과 사용자가 합의한 조건을 구분하며 보호 조항은 조건표 경로로 갱신 |

새 초안의 품질 검사는 초안 생성 내부 단계이며, 사용자가 실행하는 기존 위험 검토/추천 기능과 별도입니다. 기존 `최종 수정 요청`은 법률적 FINAL 승인이나 전자서명이 아닙니다.

## 4. 장기 저장소와 RAG를 정확히 구분하기

### 4.1 저장되는 정보

| 정보 | 위치 | 지속성과 재사용 방식 |
| --- | --- | --- |
| 문서별 입력·첨부·비동기 작업 | Streamlit session + [workflow_state.py](../agent/workflow_state.py) | 브라우저 세션 상태. 서버 재시작 후 영속 복구 보장 없음 |
| 계약 기본정보 | `kekorea_contracts` | 계약 목록과 현재 revision |
| 계약 본문/조건 이력 | `kekorea_contract_revisions.snapshot` JSONB | revision별 저장·조회·복구 |
| 계약별 대화 | `kekorea_contract_messages` | DB에 저장. 현재 조회 상한 200건, AI 분석/작성은 최근 최대 30개 메시지 사용 |
| 메모·수정 제안 | `kekorea_contract_annotations` | 문장 ID·base revision·제안/적용 상태 저장 |
| 계약별 첨부·공통 샘플 | `kekorea_contract_references` + 비공개 Storage | 계약별 원본과 승인 기반 공통 재사용을 구분 |
| 승인된 선호 문구 | `kekorea_preferred_clauses` | 유형·언어·활성 여부에 맞는 문구를 생성에 전달 |
| 출력 기록/파일 | `kekorea_contract_exports` + 비공개 `kekorea-contracts` 버킷 | revision·형식·파일 해시·경로 저장 |
| 제품·가격·거래처 | `kekorea_catalog_imports`, `kekorea_products`, `kekorea_purchase_prices`, `kekorea_buyer_prices`, `kekorea_counterparties` | 거래 문서의 조회·보완 기준 데이터 |

DB 정의는 [계약 마이그레이션](../supabase/migrations/202611050001_contracts.sql), [가격 마이그레이션](../supabase/migrations/202610300001_eclado_catalog.sql), [거래처 마이그레이션](../supabase/migrations/202611030001_counterparties.sql)에 있습니다. SQL 파일 존재만으로 운영 DB에 적용됐다고 간주하지 않습니다.

### 4.2 공통 기억이 만들어지는 과정

`원본 등록 → 비공개 보관/해시 확인 → 승인 대기 → 관리자가 익명화 참고 메모 작성·검토 → 명시적 승인 → 검색 재사용`

- [library.py](../contracts/library.py)의 원본 ID는 파일 SHA-256 기반이며 같은 원본의 중복 등록을 확인합니다. 원본 파일은 `kekorea-contracts/library/sources/...`에 보관합니다.
- 공통 레코드는 `contract_id=NULL`입니다. `source_locations` JSONB의 관리용 manifest에 제목·유형·언어·활성 상태·revision·검토 시각·승인된 chunk·임베딩을 저장합니다.
- 관리자가 지정한 실제 원문 위치에 연결된 참고 메모를 승인합니다. 등록만 한 `library_pending`과 승인된 `library_approved`를 구분합니다.
- [promote_reference.py](../contracts/promote_reference.py)는 계약 소속·원본 해시를 확인하고 기존 첨부를 공통 승인 대기로 별도 등록합니다. 원본 계약에서 자동 삭제하거나 즉시 검색에 공개하지 않습니다.
- 연락처·일부 숫자/비율 패턴 차단은 보조 검사입니다. 회사명·개인정보 제거를 자동으로 완벽하게 수행하는 익명화 엔진은 아닙니다. 관리자 검토가 필요합니다.
- **계약 저장 = 장기 기록, 승인된 메모 검색 = 지식 재사용, 모델 가중치 학습 = 미구현**입니다. 모든 계약이나 모든 대화를 전역 기억으로 자동 공유하지 않습니다.

### 4.3 검색 방식 두 가지

1. **기존 공통 검색:** `search_library()`는 승인·활성·계약 유형을 필터링합니다. 기본 `text-embedding-3-small`, 512차원이며 설정상 `text-embedding-3-large`도 허용합니다. 벡터가 호환되면 Python에서 코사인 유사도 80% + 키워드 20%로 계산합니다. 기본 6개, 최대 8개 조각을 반환하며 조회 상한은 500개 레코드입니다. 임베딩 장애/불일치 시 키워드 경로와 안내를 사용합니다.
2. **신규 초안의 주제별 검색:** `search_library_topics()`는 승인 레코드를 한 번 읽고 조항별로 최대 3개를 키워드 검색합니다. 이 추가 단계는 임베딩 API를 호출하지 않습니다. 이후 선택 첨부자료와 합쳐 문맥을 발췌합니다.

청크당 참고 메모는 최대 2,500자, 샘플당 최대 64개입니다. 벡터는 JSONB의 숫자 배열이며 DB의 벡터 인덱스가 아닙니다. 소스 ID·원문 위치·라이브러리 revision과 검증된 인용을 추적하지만, 관련 계약서가 충분히 등록됐는지·검색 품질이 충분한지는 별도 평가해야 합니다. 참고자료의 금액·기한·법률·당사자를 현재 거래의 확정 사실로 상속하지 않습니다.

## 5. 무역 문서 기능

| 기능 | 주요 파일 | 구현 및 보호 규칙 |
| --- | --- | --- |
| 텍스트·이미지·PDF 추출 | [attachments.py](../agent/attachments.py), [extractor.py](../agent/extractor.py) | Responses API 구조화 추출. PyMuPDF로 텍스트/페이지 이미지 준비. 최대 5파일, 각 10 MB, 합계 20 MB |
| 상품 식별 | [product_matching.py](../agent/product_matching.py) | SKU·용량·변형 제약과 문자열 유사도. 90% 이상 호환 단일 후보도 사용자 확인, 68~90%는 후보 제시. 임베딩 매칭 아님 |
| 가격 조회 | [pricing.py](../agent/pricing.py) | PO는 검증된 ECLADO KRW 매입가, PI는 Dear Glow 판매가, CI는 첨부 PI 가격 보존. CI/PL 매칭으로 카탈로그 가격을 덮어쓰지 않음 |
| 거래처 보완 | [counterparties.py](../agent/counterparties.py) | 명시된 값/N/A 우선. 없는 주소나 배송지를 임의 추론하지 않음 |
| 금액·프로모션·샘플 | [trade_documents.py](../agent/trade_documents.py), [promotions.py](../agent/promotions.py), [samples.py](../agent/samples.py) | Decimal 계산, 명시적 수량 0 유지, 유상/FOC 구분, 샘플 수동값 보존 |
| PI → CI | [ci_import.py](../agent/ci_import.py) | PI 거래가격·수량 근거 보존, 은행/결제정보 제외. PI 없는 CI는 차단 |
| PL 합계 승인 | [packing_review.py](../agent/packing_review.py), [packing.py](../agent/packing.py) | 원본/계산값 비교·명시적 승인·단위 분리. 컨테이너 크기를 개수로 곱하지 않음 |
| 메뉴별 동시 작업 | [workflow_state.py](../agent/workflow_state.py) | 세션별 `ThreadPoolExecutor(max_workers=3)`, 작업 복사본·오래된 결과 방지. 분산 작업 큐 아님 |
| PDF/Excel·직인 | [renderers.py](../agent/renderers.py), [pi_pdf.py](../agent/pi_pdf.py), [seal_storage.py](../agent/seal_storage.py) | 실제 공간에 따른 페이지 분할, 하단 묶음 보존, 비공개 직인 SHA-256 확인 |

## 6. 입력·출력과 외부 전송 경계

- 계약 참고자료는 PDF/DOCX/HWP5, 파일당 최대 20 MB, PDF 최대 100페이지, 요청당 최대 5개입니다. 구형 `.doc`는 PDF/DOCX 변환이 필요합니다. HWP는 읽기 지원이며 HWP 출력 기능은 없습니다.
- 텍스트 PDF는 PyMuPDF, DOCX는 ZIP/XML, HWP5는 `pyhwp` subprocess로 추출합니다. 스캔 참고 PDF의 OCR은 사용자 동의 후 OpenAI로 전송합니다.
- **계약 참고 OCR은 이미지 상단 78%만 처리**합니다. 하단 22%의 조항이 빠질 수 있으며 서명·직인·수기 판독/완전성을 보장하지 않습니다. 무역 PDF 입력 전처리와 같은 경로라고 설명하면 안 됩니다.
- 계약 출력은 ReportLab PDF + `python-docx` DOCX입니다. DRAFT는 저장된 검토용 본문을 출력합니다. FINAL은 현재 revision 승인과 직인 권한 검증이 필요하며 미확정 문구 출력은 별도 동의로만 허용합니다. 렌더러 직접 호출이 승인을 뜻하지 않습니다.
- 렌더링 성공 후 비공개 저장이 실패하면 현재 세션에 직접 다운로드를 제공할 수 있습니다. 서버에 저장된 기록과 구분하며 세션 종료 후 보존을 보장하지 않습니다.
- 추출·생성·검토·임베딩/OCR 실행은 각 경로에서 관련 내용을 OpenAI에 전송할 수 있습니다. DB 영속 저장과 모델 요청은 별도 처리입니다. 민감 문서의 외부 처리 허용 여부를 먼저 확인하세요.

## 7. 실행·설정·테스트

저장소 루트에서 실행합니다. Python 기준은 [`.python-version`](../../.python-version), 패키지는 [requirements.txt](../requirements.txt)입니다.

```powershell
# 로컬 전용 화면: 같은 포트를 사용 중이면 기존 서버를 먼저 확인
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m streamlit run .\Quotation_KEKOREA\app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false

# 전체 회귀 테스트
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v

git diff --check
```

로그 저장과 진행 표시를 함께 하려면 다음처럼 실행합니다. `*> 파일`만 쓰면 터미널에는 진행 내용이 보이지 않습니다. 실행한 테스트의 종료 코드는 `$LASTEXITCODE`로 확인합니다.

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v 2>&1 | Tee-Object -FilePath .\logs\tests\contract_test_full.log
$LASTEXITCODE
```

### 환경변수

값은 Git 제외 `.env` 또는 서버 Secrets에 보관합니다. [환경 예제](../.env.example)는 이름/형식 확인용입니다.

| 설정 | 역할 |
| --- | --- |
| `KEKOREA_AUTH_USERNAME`, `KEKOREA_AUTH_PASSWORD`, `KEKOREA_AUTH_SESSION_SECRET` | 앱 관리자 로그인과 서명된 세션; Streamlit Secrets에 보관 |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | 구조화 추출 및 기본 AI 모델 |
| `CONTRACT_OPENAI_MODEL` | 계약 전용 모델 선택; 비어 있으면 기본 모델 사용 |
| `CONTRACT_LIBRARY_EMBEDDING_MODEL` | 공통 참고 메모의 임베딩 모델 |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | 서버 측 DB/Storage 접근. 키를 브라우저 코드에 노출하지 않음 |
| `CONTRACT_LIBRARY_ADMIN_TOKEN` | 샘플 등록·원본 열람·승인 관리 키. 앱 전체 로그인 키가 아님 |
| `KEKOREA_USD_*` 6개 항목 | PI/커미션 수취 은행정보. 실제 값은 문서·로그에 복사하지 않음 |
| `KEKOREA_COMPANY_SEAL_BASE64` | 선택적 이전 방식 대체 경로; 기본은 비공개 Storage + 해시 확인 |

샘플 관리 스크립트 [import_contract_samples.py](../scripts/import_contract_samples.py)는 검토된 로컬 manifest와 등록 결과 receipt를 사용합니다. 원본·manifest·receipt는 Git 제외 `private/contracts` 아래에 보관하고, 재색인과 DB 쓰기는 담당자가 승인된 자료로 실행하세요.

## 8. 검증·배포·운영의 현재 경계

| 항목 | 확인한 내용 | 미확인/한계 |
| --- | --- | --- |
| 커밋별 과거 전체 테스트 | `987fd16`: 498개, `97a6199`: 501개 통과 | 그 이후 코드 전체를 같은 수치로 검증했다고 설명하지 않음 |
| 대조 기준 코드의 자동 검사 | `f335e9e`의 GitHub Actions 성공, 실행 `42749663125` | CI 성공과 운영 화면/실제 모델 품질은 별개 |
| 테스트 근거 | [실행 로그](../../logs/tests/drafting_quality_2026-11-09.log), [신규 테스트](../tests/test_contract_drafting.py), [연결 테스트](../tests/test_contract_library_ui.py) | 기존 Streamlit/PyMuPDF 경고 남음 |
| 로컬 임시 화면 | `127.0.0.1:8502`는 로컬 실행 예시 | 현재 가동을 확인한 주소가 아님. 발표 직전 직접 실행·로그인·화면 확인 필요 |
| 로컬 데이터 | 사용자 선택에 따라 **기존 Supabase DB 공유** | 임시 화면에서 만든 계약도 기존 DB에 저장. `[TEST]` 제목 사용; 완전히 격리된 staging DB가 아님 |
| Render | [render.yaml](../../render.yaml)에 `main`·Python·Streamlit 실행 설정 | 이번 변경의 배포/대시보드 연결·자동 반영 여부는 미확인 |
| Streamlit 운영 | 별도 호스팅 대상 | 이번 변경의 실제 배포와 문서 생성 경로는 미확인 |

- 앱 진입 전 관리자 로그인이 구현되어 있습니다(`Auth/gate.py`, `Auth/session.py`). 서명된 세션은 최초 로그인 후 12시간 제한이며 새로고침을 지원합니다. JavaScript 쿠키는 HttpOnly가 아니며, 사용자별 계약 권한 분리와 조직용 인증까지 구현한 것으로 설명하지 않습니다.
- 샘플 관리 키는 관리 영역에만 적용됩니다. 외부 공개 시에는 앱 인증·권한·비용 제한·감사 체계를 먼저 설계해야 합니다.
- 로컬 실행은 코드 배포와 분리되지만 DB를 자동 복제하지 않습니다. 운영 데이터를 수정하는 테스트나 삭제·복구 시연을 임의로 하지 마세요.
- Render 설정 파일의 자동 배포 선언과 실제 서비스의 Git 연결 상태는 별개입니다. 실제 서비스 상태는 배포 담당자가 확인해야 합니다.
- 의존성 라이선스의 적용 범위·실제 배포 승인 기록은 팀이 별도로 보관/검토합니다. 이 문서로 법적 적정성을 확인한 것으로 취급하지 않습니다.

## 9. 팀 인수인계에서 누락되기 쉬운 항목

| 항목 | 현재 결론 / 다음 확인 |
| --- | --- |
| 장기기억의 범위 | 계약 기록과 승인된 참고 지식은 저장됨. 모든 대화의 전역 자동 기억·자동학습은 없음 |
| 프레임워크 주장 | 계약 분석·검토 초안에 LangGraph 도입. LangChain 기반 검색·MCP 런타임·fine-tuning 도입으로 확대 해석하지 않음 |
| 지식 데이터 준비 | 실제 승인 샘플 수·조항별 다양성·개인정보 제거 상태는 이번 코드 검토로 확인하지 않음 |
| 의미 품질 평가 | 불가항력 등 대표 조항의 기준 계약 세트로 누락·허위 조건·검색 적합성·비용/지연을 실모델 평가해야 함 |
| OCR 완전성 | 상단 78% 크롭 및 불명확 문자 때문에 추출 원문과 실제 PDF를 비교해야 함 |
| 지속성 | 세션 메모리, DB 저장, Storage 업로드 성공, 직접 다운로드를 구분 |
| 운영 준비 | 관리자 로그인 구현. 사용자별 계약 권한, 조직용 인증, 독립 staging DB, 백업/복구 절차, 부하/비용 측정과 운영 모니터링은 별도 확인/구축 대상 |
| 오류 대응 | `logs/tests`·`logs/preview`와 revision·source ID로 추적. API 키·원본 계약·실제 계좌를 오류 로그에 남기지 않음 |
| 변경 규칙 | [AGENTS.md](../AGENTS.md) 보호 규칙과 [README 검사](../../scripts/check_readme_sync.py) 준수. 다섯 README를 함께 점검 |

## 10. 발표·유지보수 연결

- 팀 설명: 이 문서의 구현 표 → 저장소/RAG → 실행/검증 순서로 공유합니다.
- 발표/시연: [발표용 README](../Presentation/README.md)를 사용합니다. [5분 발표 대본](../Presentation/presentation_script_ko.md)은 준비된 가상 계약을 기준으로 읽고 시연하도록 갱신했습니다. 발표 전 실제 접속과 가상 파일을 확인하세요.
- 상세 계약 기능: [README_CONTRACTS.md](../README_CONTRACTS.md). 최근 설계: [초안 품질 계획](../../docs/superpowers/plans/2026-11-09-draft-quality-pipeline.md).


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
- 문서만 수정했다. 발표용 계약·캡처·파일 준비, 실제 낭독 시간 및 운영 시연 성공은 미확인이다. 준비 자료: [팀 안내](README.md), [발표 안내](../Presentation/README.md), [발표 대본](../Presentation/presentation_script_ko.md).
