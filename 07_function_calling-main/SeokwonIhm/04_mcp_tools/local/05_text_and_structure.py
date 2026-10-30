from pathlib import Path
import sys
import asyncio

from mcp import ClientSession, StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().with_name("01_menu_server.py")

async def main():
    server = StdioServerParameters(command=sys.executable, args =[str(SERVER)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            listed = await session.list_tools()
            for name in ("lookup_menu_text","lookup_menu"):
                tool = next(tool for tool in listed.tools if tool.name == name)
                result = await session.call_tool(name,{"max_price":4000})
                print("도구:", name)
                print("반환구조:", tool.output_schema)
                print("content:",[item.model_dump(mode="json") for item in result.content])
                print("structured_content", result.structured_content)
   

asyncio.run(main())
