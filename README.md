# KE_KOREA_CO_LTD
견적서 및 회사 에이전트 모음

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
