"""Trade tasks are placeholders until existing user-approved workflow is wired."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class TradeTask:
    kind: str
    status: str = "needs_input"
    approved_revision: str | None = None

def prepare_trade_task(kind: str) -> TradeTask:
    if kind not in {"PO", "PI", "CI", "PL"}:
        raise ValueError("Unrecognized trade document")
    return TradeTask(kind=kind)
