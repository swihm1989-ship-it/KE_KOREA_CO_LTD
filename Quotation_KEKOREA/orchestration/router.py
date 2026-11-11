"""Conservative classifier for untrusted email/manual text. No approvals."""
from __future__ import annotations
import re

DOC_TYPES = ("PI", "PO", "CI", "PL", "CONTRACT")
_PATTERNS = {
    "PI": (r"\bpro\s*forma\s*invoice\b", r"\bPI\b", r"견적송장", r"견적\s*인보이스"),
    "PO": (r"\bpurchase\s*order\b", r"\bPO\b", r"발주서"),
    "CI": (r"\bcommercial\s*invoice\b", r"\bCI\b", r"상업송장"),
    "PL": (r"\bpacking\s*list\b", r"\bPL\b", r"포장명세서", r"패킹리스트"),
    "CONTRACT": (r"\bcontract\b", r"\bagreement\b", r"계약서", r"계약\s*초안"),
}

def classify(subject: str, body: str, requested: list[str] | None = None) -> list[str]:
    """Mentions only identify tasks; never imply authorization to create or send."""
    if requested is not None:
        output = []
        for kind in requested:
            normalized = str(kind).strip().upper()
            if normalized not in DOC_TYPES:
                raise ValueError(f"Unsupported document kind: {kind!r}")
            if normalized not in output:
                output.append(normalized)
        return output
    text = f"{subject or ''}\n{body or ''}"
    return [kind for kind, expressions in _PATTERNS.items()
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in expressions)]
