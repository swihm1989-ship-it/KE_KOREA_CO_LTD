"""Revision-safe contract patch application and restoration."""
from copy import deepcopy
from uuid import uuid4

from Quotation_KEKOREA.contracts.models import validate_snapshot


class RevisionConflict(ValueError):
    pass


def find_sentence(snapshot, sentence_id):
    for clause in snapshot.get("clauses", []):
        for sentence in clause.get("sentences", []):
            if sentence.get("id") == sentence_id:
                return sentence
    raise RevisionConflict("The selected sentence no longer exists.")


def propose_sentence_deletion(snapshot, sentence_id):
    """Offer removal as an ordinary revision proposal, without any AI/API call.

    This does not save anything. The existing comparison/approval flow must
    validate against the current revision before committing the deletion.
    """
    snapshot = validate_snapshot(snapshot)
    sentence = find_sentence(snapshot, sentence_id)
    if sentence_id in {f'commission_payment_sentence_{i}' for i in range(3)}:
        raise ValueError("기본 커미션 지급 조항은 BOX 2 지급조건 편집기에서 관리해 주세요.")
    change_id = f"change_{uuid4().hex}"
    proposal = {
        "id": f"proposal_{uuid4().hex}",
        "contract_id": snapshot["contract_id"],
        "base_revision": snapshot["revision"],
        "target_sentence_id": sentence_id,
        "instruction": "사용자가 문장 삭제 요청",
        "changes": [{
            "id": change_id, "sentence_id": sentence_id,
            "original_text": sentence["text"], "proposed_text": "",
            "delete_sentence": True, "term_key": None,
            "required_to_resolve_conflict": False,
            "reason": "사용자가 선택한 문장 삭제. 이 조항이 마지막 문장이면 조항 제목도 함께 삭제됩니다.",
        }],
        "issues": [],
        "explanation": (
            "선택한 문장을 삭제할 후보입니다. 수정 전후 및 전체 계약서 "
            "미리보기를 확인한 뒤 승인하면 새 Revision에 반영됩니다. "
            "기존 Revision은 유지됩니다."
        ),
    }
    # Fail closed early on missing/stale IDs, but never mutate the source.
    apply_proposal(snapshot, proposal, [change_id])
    return proposal


def apply_proposal(snapshot, proposal, selected_change_ids):
    if proposal.get("base_revision") != snapshot.get("revision"):
        raise RevisionConflict("This proposal is out of date. Review it against the latest revision.")
    selected = set(selected_change_ids)
    changes = {change.get("id"): change for change in proposal.get("changes", [])}
    if not selected or not selected.issubset(changes):
        raise ValueError("Select at least one valid proposed change.")
    if any(change.get("required_to_resolve_conflict") and change_id not in selected
           for change_id, change in changes.items()):
        raise RevisionConflict("Required related changes must be applied together.")
    for change_id in selected:
        change = changes[change_id]
        if change.get("term_key"):
            continue
        sentence = find_sentence(snapshot, change.get("sentence_id"))
        if sentence.get("text") != change.get("original_text"):
            raise RevisionConflict("A sentence changed after the proposal was created.")
    result = deepcopy(snapshot)
    for change_id in selected:
        change = changes[change_id]
        if change.get("term_key"):
            if change["term_key"].startswith("party."):
                _, role, field = change["term_key"].split(".", 2)
                party = next((item for item in result.get("parties", [])
                              if role in item.get("roles", [])), None)
                if field == "_remove":
                    if party is not None:
                        party["roles"] = [value for value in party.get("roles", [])
                                          if value != role]
                        if not party["roles"]:
                            result["parties"].remove(party)
                    continue
                if party is None:
                    party = {"id": f"party_{uuid4().hex}", "legal_name": None,
                             "country": None, "address": None, "representative": None,
                             "roles": [role]}
                    result.setdefault("parties", []).append(party)
                party[field] = change.get("term_value", {}).get("value", change.get("proposed_text"))
                continue
            if change["term_key"].startswith("omission."):
                key = change["term_key"].split(".", 1)[1]
                reason = change.get("term_value", {}).get("value")
                if reason:
                    result.setdefault("omissions", {})[key] = {
                        "reason": reason, "confirmed": True,
                    }
                else:
                    result.setdefault("omissions", {}).pop(key, None)
                continue
            terms = {term.get("key"): term for term in result.get("terms", [])}
            term = terms.get(change["term_key"])
            if term is None:
                term = {"id": f"term_{uuid4().hex}", "key": change["term_key"],
                        "status": "confirmed", "source_refs": []}
                result.setdefault("terms", []).append(term)
            term.update(deepcopy(change.get("term_value") or {}))
            term["key"] = change["term_key"]
            term["value"] = change.get("term_value", {}).get("value", change.get("proposed_text"))
            term["status"] = change.get("term_value", {}).get("status", "confirmed")
            for source_ref in term.get("source_refs") or []:
                document_id = source_ref.get("document_id") if isinstance(source_ref, dict) else None
                if document_id and document_id not in result.setdefault("reference_ids", []):
                    result["reference_ids"].append(document_id)
        elif change.get("sentence_id"):
            if change.get("delete_sentence"):
                for clause in list(result.get("clauses", [])):
                    clause["sentences"] = [sentence for sentence in clause.get("sentences", [])
                                           if sentence.get("id") != change["sentence_id"]]
                    if not clause["sentences"]:
                        result["clauses"].remove(clause)
            else:
                find_sentence(result, change["sentence_id"])["text"] = change["proposed_text"]
    result["revision"] = int(snapshot.get("revision", 0)) + 1
    return validate_snapshot(result)


def restore_revision(current_snapshot, historical_snapshot):
    restored = deepcopy(historical_snapshot)
    restored["contract_id"] = current_snapshot["contract_id"]
    restored["revision"] = int(current_snapshot.get("revision", 0)) + 1
    return validate_snapshot(restored)


def preserve_sentence_ids(old_snapshot, new_clauses):
    old = {sentence.get("text"): sentence.get("id")
           for clause in old_snapshot.get("clauses", [])
           for sentence in clause.get("sentences", [])}
    for clause in new_clauses:
        for sentence in clause.get("sentences", []):
            sentence["id"] = old.get(sentence.get("text"), sentence.get("id") or f"sentence_{uuid4().hex}")
    return new_clauses
