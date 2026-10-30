"""실제로 확인한 비품·견적·기술 참고 자료를 대화 동안 보관한다."""
import re

from mcp_results import request_urls


def new_state(request):
    return {"products": None, "product_ids": set(), "explicit_ids": set(re.findall(r"\bP\d{3}\b", request)),
            "quote": None, "policy_read": False, "known_urls": request_urls(request),
            "bodies": {}, "search_used": False, "empty_reference": False, "error": None}


def continue_request(state, follow_up):
    if state["quote"] is not None or state["bodies"]:
        return new_state(follow_up)
    state["explicit_ids"].update(re.findall(r"\bP\d{3}\b", follow_up))
    state["known_urls"].update(request_urls(follow_up))
    return state


def continue_batch(state, follow_up, results, required_urls):
    next_state = continue_request(state, follow_up)
    if next_state is not state:
        return next_state, [], request_urls(follow_up)
    return next_state, results, required_urls | request_urls(follow_up)


def remember_result(state, outcome, definitions):
    if outcome["status"] == "error":
        state["error"] = outcome["payload"].get("error", "자료 조회가 실패했습니다.")
        return
    name, payload = outcome["call"]["name"], outcome["payload"]
    if name in {"find_products", "lookup_product"}:
        # STEP 02 · 실제 조회 결과를 다음 도구 선택에 사용할 근거로 보관한다.
        products = payload["products"] if name == "find_products" else [payload]
        state["products"] = products
        state["product_ids"] = {row["product_id"] for row in products if row ["stock"] >0}
        state["known_urls"].update(row["reference_url"] for row in products)
        
    elif name == "calculate_quote":
        state["quote"] = payload
        state["known_urls"].add(payload["reference_url"])
    elif name == "read_purchase_policy":
        state["policy_read"] = True
    elif name == definitions["search"]["function"]["name"]:
        state["search_used"] = True
        state["known_urls"].update(row["url"] for row in payload["results"])
        state["empty_reference"] = not payload["results"]
    elif name == definitions["extract"]["function"]["name"]:
        state["bodies"].update({row["url"]: row["raw_content"] for row in payload["results"] if row["raw_content"].strip()})
        state["empty_reference"] = not payload["results"] or bool(payload["failed_results"])
