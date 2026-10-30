import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# 원문: A의 2026-11-25 가능 시간을 알려줘

class AvailablityArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    participant_id: Literal["A", "B"]
    date: str

REQUESTED = {"participant_id" : "A", "date" : "2026-11-25"}
# arguments = {"participant_id" : "A", "date" : "2026-11-25"}
# model_validate 시 오류
# arguments = {"participant_id" : "C", "date" : "2026-11-25"}
# 원문과 동일하지 않은 오류
# arguments = {"participant_id" : "B", "date" : "2026-11-25"}
arguments = {"participant_id" : "B", "date" : "20261131"}

print("검사 전 인자:", arguments)
checked = AvailablityArgs.model_validate(arguments)
print("검사 후 인자:", checked.model_dump())
datetime.date.fromisoformat(checked.date)
if checked.model_dump() != REQUESTED:
    raise ValueError("원래 요청한 참석자, 날짜와 다르다.")