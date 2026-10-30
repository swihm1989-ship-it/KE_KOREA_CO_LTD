"""공식 Tavily MCP로 지정한 URL의 본문을 추출해 안내한다."""
import asyncio
import os

import httpx2

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

TOOL_NAME = "tavily_extract"
REQUEST = "https://docs.python.org/3/library/sqlite3.html 본문을 실제로 추출하고, sqlite3의 용도와 데이터베이스 연결 방법을 짧게 설명해 줘."
INSTRUCTION = "제공된 URL은 반드시 Tavily 추출 도구로 읽는다. 이 예제에서는 검색하지 않는다. 실제 추출 결과에 근거해 sqlite3의 용도와 연결 방법을 안내하고 출처 URL을 함께 표시한다. 본문을 얻지 못했으면 확인하지 못했다고 알린다."


async def main():
    load_dotenv()
    headers = {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"}
    # 인증 헤더는 HTTP 클라이언트에 설정하고 MCP 연결에 전달한다.
    async with httpx2.AsyncClient(
        headers=headers, timeout=httpx2.Timeout(30.0, read=300.0),
    ) as http_client:
        # 원격 MCP 서버에 연결한다. 도구 목록 조회 자체는 모델 호출이 아니다.
        async with streamable_http_client("https://mcp.tavily.com/mcp/", http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                available = (await session.list_tools()).tools
                print("서버의 도구:", [item.name for item in available])
                selected = next(item for item in available if item.name.replace("-", "_") == TOOL_NAME)
                print("선택한 도구:", selected.name)
                print("입력 구조:", selected.input_schema)

                # 서버가 알려 준 이름·설명·입력 구조를 그대로 모델에 전달한다.
                definition = {"type": "function", "function": {
                    "name": selected.name, "description": selected.description or "",
                    "parameters": selected.input_schema,
                }}
                model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
                messages = [("system", INSTRUCTION), ("human", REQUEST)]
                response = await model.bind_tools([definition]).ainvoke(messages)
                print("모델의 호출 요청:", response.tool_calls)
                messages.append(response)

                for call in response.tool_calls:
                    # 도구의 Python 구현은 서버에서 실행된다.
                    result = await session.call_tool(call["name"], call["args"])
                    print("실제 MCP 결과:", result.model_dump(mode="json", exclude_none=True))
                    if result.is_error:
                        raise RuntimeError("MCP 도구 실행이 실패했습니다.")
                    messages.append(ToolMessage(
                        content=result.model_dump_json(exclude_none=True),
                        tool_call_id=call["id"],  # MCP 요청 ID가 아닌 모델의 호출 ID다.
                    ))

                answer = await model.ainvoke(messages) if response.tool_calls else response
                print("최종 안내:", answer.text)


asyncio.run(main())