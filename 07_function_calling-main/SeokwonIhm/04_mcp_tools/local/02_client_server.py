from pathlib import Path
import sys
import asyncio

from mcp import ClientSession, StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().with_name("01_menu_server.py")

async def main():
    server = StdioServerParameters(command=sys.executable, args =[str(SERVER)])
    #
    async with stdio_client(server) as (read, write):

        async with ClientSession(read,write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                print("이름:", tool.name)
                print("이름:", tool.description)
                print("이름:", tool.input_schema)

            result = await session.call_tool(
                "lookup_menu",
                {"max_price": 5000, "category": "커피", "temperature":"ICE"}
            )

            print(result.model_dump_json(indent=2))



asyncio.run(main())
