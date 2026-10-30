import os 
import json
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage

AVAILABLITY = {
    "2026-11-25" : { "A" : ["09:00~12:00"], "B" : ["10:00~11:00"]},
    "2026-11-26" : { "A" : ["09:00~12:00"], "B" : ["09:00~12:00"]},
    "2026-11-27" : { "A" : ["09:00~10:00"], "B" : ["11:00~12:00"]},
}

load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])

@tool
def read_availiablity(participant_id: str, date: str) -> dict:
    """참가자의 지정한 날짜에 가능한 시간을 조회한다. 날짜는 YYYY-MM-DD이다."""
    return {
        "participant_id" : participant_id,
        "date" : date,
        "times" : AVAILABLITY.get(date, {}).get(participant_id)
    }

# REQUEST = "A의 2026-11-27 가능 시간을 알려 줘."
REQUEST = "A의 2026-11-24 가능 시간을 알려 줘."
# REQUEST = "A의 가능 시간을 알려 줘."
# REQUEST = "시간대가 무슨 뜻이야?"
messages = [
    ("system", "참가자의 가능 시간을 안내한다. "
    "참석자와 날짜가 있으면 조회하고, 빠졌으면 질문한다. "
    "일반 질문은 직접 답한다."),
    ("human", REQUEST)
]

model_with_tools = model.bind_tools([read_availiablity])    # 도구 사용법을 모델에 연결한다.
response = model_with_tools.invoke(messages)
# 호출 요청이 담긴 원래 AIMessage를 유지한다.
messages.append(response)

for call in response.tool_calls:
    # 실제 조회 실행
    result = read_availiablity.invoke(call["args"])
    print("실제 조회 결과:", result)
    tool_message = ToolMessage(
        content=json.dumps(result, ensure_ascii=False),  # 반환 메세지를 문자열로 만든다.
        tool_call_id=call["id"]
    )
    print("돌려줄 메세지:", tool_message)
    messages.append(tool_message)

# 도구를 요청했으면 결과를 읽게하고 없으면 첫 답변으로 끝낸다.
answer = model.invoke(messages) if response.tool_calls else response
print("최종 안내:", answer.text)