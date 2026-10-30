"""행사 문의 한 건을 받아 생수와 간식 준비 수량을 계산한다."""
import os
from math import ceil
from typing import Self

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SupplyArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    participants: int = Field(ge=1, le=500)
    reserve_percent: int = Field(default=10, ge=0, le=30)


class SupplyResult(SupplyArgs):
    # 입력 계약의 엄격한 타입·범위·추가 키 금지를 상속한다.
    servings: int = Field(ge=1)
    water_bottles: int = Field(ge=1)
    snack_boxes: int = Field(ge=1)

    @model_validator(mode="after")
    def check_quantities(self) -> Self:
        expected = ceil(self.participants * (100 + self.reserve_percent) / 100)
        if self.servings != expected:
            raise ValueError("준비 인원 계산이 참가 인원·여유 비율과 다릅니다.")
        if self.water_bottles != expected or self.snack_boxes != ceil(expected / 10):
            raise ValueError("생수 1인 1병·간식 1상자 10인분 기준과 다릅니다.")
        return self


@tool(args_schema=SupplyArgs)
def calculate_supplies(participants: int, reserve_percent: int = 10) -> SupplyResult:
    """행사 준비 수량을 계산한다. 인원은 1~500명, 여유 비율은 0~30%, 생략 시 10%다.

    준비 인원은 여유분을 포함하여 올림한다. 생수는 준비 인원당 1병,
    간식은 상자당 10인분이며 필요한 상자 수를 올림한다.
    """
    # 정수 나눗셈으로 올림 계산한다. 외부 자료가 필요 없는 가상 준비 기준이다.
    servings = (participants * (100 + reserve_percent) + 99) // 100
    return SupplyResult(
        participants=participants,
        reserve_percent=reserve_percent,
        servings=servings,
        water_bottles=servings,
        snack_boxes=(servings + 9) // 10,
    )


def main() -> None:
    request = input("행사 준비 문의를 입력하세요: ").strip()
    if not request:
        print("참가 인원을 포함한 행사 준비 문의를 입력해 주세요.")
        return  # 빈 입력에는 모델을 호출하지 않는다.

    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    messages: list[AnyMessage | tuple[str, str]] = [
        ("system", "행사 담당자에게 생수와 간식 준비 수량을 안내한다. "
         "참가 인원이 있으면 calculate_supplies 도구를 정확히 한 번 호출해 계산한다. "
         "참가 인원이 없거나 모호하면 인원을 확인 질문하고 도구는 호출하지 않는다. "
         "참가 인원은 정수 1~500명, 여유 비율은 정수 0~30%다. "
         "범위를 벗어나거나 정수가 아닌 값은 허용 조건을 안내하고 도구를 호출하지 않는다. "
         "여유 비율 생략 시 계약 기본값 10%를 적용하며 추가로 묻지 않는다. "
         "여유 없이 준비한다면 비율 0%를 사용하고 인원과 비율을 임의로 바꾸지 않는다. "
         "준비 인원은 여유분을 포함해 올림하고, 생수는 1인 1병, 간식은 상자당 10인분이다. "
         "최종 수량은 검증된 도구 반환값만 근거로 안내하며 적용한 여유 비율도 알린다. "
         "이는 가상 준비 기준에 따른 계획이며 실제 구매·예약·배송 완료를 안내하지 않는다. "
         "가격·브랜드·행사 시간 등 도구 결과에 없는 정보를 만들지 않는다. "
         "다른 물품이나 비용 계산을 요청하면 이 도구의 지원 범위를 안내한다."),
        ("human", request),
    ]
    response = model.bind_tools([calculate_supplies]).invoke(messages)
    print("모델의 호출 요청:", response.tool_calls)
    if not response.tool_calls:
        print("최종 안내:", response.text)
        return

    if len(response.tool_calls) != 1:
        raise ValueError("한 요청에는 계산 도구 호출이 한 번이어야 합니다.")
    messages.append(response)
    for call in response.tool_calls:
        if call["name"] != calculate_supplies.name:
            raise ValueError("지원하지 않는 도구 호출입니다.")
        # 입력 검사 → 실제 계산 → 반환 형식·계산식·실행 인자 일치 검사
        checked_args = SupplyArgs.model_validate(call["args"])
        print("검사 후 인자:", checked_args.model_dump())
        result = calculate_supplies.invoke(checked_args.model_dump())
        checked_result = SupplyResult.model_validate(result.model_dump())
        if (checked_result.participants, checked_result.reserve_percent) != (
            checked_args.participants, checked_args.reserve_percent
        ):
            raise ValueError("반환된 참가 인원·여유 비율이 실행 인자와 다릅니다.")
        print("실제 도구 결과:", checked_result.model_dump())
        # 실패는 예외로 중단한다. 검증을 통과한 결과만 원래 호출 ID로 전달한다.
        messages.append(ToolMessage(
            content=checked_result.model_dump_json(),
            tool_call_id=call["id"],
        ))

    print("최종 안내:", model.invoke(messages).text)


if __name__ == "__main__":
    main()
