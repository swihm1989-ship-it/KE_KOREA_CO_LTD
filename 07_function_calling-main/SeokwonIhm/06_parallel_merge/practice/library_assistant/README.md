# 세 도서관 병렬 대출 가능 도서 조회

`app.py`를 기존 `SeokwonIhm/.venv` 인터프리터로 Run하면 대화를 시작한다. 기존 `SeokwonIhm/.env`의 모델 설정과 키를 사용하며 새 환경 파일을 만들지 않는다. 이 폴더에서 PowerShell로 실행할 수도 있다.

```powershell
& ..\..\..\.venv\Scripts\python.exe app.py
```

## 코드 구성

| 파일 | 역할 |
| --- | --- |
| `contracts.py` | 제목·권수·JSON·작업 기록·병합 반환 검사 |
| `tools.py` | JSON 조회와 `compare_library_stock(title)` 도구 정의 |
| `batch.py` | `asyncio.gather`, `Semaphore`를 통한 실행과 합류 후 병합 |
| `prompts.py` | 제목 질문, 일반 설명, 예약 미지원, 실제 자료에 근거한 답변 지시 |
| `app.py` | 대화 이력, 도구 실행, 원래 호출 ID의 `ToolMessage` 연결 |
| `compare_execution.py` | 외부 모델 없이 순차·병렬 비교 및 실행 기록 생성 |
| `test_library_assistant.py` | 자료·동시 실행·실패·취소·대화 연결 회귀 테스트 |

모델이 호출하는 도구는 `compare_library_stock(title)` 하나다. 내부 지점별 조회에는 모델 API나 MCP를 사용하지 않고 제공된 JSON을 직접 읽는다. 모델 도구 호출 1개 안에 중앙·동부·서부 작업 3개가 있으며, 실제 병합 결과를 담은 `ToolMessage`는 원래 호출 ID로 1개만 전달한다.

`batch.py`는 세 작업을 `asyncio.gather`로 예약하고 `async with semaphore` 안에서 최대 2개를 동시에 실행한다. 중앙과 동부가 시작된 뒤 먼저 끝난 작업의 자리를 서부가 사용한다. 작업 시간은 자리를 얻은 뒤부터 측정하며, 자리 대기는 전체 시간에 포함된다. 지연은 `asyncio.sleep`, 파일 읽기는 `asyncio.to_thread`를 사용한다.

모든 작업이 끝난 뒤 `merge_results()`가 권수 1권 이상·등록 도서 0권·미등록·오류를 구분한다. 일부 오류는 `partial`, 전부 오류는 `failed`이며 성공한 결과는 유지한다. 미등록도 정상 조회여서 세 지점이 정상 반환하면 `complete`다. 호출자의 취소는 오류 결과로 바꾸지 않고 상위로 전파한다.

## 설정과 입력 예시

`tools.py`의 `SCENARIO`는 `normal`, `east_error`, `all_error` 중 선택하고 `MAX_CONCURRENCY`는 1 또는 2로 정한다. 변경 후 새로 Run한다. 모델에는 제목만 인자로 공개하며 실행 조건은 Python이 정한다.

- `파이썬 첫걸음을 빌릴 수 있는 지점을 알려 줘.`
- `데이터 분석 입문을 빌릴 수 있어?`
- `비동기 프로그래밍은 어디서 빌려?`
- `책을 빌릴 수 있는 지점을 알려 줘.` → 제목 질문에 `파이썬 첫걸음`
- `대출 가능 0권과 도서 미등록은 무슨 차이야?`
- `파이썬 첫걸음을 예약해 줘.`

일반 개념 설명과 예약 요청은 도구 없이 답하도록 지시한다. 새 제목에는 새 조회를 실행하며 이전 책의 권수를 재사용하지 않는다. 자료는 실습용 고정 JSON이므로 실시간 도서관 정보나 예약·대출 완료로 표현하지 않는다.

## 모델 없는 검증

```powershell
# TITLE·SCENARIO·MAX_CONCURRENCY를 바꾸어 순차·병렬 한 쌍 비교
& ..\..\..\.venv\Scripts\python.exe compare_execution.py

# 네 제목과 실패 시나리오, 순차/상한 1/상한 2 검증
& ..\..\..\.venv\Scripts\python.exe compare_execution.py --verify-all

# 로컬 테스트 전체 실행
& ..\..\..\.venv\Scripts\python.exe -m unittest discover -v
```

`comparison_results.json`, `verification.json`에 실제 지점별 실행 구간·오류·병합 반환·모델 없는 정형 안내를 기록한다. `REPORT.md`는 결과 요약이다. 총시간과 속도 차이는 관찰값이며 모든 실행 환경에서 같은 속도 향상을 보장하지 않는다.

대화 테스트는 모델의 응답을 고정해 메시지 연결을 검사한다. 실제 모델의 자연어 판단·최종 답변을 검증한 기록과 구분해야 한다. 실제 모델 API는 `app.py`를 Run할 때 사용한다.
