"""외부 모델 API 없이 실제 JSON·병렬 실행·병합을 검증한다."""
import asyncio
from datetime import datetime
import unittest
import json

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from app import answer
from batch import merge_results
from contracts import BranchResult, CompareArgs
from tools import run_comparison, compare_library_stock


def semantic_result(result):
    return {key: result[key] for key in ('title', 'collection_status', 'available_branches',
                                       'unavailable_branches', 'not_found_branches', 'errors')}


class LibraryTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_counts_and_two_jobs_overlap(self):
        result = await run_comparison(' 파이썬 첫걸음 ')
        self.assertEqual(result['collection_status'], 'complete')
        self.assertEqual([(r['branch_id'], r['available_count']) for r in result['available_branches']],
                         [('central', 2), ('west', 1)])
        self.assertEqual(result['unavailable_branches'][0]['branch_id'], 'east')
        self.assertEqual([j['branch_id'] for j in result['jobs']], ['central', 'east', 'west'])
        self.assertEqual(result['peak_active'], 2)
        central, east, west = result['jobs']
        self.assertLess(datetime.fromisoformat(east['started_at']), datetime.fromisoformat(central['finished_at']))
        self.assertGreaterEqual(datetime.fromisoformat(west['started_at']), datetime.fromisoformat(east['finished_at']))

    async def test_zero_stock_is_complete_not_missing(self):
        result = await run_comparison('데이터 분석 입문')
        self.assertEqual(result['collection_status'], 'complete')
        self.assertEqual(len(result['unavailable_branches']), 3)
        self.assertEqual(result['not_found_branches'], [])

    async def test_registered_zero_and_missing_are_distinct(self):
        result = await run_comparison('비동기 프로그래밍')
        self.assertEqual(result['available_branches'][0]['available_count'], 1)
        self.assertEqual(result['unavailable_branches'][0]['branch_id'], 'west')
        self.assertEqual(result['not_found_branches'][0]['branch_id'], 'east')
        self.assertIsNone(result['not_found_branches'][0]['available_count'])

    async def test_all_missing_is_still_complete(self):
        result = await run_comparison('우주 항해 입문')
        self.assertEqual(result['collection_status'], 'complete')
        self.assertEqual(len(result['not_found_branches']), 3)
        self.assertEqual(result['errors'], [])

    async def test_east_error_preserves_other_counts(self):
        result = await run_comparison('파이썬 첫걸음', scenario='east_error')
        self.assertEqual(result['collection_status'], 'partial')
        self.assertEqual([r['branch_id'] for r in result['available_branches']], ['central', 'west'])
        self.assertEqual(result['errors'][0]['branch_id'], 'east')
        self.assertIsNone(result['jobs'][1]['result'])
        self.assertEqual(result['unavailable_branches'], [])
        self.assertEqual(result['not_found_branches'], [])

    async def test_all_error_has_no_confirmed_stock(self):
        result = await run_comparison('파이썬 첫걸음', scenario='all_error')
        self.assertEqual(result['collection_status'], 'failed')
        self.assertEqual(len(result['errors']), 3)
        self.assertEqual(result['available_branches'], [])
        self.assertEqual(result['unavailable_branches'], [])
        self.assertEqual(result['not_found_branches'], [])

    async def test_sequential_parallel_and_limit_one_have_same_data(self):
        for scenario in ('normal', 'east_error', 'all_error'):
            sequential = await run_comparison('파이썬 첫걸음', scenario=scenario, parallel=False)
            parallel = await run_comparison('파이썬 첫걸음', scenario=scenario)
            limited = await run_comparison('파이썬 첫걸음', scenario=scenario, max_concurrency=1)
            self.assertEqual(semantic_result(sequential), semantic_result(parallel))
            self.assertEqual(semantic_result(limited), semantic_result(parallel))
            self.assertEqual(sequential['peak_active'], 1)
            self.assertEqual(limited['peak_active'], 1)
            self.assertEqual(parallel['peak_active'], 2)

    async def test_cancellation_propagates(self):
        task = asyncio.create_task(run_comparison('파이썬 첫걸음'))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_tool_schema_only_exposes_title(self):
        self.assertEqual(set(compare_library_stock.args_schema.model_fields), {'title'})
        result = await compare_library_stock.ainvoke({'title': '파이썬 첫걸음'})
        self.assertEqual(len(result['jobs']), 3)

    async def test_invalid_title_and_configuration(self):
        with self.assertRaises(ValueError):
            CompareArgs(title='  ')
        with self.assertRaises(ValueError):
            CompareArgs(title=123)
        with self.assertRaises(ValueError):
            await run_comparison('파이썬 첫걸음', scenario='missing')
        for value in (0, -1, True, 3):
            with self.assertRaises(ValueError):
                await run_comparison('파이썬 첫걸음', max_concurrency=value)

    async def test_inconsistent_return_and_missing_job_are_rejected(self):
        with self.assertRaises(ValueError):
            BranchResult(branch_id='east', name='동부도서관', title='책', found=False,
                         available_count=0, updated_at='2026-10-29T09:00:00+09:00')
        result = await run_comparison('파이썬 첫걸음')
        with self.assertRaises(ValueError):
            merge_results('파이썬 첫걸음', {**result, 'jobs': result['jobs'][:2]})


class ScriptedModel(RunnableLambda):
    """모델 선택을 고정해 대화 연결만 검사한다. 실제 자연어 판단 검증은 아니다."""
    def __init__(self, responses):
        self.responses = iter(responses)
        super().__init__(lambda prompt: next(self.responses))

    def bind_tools(self, *args, **kwargs):
        return self


def request_tool(title, call_id):
    return AIMessage(content='', tool_calls=[{'name': 'compare_library_stock',
        'args': {'title': title}, 'id': call_id, 'type': 'tool_call'}])


class DialogueTests(unittest.IsolatedAsyncioTestCase):
    async def test_clarification_then_one_tool_message_for_three_jobs(self):
        model = ScriptedModel([AIMessage(content='어떤 책을 찾으시나요?'),
                               request_tool('파이썬 첫걸음', 'original-call'),
                               AIMessage(content='조회 결과를 안내합니다.')])
        messages = []
        await answer(model, messages, '책을 빌릴 수 있는 지점을 알려 줘.', emit=lambda _: None)
        self.assertFalse(any(isinstance(m, ToolMessage) for m in messages))
        await answer(model, messages, '파이썬 첫걸음', emit=lambda _: None)
        returned = [m for m in messages if isinstance(m, ToolMessage)]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned[0].tool_call_id, 'original-call')
        self.assertEqual(len(json.loads(returned[0].content)['jobs']), 3)
        self.assertIn('어떤 책을 찾으시나요?', [m.content for m in messages])

    async def test_new_title_requeries_instead_of_reusing_previous_stock(self):
        model = ScriptedModel([request_tool('파이썬 첫걸음', 'first'), AIMessage(content='첫 결과'),
                               request_tool('데이터 분석 입문', 'second'), AIMessage(content='새 결과')])
        messages = []
        await answer(model, messages, '파이썬 첫걸음 찾아 줘.', emit=lambda _: None)
        await answer(model, messages, '그럼 데이터 분석 입문은?', emit=lambda _: None)
        results = [json.loads(m.content) for m in messages if isinstance(m, ToolMessage)]
        self.assertEqual(len(results), 2)
        self.assertEqual(len(results[0]['available_branches']), 2)
        self.assertEqual(results[1]['title'], '데이터 분석 입문')
        self.assertEqual(len(results[1]['unavailable_branches']), 3)
        self.assertEqual(results[1]['available_branches'], [])

    async def test_non_tool_answer_adds_no_tool_message(self):
        for request in ('대출 가능 0권과 도서 미등록은 무슨 차이야?', '파이썬 첫걸음을 예약해 줘.'):
            messages = []
            model = ScriptedModel([AIMessage(content='일반 설명 또는 지원 범위 안내')])
            await answer(model, messages, request, emit=lambda _: None)
            self.assertFalse(any(isinstance(m, ToolMessage) for m in messages))

    async def test_invented_title_and_multiple_calls_are_rejected_before_execution(self):
        scenarios = [request_tool('없는 제목', 'invented'), AIMessage(content='', tool_calls=[
            {'name': 'compare_library_stock', 'args': {'title': '파이썬 첫걸음'}, 'id': call_id,
             'type': 'tool_call'} for call_id in ('one', 'two')])]
        for response in scenarios:
            messages = []
            await answer(ScriptedModel([response, AIMessage(content='실행 거부 안내')]), messages,
                         '파이썬 첫걸음 찾아 줘.', emit=lambda _: None)
            returned = [m for m in messages if isinstance(m, ToolMessage)]
            self.assertEqual(len(returned), len(response.tool_calls))
            self.assertTrue(all(m.status == 'error' for m in returned))


if __name__ == '__main__':
    unittest.main()
