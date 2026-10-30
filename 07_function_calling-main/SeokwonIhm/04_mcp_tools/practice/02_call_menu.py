"""2단계: 모델 없이 카페 MCP 도구를 직접 호출한다."""
import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).resolve().parents[1] / "local" / "01_menu_server.py"


async def main():
    parameters = StdioServerParameters(
        command=sys.executable, args=[str(SERVER_PATH)]
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 이번에는 모델 대신 우리가 도구 이름과 인자를 정한다.
            arguments = {
                "max_price": 3000,
                "category": "커피",
                "temperature": "ICE",
            }
            print("호출 도구: lookup_menu")
            print("호출 인자:")
            print(json.dumps(arguments, ensure_ascii=False, indent=2))

            result = await session.call_tool("lookup_menu", arguments)
            print("\n실제 MCP 반환 결과:")
            print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

            # 빈 메뉴 목록은 정상 결과이고, 도구 실행 실패와는 다르다.
            if result.is_error:
                raise RuntimeError("MCP 도구 실행 실패: 위의 실제 반환 결과를 확인하세요.")


if __name__ == "__main__":
    asyncio.run(main())
