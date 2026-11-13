"""Conservative classifier for untrusted email/manual text. No approvals."""
from __future__ import annotations
import re

DOC_TYPES = ("PI", "PO", "CI", "PL", "CONTRACT")
_PATTERNS = {
    "PI": (r"\bpro\s*forma\s*invoice(?![A-Za-z0-9_])", r"\bPI(?![A-Za-z0-9_])", r"견적송장", r"견적\s*인보이스", r"견적서", r"\bquotation(?![A-Za-z0-9_])", r"\bquote(?![A-Za-z0-9_])"),
    "PO": (r"\bpurchase\s*order(?![A-Za-z0-9_])", r"\bPO(?![A-Za-z0-9_])", r"발주서"),
    "CI": (r"\bcommercial\s*invoice(?![A-Za-z0-9_])", r"\bCI(?![A-Za-z0-9_])", r"상업송장", r"\bCI\s*[/&+ -]?\s*PL\b"),
    "PL": (r"\bpacking\s*list(?![A-Za-z0-9_])", r"\bPL(?![A-Za-z0-9_])", r"포장명세서", r"패킹리스트", r"\bCI\s*[/&+ -]?\s*PL\b"),
    "CONTRACT": (r"\bcontract(?![A-Za-z0-9_])", r"\bagreement(?![A-Za-z0-9_])", r"계약서", r"계약\s*초안",
                 r"\bM\s*\.?\s*O\s*\.?\s*U(?![A-Za-z0-9_])", r"\bmemorandum\s+of\s+understanding\b", r"양해\s*각서"),
}

def classify(subject: str, body: str, requested: list[str] | None = None) -> list[str]:
    """Mentions only identify tasks; never imply authorization to create or send."""
    if requested is not None:
        output = []
        for kind in requested:
            normalized = str(kind).strip().upper()
            if normalized == 'CIPL':
                for alias in ('CI','PL'):
                    if alias not in output: output.append(alias)
                continue
            if normalized not in DOC_TYPES:
                raise ValueError(f"Unsupported document kind: {kind!r}")
            if normalized not in output:
                output.append(normalized)
        return output
    text = f"{subject or ''}\n{body or ''}"
    return [kind for kind, expressions in _PATTERNS.items()
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in expressions)]
