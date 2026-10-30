"""가상 주문 DB의 번호·상태 조회 결과를 모델의 고객 안내에 연결한다."""
import os
from pathlib import Path
import sqlite3
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

DATABASE_PATH = Path(__file__).resolve().parent / "data" / "orders.sqlite3"


class OrderArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    order_id: str | None = Field(default=None, min_length=1)
    status: Literal["배송 준비", "배송 중", "배송 완료", "취소"] | None = None


class Order(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    order_id: str
    product_id: str
    product_name: str
    quantity: int = Field(ge=1)
    status: Literal["배송 준비", "배송 중", "배송 완료", "취소"]
    order_date: str
    expected_delivery_date: str | None


class OrderResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    count: int = Field(ge=0)
    orders: list[Order]


@tool(args_schema=OrderArgs)
def find_orders(order_id: str | None = None, status: str | None = None) -> OrderResult:
    """주문 번호나 상태로 주문을 읽는다. 둘 다 생략하면 전체 목록을 읽는다."""
    conditions, params = [], []
    if order_id is not None:
        conditions.append("order_id = ?")
        params.append(order_id)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    query = (
        "SELECT order_id, product_id, product_name, quantity, status, "
        "order_date, expected_delivery_date FROM orders"
    )
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY order_id"
    connection = sqlite3.connect(DATABASE_PATH.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        # TODO 1: query와 params로 조회한 모든 행을 rows에 담는다.
        rows = connection.execute(query,params).fetchall()

    finally:
        connection.close()
    # TODO 2: 조회 행을 사전으로 바꾸고 개수와 함께 OrderResult로 반환한다.
    return OrderResult(count=len(rows),orders=[Order.model_validate(dict(row)) for row in rows])


REQUEST = "ORD-1001 주문이 지금 배송 중인지 확인해 줘."
# REQUEST = "배송 중인 주문은 몇 건이고 어떤 주문인지 알려 줘."
# REQUEST = "전체 주문 목록을 주문번호와 상품명·수량·상태로 정리해 줘."
# 아래 안내 줄은 세 부분을 모두 완성한 뒤 삭제한다.

load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
messages = [
    ("system", "주문 요청은 번호·상태 조건으로 반드시 도구를 조회한다. "
     "특정 주문의 현재 상태를 물으면 order_id만 전달하고 status는 생략한다. 상태별 목록 요청에만 status를 사용한다. "
     "상태는 배송 준비·배송 중·배송 완료·취소이며 전체 목록 요청은 두 인자를 생략한다. "
     "반환된 count와 orders를 근거로 요청한 건수·상품·수량·상태를 간결하게 안내한다. "
     "count가 0이면 조건에 맞는 주문이 없다고 알린다. "
     "예상 배송일이 null이면 확인되지 않은 값이며 임의로 날짜를 만들지 않는다. "
     "예상 배송일은 확정 도착일로 단정하지 않는다. "
     "이 도구는 조회만 하므로 주문 취소나 배송 변경을 실제로 처리했다고 말하지 않는다."),
    ("human", REQUEST),
]
model_with_tools = model.bind_tools([find_orders])
response = model_with_tools.invoke(messages)  # 모델이 실행할 도구와 인자를 고른다.
print("모델의 호출 요청:", response.tool_calls)
messages.append(response)  # 원래 호출 요청을 실행 결과 앞에 남긴다.

for call in response.tool_calls:
    result = find_orders.invoke(call["args"])  # 여기서 실제 자료를 읽는다.
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
