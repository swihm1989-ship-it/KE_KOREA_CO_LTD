"""검색 결과를 근거로 모델이 공식 Python 학습 자료를 소개한다."""
import os

from dotenv import load_dotenv
import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SearchArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    query: str = Field(min_length=1)
    count: int = Field(default=3, ge=1, le=20)


class SearchItem(BaseModel):
    model_config = ConfigDict(strict=True)
    title: str
    url: HttpUrl
    content: str | None


class SearchResults(BaseModel):
    model_config = ConfigDict(strict=True)
    results: list[SearchItem]


@tool(args_schema=SearchArgs)
def search_web(query: str, count: int = 3) -> SearchResults:
    """Tavily에서 웹 페이지 제목·URL·내용 발췌를 조회한다."""
    # TODO 1: query·count를 Tavily의 query·max_results 키에 담아 payload를 만든다.
    payload = {
        "query" : query, "max_results": count,
    }
    response = httpx.post(
        "https://api.tavily.com/search",
        json=payload,
        headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
        timeout=10,
    )
    response.raise_for_status()
    # TODO 2: 응답 JSON 전체를 SearchResults로 검사해 반환한다.
    return SearchResults(results=response.json())


REQUEST = 'Python 공식 문서에서 초보자용 학습 자료를 3개 찾아 제목과 링크를 소개해 줘.'
# REQUEST = "Python 공식 문서의 리스트 설명을 2개 찾아 링크를 알려 줘."
# 아래 안내 줄은 TODO 1~3을 모두 완성한 뒤 삭제한다.

load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
messages = [
    ("system", '최신 웹 자료를 찾는 요청은 반드시 검색 도구를 사용한다. '
     '찾을 자료 개수가 명시되면 그 개수를 count로 전달한다. '
     '공식 Python 학습 자료는 검색어에 site:docs.python.org를 넣어 찾는다. '
     '실제 검색 결과의 제목·URL·내용을 근거로 간결하게 소개한다. '
     '결과가 적으면 확인한 개수만 안내하고, 빈 목록이면 검색 결과가 없다고 알린다.'),
    ("human", REQUEST),
]
model_with_tools = model.bind_tools([search_web])
response = model_with_tools.invoke(messages)  # 모델이 실행할 도구와 인자를 고른다.
print("모델의 호출 요청:", response.tool_calls)
messages.append(response)  # 원래 호출 요청을 실행 결과 앞에 남긴다.

for call in response.tool_calls:
    result = search_web.invoke(call["args"])  # 여기서 실제 자료를 읽는다.
    print("실제 도구 결과:", result.model_dump(mode="json"))
    # TODO 3: 결과를 JSON으로 직렬화하고 원래 호출 ID로 ToolMessage를 만든다.
    raise NotImplementedError("TODO 3: 실제 결과와 호출 ID로 tool_message를 만드세요.")
    messages.append(tool_message)

# 결과를 읽은 모델의 안내를 받는다. 호출 요청이 없으면 첫 답변으로 끝낸다.
answer = model.invoke(messages) if response.tool_calls else response
print("최종 안내:", answer.text)