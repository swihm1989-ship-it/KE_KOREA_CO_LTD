"""하나의 업무 도구 안에서 요청한 주제들을 병렬 검색하고 합류 결과로 답한다."""
import asyncio
import json
import os

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from prompts import DIALOGUE_PROMPT
from tools import build_reference_tool
from tavily_connection import connect_tavily

REQUEST = "키보드 구매에 참고할 USB와 Bluetooth 공식 자료를 각각 찾아 줘."
MAX_CONCURRENCY = 2
MAX_ROUNDS = 3


async def answer(model, messages, request, session, definitions):
    # 이전 대화는 유지하면서 이번 사용자 요청을 이력 끝에 연결한다.
    messages.append(("human", request))
    # 같은 MCP 연결을 사용하는 도구를 준비한다. 아직 내부 검색을 실행하는 단계는 아니다.
    reference_tool = build_reference_tool(session, definitions, MAX_CONCURRENCY)
    attempted = False  # 새 사용자 턴마다 새 실행을 허용하되, 같은 턴에서는 한 번만 실행한다.
    for _ in range(MAX_ROUNDS):
        # 모델에는 업무 도구 하나를 공개한다. 주제별 동시 검색은 도구 안의 Python이 맡는다.
        selected = model if attempted else model.bind_tools([reference_tool], tool_choice="auto", parallel_tool_calls=False)
        response = await (DIALOGUE_PROMPT | selected).ainvoke({"history": messages})
        messages.append(response)  # 문자열로 바꾸기 전의 AIMessage와 원래 호출 ID를 유지한다.
        calls = response.tool_calls
        print("모델 호출:", calls)
        # 도구 호출이 없는 질문·최종 안내만 문자열로 읽어 화면에 반환한다.
        if not calls:
            return StrOutputParser().invoke(response)

        # 예상하지 않은 복수·미등록·추가 호출은 모두 거부한다. 일부만 먼저 실행하지 않는다.
        valid = not attempted and len(calls) == 1 and calls[0]["name"] == reference_tool.name
        attempted = True
        if not valid:
            for call in calls:
                messages.append(ToolMessage(content="이 턴에서는 collect_reference_materials 한 번만 실행할 수 있습니다.",
                                            tool_call_id=call["id"], name=call["name"], status="error"))
            continue

        call = calls[0]
        try:
            # 업무 도구 → 공통 검색 함수 → STEP01 실행 → STEP02 합류 순서로 이어진다.
            merged = await reference_tool.ainvoke(call["args"])
        except (NotImplementedError, asyncio.CancelledError):
            raise
        except Exception as exc:
            messages.append(ToolMessage(content=f"검색 자료 수집 오류: {type(exc).__name__}: {exc}",
                                        tool_call_id=call["id"], name=call["name"], status="error"))
            continue
        # 다음 모델 응답이 이 실제 결과를 근거로 쓰도록 STEP03에서 원래 호출 ID에 연결한다.
        print("검색 자료 합류 판정:", {key: value for key, value in merged.items() if key != "sources"})
        # STEP 03 · 합류한 실제 결과를 원래 업무 도구 호출 ID의 메시지로 전달한다.
        messages.append(ToolMessage(content=json.dumps(merged,ensure_ascii=False),
                                    tool_call_id=call["id"], name=call["name"], status="success"))
    return "모델 호출 한도에 도달했습니다. 실제로 확보한 도구 결과까지만 확인해 주세요."


async def main():
    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    messages, request = [], REQUEST
    # 연결과 messages는 대화 동안 유지하고, 새 입력마다 answer를 다시 실행한다.
    async with connect_tavily() as (session, definitions):
        while request:
            print("요청:", request)
            print("모델 안내:", await answer(model, messages, request, session, definitions))
            request = input("추가 요청(빈 입력이면 종료): ").strip()


if __name__ == "__main__":
    asyncio.run(main())
