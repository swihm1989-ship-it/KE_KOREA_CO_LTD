"""Strictly read-only facade for the existing private contract repository.

The only repository API calls permitted here are list_contracts and
load_contract; this cannot create, update, delete or export any contract.
Requires authenticated UI before invocation.
"""
from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any


def make_reader(env: Mapping[str, str]):
    """Instantiate the existing private repository with SERVER-only credentials."""
    from Quotation_KEKOREA.contracts.repository import ContractRepository
    return ContractRepository(env)


def read_contract_list(repo, *, keyword: str = "", language: str = "") -> list[dict[str, Any]]:
    records = repo.list_contracts()
    if not isinstance(records, list):
        raise ValueError("Contract database returned an unexpected list format")
    query = str(keyword or "").strip().casefold()
    language = str(language or "").strip().lower()
    results = []
    for row in records:
        if not isinstance(row, dict):
            continue
        if language and str(row.get("language") or "").lower() != language:
            continue
        visible = " ".join(str(row.get(field) or "") for field in (
            "title", "contract_type", "status", "id",
        )).casefold()
        if query and query not in visible:
            continue
        results.append({field: row.get(field) for field in (
            "id", "title", "contract_type", "language", "status",
            "current_revision", "updated_at",
        )})
    return results


def read_contract_versions(repo, contract_id: str) -> list[dict[str, Any]]:
    """ID must be present in CURRENT list; do not permit arbitrary record fetches."""
    known = {str(row.get("id")) for row in repo.list_contracts()
             if isinstance(row, dict) and row.get("id")}
    if not contract_id or contract_id not in known:
        raise ValueError("Selected contract is not in the authorized contract listing")
    revisions = repo.load_contract(contract_id)
    if not isinstance(revisions, list):
        raise ValueError("Unexpected contract revision format")
    result = []
    for row in revisions:
        if not isinstance(row, dict):
            continue
        snapshot = row.get("snapshot")
        if not isinstance(snapshot, dict):
            continue
        if str(snapshot.get("contract_id")) != str(contract_id):
            raise ValueError("Contract ID mismatch in revision record")
        result.append({
            "revision": row.get("revision"),
            "change_summary": row.get("change_summary"),
            "created_at": row.get("created_at"),
            "snapshot": deepcopy(snapshot),
        })
    return result


def inspect_contract_version(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Existing deterministic checks only; not an AI legal opinion."""
    from Quotation_KEKOREA.contracts.models import validate_snapshot as normalize
    from Quotation_KEKOREA.contracts.rules import validate_snapshot as check
    from Quotation_KEKOREA.contracts.review_summary import review_cards
    validated = normalize(deepcopy(dict(snapshot)))
    issues = check(validated, for_export=False, env={})
    return {
        "method": "existing_deterministic_rules",
        "issues": deepcopy(issues),
        "cards": review_cards(issues, language=validated.get("language", "ko")),
        "revision": validated["revision"],
    }
