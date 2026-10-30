"""비품 문의의 선택·결과 반영·후속 호출을 한 흐름으로 읽는다."""
import asyncio
import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from execution import execute_call, result_message, set_tool_descriptions
from progress import continue_request, new_state, remember_result
from prompts import DIALOGUE_PROMPT
from routing import decide_next_step, select_tools
from tavily_connection import connect_tavily

# REQUEST = "P004 10개의 견적 내줘."
REQUEST = "https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/ 이 문서의 본문을 읽고 설명한다." 
TOOL_CHOICE = "auto"  # auto / required / find_products / none
DESCRIPTION_STYLE = "clear"  # clear / vague: 규정 도구의 설명만 비교한다.
MAX_ROUNDS = 8


async def main():
    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    text_parser = StrOutputParser()
    policy_description = set_tool_descriptions(DESCRIPTION_STYLE)
    print("규정 도구 설명:", policy_description)
    messages, state = [("human", REQUEST)], new_state(REQUEST)
    print("요청:", REQUEST)
    async with connect_tavily() as (session, definitions):
        for round_number in range(1, MAX_ROUNDS + 1):
            next_step = decide_next_step(state)
            exposed = select_tools(state, definitions) if next_step == "continue" else []
            names = {item.name if hasattr(item, "name") else item["function"]["name"] for item in exposed}
            visible_urls, visible_ids = set(state["known_urls"]), state["product_ids"] | state["explicit_ids"]
            print("다음 행동:", next_step, "공개 도구:", sorted(names))

            choice = "auto"
            if round_number == 1 and TOOL_CHOICE != "auto":
                # STEP 07 · 비교할 선택 정책은 첫 호출에만 적용한다.
                choice = TOOL_CHOICE
            print(f"모델 호출 {round_number} · 적용 정책: {choice if exposed else '도구 없음'}")
            selected = model.bind_tools(exposed, tool_choice=choice) if exposed else model
            response = await (DIALOGUE_PROMPT | selected).ainvoke({
                "history": messages, "available_tools": ", ".join(sorted(names)) or "없음",
            })
            print("모델 호출:", response.tool_calls)
            messages.append(response)  # 호출 원문을 그 ID의 실제 결과 앞에 유지한다.

            if not response.tool_calls:
                # 도구 선택 응답은 AIMessage로 유지하고, 호출 없는 안내만 문자열로 읽는다.
                print("모델 안내:", text_parser.invoke(response))
                if next_step != "continue":
                    break
                follow_up = input("추가 요청(빈 입력이면 종료): ").strip()
                if not follow_up:
                    print("종료: 사용자가 대화를 마침")
                    break
                # STEP 04 · 보충 입력을 원래 요청·질문과 같은 대화에 연결한다.
                messages.append(("human", follow_up))
                state = continue_request(state, follow_up)
                continue

            for call in response.tool_calls:
                outcome = await execute_call(call, session, definitions, names, visible_urls, visible_ids)
                print("실제 결과:", outcome)
                remember_result(state, outcome, definitions)
                print("확인한 제품 ID:", sorted(state["product_ids"]), "견적:", state["quote"], "규정:", state["policy_read"])
                messages.append(result_message(outcome))  # 원래 호출 ID에 실제 결과를 연결한다.
        else:
            print("종료: 모델 호출 한도에 도달해 미완료")


asyncio.run(main())
