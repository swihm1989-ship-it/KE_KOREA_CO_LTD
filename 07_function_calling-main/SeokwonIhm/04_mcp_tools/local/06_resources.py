from pathlib import Path
import sys
import asyncio
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp import ClientSession, StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().with_name("01_menu_server.py")

async def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    server = StdioServerParameters(command=sys.executable, args =[str(SERVER)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            print("고정 자료 목록:", (await session.list_resources()).model_dump(mode="json"))
            print("자료 URI툴:", (await session.list_resource_templates()).model_dump(mode="json"))      

            guide = await session.read_resource("cafe://guide")
            coffee = await session.read_resource("cafe://menu/커피")

            guide_text = "\n".join(item.text for item in guide.contents)
            coffee_text = "\n".join(item.text for item in coffee.contents)

            print("guide_text", guide_text)
            print("guide_text", coffee_text)


    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    answer = await model.ainvoke([
        ("system", "제공 된 안내문과 메뉴 자료만 근거로 답하고 없는 정보는 만들지 마.\n"
         "안내문:\n"+ guide_text + "메뉴자료:\n" + coffee_text),
        ("human", "몇시까지 주문 가능, 재고가 있는 5천원 이하 커피는 무엇?")
        
    ])

    print(answer.text)


asyncio.run(main())
