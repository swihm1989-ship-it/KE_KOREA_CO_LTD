"""공식 Tavily MCP의 검색 도구를 발견하고 실제 검색 결과로 안내한다."""
import asyncio
import os

import httpx2

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tracers import Run
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

TOOL_NAME = "tavily_search"
REQUEST = "Python 공식 문서에서 초보자용 학습 자료를 3개 검색해서 제목과 링크를 소개해 줘. 검색 범위는 docs.python.org로 한정해 줘."
INSTRUCTION = "검색 요청은 반드시 제공된 Tavily 도구로 실행한다. 검색어에 site:docs.python.org를 포함하고 max_results는 3으로 설정한다. 도구가 반환한 제목·URL·본문 설명만 근거로 안내한다. 검색 결과가 적으면 확인한 개수만 안내하고 링크를 만들지 않는다. 문서 버전은 검색 결과의 표기만 전달하고 최신 버전이라고 단정하지 않는다. 검색 도구는 한 번만 사용하고 반환 목록의 제목과 URL을 그대로 사용한다. 목록에 없는 링크로 바꾸거나 덧붙이지 않는다."

async def main():
    load_dotenv()
    headers = {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"}
    async with httpx2.AsyncClient(
        headers=headers, timeout=httpx2.Timeout(30.0, read=300.0)
    ) as http_client:
        # 원격 MCP 서버에 연결한다.
        async with streamable_http_client(
            "https://mcp.tavily.com/mcp/", http_client=http_client
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                available = (await session.list_tools()).tools
                print("서버의 도구:", [item.name for item in available])
                selected = next(item for item in available if item.name == TOOL_NAME)
                print("선택한 도구:", selected.name)
                print("입력 구조:", selected.input_schema)

                # 서버가 알려준 이름, 설명, 입력 구조를 그대로 모델에게 전달한다.
                definition = {"type": "function", "function" : {
                    "name" : selected.name, "description" : selected.description,
                    "parameters" : selected.input_schema
                }}

                model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
                messages = [("system", INSTRUCTION), ("human", REQUEST)]
                response = await model.bind_tools([definition]).ainvoke(messages)
                print("모델의 호출 요청:", response.tool_calls)
                messages.append(response)

                for call in response.tool_calls:
                    result = await session.call_tool(call["name"], call["args"])
                    print("실제 MCP 결과:", result.model_dump(mode="json"))
                    if result.is_error:
                        raise RuntimeError("MCP 도구 실행이 실패했습니다.")
                    messages.append(ToolMessage(
                        content=result.model_dump_json(exclude_none=True),
                        tool_call_id=call["id"]
                    ))

                answer = await model.ainvoke(messages) if response.tool_calls else response
                print("최종 안내:", answer.text)

asyncio.run(main())