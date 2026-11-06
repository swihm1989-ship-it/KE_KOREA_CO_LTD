# KE_KOREA_CO_LTD
무역 문서 및 AI 계약서 작성·검토 워크스페이스

## Quotation KEKOREA

제품군별 PO, PI, Commercial Invoice, Packing List 및 CIPL 검토용 초안을 만드는 Streamlit 앱입니다. 팀 공유 요약은 2026-11-05 기준입니다.

- [팀 공유용 구현·연동 안내](Quotation_KEKOREA/Team/README.md)
- [요구사항·설계·현재 구현/검증 상태](Quotation_KEKOREA/README.md)
- [ECLADO 가격 마스터 SQL 및 적용 안내](Quotation_KEKOREA/supabase/README.md)
- [향후 수정 시 지켜야 할 변경 보호 지침](Quotation_KEKOREA/AGENTS.md)
- [발표 스크립트](Quotation_KEKOREA/Presentation/presentation_script_ko.md)
- [Render 배포 앱](https://ke-korea-quotation.onrender.com/)
- [기존 Streamlit 배포 앱](https://ke-korea.streamlit.app/)
- 참고 학습 자료: `07_function_calling-main/SeokwonIhm/`

이미지·텍스트 추출, Supabase 가격 조회, 비공개 직인 로딩, 누락 정보 입력, PDF 페이지 분할과 파일 다운로드를 구현했습니다. 명시된 주문수량 0은 행을 유지하고 금액 0으로 계산합니다. 회사 명판·직인과 계좌정보는 페이지 사이에서 나누지 않습니다. 세부 변경 이력과 검증 방법은 프로젝트 README에 기록합니다. 모든 결과물은 사용자가 검토하는 초안이며 실제 발주·발송은 자동 수행하지 않습니다.

## 2026-11-06 TASTE 계약서 UI 및 README 동기화

- 기존 PO·PI·CI·PL 문서 자동화와 별도로 한국어/영어 계약서 초안, 대화 기반 조건 추출, 문장별 수정·비교·revision 저장 기능을 제공한다.
- 계약서 기능은 초안 중심 작업 흐름을 유지하고, 검토 이슈를 한국어로 최대 5개 주제로 요약한다. 기존 원본 검토 기록과 최종 내보내기 검사 규칙은 유지한다.
- 계약서에는 참고 문서와 승인된 조항의 검색(RAG) 기반 위험 검토가 포함되며, 위험 검토와 AI 분석은 자동으로 법률 검증을 완료한 것으로 취급하지 않는다.
- 수수료 계약의 지급기한·연체이율은 입력·갱신할 수 있다. 기본 D+7은 초기 제안일 뿐 사용자 합의 내용을 자동으로 덮어쓰지 않는다.
- 변경 시 프로젝트, 계약서, 팀, 발표용 README를 코드와 함께 동기화한다. [변경 보호 지침](Quotation_KEKOREA/AGENTS.md) 및 `scripts/check_readme_sync.py` 참고.
- GitHub 코드 반영, 로컬 테스트, 실제 Streamlit 운영 확인은 각각 구분한다.

### 2026-11-06 검증 보완

계약 수수료 기본 D+7 영문 조항은 `seven (7) calendar days` 표기를 유지하며, 사용자 지정 기간은 해당 일수를 출력합니다. PO/PI 상품명에 확인이 필요한 주석이 남아 있으면 PDF/Excel 생성 버튼을 비활성화합니다. 관련 상세 사항과 검증 방법은 `Quotation_KEKOREA/README.md`를 참조합니다.

2026-11-06 CI 회귀 보완: PO/PI는 확인이 필요한 제품 주석이 남으면 PDF/Excel 생성을 차단합니다. CI는 원본 PI 거래가격을 유지하며, 상품명 매칭이 미확정인 경우 경고 및 DRAFT 표시를 전제로 검토용 파일 생성을 허용합니다.
