"""MCP 서버에서 발견한 메뉴 조회 도구를 LangChain의 모델의 안내에 연결한다."""
import os
import asyncio
from pathlib import Path
import sys

from dotenv import load_dotenv
from langchain_core.messages import MessageLikeRepresentation, ToolMessage
from langchain_openai import ChatOpenAI
from mcp import ClientSession, StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().with_name("01_menu_server.py")
REQUEST = "3천원 이하의 아이스 커피를 추천하고 가격과 재고를 알려 줘."
# REQUEST = "아이스 커피를 추천해 줘."
# REQUEST = "따뜻한 에이드를 7천원 이하에서 추천해 줘."

async def main():
    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    server = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            # next()는 받은 목록에서 이름이 일치하는 첫 도구를 고른다.
            menu_tool = next(tool for tool in listed.tools if tool.name == "lookup_menu")
            tools = [{"type" : "function", "function" : {
                "name" : menu_tool.name,
                "description" : menu_tool.description,
                "parameters" : menu_tool.input_schema
            }}]
            messages: list[MessageLikeRepresentation] = [
                ("system", "메뉴는 도구로 조회한다. 예산이 없으면 예산만 질문하고 추측하지 않는다. "
                 "종류·온도 생략은 전체로 조회하며 따뜻한은 HOT, 아이스는 ICE다. "
                 "확인한 메뉴 중 재고가 있는 것만 이름·가격·재고·설명에 근거한 이유로 추천한다. "
                 "빈 목록이나 전부 품절이면 추천할 메뉴가 없다고 알린다. "
                 "자료에 없는 사실이나 주문·결제 완료를 만들지 않는다."),
                ("human", REQUEST),
            ]

            response = await model.bind_tools(tools).ainvoke(messages)
            print("모델의 도구요청:", response.tool_calls)
            messages.append(response)
            for call in response.tool_calls:
                result=await session.call_tool(call["name"], call["args"])
                print("실제 MCP결과:", result.model_dump(mode="json"))
                if result.is_error:
                    raise ValueError("MCP 도구 실행이 실패했습니다. 실제결과를 확인해봐")
                messages.append(ToolMessage(
                    content=result.model_dump_json(), tool_call_id=call["id"]
                ))

            answer = await model.ainvoke(messages) if response.tool_calls else response
            print("최종안내:", answer.text)

asyncio.run(main())
