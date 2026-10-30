"""공식 Tavily MCP 연결과 발견한 검색·추출 계약을 준비한다."""
from contextlib import asynccontextmanager
import os

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

TAVILY_MCP_URL = "https://mcp.tavily.com/mcp/"


@asynccontextmanager
async def connect_tavily():
    # 호출하는 앱에서 load_dotenv()한 기존 키를 사용하며 헤더를 출력하지 않는다.
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
        timeout=httpx2.Timeout(30.0, read=120.0),
    ) as http_client:
        async with streamable_http_client(TAVILY_MCP_URL, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                available = (await session.list_tools()).tools
                definitions = {}
                for kind in ("search", "extract"):
                    selected = next(item for item in available
                                    if item.name.replace("-", "_") == f"tavily_{kind}")
                    # search/extract는 앱의 구분 키다. 실제 호출 이름은 서버 값을 유지한다.
                    definitions[kind] = {"type": "function", "function": {
                        "name": selected.name,
                        "description": selected.description or "",
                        "parameters": selected.input_schema,
                    }}
                yield session, definitions
