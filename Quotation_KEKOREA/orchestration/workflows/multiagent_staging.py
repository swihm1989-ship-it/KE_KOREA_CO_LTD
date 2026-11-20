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
        details = tuple(fn(subject, body))
        markers = ("확인 필요", "검토 필요", "상충하는", "불일치",
                   "비정상", "초과", "미확정", "합계가 100%가 아님")
        status = "needs_review" if any(
            marker in detail for detail in details for marker in markers
        ) else "ok"
        return AgentResult(name, status, details,
                           round((time.perf_counter() - start) * 1000))
    except (ValueError, TypeError, RuntimeError) as exc:
        return AgentResult(name, "needs_review", (type(exc).__name__,),
                           round((time.perf_counter() - start) * 1000))


def classify_agent(subject, body):
    request = prepare_mail_request(subject, body)
    return ["문서 후보: " + (", ".join(request.kinds) if request.kinds else "미확정"),
            "원본 지문: " + request.fingerprint[:12]]


def payment_agent(subject, body):
    """Extract percentages adjacent to each payment label without crossing lines.

    Handles both "Deposit: 40%" and "40% deposit" and never attaches the
    40% from "Deposit: 40%\nBalance: 60%" to the balance label.
    Same-line "Deposit: 40% Balance: 60%" is also disambiguated.
    """
    text = str(subject or "") + "\n" + str(body or "")
    labels = (
        ("선금/계약금", r"(?:deposit|down[ \t]+payment|선금|계약금)"),
        ("잔금", r"(?:balance|remaining[ \t]+payment|잔금)"),
        ("할인", r"(?:discount|할인율|할인)"),
    )
    pct = r"(\d{1,3}(?:\.\d+)?)[ \t]*%"
    found = []
    for name, label in labels:
        # Horizontal whitespace only; do not cross newline or a new field.
        after = re.compile(
            r"(?i)(?:" + label + r")[ \t]*(?:is|of|:|=|-)?[ \t]*" + pct
        )
        # Never interpret "40% Balance: 60%" as a 40% balance.
        before = re.compile(
            r"(?i)" + pct + r"[ \t]*(?:(?:as|for|of)[ \t]+)?(?:"
            + label + r")\b(?![ \t]*[:=])"
        )
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


def smoke_tests() -> tuple[tuple[str, bool], ...]:
    """In-process synthetic regression tests: no external services or fixtures."""
    from Quotation_KEKOREA.orchestration.workflows.trade_terms_staging import extract_trade

    good = ("Please prepare PI and PO",
            "Product: Solar Cell M10 PERC\nQuantity: 100,000 pcs\n"
            "Unit Price: USD 0.20/pc\nTotal: USD 20,000\n"
            "Payment: 30% deposit and 70% balance.\nDelivery: CIF Shanghai")
    first = analyze(*good)
    pay = first["results"][1].details
    trade = extract_trade(*good)
    accurate = (first["results"][0].status == "ok"
                and "선금/계약금: 30%" in pay and "잔금: 70%" in pay
                and trade["calculated_total"] == "20,000"
                and trade["currency"] == "USD"
                and "CIF" in (trade["delivery"] or ""))

    mismatch = extract_trade(
        "Please prepare PI",
        "Product: Solar Cell\nQuantity: 100,000 pcs\n"
        "Unit Price: USD 0.20/pc\nTotal: USD 22,000")
    mismatch_found = any("총액 불일치" in msg for msg in mismatch["warnings"])

    bad_payment = analyze(
        "Please prepare PI", "Deposit: 30%\nBalance: 60%")
    bad_payment_found = any(
        "합계가 100%" in msg for msg in bad_payment["results"][-1].details)

    multi = extract_trade(
        "Please prepare PI",
        "Product: Cell A\nProduct: Cell B\nQuantity: 200 pcs\nUnit Price: USD 0.2")
    multi_flagged = multi["calculated_total"] is None and any(
        "복수 품목" in msg for msg in multi["warnings"])

    # Regression: original customer-like email previously treated 40% deposit
    # as a second conflicting balance percentage across a newline.
    first_mail = ("Request for PI and PO – M10 Solar Cells",
                  "Dear Sales Team,\nPlease prepare a PI and PO.\n"
                  "Product: M10 P-Type PERC Solar Cell\nQuantity: 250,000 pcs\n"
                  "Unit Price: USD 0.185/pc\nTotal: USD 46,250\n"
                  "Payment Terms:\nDeposit: 40%\nBalance: 60%\n"
                  "Delivery: CIF Shanghai\nLead Time: 15 days after deposit.")
    first_result = analyze(*first_mail)
    first_payment = first_result["results"][1]
    first_correct = (
        first_payment.status == "ok"
        and "선금/계약금: 40%" in first_payment.details
        and "잔금: 60%" in first_payment.details
        and not any("상충" in d for d in first_payment.details)
        and extract_trade(*first_mail)["calculated_total"] == "46,250"
    )
    inline = payment_agent("", "Deposit: 40% Balance: 60%")
    inline_correct = ("선금/계약금: 40%" in inline
                      and "잔금: 60%" in inline
                      and not any("상충" in d for d in inline))
    before = payment_agent("", "40% deposit and 60% balance")
    before_correct = ("선금/계약금: 40%" in before
                      and "잔금: 60%" in before
                      and not any("상충" in d for d in before))

    multi_complete_text = (
        "Product: M10 PERC Solar Cell\nQuantity: 500,000 pcs\n"
        "Unit Price: USD 0.18/pc\n\n"
        "Product: M6 Solar Cell\nQuantity: 300,000 pcs\n"
        "Unit Price: USD 0.12/pc\n\n"
        "Payment Terms:\n30% deposit and 70% balance.\nDelivery: CIF Shanghai"
    )
    multi_complete = extract_trade("Request for PI and PO – Multiple Solar Products",
                                   multi_complete_text)
    multi_correct = (
        len(multi_complete["items"]) == 2
        and multi_complete["items"][0]["line_total"] == "90,000"
        and multi_complete["items"][1]["line_total"] == "36,000"
        and multi_complete["calculated_total"] == "126,000"
        and not multi_complete["warnings"]
    )
    multi_bad_total = extract_trade(
        "Request for PI", multi_complete_text + "\nTotal: USD 125,000"
    )
    multi_total_warning = any(
        "총액 불일치" in warning for warning in multi_bad_total["warnings"])
    multi_incomplete = extract_trade(
        "Please prepare PI",
        "Product: Cell A\nQuantity: 100 pcs\nUnit Price: USD 0.2/pc\n"
        "Product: Cell B\nQuantity: 200 pcs"
    )
    multi_incomplete_flag = (
        multi_incomplete["calculated_total"] is None and
        any("미기재" in warning for warning in multi_incomplete["warnings"])
    )
    mixed_currency = extract_trade(
        "Please prepare PI",
        "Product: Cell A\nQuantity: 100 pcs\nUnit Price: USD 0.2/pc\n"
        "Product: Cell B\nQuantity: 200 pcs\nUnit Price: EUR 0.3/pc"
    )
    mixed_currency_flag = (
        mixed_currency["calculated_total"] is None and
        any("통화가 서로 다름" in warning for warning in mixed_currency["warnings"])
    )
    unit_mismatch = extract_trade(
        "Please prepare PI",
        "Product: Cell A\nQuantity: 100 kg\nUnit Price: USD 0.2/pc"
    )
    unit_mismatch_flag = (
        unit_mismatch["calculated_total"] is None and
        any("단위 불일치" in warning for warning in unit_mismatch["warnings"])
    )

    return (
        ("선금 30% / 잔금 70% · PI/PO 분류 · 총액 계산", accurate),
        ("명시된 총액과 계산 총액 불일치 탐지", mismatch_found),
        ("선금과 잔금의 합계 100% 미달 탐지", bad_payment_found),
        ("복수 품목의 잘못된 총액 계산 방지", multi_flagged),
        ("실제 메일 형식 선금 40% / 잔금 60% / 총액 정확성", first_correct),
        ("동일 행 Deposit: 40% Balance: 60% 구별", inline_correct),
        ("역순 표기 40% deposit and 60% balance 인식", before_correct),
        ("복수 품목 M10/M6 개별 금액 및 총액 USD 126,000", multi_correct),
        ("복수 품목의 입력 총액 불일치 탐지", multi_total_warning),
        ("복수 품목의 단가 누락 시 합계 계산 중단", multi_incomplete_flag),
        ("서로 다른 통화의 품목 합계 계산 중단", mixed_currency_flag),
        ("수량 단위와 단가 기준 단위 불일치 차단", unit_mismatch_flag),
    )
