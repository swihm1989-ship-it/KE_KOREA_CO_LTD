"""Non-destructive preview recovery for duplicate keys in old contract revisions.

Never rewrite the Supabase revision during loading. A human explicitly approves
the preview in the UI before a *new* revision can be committed.
"""
from copy import deepcopy

from Quotation_KEKOREA.contracts.models import validate_snapshot
from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys


def has_legacy_duplicate_term_keys(snapshot):
    """Detect literal and multilingual alias collisions without modifying data."""
    seen = set()
    for term in snapshot.get("terms", []):
        if not isinstance(term, dict) or not term.get("key"):
            continue
        normalized, _ = normalize_term_keys({"terms": [term]})
        key = normalized["terms"][0]["key"]
        if key in seen:
            return True
        seen.add(key)
    return False


def prepare_duplicate_term_recovery(snapshot):
    """Return a validated, UNSAVED candidate plus original duplicate details.

    Keep one representative per normalized key. Prefer a confirmed item over an
    unconfirmed one, but never conceal differing values: every removed duplicate
    is retained in the review metadata, including original IDs and source refs.
    """
    candidate = deepcopy(snapshot)
    groups = {}
    ordered_keys = []
    for term in candidate.get("terms", []):
        if not isinstance(term, dict) or not term.get("key"):
            raise ValueError("Saved contract has a malformed term; manual recovery required.")
        normalized, _ = normalize_term_keys({"terms": [term]})
        if not normalized["terms"]:
            raise ValueError("Saved contract has an unrecognized empty term.")
        item = deepcopy(term)
        key = normalized["terms"][0]["key"]
        if key not in groups:
            ordered_keys.append(key)
            groups[key] = []
        groups[key].append(item)

    recovered = []
    collisions = []
    replaced_ids = {}
    for key in ordered_keys:
        items = groups[key]
        winner = next((item for item in items if item.get("status") == "confirmed"), items[0])
        # Do not change an existing confirmed value or source evidence.
        selected = deepcopy(winner)
        selected["key"] = key
        recovered.append(selected)
        if len(items) > 1:
            collisions.append({
                "key": key,
                "selected_id": selected.get("id"),
                "candidates": deepcopy(items),
            })
            for item in items:
                if item is not winner and item.get("id") and selected.get("id"):
                    replaced_ids[item["id"]] = selected["id"]

    if not collisions:
        # Distinguish a genuine duplicate from an unrelated invalid snapshot.
        return validate_snapshot(candidate), []
    candidate["terms"] = recovered
    for clause in candidate.get("clauses", []):
        for sentence in clause.get("sentences", []):
            ids = sentence.get("term_ids") or []
            sentence["term_ids"] = list(dict.fromkeys(
                replaced_ids.get(term_id, term_id) for term_id in ids
            ))
    candidate["_term_recovery_pending"] = collisions
    # A review issue remains in the new revision after the user accepts the
    # mapping; accepting it is not confirming commercial facts.
    candidate.setdefault("issues", []).append({
        "code": "legacy_duplicate_term_review",
        "severity": "confirm",
        "message": "과거 계약조건의 중복 항목을 정리했습니다. 원문 수량·단가·단위 및 충돌값을 확인해 주세요.",
        "confirmed": False,
    })
    validate_snapshot(candidate)
    return candidate, collisions
