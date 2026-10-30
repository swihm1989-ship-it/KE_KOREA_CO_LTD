"""MCP 응답의 필수 필드와 이번 요청에 실제로 적힌 URL을 읽는다."""
import json
import re

from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict


class SearchItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    url: str
    title: str
    content: str


class SearchResults(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    results: list[SearchItem]


class ExtractItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    url: str
    raw_content: str


class ExtractFailure(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    url: str
    error: str


class ExtractResults(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    results: list[ExtractItem]
    failed_results: list[ExtractFailure]


def _response_data(result: CallToolResult):
    """구조화된 결과를 우선 읽고, 없는 경우 JSON 텍스트를 읽는다."""
    if result.is_error:
        raise ValueError("Tavily MCP가 도구 실행 오류를 반환했습니다.")
    if result.structured_content is not None:
        return result.structured_content
    for item in result.content:
        if item.type == "text":
            try:
                return json.loads(item.text)
            except json.JSONDecodeError:
                continue
    raise ValueError("Tavily 응답에서 JSON 결과를 찾지 못했습니다.")


def parse_search_result(result: CallToolResult) -> SearchResults:
    # results는 필수다. 누락·잘못된 타입을 정상 빈 검색으로 바꾸지 않는다.
    return SearchResults.model_validate(_response_data(result))


def parse_extract_result(result: CallToolResult) -> ExtractResults:
    # 성공 본문과 개별 URL 실패를 구분하고, 사용하지 않는 제공자 필드는 무시한다.
    return ExtractResults.model_validate(_response_data(result))


def request_urls(text: str) -> set[str]:
    """사용자가 이번 요청에 실제로 적은 HTTP(S) URL만 모은다."""
    urls = set()
    closing = {")": "(", "]": "[", "}": "{"}
    for found in re.findall(r"https?://[^\s<>\"'`]+", text):
        url = found.rstrip(".,;:!?…。。，；：！？”’")
        # 마크다운 링크의 닫는 괄호는 제외하고 URL 안의 짝맞는 괄호는 유지한다.
        while url and url[-1] in closing and url.count(url[-1]) > url.count(closing[url[-1]]):
            url = url[:-1]
        urls.add(url)
    return urls
