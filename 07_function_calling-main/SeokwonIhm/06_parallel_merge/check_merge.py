"""선택 확인: 통제된 검색 표본으로 상한·빈 결과·실패·취소를 확인한다."""
import asyncio
import json

from batch import execute_batch, merge_results


async def main():
    # STEP01·02 작성 뒤 선택 실행한다. 같은 배치·합류 함수에 통제된 결과를 넣어 분기를 확인한다.
    print("통제된 표본: 실제 모델·MCP·외부 서비스 호출은 모두 0회입니다.")
    # active는 현재 run_one 안의 작업 수, peak는 그 수가 가장 컸을 때의 값이다.
    active, peak = 0, 0

    async def run_one(job):
        # main에 있는 두 변수를 이 내부 함수에서도 갱신한다.
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            # 실제 검색 대신 응답 지연을 흉내 낸다. 대기 중에는 다른 작업이 진행될 수 있다.
            await asyncio.sleep(job.get("delay", 0.01))
            # error는 실행 예외, empty는 정상 반환된 빈 검색 목록을 재현한다.
            if job.get("kind") == "error":
                raise TimeoutError("통제된 검색 오류")
            # 자료의 필드 형식은 실제 검색과 같지만, example.test와 내용은 모두 검증용 표본이다.
            rows = [] if job.get("kind") == "empty" else [{
                "title": job["topic"] + " 통제된 제목", "url": "https://example.test/" + job["topic"],
                "content": job["topic"] + " 통제된 검색 요약"}]
            return {"results": rows}
        finally:
            # 정상 종료·예외·취소 모두 실행 중인 작업 수를 줄이고 상위로 돌아간다.
            active -= 1

    # 세 작업을 상한 2로 실행해 세 번째 대기와 완료 순서·반환 순서의 차이를 관찰한다.
    jobs = [{"topic": "USB", "label": "USB", "delay": 0.06},
            {"topic": "Bluetooth", "label": "Bluetooth", "delay": 0.01},
            {"topic": "추가 표본", "label": "추가 표본", "delay": 0.02}]
    success = await execute_batch(jobs, run_one, max_concurrency=2)
    # peak_active=2와 입력 순서 USB·Bluetooth·추가 표본을 본다. 완료 순서와는 별개다.
    print("통제된 상한 확인:", {"peak_active": peak, "input_order": [x["job"]["topic"] for x in success]})
    # 두 호출 모두 작업 기록 목록을 반환한다. 빈 결과는 error 없이, 예외는 error에 기록된다.
    empty = await execute_batch([{"topic": "Bluetooth", "kind": "empty"}], run_one)
    failed = await execute_batch([{"topic": "Bluetooth", "kind": "error"}], run_one)
    # 필수 주제는 USB·Bluetooth로 두고, 자료가 모두 있음 / 누락 / 빈 결과 / 실패를 비교한다.
    # success[:2]는 두 필수 주제, [:1]은 USB만 남긴다. *empty·*failed는 기록 목록을 펼친다.
    cases = [("두 주제 확보", success[:2]), ("아직 없는 주제", success[:1]),
             ("정상 빈 검색", [success[0], *empty]), ("검색 실패", [success[0], *failed])]
    # 차례로 ready / collect_more / show_partial / show_partial과 성공 자료 보존을 확인한다.
    for label, results in cases:
        print("합류 표본:", label)
        print(json.dumps(merge_results(results, {"USB", "Bluetooth"}), ensure_ascii=False, indent=2))

    # 긴 작업을 Task로 예약하고, 잠시 기다려 실행 중인 작업의 취소를 확인한다.
    task = asyncio.create_task(execute_batch([{"topic": "취소 표본", "delay": 1}], run_one))
    await asyncio.sleep(0.01)
    # 취소를 요청한 뒤 await에서 CancelledError가 전달되는지 확인한다.
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("취소 확인: CancelledError가 호출자에게 전파됐습니다.")


if __name__ == "__main__":
    asyncio.run(main())
