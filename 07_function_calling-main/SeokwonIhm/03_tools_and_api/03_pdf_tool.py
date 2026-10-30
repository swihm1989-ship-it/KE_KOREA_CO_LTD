"""PDF를 읽고 모델이 운영 시간과 방문 준비물을 안내한다."""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

PDF_PATH = Path(__file__).resolve().parent / "data" / "notice.pdf"


class PDFArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    page_number: int = Field(ge=1)


class PDFPage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    page_number: int = Field(ge=1)
    text: str


@tool(args_schema=PDFArgs)
def read_notice(page_number: int) -> PDFPage:
    """안내문 한 쪽을 읽는다. 1쪽 운영·방문, 2쪽 배송·출고, 3쪽 교환·반품, 4쪽 결제·증빙이다."""
    with PDF_PATH.open("rb") as stream:
        reader = PdfReader(stream)
        if not 1 <= page_number <= len(reader.pages):
            raise ValueError("PDF에 있는 페이지 번호를 지정한다.")
        # TODO 1: 요청한 쪽의 텍스트를 text에 담고, 추출 결과가 없으면 빈 문자열로 둔다.
        text = reader.pages[page_number - 1].extract_text() or ""
    # TODO 2: page_number와 정리한 text로 PDFPage를 생성해 반환한다.
    return PDFPage(page_number=page_number,text=text.strip())


REQUEST = '안내문 1쪽을 확인해서 운영 시간과 방문 전에 준비할 것을 알려 줘.'
# REQUEST = "할인 후 상품 금액 35,000원인 주문을 제주로 받으면 배송비가 얼마인가요?"
# REQUEST = "상품을 받은 지 5일 됐고 미사용인데 교환 신청에 무엇이 필요한가요?"
# REQUEST = "계좌이체로 결제했는데 현금영수증은 어떻게 신청하나요?"
# 아래 안내 줄은 TODO 1~3을 모두 완성한 뒤 삭제한다.

load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
messages = [
    ("system", '안내문 질문은 도구로 해당 쪽을 읽는다. '
     '목차는 1쪽 운영·방문, 2쪽 배송·출고, 3쪽 교환·반품, 4쪽 결제·증빙이다. '
     '쪽 번호가 있으면 그 쪽을 읽고, 없으면 질문 주제에 맞는 한 쪽을 고른다. '
     '질문 주제가 불분명하면 먼저 확인한다. '
     '반환된 페이지 텍스트에서 질문에 필요한 정보를 골라 간결하게 안내한다. '
     '자료에 없는 정책이나 처리 결과는 덧붙이지 않는다.'),
    ("human", REQUEST),
]
model_with_tools = model.bind_tools([read_notice])
response = model_with_tools.invoke(messages)  # 모델이 실행할 도구와 인자를 고른다.
print("모델의 호출 요청:", response.tool_calls)
messages.append(response)  # 원래 호출 요청을 실행 결과 앞에 남긴다.

for call in response.tool_calls:
    result = read_notice.invoke(call["args"])  # 여기서 실제 자료를 읽는다.
    print("실제 도구 결과:", result.model_dump(mode="json"))
    # TODO 3: 결과를 JSON으로 직렬화하고 원래 호출 ID로 ToolMessage를 만든다.
    tool_message = ToolMessage(
        content = result.model_dump_json(),
        tool_call_id=call["id"],
    )
    messages.append(tool_message)

# 결과를 읽은 모델의 안내를 받는다. 호출 요청이 없으면 첫 답변으로 끝낸다.
answer = model.invoke(messages) if response.tool_calls else response
print("최종 안내:", answer.text)
