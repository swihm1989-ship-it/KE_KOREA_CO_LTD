"""1단계: 카페 MCP 서버에 연결해 도구의 사용법을 확인한다."""
import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).resolve().parents[1] / "local" / "01_menu_server.py"


async def main():
    # 현재 가상환경의 Python으로 서버를 시작한다.
    parameters = StdioServerParameters(
        command=sys.executable, args=[str(SERVER_PATH)]
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            # 서버와 통신 준비를 마친 뒤, 제공하는 도구 목록을 요청한다.
            await session.initialize()
            available = await session.list_tools()
            print("서버 연결 성공!")
            for tool in available.tools:
                print(f"\n도구 이름: {tool.name}")
                print(f"설명: {tool.description}")
                print("입력 구조:")
                print(json.dumps(tool.input_schema, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
