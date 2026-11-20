"""Staging-only, read-only multi-agent prototype.

Runs independent classification and numeric risk checks concurrently.
No provider calls, database writes, document creation or email sending.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import time

from Quotation_KEKOREA.orchestration.workflows.mail_intake import prepare_mail_request
from Quotation_KEKOREA.orchestration.workflows.trade_terms_staging import describe_trade, crosscheck


@dataclass(frozen=True)
class AgentResult:
    name: str
    status: str
    details: tuple[str, ...]
    elapsed_ms: int


def _run(name, fn, subject, body):
    start = time.perf_counter()
    try:
        return AgentResult(name, "ok", tuple(fn(subject, body)),
                           round((time.perf_counter() - start) * 1000))
    except (ValueError, TypeError, RuntimeError) as exc:
        return AgentResult(name, "needs_review", (type(exc).__name__,),
                           round((time.perf_counter() - start) * 1000))


def classify_agent(subject, body):
    request = prepare_mail_request(subject, body)
    return ["문서 후보: " + (", ".join(request.kinds) if request.kinds else "미확정"),
            "원본 지문: " + request.fingerprint[:12]]


def payment_agent(subject, body):
    """Recognize local percentage-label pairs in either order.

    Never search across another percentage or payment label: ambiguous cases
    are explicitly flagged instead of silently assigning the wrong number.
    """
    text = subject + "\n" + body
    labels = (
        ("선금/계약금", r"(?:deposit|down\s*payment|선금|계약금)"),
        ("잔금", r"(?:balance|remaining\s*payment|잔금)"),
        ("할인", r"(?:discount|할인율|할인)"),
    )
    pct = r"(\d{1,3}(?:\.\d+)?)\s*%"
    found = []
    for name, label in labels:
        # Label first: 'deposit: 30%' but never skip over another label.
        after = re.compile(r"(?i)(?:" + label + r")\s*(?:is|of|:|=|-)?\s*" + pct)
        # Percentage first: '30% deposit', '70% balance'.
        before = re.compile(r"(?i)" + pct + r"\s*(?:as|for|of)?\s*(?:" + label + r")\b")
        values = [m.group(1) for m in after.finditer(text)]
        values += [m.group(1) for m in before.finditer(text)]
        if len(set(values)) > 1:
            found.append(name + ": 상충하는 비율 - 확인 필요")
        elif values:
            val = Decimal(values[0])
            found.append(name + ": " + str(val) + "%" if val <= 100
                         else name + ": 비정상 비율 - 확인 필요")
    if not found:
        found.append("지급·할인 비율: 명시적 패턴 없음 - 확인 필요")
    if any(x.startswith("잔금:") for x in found) and not any(x.startswith("할인:") for x in found):
        found.append("검증: 잔금 비율을 할인율로 사용하지 않음")
    return found


def integrity_agent(subject, body):
    text = subject + "\n" + body
    warnings = []
    if len(text) > 12000:
        warnings.append("12,000자 초과: 자동 절단 금지")
    if re.search(r"(?i)\b(?:ignore previous instructions|system prompt|developer message)\b", text):
        warnings.append("외부 문서의 지시문 의심: 데이터로만 취급")
    if not re.search(r"(?i)(?:\b\d[\d,.]*\s*(?:pcs|units|kg|mw|wp)\b|\bquantity\b|수량|개|장)", text):
        warnings.append("수량 근거 확인 필요")
    return warnings or ["기본 무결성 경고 없음 (정확성 보증 아님)"]


def analyze(subject: str, body: str) -> dict:
    """Four parallel specialists and one downstream deterministic cross-check.

    No side effects, account access, model calls, database writes or sending.
    """
    tasks = (("문서 라우팅", classify_agent),
             ("지급조건 검증", payment_agent),
             ("상품·가격 추출", describe_trade),
             ("입력 무결성", integrity_agent))
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run, name, fn, subject, body) for name, fn in tasks]
        results = [f.result() for f in futures]
    payment_details = results[1].details
    results.append(_run("교차 검증",
                        lambda s, b: crosscheck(s, b, payment_details),
                        subject, body))
    return {"results": results,
            "total_ms": round((time.perf_counter() - start) * 1000),
            "mode": "staging_read_only_deterministic",
            "parallel_agents": 4,
            "verification_agents": 1}
