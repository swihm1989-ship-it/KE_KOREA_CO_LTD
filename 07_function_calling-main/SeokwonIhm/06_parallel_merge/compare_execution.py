"""입력한 N개 주제의 순차·병렬 검색을 비교한 뒤 병렬 결과만 합류한다."""
import asyncio
import json
from time import perf_counter

from dotenv import load_dotenv

from batch import merge_results
from tools import run_searches, search_jobs
from tavily_connection import connect_tavily

TOPICS = ["USB", "Bluetooth"]  # 비교용 입력이다. 한 주제나 세 주제로 바꿀 수 있다.
# DOMAINS = ["learn.microsoft.com"]  # None이면 사이트를 제한하지 않는다.
DOMAINS = None
MAX_CONCURRENCY = 2  # STEP 01 작성 뒤 None·1·2로 바꾸어 실행 구간의 겹침을 비교한다.


async def main():
    load_dotenv()
    async with connect_tavily() as (session, definitions):
        # 계획만 만드는 단계다. 실제 검색 전에 입력 검증과 필요한 주제 목록을 확정한다.
        jobs = search_jobs(definitions, TOPICS, DOMAINS)
        required_topics = [job["topic"] for job in jobs]
        print("비교할 검색 작업:", jobs)
        parallel_results = []
        # 같은 N개 입력을 각각 실행한다. 완주하면 MCP 검색은 2N번이며 모델 호출은 없다.
        for label, parallel in [("sequential", False), ("parallel", True)]:
            started = perf_counter()
            results = await run_searches(session, definitions, required_topics, DOMAINS,
                                         max_concurrency=MAX_CONCURRENCY, parallel=parallel)
            report = {"mode": label, "model_calls": 0, "job_count": len(results),
                      "elapsed_seconds": round(perf_counter() - started, 4), "results": results}
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if parallel:
                parallel_results = results

    # 두 구간을 마친 뒤 병렬 결과만 합류하므로 STEP 01 다음 STEP 02에 도달한다.
    print("합류 대상: 병렬 실행 결과", len(parallel_results), "개")
    merged = merge_results(parallel_results, required_topics)
    print("검색 자료 합류 판정:", json.dumps(merged, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
