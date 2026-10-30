"""MCP 입력 거부와 정상 빈 결과, 구조화 된 반환을 모델 없이 확인한다."""
import asyncio
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().with_name("01_menu_server.py")

# 정상 조회·빈 결과·입력 오류를 같은 도구에 보내 비교할 점검 값이다.
CASES = [
    ("정상 조회", {"max_price": 5000, "category": "커피", "temperature": "ICE"}),
    ("정상 빈 결과", {"max_price": 7000, "category": "에이드", "temperature": "HOT"}),
    ("필수 예산 누락", {"category": "커피"}),
    ("예산 타입 오류", {"max_price": "5000"}),
    ("예산 범위 오류", {"max_price": -1}),
    ("허용 종류 오류", {"max_price": 5000, "category": "주스"}),
]

async def main():
    server = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool = next(tool for tool in (await session.list_tools()).tools if tool.name=="lookup_menu")

            print("입력 계약:", tool.input_schema)
            print("입력 계약:", tool.output_schema)
            for label, arguments in CASES:
                result = await session.call_tool(tool.name, arguments)
                print(label, "입력:",arguments)
                print("도구 오류 여부:", result.is_error)
                print("실제 결과:", result.model_dump(mode="json"))


asyncio.run(main())
