"""사진 인화 견적: --local은 모델 없이 실행하고, 기본 실행은 REQUEST를 사용한다."""

import argparse
import json
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field


PRICES = {"4x6": 400, "5x7": 700}
REQUEST = "5x7 사진 6장 인화 비용을 알려 줘."
# REQUEST = "4x6 사진 3장 인화 비용을 알려 줘."
# REQUEST = "5x7 사진 인화 비용을 알려 줘."


class PhotoPrintArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    size: Literal["4x6", "5x7"]
    quantity: int = Field(ge=1, le=20)


class PhotoPrintResult(PhotoPrintArgs):
    # 입력과 같은 엄격한 설정 및 크기·수량 범위를 상속한다.
    unit_price_won: int
    total_fee_won: int


@tool(args_schema=PhotoPrintArgs)
def calculate_photo_print(size: str, quantity: int) -> dict:
    """사진 크기(4x6 또는 5x7)와 수량(1~20장)으로 인화 비용을 계산한다."""
    unit_price = PRICES[size]
    return {
        "size": size,
        "quantity": quantity,
        "unit_price_won": unit_price,
        "total_fee_won": unit_price * quantity,
    }


def validate_result(raw: dict, arguments: PhotoPrintArgs) -> PhotoPrintResult:
    """반환 형식, 실행 인자와의 일치, 가격표와 계산식을 검사한다."""
    result = PhotoPrintResult.model_validate(raw)
    if (result.size, result.quantity) != (arguments.size, arguments.quantity):
        raise ValueError("반환 크기·수량이 실행 인자와 다릅니다.")
    if result.unit_price_won != PRICES[arguments.size]:
        raise ValueError("반환 단가가 가격표와 다릅니다.")
    if result.total_fee_won != PRICES[arguments.size] * arguments.quantity:
        raise ValueError("반환 총금액이 단가 × 수량과 다릅니다.")
    return result


def run_local() -> None:
    """모델 없이 두 계산 결과와 잘못된 정수 금액의 차단을 확인한다."""
    for arguments in [{"size": "5x7", "quantity": 6},
                      {"size": "4x6", "quantity": 3}]:
        print("전달한 인자:", arguments)
        checked_args = PhotoPrintArgs.model_validate(arguments)
        raw = calculate_photo_print.invoke(checked_args.model_dump())
        print("함수 반환값:", raw)
        print("검사 후 결과:", validate_result(raw, checked_args).model_dump())

    print("경계 사례 기대: 총금액을 정수 4100으로 바꾸면 계산 검사에서 중단한다.")
    checked_args = PhotoPrintArgs(size="5x7", quantity=6)
    wrong_result = calculate_photo_print.invoke(checked_args.model_dump())
    wrong_result["total_fee_won"] = 4100
    try:
        validate_result(wrong_result, checked_args)
    except ValueError as error:
        # 의도적으로 만든 오류를 관찰한다. 모델 흐름에서는 예외를 잡지 않는다.
        print("경계 사례 실제:", type(error).__name__, str(error))
    else:
        raise AssertionError("잘못된 총금액을 차단하지 못했습니다.")


def run_request(request: str) -> str:
    """모델 호출 → 검증·실행 → 검증된 ToolMessage → 최종 안내를 연결한다."""
    # 어느 디렉터리에서 실행해도 개인 환경을 먼저 찾는다. 기존 환경값은 유지한다.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    model_with_tools = model.bind_tools([calculate_photo_print])
    messages = [
        ("system", "사진 인화 비용 견적을 안내한다. "
         "지원 크기는 4x6, 5x7이고 수량은 정수 1~20장이다. "
         "요청에 크기와 수량이 모두 있으면 계산 도구를 정확히 한 번 호출한다. "
         "빠진 값은 임의로 채우지 말고 질문하며 도구를 호출하지 않는다. "
         "지원하지 않는 크기나 범위를 벗어난 수량은 지원 조건을 안내한다. "
         "최종 금액은 검사된 도구 결과만 근거로 안내한다. "
         "비용 견적이므로 주문 접수나 인화 처리 완료를 안내하지 않는다."),
        ("human", request),
    ]
    print("요청:", request)
    response = model_with_tools.invoke(messages)
    print("모델 tool_calls:", response.tool_calls)
    if response.tool_calls:
        if len(response.tool_calls) != 1:
            raise ValueError("한 견적 요청에는 도구를 한 번만 실행해야 합니다.")
        messages.append(response)
        for call in response.tool_calls:
            if call["name"] != calculate_photo_print.name:
                raise ValueError(f"알 수 없는 도구입니다: {call['name']}")
            checked_args = PhotoPrintArgs.model_validate(call["args"])
            arguments = checked_args.model_dump()
            print("검사 후 인자:", arguments)
            raw = calculate_photo_print.invoke(arguments)
            print("함수 반환값:", raw)
            checked_result = validate_result(raw, checked_args)
            print("검사 후 결과:", checked_result.model_dump())
            messages.append(ToolMessage(
                content=json.dumps(checked_result.model_dump(), ensure_ascii=False),
                tool_call_id=call["id"],
            ))
        final_text = model.invoke(messages).text
    else:
        final_text = response.text
    print("최종 안내:", final_text)
    return final_text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="모델 호출 없이 검사")
    parser.add_argument("--request", default=REQUEST, help="한 번에 확인할 요청 문장")
    options = parser.parse_args()
    if options.local:
        run_local()
    else:
        run_request(options.request)
