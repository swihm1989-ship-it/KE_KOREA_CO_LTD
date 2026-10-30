"""비교 실행과 대화 앱이 전달받은 주제의 검색 작업·합류 함수를 함께 사용한다."""
import re
from ipaddress import ip_address
from urllib.parse import urlsplit

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from batch import execute_batch, merge_results
from mcp_results import parse_search_result

MAX_TOPICS = 5  # 한 번에 수집할 주제 수의 비용 상한이며, 동시 실행 상한과는 별개다.
HOSTNAME = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class SearchArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    topics: list[str] = Field(min_length=1, max_length=MAX_TOPICS)
    domains: list[str] | None = None

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, values):
        cleaned = [value.strip() for value in values]
        if not all(cleaned):
            raise ValueError("검색 주제는 비어 있지 않은 문자열이어야 합니다.")
        return list(dict.fromkeys(cleaned))

    @field_validator("domains")
    @classmethod
    def clean_domains(cls, values):
        if values is None:
            return None
        cleaned = [value.strip().lower() for value in values]
        if not all(HOSTNAME.fullmatch(value) for value in cleaned):
            raise ValueError("도메인은 URL·경로·포트·와일드카드가 없는 호스트 이름이어야 합니다.")
        return list(dict.fromkeys(cleaned))


def search_jobs(definitions, topics, domains=None):
    planned = SearchArgs(topics=topics, domains=domains)
    name = definitions["search"]["function"]["name"]
    # 주제마다 실제 검색어를 가진 작업 하나를 만든다. 도메인을 생략하면 사이트 제한이 없다.
    options = {"max_results": 2, "include_raw_content": False}
    if planned.domains:
        options["include_domains"] = planned.domains
    return [{"topic": topic, "label": topic + " 자료 검색", "name": name,
             "args": {"query": topic, **options}} for topic in planned.topics]


async def run_searches(session, definitions, topics, domains=None, max_concurrency=2, parallel=True):
    planned = SearchArgs(topics=topics, domains=domains)
    # 실행 방법만 정의한다. 배치가 이 함수를 await할 때 실제 MCP 검색이 시작된다.
    async def run_one(job):
        returned = await session.call_tool(job["name"], job["args"])
        parsed = parse_search_result(returned).model_dump()
        for row in parsed["results"]:
            if not all(row[key].strip() for key in ("title", "url", "content")):
                raise ValueError("검색 결과의 제목·URL·검색 요약이 비어 있습니다.")
            address = urlsplit(row["url"])
            host = address.hostname or ""
            try:
                ip_address(host)
                valid_host = True
            except ValueError:
                valid_host = bool(HOSTNAME.fullmatch(host.encode("idna").decode("ascii")))
            if address.scheme not in ("http", "https") or not valid_host:
                raise ValueError("검색 결과에 유효한 HTTP(S) 주소가 없습니다.")
            if planned.domains and not any(host == domain or host.endswith("." + domain) for domain in planned.domains):
                raise ValueError("요청한 도메인 범위 밖의 검색 결과입니다.")
        return parsed

    # 검색 한 번이 작업 하나다. 각 작업은 다른 주제의 반환을 기다릴 필요가 없다.
    return await execute_batch(search_jobs(definitions, planned.topics, planned.domains), run_one,
                               max_concurrency=max_concurrency, parallel=parallel)


def build_reference_tool(session, definitions, max_concurrency=2):
    # 모델이 고른 주제·도메인을 같은 검색 실행 함수에 전달하는 업무 도구를 만든다.
    @tool(args_schema=SearchArgs)
    async def collect_reference_materials(topics: list[str], domains: list[str] | None = None) -> dict:
        """요청한 주제별 참고 자료를 검색하고 실제 제목·URL·검색 요약을 함께 모은다.

        topics에는 주제마다 검색어 하나를 넣는다. domains는 선택적인 사이트 호스트 이름 목록이다.
        검색 요약을 반환하며 URL 본문 읽기·주문 실행은 지원하지 않는다.
        """
        planned = SearchArgs(topics=topics, domains=domains)
        results = await run_searches(session, definitions, planned.topics, planned.domains,
                                    max_concurrency=max_concurrency)
        # 모든 내부 검색이 돌아온 뒤 이번 요청의 주제 목록을 기준으로 한 결과로 합류한다.
        return merge_results(results, planned.topics)

    return collect_reference_materials
