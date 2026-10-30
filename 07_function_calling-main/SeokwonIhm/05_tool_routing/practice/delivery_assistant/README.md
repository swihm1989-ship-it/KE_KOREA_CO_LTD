# 배송 상태·수령 장소 MCP 도우미

`app.py`를 SeokwonIhm의 기존 `.venv` 인터프리터로 Run하면 터미널 대화를 시작한다. `SeokwonIhm/.env`의 `OPENAI_MODEL`, `OPENAI_API_KEY`를 사용한다. 환경 파일이나 키를 이 폴더에 복사할 필요가 없다. 서버는 앱이 자동 실행한다.

이 폴더에서 PowerShell로 실행할 수도 있다.

```powershell
& ..\..\..\.venv\Scripts\python.exe app.py
```

## 사용한 도구

| MCP 도구 | 입력 | 자료·용도 |
| --- | --- | --- |
| `lookup_delivery` | `tracking_number` | `../data/deliveries.json`에서 배송 상태 조회 |
| `lookup_pickup_point` | `pickup_point_id` | 현재 배송이 보관소 도착 상태일 때 `../data/pickup_points.json`에서 장소 조회 |

`server.py`는 설치된 MCP 2.x의 `MCPServer`를 사용한다. 앱은 stdio MCP 세션으로 도구 목록을 발견하고 도구를 호출한다. 실제 사용한 도구는 코드의 `# 사용 도구`, `# 사용 MCP 도구` 주석에도 명시했다. 외부 검색 도구는 이 과제에 필요하지 않다.

일반 질문과 배송 외 질문은 배송 도구 없이 답한다. 배송 문의는 번호가 없으면 먼저 물으며, 보충 답변은 원래 질문과 같은 대화에 추가한다. 변경 문의도 상태를 조회한 후 변경 미지원 안내를 한다. 이 동작은 원본 과제의 변경 요청 도구 0회 규칙 대신 사용자가 선택한 규칙을 따른다. 데이터는 읽기 전용이며 실제 변경을 수행하지 않는다.

## 모델과 Python의 역할

- 모델: `Intent` 구조화 응답으로 일반/배송/변경 문의를 분류하고 번호를 추출한다. 현재 공개된 도구의 인자를 선택하고, 실제 반환값으로 안내를 작성한다.
- Python: 이번 요청·보충 답변에 없는 번호는 거부한다. 배송 조회 전에는 배송 도구만 공개한다. 보관소 도착 결과가 있을 때만 보관소 도구를 공개하고, 인자가 현재 반환 ID와 같은지 검사한다.
- Python: 새 문의마다 조회 상태를 초기화하고, 도구 실행은 최대 4회로 제한한다. 잘못된 모델 요청도 4번까지만 받는다. 모든 도구 요청에는 동일한 호출 ID의 `ToolMessage`를 연결한다.
- Python: Pydantic으로 입력·반환을 검사한다. 미등록은 `found=false`, 실행 실패는 오류 메시지로 구분한다. 보관소 미등록이어도 이미 확인한 배송 상태는 보존한다.

`updated_at`은 가상 자료의 기준 시각이다. 앱은 실제 택배사에 연결하거나 실시간 상태를 확인하지 않는다.

## 검증

```powershell
# 외부 모델 API 없이 실제 로컬 MCP 통신과 JSON·계약 검사
& ..\..\..\.venv\Scripts\python.exe -m unittest discover -v

# 실제 모델 API 사용: 요청·예상 경로·실제 호출·반환·최종 안내 기록 생성
& ..\..\..\.venv\Scripts\python.exe verify_scenarios.py
```

`verification.json`은 실제 모델/MCP 실행 기록이다. `REPORT.md`에 결과와 구현 시 수정한 사항을 정리한다. 검증 스크립트의 `path_passed`는 호출 경로 검사이며 최종 안내 문장의 사실 일치는 기록을 별도로 확인한다.
