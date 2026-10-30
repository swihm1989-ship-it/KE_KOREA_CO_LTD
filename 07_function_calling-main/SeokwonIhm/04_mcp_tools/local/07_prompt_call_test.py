from pathlib import Path
import sys
import asyncio
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import TextContent, TextResourceContents

SERVER = Path(__file__).resolve().with_name("01_menu_server.py")

async def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    server = StdioServerParameters(command=sys.executable, args =[str(SERVER)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            print("요청 틀 목록", (await session.list_prompts()).model_dump(mode="json"))
            prompt = await session.get_prompt(
                "menu_guide", {"question": "영업 시간과 주문 마감, 좌석수를 알려주세요"}
            )

            print("가져온 요청 틀:", prompt.model_dump(mode="json"))

            guide = await session.read_resource("cafe://guide")
            guide_text = "\n".join(
                item.text for item in guide.contents
                if isinstance(item, TextResourceContents)
            )


    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    messages = [("system", "매장 안내문:\n" + guide_text)]
    for message in prompt.messages:
        if not isinstance(message.content, TextContent):
            raise ValueError("텍스트 형식의 요청 틀만 사용할 수 있습니다.")
        messages.append((message.role, message.content.text))
    answer = await model.ainvoke(messages)
    print("최종안내:", answer.text)

asyncio.run(main())
