"""가상 상품 CSV를 조회하고 모델이 용도와 재고에 맞는 상품을 추천한다."""
import csv
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.csv"


class CatalogArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    category: Literal["문구", "전자기기", "가방", "생활용품"]
    max_price: int = Field(ge=0)


class Product(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    product_id: str
    name: str
    price_won: int = Field(ge=0)
    stock: int = Field(ge=0)
    description: str


class CatalogResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    products: list[Product]


@tool(args_schema=CatalogArgs)
def filter_catalog(category: str, max_price: int) -> CatalogResult:
    """상품 분류와 최대 가격에 맞는 상품 목록을 읽는다. 가격은 원 단위다."""
    selected = []
    with CATALOG_PATH.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            # TODO 1: 분류와 최대 가격 조건을 비교해 matches에 담는다.
            if row["category"] == category and int(row["price_won"]) <= max_price:
                selected.append({
                    "product_id": row["product_id"], "name":row["name"],
                    "price_won": int(row["price_won"]), "stock": int(row["stock"]),
                    "description": row["description"],
                }) 
    # TODO 2: 선택한 상품 목록으로 CatalogResult를 만들어 반환한다.
    return CatalogResult(products=selected)


REQUEST = "문구 상품 중 5,000원 이하이고 재고가 있는 상품을 추천하고 가격과 재고를 알려 줘."
# REQUEST = "전자기기 중 2만원 이하이고 재고가 있는 상품을 추천해 줘."
# REQUEST = "노트북을 담아 휴대할 가방을 2만원 이하에서 추천해 줘."
# REQUEST = "문구 상품 중 2천원 이하이고 재고가 있는 상품을 추천해 줘."
# 아래 안내 줄은 세 부분을 모두 완성한 뒤 삭제한다.

load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
messages = [
    ("system", "상품 분류는 문구·전자기기·가방·생활용품이다. "
     "추천 요청의 분류와 예산으로 반드시 도구를 조회하고 조건이 빠졌으면 질문한다. "
     "조회된 상품 중 재고 0은 품절로 보고 추천에서 제외한다. "
     "용도를 물으면 조회된 description을 근거로 맞는 상품을 고른다. "
     "이름·가격·확인한 재고와 선택 이유를 간결하게 안내한다. "
     "자료에 없는 기능·호환성·입고일을 만들거나 주문 처리를 완료했다고 말하지 않는다."),
    ("human", REQUEST),
]
model_with_tools = model.bind_tools([filter_catalog])
response = model_with_tools.invoke(messages)  # 모델이 실행할 도구와 인자를 고른다.
print("모델의 호출 요청:", response.tool_calls)
messages.append(response)  # 원래 호출 요청을 실행 결과 앞에 남긴다.

for call in response.tool_calls:
    result = filter_catalog.invoke(call["args"])  # 여기서 실제 자료를 읽는다.
    print("실제 도구 결과:", result.model_dump(mode="json"))
    # TODO 3: 결과 JSON과 원래 호출 ID로 ToolMessage를 만든다.
    tool_message = ToolMessage(
        content=result.model_dump_json(),
        tool_call_id=call["id"]
        
    )
    messages.append(tool_message)

# 결과를 읽은 모델의 안내를 받는다. 호출 요청이 없으면 첫 답변으로 끝낸다.
answer = model.invoke(messages) if response.tool_calls else response
print("최종 안내:", answer.text)
