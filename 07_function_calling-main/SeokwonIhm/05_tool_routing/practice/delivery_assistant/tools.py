"""실습 JSON을 읽는다. 실제 배송사 접속이나 배송지 변경은 하지 않는다."""
import json
from pathlib import Path

from pydantic import TypeAdapter

from contracts import DeliveryArgs, DeliveryResult, PickupArgs, PickupResult

DATA = Path(__file__).resolve().parent.parent / 'data'


def read_rows(filename, result_type):
    rows = json.loads((DATA / filename).read_text(encoding='utf-8'))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError('조회 자료는 객체 목록이어야 합니다.')
    # 파일 오류·잘못된 반환 구조는 미등록(found=false)으로 숨기지 않는다.
    return TypeAdapter(list[result_type]).validate_python(
        [dict(row, found=True) for row in rows])


# 사용 도구: lookup_delivery — deliveries.json의 운송장번호로 배송 상태 조회.
def lookup_delivery(tracking_number: str) -> DeliveryResult:
    number = DeliveryArgs(tracking_number=tracking_number).tracking_number
    rows = read_rows('deliveries.json', DeliveryResult)
    return next((row for row in rows if row.tracking_number == number),
                DeliveryResult(found=False, tracking_number=number))


# 사용 도구: lookup_pickup_point — 현재 배송 결과의 ID로 수령 장소 조회.
def lookup_pickup_point(pickup_point_id: str) -> PickupResult:
    point_id = PickupArgs(pickup_point_id=pickup_point_id).pickup_point_id
    rows = read_rows('pickup_points.json', PickupResult)
    return next((row for row in rows if row.pickup_point_id == point_id),
                PickupResult(found=False, pickup_point_id=point_id))
