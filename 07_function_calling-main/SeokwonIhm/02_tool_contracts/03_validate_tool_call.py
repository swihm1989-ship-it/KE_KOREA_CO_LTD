import os
import json
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI


class AvailablityArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    participant_id: Literal["A", "B"]
    date: str

class AvailablityResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    participant_id: str
    date: str
    times: list[str] | None

AVAILABLITY = {
    "2026-11-25" : { "A" : ["09:00~12:00"], "B" : ["10:00~11:00"]},
    "2026-11-26" : { "A" : ["09:00~12:00"], "B" : ["09:00~12:00"]},
    "2026-11-27" : { "A" : ["09:00~10:00"], "B" : ["11:00~12:00"]},
}

@tool(args_schema=AvailablityArgs)
def read_availiablity(participant_id: str, date: str) -> dict:
    """참가자의 지정한 날짜에 가능한 시간을 조회한다. 날짜는 YYYY-MM-DD이다."""
    return {
        "participant_id" : participant_id,
        "date" : date,
        "times" : AVAILABLITY.get(date, {}).get(participant_id)
    }

load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
model_with_tools = model.bind_tools([read_availiablity]) 

REQUEST = "A의 2026-11-27 가능 시간을 알려 줘."
# REQUEST = "A의 2026-11-24 가능 시간을 알려 줘."
# REQUEST = "A의 가능 시간을 알려 줘."
# REQUEST = "시간대가 무슨 뜻이야?"
messages = [
    ("system", "참가자의 가능 시간을 안내한다. "
    "참석자와 날짜가 있으면 조회하고, 빠졌으면 질문한다. "
    "일반 질문은 직접 답한다."),
    ("human", REQUEST)
]
response = model_with_tools.invoke(messages)

if response.tool_calls:
    messages.append(response)   # 모델의 호출 요청을 대화에 남긴다.
    for call in response.tool_calls:
        # 입력 검사
        checked_args = AvailablityArgs.model_validate(call["args"])
        print("검사 후 인자:", checked_args)

        # 실제 조회
        raw = read_availiablity.invoke(checked_args.model_dump())
        print("조회 된 값:", raw)

        # 반환 검사
        checked_result = AvailablityResult.model_validate(raw)
        if ((checked_result.participant_id, checked_result.date) != (
            checked_args.participant_id, checked_args.date)
        ):
            raise ValueError("조회 결과의 참석자, 날짜가 실행 인자와 다르다.")
        print("검사 후 결과:", checked_result)

        # 결과 전달
        messages.append(ToolMessage(
            content=json.dumps(checked_result.model_dump(), ensure_ascii=False),
            tool_call_id=call["id"]
        ))

    print("최종 안내:", model.invoke(messages).text)    # 모델이 실제 조회 결과를 읽고 답변하기 
else:   
    print("최종 안내:", response.text)  # 도구 요청이 없으면 첫 모델 답변으로 종료하기