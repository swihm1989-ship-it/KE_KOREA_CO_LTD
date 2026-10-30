"""실제 JSON 및 로컬 MCP 서버를 사용하는 회귀 검증. 외부 모델 호출 없음."""
import unittest
from functools import wraps
from unittest.mock import patch

from app import connect_delivery, execute_call, new_state, available_tools
from tools import lookup_delivery, lookup_pickup_point
from contracts import DeliveryResult, PickupResult


class DataTests(unittest.TestCase):
    def test_delivery_statuses_and_missing(self):
        for number, expected in [('D100', 'in_transit'), ('D200', 'ready_for_pickup'),
                                 ('D300', 'delivered'), ('D400', 'ready_for_pickup')]:
            self.assertEqual(lookup_delivery(number).status, expected)
        result = lookup_delivery(' D999 ')
        self.assertFalse(result.found)
        self.assertEqual(result.tracking_number, 'D999')
        self.assertIsNone(result.status)

    def test_pickup_points_and_missing(self):
        self.assertEqual(lookup_pickup_point('S001').name, '한빛 수령소')
        self.assertEqual(lookup_pickup_point(' S002 ').name, '새봄 수령소')
        missing = lookup_pickup_point('S999')
        self.assertFalse(missing.found)
        self.assertIsNone(missing.address)

    def test_blank_input_and_file_failure_are_errors(self):
        with self.assertRaises(ValueError):
            lookup_delivery('   ')
        with patch('tools.Path.read_text', side_effect=OSError('read failed')):
            with self.assertRaises(OSError):
                lookup_delivery('D100')

    def test_inconsistent_return_contracts_are_rejected(self):
        with self.assertRaises(ValueError):
            DeliveryResult(found=True, tracking_number='D100', status='in_transit',
                           status_note='이동 중', pickup_point_id='S001', updated_at='2026-10-29')
        with self.assertRaises(ValueError):
            PickupResult(found=False, pickup_point_id='S999', address='추측 주소')


def with_mcp(test):
    @wraps(test)
    async def connected(self):
        # anyio의 진입/종료는 unittest setup/teardown의 서로 다른 Task로 나누지 않는다.
        async with connect_delivery() as (self.session, self.definitions):
            await test(self)
    return connected


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, state, name, args):
        return await execute_call(self.session, state, {'id': 'test-call', 'name': name, 'args': args})

    @with_mcp
    async def test_discovery_and_delivery_then_pickup(self):
        self.assertEqual(set(self.definitions), {'lookup_delivery', 'lookup_pickup_point'})
        for number, point in [('D200', 'S001'), ('D400', 'S002')]:
            state = new_state(number)
            result = await self.call(state, 'lookup_delivery', {'tracking_number': number})
            self.assertEqual(result.status, 'success')
            self.assertEqual(state['delivery']['pickup_point_id'], point)
            self.assertEqual(available_tools(state), ['lookup_pickup_point'])
            await self.call(state, 'lookup_pickup_point', {'pickup_point_id': point})
            self.assertTrue(state['pickup']['found'])
            self.assertEqual(available_tools(state), [])

    @with_mcp
    async def test_no_pickup_for_transit_delivered_or_missing(self):
        for number in ('D100', 'D300', 'D999'):
            state = new_state(number)
            await self.call(state, 'lookup_delivery', {'tracking_number': number})
            self.assertEqual(available_tools(state), [])
            result = await self.call(state, 'lookup_pickup_point', {'pickup_point_id': 'S001'})
            self.assertEqual(result.status, 'error')
            self.assertEqual(state['calls'], 1)

    @with_mcp
    async def test_new_request_cannot_reuse_previous_pickup(self):
        first = new_state('D200')
        await self.call(first, 'lookup_delivery', {'tracking_number': 'D200'})
        second = new_state('D100')
        result = await self.call(second, 'lookup_pickup_point', {'pickup_point_id': 'S001'})
        self.assertEqual(result.status, 'error')
        self.assertEqual(second['calls'], 0)

    @with_mcp
    async def test_reject_wrong_tracking_and_wrong_pickup_id(self):
        state = new_state('D400')
        result = await self.call(state, 'lookup_delivery', {'tracking_number': 'D200'})
        self.assertEqual(result.status, 'error')
        self.assertEqual(state['calls'], 0)
        await self.call(state, 'lookup_delivery', {'tracking_number': 'D400'})
        result = await self.call(state, 'lookup_pickup_point', {'pickup_point_id': 'S001'})
        self.assertEqual(result.status, 'error')
        self.assertEqual(state['calls'], 1)

    @with_mcp
    async def test_four_call_limit(self):
        state = new_state('D100')
        state['calls'] = 4
        result = await self.call(state, 'lookup_delivery', {'tracking_number': 'D100'})
        self.assertEqual(result.status, 'error')
        self.assertEqual(state['calls'], 4)

    @with_mcp
    async def test_mcp_execution_error_is_not_a_missing_delivery(self):
        result = await self.session.call_tool('lookup_delivery', {'tracking_number': '   '})
        self.assertTrue(result.is_error)


if __name__ == '__main__':
    unittest.main()
