"""Deterministic guardrails for the draft-first contract chat."""
import re


def wants_contract_draft(text):
    """Explicit user request to prepare a draft; never infer from prior messages."""
    text = str(text or '').strip()
    if re.search(r'(초안|계약서).{0,50}(작성|만들|생성|보여|써\s*줘|써\s*주세요)', text):
        return True
    if re.search(r'(작성|만들|생성).{0,30}(초안|계약서)', text):
        return True
    return bool(re.search(r'\b(draft|generate|create|write)\b.{0,60}\b(contract|agreement|draft)\b',
                          text, flags=re.IGNORECASE) or
                re.search(r'\b(contract|agreement)\b.{0,60}\b(draft|generate|create|write)\b',
                          text, flags=re.IGNORECASE))


def should_generate_draft(prompt, messages, *, has_clauses=False):
    """Draft on explicit request or after the first follow-up response."""
    return not has_clauses and (wants_contract_draft(prompt) or
                                sum(m.get('role') == 'user' for m in messages) >= 2)


def select_new_questions(questions, messages, *, limit=2):
    """No recurring interrogation: one round, max two focused questions.

    This affects conversational questions only; safety issues remain available
    in the review panel and required checks for final export remain unchanged.
    """
    if limit <= 0 or sum(m.get('role') == 'user' for m in messages) >= 2:
        return []
    previous = re.sub(r'[^0-9a-z가-힣]+', '', '\n'.join(
        str(m.get('content') or '') for m in messages
        if m.get('role') == 'assistant').casefold())
    selected = []
    fingerprints = set()
    for raw in questions or []:
        question = str(raw or '').strip()
        normalized = re.sub(r'[^0-9a-z가-힣]+', '', question.casefold())
        if not normalized or normalized in previous or normalized in fingerprints:
            continue
        fingerprints.add(normalized)
        selected.append(question)
        if len(selected) >= max(0, limit):
            break
    return selected
