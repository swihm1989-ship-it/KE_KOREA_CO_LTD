"""NASA 공개 CSV에서 외계행성을 검색하고 문의 한 건에 답한다."""
import csv
import os
from pathlib import Path
from typing import Literal, Self

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator

PLANET_PATH = Path(__file__).resolve().parent / "data" / "exoplanets.csv"
DiscoveryMethod = Literal[
    "Astrometry", "Disk Kinematics", "Eclipse Timing Variations", "Imaging",
    "Microlensing", "Orbital Brightness Modulation", "Pulsar Timing",
    "Pulsation Timing Variations", "Radial Velocity", "Transit", "Transit Timing Variations",
]


class SearchArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    max_radius_earth: float = Field(gt=0, allow_inf_nan=False)
    discovered_since: int = Field(default=1900, ge=1900, le=2026)
    discovery_method: DiscoveryMethod | Literal["전체"] = "전체"
    limit: int = Field(default=5, ge=1, le=10)


class Planet(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str = Field(alias="pl_name", min_length=1)
    host_star: str = Field(alias="hostname", min_length=1)
    discovery_method: DiscoveryMethod = Field(alias="discoverymethod")
    discovery_year: int = Field(alias="disc_year", ge=1900, le=2026)
    radius_earth: float | None = Field(alias="pl_rade", gt=0, allow_inf_nan=False)


class PlanetResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    total_matches: int = Field(ge=0)
    returned_count: int = Field(ge=0, le=10)
    planets: list[Planet]

    @model_validator(mode="after")
    def check_counts(self) -> Self:
        if self.returned_count != len(self.planets) or self.total_matches < self.returned_count:
            raise ValueError("검색 건수와 반환 목록의 개수가 맞지 않습니다.")
        return self


@tool(args_schema=SearchArgs)
def search_exoplanets(
    max_radius_earth: float,
    discovered_since: int = 1900,
    discovery_method: str = "전체",
    limit: int = 5,
) -> PlanetResult:
    """NASA CSV에서 반지름 상한(지구 반지름 배수) 이하의 외계행성을 검색한다.

    반지름 상한은 필수 양수다. 발견 연도는 해당 연도 포함 이후이며 생략 시 전체 연도,
    방법 생략 시 전체다. 작은 반지름·행성명 순으로 기본 5개, 최대 10개를 반환한다.
    반지름이 없는 행성은 크기 조건 검색에서 제외한다.
    """
    selected = []
    with PLANET_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["pl_name", "hostname", "discoverymethod", "disc_year", "pl_rade"]:
            raise ValueError("NASA CSV의 열 구성이 올바르지 않습니다.")
        for row in reader:
            # 모든 원본 행을 먼저 변환·검증한다. 빈 반지름은 미확인 값이다.
            row["disc_year"] = int(row["disc_year"])
            row["pl_rade"] = float(row["pl_rade"]) if row["pl_rade"] else None
            planet = Planet.model_validate(row)
            if (
                planet.radius_earth is not None
                and planet.radius_earth <= max_radius_earth
                and planet.discovery_year >= discovered_since
                and (discovery_method == "전체" or planet.discovery_method == discovery_method)
            ):
                selected.append(planet)

    selected.sort(key=lambda planet: (planet.radius_earth, planet.name))
    shown = selected[:limit]
    # 빈 목록도 정상 결과다. 파일·변환·검증 실패는 예외로 중단한다.
    return PlanetResult(total_matches=len(selected), returned_count=len(shown), planets=shown)


def main() -> None:
    request = input("외계행성 검색 요청을 입력하세요: ").strip()
    if not request:
        print("반지름 상한을 포함해 입력해 주세요. 예: 지구 반지름의 2배 이하 행성을 찾아 줘.")
        return

    load_dotenv()
    model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
    messages: list[AnyMessage | tuple[str, str]] = [
        ("system", "NASA Exoplanet Archive CSV로 외계행성 검색을 안내한다. "
         "자료는 2026-10-27에 내려받은 PS 기본 파라미터 기록이며 반지름 상하한만 있는 행성은 제외했다. "
         "반지름 상한이 있으면 search_exoplanets를 정확히 한 번 호출한다. "
         "반지름은 지구 반지름의 배수다. 지구 2배 크기라고 하면 반지름 상한 2로 해석하되 단위를 답변에 명시한다. "
         "반지름 상한이 없거나 크기 조건이 모호하면 필요한 상한을 질문하고 도구를 실행하지 않는다. "
         "질량·지름·거리의 조건을 반지름으로 임의 변환하지 말고 지원 조건을 안내한다. "
         "상한은 유한한 양수, 발견 시작 연도는 정수 1900~2026, 표시 개수는 정수 1~10이다. "
         "지원하지 않는 값은 조건을 안내하고 도구를 실행하지 않는다. "
         "발견 연도 생략은 discovered_since=1900, 방법 생략은 전체, 표시 개수 생략은 limit=5다. 추가로 묻지 않는다. "
         "발견 연도 조건은 해당 연도를 포함한다. '2015년 이후'는 2015, '2015년 초과'는 2016이다. "
         "발견 방법은 Astrometry, Disk Kinematics, Eclipse Timing Variations, Imaging, Microlensing, "
         "Orbital Brightness Modulation, Pulsar Timing, Pulsation Timing Variations, Radial Velocity, Transit, Transit Timing Variations이다. "
         "통과법은 Transit, 시선속도법은 Radial Velocity, 직접 촬영은 Imaging, 미세중력렌즈법은 Microlensing으로 전달한다. "
         "반환된 total_matches는 전체 조건 일치 건수, returned_count는 작은 반지름 순으로 표시한 건수다. "
         "검색 결과의 행성명·항성명·발견 연도·방법·반지름을 간결하게 안내하고 두 건수를 구분한다. "
         "빈 목록이면 이 CSV 자료에서 조건에 맞는 결과가 없다고 안내한다. 우주에 존재하지 않는다고 단정하지 않는다. "
         "반지름 미확인 행성은 크기 검색에서 제외되며, 현재 실시간 목록이나 전체 행성을 망라하는 자료라고 말하지 않는다. "
         "지구와 크기가 비슷하다는 사실로 생명체나 거주 가능성을 판단하지 않는다. 자료에 없는 정보를 만들지 않는다."),
        ("human", request),
    ]
    response = model.bind_tools([search_exoplanets]).invoke(messages)
    print("모델의 호출 요청:", response.tool_calls)
    if not response.tool_calls:
        print("최종 안내:", response.text)
        return
    if len(response.tool_calls) != 1:
        raise ValueError("한 요청에는 검색 도구를 한 번만 호출해야 합니다.")
    messages.append(response)
    for call in response.tool_calls:
        if call["name"] != search_exoplanets.name:
            raise ValueError("지원하지 않는 도구입니다.")
        # 입력 계약 검사 후 실제 CSV를 읽고 반환 계약을 다시 확인한다.
        checked_args = SearchArgs.model_validate(call["args"])
        print("검사 후 인자:", checked_args.model_dump())
        result = search_exoplanets.invoke(checked_args.model_dump())
        checked_result = PlanetResult.model_validate(result.model_dump(by_alias=True))
        print("실제 도구 결과:", checked_result.model_dump())
        messages.append(ToolMessage(
            content=checked_result.model_dump_json(),
            tool_call_id=call["id"],
        ))
    print("최종 안내:", model.invoke(messages).text)


if __name__ == "__main__":
    main()
