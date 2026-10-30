"""도구의 실제 실행·입력 거부·원래 호출 ID의 결과 전달을 연결한다."""
import json

from langchain_core.messages import ToolMessage

from mcp_results import parse_extract_result, parse_search_result
from prompts import CLEAR_DESCRIPTIONS
from tools import calculate_quote, find_products, lookup_product, read_purchase_policy

LOCAL_TOOLS = [find_products, lookup_product, read_purchase_policy, calculate_quote]


def set_tool_descriptions(style):
    for item in LOCAL_TOOLS:
        item.description = CLEAR_DESCRIPTIONS[item.name]
    if style == "vague":
        read_purchase_policy.description = "비품 관련 정보를 처리한다."
    return read_purchase_policy.description


async def invoke_tool(call, session, definitions, names, visible_urls, visible_ids):
    if call["name"] not in names:
        raise ValueError("현재 단계에서 공개하지 않은 도구입니다.")
    if call["name"] == calculate_quote.name and call["args"].get("product_id") not in visible_ids:
        raise ValueError("사용자가 명시했거나 이전 조회에서 확인한 제품만 견적을 낼 수 있습니다.")
    local_by_name = {item.name: item for item in LOCAL_TOOLS}
    if call["name"] in local_by_name:
        return local_by_name[call["name"]].invoke(call["args"]).model_dump()
    if call["name"] == definitions["search"]["function"]["name"]:
        return parse_search_result(await session.call_tool(call["name"], call["args"])).model_dump()
    if call["name"] != definitions["extract"]["function"]["name"]:
        raise ValueError("등록되지 않은 도구입니다.")
    urls = call["args"].get("urls")
    # STEP 08 · 추출할 주소는 이번 모델 호출 전에 확인한 URL 안에서 고른다.
    if not isinstance(urls, list) or not urls or not all(isinstance(url, str) for url in urls) or not set(urls) <= visible_urls:
        raise ValueError("이전 URL만 추출가능쓰")
    
    return parse_extract_result(await session.call_tool(call["name"], call["args"])).model_dump()


async def execute_call(call, session, definitions, names, visible_urls, visible_ids):
    try:
        payload = await invoke_tool(call, session, definitions, names, visible_urls, visible_ids)
        return {"call": call, "status": "success", "payload": payload}
    except NotImplementedError:
        raise  # 미작성 지점은 실제 서비스 오류로 바꾸지 않고 그대로 표시한다.
    except Exception as error:
        return {"call": call, "status": "error", "payload": {"error": str(error)}}


def extraction_urls(calls, definitions, visible_urls):
    required = set()
    for call in calls:
        urls = call["args"].get("urls")
        if call["name"] == definitions["extract"]["function"]["name"] and isinstance(urls, list) and urls and all(isinstance(url, str) for url in urls) and set(urls) <= visible_urls:
            required.update(urls)
    return required


def result_message(outcome):
    return ToolMessage(content=json.dumps(outcome["payload"], ensure_ascii=False),
                       tool_call_id=outcome["call"]["id"], status=outcome["status"])
