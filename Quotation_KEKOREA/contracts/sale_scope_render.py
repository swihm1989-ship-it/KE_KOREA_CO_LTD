"""Render saved sales scope rows as an actual two-column document table.

The source sentences remain editable and their approval metadata is unchanged.
Legacy 'Proposed (not agreed)' prefixes are presentation-only: a single review
notice replaces repeated prefixes without treating suggestions as confirmed.
"""
from __future__ import annotations

import re

_PROPOSAL_PREFIX = re.compile(r"(?:Proposed \(not agreed\):\s*|제안\(미확정\):\s*)", re.I)


def sales_scope_display_text(sentence, text=None):
    """Hide legacy candidate prefixes in sales-spec display, never edit the snapshot.

    Only marked sale-spec rows are affected. The original term status, sentence
    text, revision history and final-export validation stay untouched.
    """
    original = str(sentence.get("text") or "") if text is None else str(text)
    if not sentence.get("sale_spec_field") or ":" not in original:
        return original
    label, value = original.split(":", 1)
    if not label.strip():
        return original
    return label + ": " + _PROPOSAL_PREFIX.sub("", value).strip()


def scope_display_items(sentences, language):
    """Return ordered ('paragraph', text) or ('table', [(label, value)]) items."""
    items, rows, pending = [], [], []

    def flush():
        if rows:
            items.append(("table", rows.copy()))
            rows.clear()
            if pending:
                notice = ("확인 필요 (미승인 조건): " if language == "ko"
                          else "Pending confirmation (not yet approved): ")
                items.append(("paragraph", notice + ", ".join(dict.fromkeys(pending))))
                pending.clear()

    for sentence in sentences:
        text = str(sentence.get("text") or "")
        field = sentence.get("sale_spec_field")
        # Only explicitly marked rows are a table; preserve edited free text.
        if field and ":" in text:
            label, value = text.split(":", 1)
            if label.strip():
                was_proposed = bool(_PROPOSAL_PREFIX.search(value))
                cleaned = sales_scope_display_text(sentence, text).split(":", 1)[1].strip()
                rows.append((label.strip(), cleaned))
                status = sentence.get("sale_spec_status")
                if cleaned and (status in ("suggested", "missing") or was_proposed):
                    pending.append(label.strip())
                continue
        flush()
        items.append(("paragraph", text))
    flush()
    return items
