"""메뉴 문의 한 건을 받아 CSV 조회 결과로 답한다."""
import csv
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

MENU_PATH = Path(__file__).resolve().parent / "data" / "menu.csv"


class MenuArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    max_price: int = Field(ge=0)
    category: Literal["전체", "커피", "차", "에이드"] = "전체"
    temperature: Literal["전체", "HOT", "ICE"] = "전체"


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


@tool(args_schema=MenuArgs)
def lookup_menu(max_price: int, category: str = "전체", temperature: str = "전체") -> MenuResult:
    """최대 가격으로 메뉴를 읽는다. 분류·온도는 생략하면 전체이며 가격은 원 단위다."""
    selected = []
    with MENU_PATH.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            row["price_won"] = int(row["price_won"])
            row["stock"] = int(row["stock"])
            menu = Menu.model_validate(row)
            if (
                (category == "전체" or menu.category == category)
                and (temperature == "전체" or menu.temperature == temperature)
                and menu.price_won <= max_price
            ):
                selected.append(menu)
    return MenuResult(menus=selected)


REQUEST = input("메뉴 문의를 입력하세요: ").strip()
print("요청:", REQUEST)
if not REQUEST:
    print("예산을 포함한 메뉴 문의를 입력해 주세요.")
else:
    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    messages = [
        ("system", "카페 메뉴의 최대 예산이 있으면 반드시 도구로 조회한다. "
         "예산이 빠졌으면 예산만 확인 질문을 하고 도구를 실행하지 않는다. 예산을 임의로 정하지 않는다. "
         "분류는 전체·커피·차·에이드이고 온도는 전체·HOT·ICE이다. 따뜻한 메뉴는 HOT, 아이스 메뉴는 ICE로 전달한다. "
         "분류나 온도가 명시되지 않으면 해당 인자는 전체로 두어 그 조건을 제한하지 않는다. 종류나 온도를 추가로 묻지 않는다. "
         "예산이 음수이거나 지원하지 않는 분류·온도라면 허용 조건을 안내하고 도구를 실행하지 않는다. "
         "반환된 menus에서 재고 0은 품절로 보고 추천에서 제외한다. 목록이 비었거나 모두 품절이면 조건에 맞는 추천 메뉴가 없다고 알린다. "
         "메뉴 이름·가격·확인한 재고와 description에 근거한 선택 이유를 간결하게 안내한다. "
         "자료에 없는 재료·효능·입고일을 만들거나 주문 접수·결제 완료를 안내하지 않는다."),
        ("human", REQUEST),
    ]
    model_with_tools = model.bind_tools([lookup_menu])
    response = model_with_tools.invoke(messages)
    print("모델의 선택 인자:", response.tool_calls)
    messages.append(response)

    for call in response.tool_calls:
        result = lookup_menu.invoke(call["args"])
        print("실제 도구 결과:", result.model_dump(mode="json"))
        messages.append(ToolMessage(
            content=result.model_dump_json(),
            tool_call_id=call["id"],
        ))

    answer = model.invoke(messages) if response.tool_calls else response
    print("최종 안내:", answer.text)
