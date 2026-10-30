import os 

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

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

REQUEST = "A의 2026-11-27 가능 시간을 알려 줘."
messages = [
    ("system", "참가자의 가능 시간을 안내한다. "
    "참석자와 날짜가 있으면 조회하고, 빠졌으면 질문한다. "
    "일반 질문은 직접 답한다."),
    ("human", REQUEST)
]

model_with_tools = model.bind_tools([read_availiablity])    # 도구 사용법을 모델에 연결한다.
response = model_with_tools.invoke(messages)

print("모델의 답변 텍스트:", response.text)
print("모델의 호출 요청:", response.tool_calls)
for call in response.tool_calls:
    print("이름:", call["name"], "인자:", call["args"], "호출 ID:", call["id"])