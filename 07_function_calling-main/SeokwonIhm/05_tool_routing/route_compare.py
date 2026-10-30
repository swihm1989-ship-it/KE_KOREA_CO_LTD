"""같은 비품 문의를 구조화된 경로 하나와 Python 분기로 실행한다."""
import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from prompts import FINAL_PROMPT
from routing import route_request
from tools import calculate_quote, find_products, lookup_product, read_purchase_policy

REQUEST = "3만원 이하의 재고 있는 키보드를 추천해 줘."

load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
result = None
try:
    route = route_request(model, REQUEST)
    print("모델이 제안한 경로:", route.model_dump_json(indent=2))
    route = validate_route(route, REQUEST)
    print("검사 통과:", route.route)
except ValueError as error:
    print("경로 검사 실패:", error)
else:
    try:
        # STEP 10 · 경로 객체를 실제 로컬 기능의 입력으로 연결한다.
        raise NotImplementedError("STEP 10: 선택한 Route를 실제 로컬 기능 또는 안내에 연결하세요.")
    except NotImplementedError:
        raise
    except (ValueError, OSError) as error:
        print("로컬 실행 실패:", error)
if result is not None:
    print("실제 결과:", result.model_dump_json(indent=2))
    # 경로 객체에는 실제 모델 tool call ID가 없으므로 가짜 ToolMessage를 만들지 않는다.
    answer_chain = FINAL_PROMPT | model | StrOutputParser()
    answer = answer_chain.invoke({"request": REQUEST, "result_json": result.model_dump_json()})
    print("최종 안내:", answer)
