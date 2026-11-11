"""Read-only preflight bridge into the EXISTING KE KOREA validation engines.

This module never stores, approves, exports, emails or mutates the caller's
input. "ready_for_user_confirmation" is NOT approval to issue or send.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ValidationReport:
    kind: str
    status: str
    blockers: tuple[str, ...]
    ready_for_user_confirmation: bool = False
    can_send: bool = False


def evaluate_trade_candidate(candidate: Mapping[str, Any]) -> ValidationReport:
    """Call the existing deterministic trade validator, without saving anything."""
    if not isinstance(candidate, Mapping):
        raise ValueError("Trade candidate must be an object")
    kind = str(candidate.get("document_type") or "").strip().upper()
    if kind not in {"PI", "PO", "CI", "PL"}:
        raise ValueError("Document type must be PI, PO, CI or PL")
    from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
    data = deepcopy(dict(candidate))
    data["document_type"] = kind
    # Do not trust caller-controlled ready/status; the source engine recomputes both.
    data.pop("ready_for_issue", None)
    data.pop("status", None)
    result = validate_and_calculate(data)
    blockers = tuple(str(item) for item in result.get("blocking_issues", ()) if str(item).strip())
    ready = bool(result.get("ready_for_issue")) and not blockers
    return ValidationReport(
        kind=kind,
        status="awaiting_document_approval" if ready else "needs_input",
        blockers=blockers,
        ready_for_user_confirmation=ready,
        can_send=False,
    )


def evaluate_contract_candidate(snapshot: Mapping[str, Any]) -> ValidationReport:
    """Validate structure and required terms via the existing contract rules.

    No drafting, revision update, export/FINAL calculation, or approval occurs.
    """
    if not isinstance(snapshot, Mapping):
        raise ValueError("Contract snapshot must be an object")
    from Quotation_KEKOREA.contracts.models import validate_snapshot as validate_model
    from Quotation_KEKOREA.contracts.rules import validate_snapshot as validate_rules
    validated = validate_model(deepcopy(dict(snapshot)))
    issues = validate_rules(validated, for_export=True, env={})
    blockers = tuple(
        str(issue.get("message", issue.get("code", "Approval required")))
        if isinstance(issue, dict) else str(issue)
        for issue in issues
    )
    if not validated.get("clauses"):
        blockers += ("계약서 조항 초안이 아직 없습니다.",)
    ready = not blockers
    return ValidationReport(
        kind="CONTRACT",
        status="awaiting_document_approval" if ready else "needs_input",
        blockers=blockers,
        ready_for_user_confirmation=ready,
        can_send=False,
    )
