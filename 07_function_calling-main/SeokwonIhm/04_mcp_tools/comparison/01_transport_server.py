"""같은 매장 안내 도구를 stdio 또는 HTTP로 제공한다."""
from pathlib import Path

from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict

TRANSPORT = "streamable-http"  # stdio와 비교할 때는 "stdio"로 바꾼다.
GUIDE_PATH = Path(__file__).resolve().parents[1] / "data" / "guide.txt"
mcp = MCPServer("매장 안내")


class Guide(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    source: str
    text: str


@mcp.tool()
def read_cafe_guide() -> Guide:
    """가상 매장의 영업시간과 이용 안내를 읽는다."""
    return Guide(source=GUIDE_PATH.name, text=GUIDE_PATH.read_text(encoding="utf-8"))


if TRANSPORT == "streamable-http":
    mcp.run(transport=TRANSPORT, host="127.0.0.1", port=8765)
else:
    mcp.run(transport=TRANSPORT)