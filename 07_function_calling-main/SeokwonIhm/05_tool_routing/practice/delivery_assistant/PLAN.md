# 배송 안내 MCP 앱 구현 계획

설계 기준: ../README.md와 사용자 지시. 배송 변경도 상태를 조회한 후 변경 미지원 안내를 한다(사용자 확인 완료). 두 JSON은 읽기 전용으로 사용한다.

- [x] contracts.py: 공백 제거 입력, 배송/보관소 반환과 문의 분류를 Pydantic으로 검사한다.
- [x] tools.py, server.py: lookup_delivery와 lookup_pickup_point를 로컬 stdio MCP 서버에 등록한다. 실행 오류와 미등록을 구분한다.
- [x] app.py, prompts.py: 일반 문의는 도구 없이, 배송 문의는 번호를 받은 후 도구를 사용한다. 보충 답변을 같은 이력에 넣고 새 문의마다 조회 상태를 초기화한다.
- [x] Python에서 현재 배송의 보관소 ID, 노출된 도구, 사용자 번호, 최대 4회 실행을 검사한다. AIMessage와 같은 ID의 ToolMessage를 유지한다.
- [x] 실제 MCP 통합 테스트와 모델 시나리오 검증을 실행하고 요청·예상 경로·실제 호출·최종 안내를 기록한다.

기존 수업 파일과 .env는 수정하거나 복사하지 않는다. 설치된 MCP 2.x의 MCPServer를 사용한다. 새 과제 폴더만 추가하고 커밋/브랜치 변경은 하지 않는다.
