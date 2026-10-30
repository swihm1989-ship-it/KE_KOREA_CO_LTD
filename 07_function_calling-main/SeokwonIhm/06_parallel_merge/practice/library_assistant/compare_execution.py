"""모델 호출 없이 같은 JSON 조회의 순차·병렬 실행을 비교하고 기록한다."""
import asyncio
import json
from pathlib import Path
import sys

from batch import format_summary
from tools import run_comparison

TITLE = '파이썬 첫걸음'
SCENARIO = 'normal'  # normal / east_error / all_error
MAX_CONCURRENCY = 2  # 1 / 2


async def main():
    reports = []
    for parallel in (False, True):
        merged = await run_comparison(TITLE, scenario=SCENARIO,
                                      max_concurrency=MAX_CONCURRENCY, parallel=parallel)
        report = {'request': f'『{TITLE}』을 빌릴 수 있는 지점을 알려 줘.',
                  'mode': 'parallel' if parallel else 'sequential', 'scenario': SCENARIO,
                  'expected_collection_status': {'normal': 'complete', 'east_error': 'partial',
                                                 'all_error': 'failed'}[SCENARIO],
                  'model_calls': 0, 'internal_jobs': 3, 'max_concurrency': MAX_CONCURRENCY,
                  'merged': merged, 'summary_without_model': format_summary(merged)}
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    fields = ('title', 'collection_status', 'available_branches', 'unavailable_branches',
              'not_found_branches', 'errors')
    assert all(reports[0]['merged'][key] == reports[1]['merged'][key] for key in fields)
    assert all(row['merged']['peak_active'] <= MAX_CONCURRENCY for row in reports)
    # 실측값을 저장한다. 속도 향상 비율은 환경에 따라 달라 합격 조건으로 사용하지 않는다.
    destination = Path(__file__).with_name('comparison_results.json')
    destination.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: 순차·병렬의 자료·오류·지점 연결이 같습니다.')


async def verify_all():
    """과제의 자료·실패 시나리오를 모델 없이 모두 실행해 제출용 기록을 남긴다."""
    cases = [('파이썬 첫걸음', 'normal', 'complete'),
             ('데이터 분석 입문', 'normal', 'complete'),
             ('비동기 프로그래밍', 'normal', 'complete'),
             ('우주 항해 입문', 'normal', 'complete'),
             ('파이썬 첫걸음', 'east_error', 'partial'),
             ('파이썬 첫걸음', 'all_error', 'failed')]
    records = []
    for title, scenario, expected in cases:
        for parallel, limit in ((False, 2), (True, 1), (True, 2)):
            result = await run_comparison(title, scenario=scenario, parallel=parallel, max_concurrency=limit)
            assert result['collection_status'] == expected
            assert result['peak_active'] == (2 if parallel and limit == 2 else 1)
            records.append({'request': f'『{title}』을 빌릴 수 있는 지점을 알려 줘.',
                            'scenario': scenario, 'mode': 'parallel' if parallel else 'sequential',
                            'max_concurrency': limit, 'expected_collection_status': expected,
                            'model_calls': 0, 'internal_jobs': 3, 'merged': result,
                            'summary_without_model': format_summary(result)})
        comparable = ('title', 'collection_status', 'available_branches', 'unavailable_branches',
                      'not_found_branches', 'errors')
        assert all(records[-3]['merged'][key] == records[-2]['merged'][key] == records[-1]['merged'][key]
                   for key in comparable)
    path = Path(__file__).with_name('verification.json')
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS: {len(records)} executions; records: {path}')
    for row in records[:3]:
        merged = row['merged']
        print(f"{row['mode']} limit={row['max_concurrency']}: "
              f"elapsed={merged['elapsed_seconds']}s, peak={merged['peak_active']}")


if __name__ == '__main__':
    asyncio.run(verify_all() if '--verify-all' in sys.argv else main())
