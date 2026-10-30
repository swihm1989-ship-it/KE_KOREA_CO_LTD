"""독립 검색의 실제 실행·개별 기록·주제별 검색 자료 합류를 연결한다."""
import asyncio
from datetime import datetime, timezone
from time import perf_counter

async def execute_batch(jobs, run_one, max_concurrency=2, parallel=True):
    # jobs를 외부에서 받은 run_one으로 실행하고 작업별 기록 목록을 반환한다.
    if max_concurrency is not None and (type(max_concurrency) is not int or max_concurrency < 1):
        raise ValueError("동시 실행 상한은 None 또는 양의 정수여야 합니다.")

    # one은 실행·상태·시간 기록을 묶으며, 아래의 await·gather에서 실제 작업을 시작한다.
    async def one(job):
        # 시간은 one 진입부터 잰다. Semaphore 자리를 기다린 시간은 작업별 시간에서 빠진다.
        started_at, started = datetime.now(timezone.utc).isoformat(), perf_counter()
        result, error, status = None, None, "ok"
        try:
            # 전달받은 실행 함수에 작업 하나를 넘겨 실제 반환을 기다린다.
            result = await run_one(job)
            print("작업의 실제 반환:", job.get("label", job.get("name", "작업")), result)
            # 정상 반환에서도 빈 목록과 일부 URL 실패를 구별한다.
            if result.get("failed_results") or any(key in result and not result[key] for key in ("results", "products")):
                if result.get("failed_results"):
                    status = "partial" if result.get("results") else "error"
                else:
                    status = "empty"
        except NotImplementedError:
            raise  # 미작성 지점을 외부 서비스 오류로 바꾸지 않는다.
        except Exception as exc:
            status, error = "error", f"{type(exc).__name__}: {exc}"
        # 원래 작업과 반환·오류·시간을 한 기록에 묶어 완료 순서와 관계없이 대응시킨다.
        return {"job": job, "status": status, "result": result, "error": error,
                "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(perf_counter() - started, 4)}

    # 순차 경로에서는 한 작업의 반환을 받은 뒤 다음 작업을 시작한다.
    if not parallel:
        return [await one(job) for job in jobs]
    # STEP 01 · 독립 작업을 함께 기다리고 실제 동시 실행 수를 제한한다.
    if max_concurrency is None:
        return await asyncio.gather(*(one(job) for job in jobs))

    semaphore = asyncio.Semaphore(max_concurrency)
    async def limited(job):
        async with semaphore:
            return await one(job)
    return await asyncio.gather(*(limited(job) for job in jobs))
    


def merge_results(results, required_topics):
    # 검색 요약을 주제별로 모은다. 본문을 읽었거나 제품 사양을 검증했다는 뜻은 아니다.
    # sources는 주제·URL별 자료, confirmed는 자료가 있는 주제다. 실패와 빈 결과는 따로 모은다.
    sources, confirmed, errors, empty_topics = {}, set(), [], []
    for item in results:
        topic = item["job"]["topic"]
        if item["error"]:
            errors.append({"topic": topic, "error": item["error"]})
        # 실행 오류로 result가 None이면 빈 딕셔너리에서 읽어 자료 목록을 비워 둔다.
        rows = (item["result"] or {}).get("results", [])
        # 제목·URL·검색 요약이 모두 비어 있지 않은 문자열인 자료만 사용한다.
        usable = [row for row in rows if all(isinstance(row.get(key), str) and row[key].strip()
                                            for key in ("title", "url", "content"))]
        # 별도 실행 예외가 없고 사용할 자료가 없으면 빈 주제로 기록한다.
        if not usable and not item["error"]:
            empty_topics.append(topic)
        # 같은 주제·URL은 한 건으로 모으고, 자료가 하나라도 있으면 해당 주제를 확보한 것이다.
        for row in usable:
            sources[(topic, row["url"])] = {"topic": topic, **row}
            confirmed.add(topic)
        # 성공 자료가 있어도 응답에 포함된 개별 실패 기록은 남긴다.
        for failure in (item["result"] or {}).get("failed_results", []):
            errors.append({"topic": topic, **failure})
    # 여기까지는 수집 현황이다. 다음 STEP02에서 필수 주제의 누락과 다음 행동을 판단한다.
    print("검색된 주제:", sorted(confirmed), "실패:", errors, "빈 주제:", empty_topics)
    # STEP 02 · 필수 주제의 검색 자료 누락과 합류 뒤 행동을 판단한다.
    missing = set(required_topics) - confirmed
    action = "show_partial" if errors or empty_topics else "collect_more" if missing else "ready"
    # 판정과 실제 자료를 호출자에게 돌려준다. 추가 검색을 여기서 실행하지는 않는다.
    return {"action": action, "required_topics": sorted(required_topics),
            "confirmed_topics": sorted(confirmed), "missing_topics": sorted(missing),
            "sources": list(sources.values()), "errors": errors, "empty_topics": sorted(set(empty_topics))}
