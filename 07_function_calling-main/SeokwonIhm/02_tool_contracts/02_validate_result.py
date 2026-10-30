from unittest.mock import Base

from pydantic import BaseModel, ConfigDict

class AvailabilityResult(BaseModel):
    model_config = ConfigDict(strict = True, extra = "forbid")
    participant_id: str
    date: str
    times: list[str]|None

REQUESTED = {"participant_id": "A", "date": "2026-11-25"}
raw = {"participant_id":"A","date":"2026-11-25","times":["08:00~12:00"]}

print("조회 원본:", raw)
checked = AvailabilityResult.model_validate(raw)
if((checked.participant_id,checked.date) != (REQUESTED["participant_id"], REQUESTED["date"])):
    raise ValueError("안됨")
print("검사후 결과", checked.model_dump())