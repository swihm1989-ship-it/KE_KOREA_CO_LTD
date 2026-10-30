"""메뉴 조회·매장 자료·안내 요청 틀을 제공하는 MCP 서버다."""
import csv
import json
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import unquote

from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict, Field

DATA = Path(__file__).resolve().parents[1] / "data"

#MCP 서버 생성 방법 
mcp = MCPServer("cafe-menu")


class Menu(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    menu_id: str
    name: str
    category: Literal["커피", "차", "에이드"]
    temperature: Literal["HOT", "ICE"]
    price_won: int = Field(ge=0)
    stock: int = Field(ge=0)
    description: str


class MenuResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    menus: list[Menu]


def read_menu() -> list[Menu]:
    """CSV의 숫자를 변환하고 각 메뉴 행을 검사한다."""
    menus = []
    with (DATA / "menu.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            row["price_won"] = int(row["price_won"])
            row["stock"] = int(row["stock"])
            menus.append(Menu.model_validate(row)) 
    return menus

@mcp.tool(title = "예산별 메뉴 조회")
def lookup_menu(
    max_price: Annotated[int, Field(strict=True, ge=0, description="최대 예산(원). 0 이상의 정수.")],
    category: Literal["전체", "커피", "차", "에이드"] = "전체",
    temperature: Literal["전체", "HOT", "ICE"] = "전체",
) -> MenuResult:
    """최대 예산 이하 메뉴를 조회한다. 종류·온도는 생략하면 전체다. 재고 0은 품절이다."""
    selected = [
        menu for menu in read_menu()
        if menu.price_won <= max_price
        and (category == "전체" or menu.category == category)
        and (temperature == "전체" or menu.temperature == temperature)
    ]
    return MenuResult(menus=selected) 


@mcp.tool(structured_output=False)
def lookup_menu_text(max_price: Annotated[int, Field(strict=True, ge=0)]):
    """같은 예산 조회 결과를 비교용 텡스트로 반환"""
    result = lookup_menu(max_price)
    return "\n".join(
        f"{menu.name}{menu.temperature}:{menu.price_won}원, 재고{menu.stock}개"
        for menu in result.menus
    ) or "조건에 맞는 메뉴가 없음"


@mcp.resource("cafe://guide", title="매장 이용안내", mime_type="text/plain")
def cafe_guide()->str:
    """,매장 이용 안내문을 읽는다."""

    return(DATA/"guide.txt").read_text(encoding="utf-8")

@mcp.resource("cafe://menu/{category}",title="종류별 메뉴", mime_type="application/json")
def menu_by_category(category:str)->str:
    """종류별 메뉴자료를 읽는다. 전체, 커피, 차 에이드를 사용한다"""
    category = unquote(category) #URI에 인코딩 된 한글을 원래 문자로 복원
    menus = [menu.model_dump() for menu in read_menu() 
             if category =="전체" or menu.category==category]
    return json.dumps({"menus":menus}, ensure_ascii=False)

@mcp.prompt(title="메뉴/매장 안내 요청")
def menu_guide(question:str)->str:
    """매장안내 자료에 근거해 답변하는 요청 틀"""
    return(
        "함께 제공 된 매장 안내문만 근거로 고객 문의에 간결하게 답한다."
        "자료에 없는 내용은 확인 되지 않았다고 알린다. \n 고객문의:"+question

    )


#stdio 속성으로 mcp 요청을 기다림
mcp.run(transport="stdio")