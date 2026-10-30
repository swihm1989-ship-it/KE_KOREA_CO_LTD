"""실제 기온 조회 결과를 모델의 날씨 안내로 연결한다."""
import os

from dotenv import load_dotenv
import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field


class WeatherArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class WeatherResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    time: str
    temperature_c: float | None
    weather_code: int | None


@tool(args_schema=WeatherArgs)
def get_weather(latitude: float, longitude: float) -> WeatherResult:
    """위도·경도의 현재 기온과 날씨 코드를 조회한다."""
    params = {
        "current": "temperature_2m,weather_code",
        "temperature_unit": "celsius",
        "timezone": "Asia/Seoul",
        "latitude": latitude,
        "longitude": longitude 
    }
    # TODO 1: 함수 인자 latitude·longitude를 params의 같은 이름 키에 추가한다.
    response = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    current = response.json()["current"]
    # TODO 2: current의 시각·기온·코드를 WeatherResult의 필드에 연결해 반환한다.
    return WeatherResult(
        time = current["time"],
        temperature_c= current["temperature_2m"],
        weather_code=current["weather_code"]
    )


REQUEST = '서울(위도 37.5665, 경도 126.9780)의 현재 기온을 조회해서 알려 줘.'
# 아래 안내 줄은 TODO 1~3을 모두 완성한 뒤 삭제한다.
 
load_dotenv()
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
messages = [
    ("system", '현재 기온은 요청에 명시된 위도·경도로 반드시 도구를 조회한다. '
     '좌표가 빠졌으면 질문한다. '
     '반환된 temperature_c와 time을 근거로 기온과 날씨 자료의 시각을 안내한다. '
     'temperature_c가 null이면 조회된 기온 정보가 없다고 안내한다. '
     'time의 시간대는 Asia/Seoul이다.'),
    ("human", REQUEST),
]
model_with_tools = model.bind_tools([get_weather])
response = model_with_tools.invoke(messages)  # 모델이 실행할 도구와 인자를 고른다.
print("모델의 호출 요청:", response.tool_calls)
messages.append(response)  # 원래 호출 요청을 실행 결과 앞에 남긴다.

for call in response.tool_calls:
    result = get_weather.invoke(call["args"])  # 여기서 실제 자료를 읽는다.
    print("실제 도구 결과:", result.model_dump(mode="json"))
    # TODO 3: 결과를 JSON으로 직렬화하고 원래 호출 ID로 ToolMessage를 만든다.
    tool_message = ToolMessage(
        content=result.model_dump_json(),
        tool_call_id=call["id"]
    )
    messages.append(tool_message)

# 결과를 읽은 모델의 안내를 받는다. 호출 요청이 없으면 첫 답변으로 끝낸다.
answer = model.invoke(messages) if response.tool_calls else response
print("최종 안내:", answer.text)