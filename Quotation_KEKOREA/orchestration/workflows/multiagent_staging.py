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
    text = subject + "\n" + body
    out = []
    for label, pattern in (
        ("선금/계약금", r"(?:deposit|down\s*payment|선금|계약금)[^\n.;]{0,55}?\b(\d{1,3}(?:\.\d+)?)\s*%"),
        ("잔금", r"(?:balance|remaining\s*payment|잔금)[^\n.;]{0,55}?\b(\d{1,3}(?:\.\d+)?)\s*%"),
        ("할인", r"(?:discount|할인율|할인)[^\n.;]{0,55}?\b(\d{1,3}(?:\.\d+)?)\s*%"),
    ):
        for match in re.finditer(pattern, text, re.I):
            val = Decimal(match.group(1))
            if val > 100:
                out.append(label + ": 비정상 비율 - 확인 필요")
            else:
                out.append(label + ": " + str(val) + "%")
    if not out:
        out.append("지급·할인 비율: 명시적 패턴 없음")
    if any(x.startswith("잔금:") for x in out) and not any(x.startswith("할인:") for x in out):
        out.append("검증: 잔금 비율을 할인율로 사용하지 않음")
    return out


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
    """Parallel independent analysis; deterministic order and no side effects."""
    tasks = (("문서 라우팅", classify_agent),
             ("지급조건 검증", payment_agent),
             ("입력 무결성", integrity_agent))
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_run, name, fn, subject, body) for name, fn in tasks]
        results = [f.result() for f in futures]
    return {"results": results,
            "total_ms": round((time.perf_counter() - start) * 1000),
            "mode": "staging_read_only"}
