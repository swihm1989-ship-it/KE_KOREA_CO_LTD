"""Render saved sales scope rows as an actual two-column document table.

The source sentences remain editable and their approval metadata is unchanged.
Legacy 'Proposed (not agreed)' prefixes are removed from the presentation,
while suggested/missing status remains in the stored source metadata.
Never insert review-state notices into contractual PDF/DOCX body text.
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
    """Return contract prose and trade-spec rows, never workflow status notices.

    The status of proposed trade terms remains in stored term/sentence metadata.
    Review warnings belong in the application review UI, not the legal document.
    """
    items, rows = [], []

    def flush():
        if rows:
            items.append(("table", rows.copy()))
            rows.clear()

    for sentence in sentences:
        text = str(sentence.get("text") or "")
        field = sentence.get("sale_spec_field")
        # Only explicitly marked rows are a table; preserve edited free text.
        if field and ":" in text:
            label, _ = text.split(":", 1)
            if label.strip():
                cleaned = sales_scope_display_text(sentence, text).split(":", 1)[1].strip()
                rows.append((label.strip(), cleaned))
                continue
        flush()
        items.append(("paragraph", text))
    flush()
    return items
