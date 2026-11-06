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
