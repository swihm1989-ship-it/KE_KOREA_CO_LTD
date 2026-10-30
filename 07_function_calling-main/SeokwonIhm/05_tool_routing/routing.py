"""현재 근거에 맞는 도구 공개·후속 행동·구조화 경로를 결정한다."""
from contracts import Route
from prompts import ROUTE_PROMPT, ROUTE_SCOPE_NOTICE
from tools import calculate_quote, find_products, lookup_product, read_purchase_policy


def select_tools(state, definitions):
    # STEP 01 · 가격·재고 조회 도구를 첫 선택지로 공개한다.
    tools = [find_products, lookup_product]
    if not state["policy_read"]:
        tools.append(read_purchase_policy)

    if state["product_ids"] or state["explicit_ids"]:
        # STEP 03 · 실제 조회 또는 사용자 입력으로 제품 ID를 확보한 뒤 견적을 공개한다.
        tools.append(calculate_quote)

    if not state["search_used"] and not (state["known_urls"] - state["bodies"].keys()):
        tools.append(definitions["search"])
    if state["known_urls"] - state["bodies"].keys():
        tools.append(definitions["extract"])
    return tools


def decide_next_step(state):
    if state["error"]:
        # STEP 06a · 실행 실패는 정상 빈 조회와 다른 안내로 끝낸다.
        return "explain_error"
    
    if state["products"] is not None and not any(item["stock"] > 0 for item in state["products"]):
        # STEP 05 · 조회된 품목 자체가 없는 경우와 모두 품절인 경우를 구별한다.
        if not state["products"]:
            return "no_match"
        return "sold_out"

    if state["quote"] is not None and not state["quote"]["available"]:
        # STEP 06b · 견적 금액이 계산돼도 요청 수량을 확보하지 못할 수 있다.
        return "insufficient_stock"

    if state["empty_reference"]:
        return "reference_missing"
    return "continue"


def route_request(model, request):
    # STEP 09 · 구조화된 응답에서 Route 검사를 받고 Python 분기에 사용한다.
    router = ROUTE_PROMPT|model.with_structured_output(Route, method = "json_schema")
    return router.invoke({"request": request})
