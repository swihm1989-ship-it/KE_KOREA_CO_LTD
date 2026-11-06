"""Validated, JSON-serializable contract workflow objects."""
from copy import deepcopy
from uuid import uuid4


CONTRACT_TYPES = {"sale", "trade_commission", "investment_commission"}
LANGUAGES = {"ko", "en"}
TERM_STATUSES = {"confirmed", "suggested", "missing"}


def new_id(prefix):
    return f"{prefix}_{uuid4().hex}"


def new_snapshot(contract_id, contract_type, language):
    if contract_type not in CONTRACT_TYPES:
        raise ValueError("Choose a supported contract type")
    if language not in LANGUAGES:
        raise ValueError("Choose Korean or English")
    return {
        "contract_id": str(contract_id),
        "revision": 1,
        "contract_type": contract_type,
        "language": language,
        "parties": [],
        "terms": [],
        "clauses": [],
        "issues": [],
        "reference_ids": [],
        "omissions": {},
        "schema_version": 1,
    }


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("Contract snapshot must be an object")
    result = deepcopy(snapshot)
    if result.get("contract_type") not in CONTRACT_TYPES:
        raise ValueError("Unsupported contract type")
    if result.get("language") not in LANGUAGES:
        raise ValueError("Unsupported contract language")
    if not str(result.get("contract_id") or "").strip():
        raise ValueError("Contract ID is required")
    try:
        if int(result.get("revision", 0)) < 1:
            raise ValueError("Contract revision must be positive")
    except (TypeError, ValueError):
        raise ValueError("Contract revision must be a positive integer") from None
    if not isinstance(result.get("parties"), list) or not isinstance(result.get("terms"), list):
        raise ValueError("Contract parties and terms must be lists")
    if not isinstance(result.get("clauses"), list):
        raise ValueError("Contract clauses must be a list")
    sentence_ids = set()
    for clause_index, clause in enumerate(result["clauses"]):
        if not isinstance(clause, dict) or not isinstance(clause.get("sentences"), list):
            raise ValueError("Each clause must contain a sentence list")
        clause.setdefault("id", new_id("clause"))
        clause.setdefault("order", clause_index + 1)
        for sentence in clause["sentences"]:
            if not isinstance(sentence, dict) or not str(sentence.get("text") or "").strip():
                raise ValueError("Contract sentences must have non-empty text")
            sentence.setdefault("id", new_id("sentence"))
            if sentence["id"] in sentence_ids:
                raise ValueError("Sentence IDs must be unique")
            sentence_ids.add(sentence["id"])
            sentence.setdefault("term_ids", [])
            sentence.setdefault("source_refs", [])
    term_keys = set()
    for term in result["terms"]:
        if not isinstance(term, dict) or not term.get("key"):
            raise ValueError("Each term must have a key")
        if term["key"] in term_keys:
            raise ValueError("Contract term keys must be unique")
        term_keys.add(term["key"])
        term.setdefault("id", new_id("term"))
        if term.get("status", "missing") not in TERM_STATUSES:
            raise ValueError("Unsupported term status")
        term.setdefault("status", "missing")
        term.setdefault("source_refs", [])
    for party in result["parties"]:
        if not isinstance(party, dict) or not isinstance(party.get("roles", []), list):
            raise ValueError("Each party must have a list of roles")
        if any(not isinstance(role, str) or not role for role in party.get("roles", [])):
            raise ValueError("Party roles must be non-empty strings")
    result.setdefault("issues", [])
    result.setdefault("reference_ids", [])
    result.setdefault("omissions", {})
    result.setdefault("schema_version", 1)
    return result
