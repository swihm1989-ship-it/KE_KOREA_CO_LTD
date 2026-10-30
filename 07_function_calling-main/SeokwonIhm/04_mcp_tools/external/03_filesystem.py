"""허용한 자료 폴더의 안내문을 Filesystem MCP로 읽어 답한다."""
import asyncio
import os

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TOOL_NAME = "read_text_file"
REQUEST = f"{(DATA_DIR / 'guide.txt').as_posix()} 파일을 읽고 영업시간과 이용 규정을 알려 줘."
INSTRUCTION = "요청에 주어진 파일을 반드시 read_text_file 도구로 읽는다. 반환된 안내문에 있는 영업시간과 이용 규정만 안내한다. 이 예제는 파일을 읽는 작업이며 파일을 작성하거나 변경하지 않는다."


async def main():
    load_dotenv()
    # 클라이언트가 로컬 서버 프로세스를 시작하고 연결 종료 때 정리한다.
    server = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(DATA_DIR)],
    )
    async with stdio_client(server) as (read, write):
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