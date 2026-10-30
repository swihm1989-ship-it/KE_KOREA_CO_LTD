"""설정된 실제 모델 + 실제 MCP 실행 기록 생성. 실행 시 모델 API 사용."""
import asyncio
import json
from pathlib import Path

from app import connect_delivery, create_model, process_request

CASES = [
    ('내 택배 어디까지 왔어?', ['D100'], ['lookup_delivery']),
    ('D100 배송 상태 알려 줘.', [], ['lookup_delivery']),
    ('D200 어디서 받아?', [], ['lookup_delivery', 'lookup_pickup_point']),
    ('D300 배송 상태 알려 줘.', [], ['lookup_delivery']),
    ('D999 조회해 줘.', [], ['lookup_delivery']),
    ('배송 중이랑 배송 완료는 무슨 차이야?', [], []),
    ('D200 배송지를 바꿔 줘.', [], ['lookup_delivery', 'lookup_pickup_point']),
    ('D400 어디서 받아?', [], ['lookup_delivery', 'lookup_pickup_point']),
    ('키보드의 기계식과 멤브레인 차이를 설명해 줘.', [], []),
]


async def main():
    model = create_model()
    records = []
    async with connect_delivery() as (session, definitions):
        async def run(request, answers, expected, history):
            replies = iter(answers)
            events = []
            result = await process_request(model, session, definitions, history, request,
                                           ask=lambda _: next(replies), emit=events.append)
            actual = [row['name'] for row in result['trace'] if row['executed']]
            passed = actual == expected and not result['state']['error']
            record = {'request': request, 'follow_up': answers, 'expected': expected,
                      'actual': actual, 'path_passed': passed, 'events': events, **result}
            records.append(record)
            # 시나리오마다 저장해 중간 통신 실패에도 완료된 기록은 남긴다.
            Path(__file__).with_name('verification.json').write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            print(('PASS' if passed else 'FAIL') + ': ' + request, flush=True)
            return result

        for request, answers, expected in CASES:
            await run(request, answers, expected, [])
        history = []
        await run('D200 어디서 받아?', [], ['lookup_delivery', 'lookup_pickup_point'], history)
        second = await run('그럼 D100은?', [], ['lookup_delivery'], history)
        assert second['state']['pickup'] is None
    if not all(record['path_passed'] for record in records):
        raise SystemExit('실제 호출 경로가 예상과 다른 시나리오가 있습니다. verification.json을 확인하세요.')
    print(f'{len(records)}개 실제 모델/MCP 시나리오 경로 통과')


if __name__ == '__main__':
    asyncio.run(main())
