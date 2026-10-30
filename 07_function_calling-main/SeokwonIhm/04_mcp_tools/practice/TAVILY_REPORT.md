# Tavily MCP 모델 검증 결과

## 검증 범위

`.env`의 설정 모델 `gpt-6-luna`와 Tavily API 키를 사용해 실제 외부 API 호출을 수행했다. 목적은 모델 전반의 지식 정확도 평가가 아니라, 외부 검색 도구 호출과 검색 결과의 제목·URL 전달 확인이다.

실행 코드: [04_tavily_verify.py](./04_tavily_verify.py)

실제 기록: [tavily_verification.json](./tavily_verification.json)

## 요청과 실행

요청: “Python 공식 문서에서 초보자 학습 자료를 최대 3개 찾아 제목과 링크를 알려 줘. docs.python.org만 검색해 줘.”

모델이 실제 요청한 도구는 `tavily_search`였다. 주요 인자는 다음과 같다. 전체 인자는 JSON 기록에 보존했다.

```json
{
  "query": "site:docs.python.org Python beginner tutorial learning resources",
  "max_results": 3,
  "search_depth": "advanced",
  "include_domains": ["docs.python.org"]
}
```

Tavily가 실제 반환한 자료:

| 제목 | URL |
| --- | --- |
| The Python Tutorial — Python 3.15.1 documentation | https://docs.python.org/3/tutorial/index |
| The Python Tutorial — Python 3.15.0 documentation | http://docs.python.org/py3k/tutorial |
| General Python FAQ — Python 3.15.2 documentation | https://docs.python.org/3/faq/general.html |

제목의 버전 표기는 검색 결과 원문이며 최신 버전으로 검증한 내용은 아니다.

최종 모델 응답은 Pydantic 구조화 출력으로 받았다. 실제 응답은 위 목록의 첫 번째와 세 번째 항목, 총 2개였다. 제목과 URL은 반환된 검색 결과와 정확히 일치했다. 두 번째 항목을 제외한 이유는 모델 응답에 없으므로 추정하지 않는다.

## 자동 검사 결과

| 검사 | 결과 |
| --- | --- |
| 검색 도구를 정확히 한 번 요청 | 통과 |
| 검색어에 `site:docs.python.org` 포함 | 통과 |
| `include_domains`가 `docs.python.org`로 제한됨 | 통과 |
| `max_results=3` | 통과 |
| Tavily 도구 실행 성공 | 통과 |
| 검색 결과가 1~3개 | 통과: 3개 |
| 검색 결과의 도메인 확인 | 통과 |
| 도구 요청 ID와 ToolMessage ID 일치 | 통과 |
| 최종 응답의 제목·URL이 실제 결과에 존재 | 통과: 2개 모두 일치 |
| 모든 검색 결과를 중복 없이 최종 응답에 포함 | 실패: 3개 중 2개 포함 |

마지막 항목은 검증 코드가 요청보다 엄격하게 추가한 검사다. 원래 요청은 ‘최대 3개’이므로 2개를 제시한 것을 요청 위반으로 단정할 수 없다. 원시 JSON의 `passed: false`는 이 추가 검사까지 모두 통과하도록 집계한 결과이며, 도구 연결 실패나 출처 조작을 의미하지 않는다. 최초 실행 기록을 그대로 보존했다.

## 평가와 한계

이 실행에서는 모델의 외부 MCP 연결, 도구 선택, 검색 조건 준수, 호출 ID 연결 및 제목·링크의 검색 결과 일치를 확인했다.

문서 본문을 별도로 추출해 사실 주장을 검증하거나, 각 자료가 프로그래밍 입문자에게 적합한지 평가하지 않았다. 검색 결과의 제목·내용 자체가 최신·정확하다는 보장도 하지 않는다. 단일 질문의 성공을 모델 전체의 정확성 보장으로 해석할 수 없다.

API 키 값은 실행 기록에 포함하지 않았다.
