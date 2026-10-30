"""두 조회 도구를 stdio로 제공하는 로컬 MCP 2.x 서버."""
from mcp.server.mcpserver import MCPServer

from contracts import DeliveryResult, PickupResult
from tools import lookup_delivery as read_delivery, lookup_pickup_point as read_pickup

server = MCPServer('delivery-assistant', log_level='WARNING')


# 사용 MCP 도구: lookup_delivery. 읽기 전용이며 배송지를 변경하지 않는다.
@server.tool()
def lookup_delivery(tracking_number: str) -> DeliveryResult:
    """사용자가 제공한 운송장번호로 가상 배송 상태를 조회한다. 번호를 추측하지 않는다."""
    return read_delivery(tracking_number)


# 사용 MCP 도구: lookup_pickup_point. 현재 배송이 보관소 도착 상태일 때만 사용.
@server.tool()
def lookup_pickup_point(pickup_point_id: str) -> PickupResult:
    """현재 배송 조회 결과가 보관소 도착일 때 반환한 보관소 ID로 주소와 운영시간을 조회한다."""
    return read_pickup(pickup_point_id)


if __name__ == '__main__':
    server.run(transport='stdio')
