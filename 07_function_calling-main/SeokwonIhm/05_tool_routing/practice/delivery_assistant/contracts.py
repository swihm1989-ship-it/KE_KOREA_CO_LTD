"""사용자 의도와 MCP 도구의 입력·반환 계약."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class DeliveryArgs(Contract):
    tracking_number: Identifier


class PickupArgs(Contract):
    pickup_point_id: Identifier


class DeliveryResult(Contract):
    found: bool
    tracking_number: Identifier
    status: Literal['in_transit', 'ready_for_pickup', 'delivered'] | None = None
    status_note: Identifier | None = None
    pickup_point_id: Identifier | None = None
    updated_at: Identifier | None = None

    @model_validator(mode='after')
    def check_result(self):
        if not self.found:
            if any(value is not None for value in
                   (self.status, self.status_note, self.pickup_point_id, self.updated_at)):
                raise ValueError('미등록 배송의 상세 필드는 null이어야 합니다.')
        else:
            if self.status is None or self.status_note is None or self.updated_at is None:
                raise ValueError('등록 배송에는 상태·설명·기준 시각이 필요합니다.')
            if (self.status == 'ready_for_pickup') != (self.pickup_point_id is not None):
                raise ValueError('보관소 도착 상태에만 보관소 ID가 필요합니다.')
        return self


class PickupResult(Contract):
    found: bool
    pickup_point_id: Identifier
    name: Identifier | None = None
    address: Identifier | None = None
    opening_hours: Identifier | None = None

    @model_validator(mode='after')
    def check_result(self):
        values = (self.name, self.address, self.opening_hours)
        if self.found and any(value is None for value in values):
            raise ValueError('등록 보관소에는 이름·주소·운영시간이 필요합니다.')
        if not self.found and any(value is not None for value in values):
            raise ValueError('미등록 보관소의 상세 필드는 null이어야 합니다.')
        return self


class Intent(Contract):
    kind: Literal['general', 'delivery', 'change']
    tracking_number: str | None
    reply: str
