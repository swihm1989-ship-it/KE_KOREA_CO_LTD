"""JSON 조회와 모델에 공개하는 업무 도구 하나를 정의한다."""
import asyncio
import json
from pathlib import Path

from langchain_core.tools import tool
from pydantic import TypeAdapter

from batch import execute_batch, merge_results
from contracts import Catalog, BranchResult, CompareArgs, Scenario, check_concurrency

DATA = Path(__file__).resolve().parent.parent / 'data'
SCENARIO = 'normal'  # normal / east_error / all_error. 설정을 바꾼 뒤 새로 Run.
MAX_CONCURRENCY = 2  # 모델 인자가 아닌 Python 설정. 1 또는 2.


def read_catalog(branch_id, name):
    # 파일명은 Python이 정한 지점 ID로만 만든다. 사용자 제목을 경로로 사용하지 않는다.
    catalog = Catalog.model_validate(json.loads((DATA / f'{branch_id}.json').read_text(encoding='utf-8')))
    if catalog.branch_id != branch_id or catalog.name != name:
        raise ValueError('파일의 지점 식별자·이름이 조회 대상과 다릅니다.')
    return catalog


def load_scenario(scenario):
    raw = json.loads((DATA / 'scenarios.json').read_text(encoding='utf-8'))
    scenarios = TypeAdapter(dict[str, Scenario]).validate_python(raw)
    if scenario not in scenarios:
        raise ValueError(f'등록되지 않은 시나리오입니다: {scenario}')
    return scenarios[scenario]


async def lookup_branch(branch_id, name, title, scenario):
    # 가상 응답 지연도 비동기 sleep을 사용해 다른 지점 조회를 막지 않는다.
    await asyncio.sleep(scenario.delays[branch_id])
    if branch_id in scenario.failures:
        raise RuntimeError('시나리오에 지정된 가상 조회 오류')
    # JSON 읽기는 스레드로 보내 이벤트 루프를 막지 않는다.
    catalog = await asyncio.to_thread(read_catalog, branch_id, name)
    book = next((book for book in catalog.books if book.title == title), None)
    return BranchResult(branch_id=branch_id, name=name, title=title, found=book is not None,
                        available_count=book.available_count if book else None,
                        updated_at=catalog.updated_at)


async def run_comparison(title, scenario=None, max_concurrency=None, parallel=True):
    title = CompareArgs(title=title).title
    limit = MAX_CONCURRENCY if max_concurrency is None else max_concurrency
    check_concurrency(limit)
    condition = await asyncio.to_thread(load_scenario, SCENARIO if scenario is None else scenario)

    async def run_one(branch_id, name):
        return await lookup_branch(branch_id, name, title, condition)

    batch = await execute_batch(run_one, max_concurrency=limit, parallel=parallel)
    return merge_results(title, batch)


# 사용 도구: compare_library_stock — 모델 호출 1개 안에서 지점별 작업 3개를 병렬 실행.
@tool(args_schema=CompareArgs)
async def compare_library_stock(title: str) -> dict:
    """정확한 책 제목으로 중앙·동부·서부 도서관의 대출 가능 권수를 병렬 비교한다.

    제목이 없으면 먼저 질문한다. 0권·도서 미등록·조회 실패를 구분한다.
    고정된 실습 자료만 조회하며 대출·예약은 실행하지 않는다.
    """
    return await run_comparison(title)
