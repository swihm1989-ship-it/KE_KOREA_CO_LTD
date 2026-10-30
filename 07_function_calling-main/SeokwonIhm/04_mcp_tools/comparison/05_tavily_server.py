"""직접 작성한 Tavily REST 검색을 MCP 도구로 제공한다."""
import os
from typing import Annotated

from dotenv import load_dotenv
import httpx
from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

mcp = MCPServer("Tavily 검색")
load_dotenv()


class SearchItem(BaseModel):
    model_config = ConfigDict(strict=True)
    title: str
    url: HttpUrl
    content: str | None


class SearchResults(BaseModel):
    model_config = ConfigDict(strict=True)
    results: list[SearchItem]


@mcp.tool()
def search_web(
    query: Annotated[str, Field(strict=True, min_length=1)],
    count: Annotated[int, Field(strict=True, ge=1, le=10)] = 3,
) -> SearchResults:
    """Tavily에서 웹 페이지 제목·URL·내용 발췌를 최대 count개 조회한다."""
    # 입력 계약은 함수의 타입·Field에서 만들어지고 실행 전에 검사된다.
    response = httpx.post(
        "https://api.tavily.com/search",
        json={"query": query, "max_results": count},
        headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
        timeout=10,
    )
    response.raise_for_status()
    # 필요한 반환 필드가 없으면 정상 빈 목록으로 바꾸지 않고 검사를 실패시킨다.
    return SearchResults.model_validate(response.json())


mcp.run(transport="stdio")