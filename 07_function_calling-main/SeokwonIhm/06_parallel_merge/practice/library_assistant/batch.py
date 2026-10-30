"""세 지점의 독립 실행과 합류 이후 판정. 외부 모델 호출 없음."""
import asyncio
from datetime import datetime, timezone
from time import perf_counter

from contracts import BRANCHES, BranchResult, CompareArgs, JobRecord, MergedResult, check_concurrency


async def execute_batch(run_one, max_concurrency=2, parallel=True):
    check_concurrency(max_concurrency)
    semaphore = asyncio.Semaphore(max_concurrency)
    active, peak_active = 0, 0
    started = perf_counter()

    async def one(branch_id, name):
        nonlocal active, peak_active
        # 자리를 얻은 뒤 측정한다. 대기 시간은 아래 전체 elapsed_seconds에 포함된다.
        async with semaphore:
            active += 1
            peak_active = max(peak_active, active)
            started_at = datetime.now(timezone.utc).isoformat()
            job_started = perf_counter()
            result, error, status = None, None, 'ok'
            try:
                result = BranchResult.model_validate(await run_one(branch_id, name))
                if result.branch_id != branch_id or result.name != name:
                    raise ValueError('조회한 지점과 반환 자료의 지점이 다릅니다.')
            except Exception as exc:
                # CancelledError는 BaseException이므로 여기서 숨기지 않고 상위로 전달한다.
                result, status, error = None, 'error', f'{type(exc).__name__}: {exc}'
            finally:
                finished_at = datetime.now(timezone.utc).isoformat()
                elapsed = perf_counter() - job_started
                active -= 1
            return JobRecord(branch_id=branch_id, name=name, status=status,
                             result=result, error=error, started_at=started_at,
                             finished_at=finished_at, elapsed_seconds=round(elapsed, 6)).model_dump()

    if parallel:
        # 병렬 실행: 세 작업을 한 번에 예약한다. 실제 실행은 Semaphore로 최대 2개.
        # gather의 반환 순서는 완료 순서가 아니라 입력 지점 순서다.
        jobs = await asyncio.gather(*(one(branch_id, name) for branch_id, name in BRANCHES))
    else:
        jobs = [await one(branch_id, name) for branch_id, name in BRANCHES]
    return {'jobs': jobs, 'elapsed_seconds': round(perf_counter() - started, 6),
            'peak_active': peak_active}


def merge_results(title, batch):
    title = CompareArgs(title=title).title
    records = [JobRecord.model_validate(job) for job in batch['jobs']]
    if [(job.branch_id, job.name) for job in records] != list(BRANCHES):
        raise ValueError('중앙·동부·서부 지점의 작업 기록 세 개가 입력 순서대로 필요합니다.')
    available, unavailable, not_found, errors = [], [], [], []
    # 합류 이후 판단: 작업 중에는 공유 결과를 변경하지 않는다.
    for job in records:
        if job.status == 'error':
            errors.append({'branch_id': job.branch_id, 'name': job.name, 'error': job.error})
            continue
        row = job.result
        if row.title != title:
            raise ValueError('작업 결과의 도서명이 이번 요청과 다릅니다.')
        if not row.found:
            not_found.append(row)
        elif row.available_count == 0:
            unavailable.append(row)
        else:
            available.append(row)
    status = 'complete' if not errors else 'failed' if len(errors) == len(BRANCHES) else 'partial'
    return MergedResult(title=title, collection_status=status, available_branches=available,
                        unavailable_branches=unavailable, not_found_branches=not_found,
                        errors=errors, jobs=records, elapsed_seconds=batch['elapsed_seconds'],
                        peak_active=batch['peak_active']).model_dump()


def format_summary(merged):
    """모델 없는 비교 실행 및 모델 실패 시 사용할 실제 자료의 정형 안내."""
    checked = MergedResult.model_validate(merged)
    lines = [f'『{checked.title}』 조회 결과 ({checked.collection_status}, 고정 가상 자료)']
    for job in checked.jobs:
        if job.status == 'error':
            lines.append(f'- {job.name}: 미확인 — {job.error}')
        else:
            row = job.result
            stock = f'대출 가능 {row.available_count}권' if row.found else '도서 미등록'
            lines.append(f'- {row.name}: {stock} (자료 기준 시각: {row.updated_at})')
    if checked.collection_status != 'complete':
        lines.append('조회 실패한 지점의 권수는 확인하지 못했습니다.')
    return '\n'.join(lines)
