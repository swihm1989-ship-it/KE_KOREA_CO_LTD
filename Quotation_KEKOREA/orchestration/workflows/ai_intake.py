"""Opt-in AI term extraction and non-final draft candidates for MASTER GRAPH.

Uses the EXISTING contract analysis service (source-verification included).
Old contract clauses are never copied to new drafts or transmitted to AI.
No writing to repository, no automatic approval, finalization, or SMTP.
"""
from __future__ import annotations

AI_WORKFLOW_REVISION = "trade-missing-terms-20261113-v2"
from Quotation_KEKOREA.observability.core import traced
from copy import deepcopy
from typing import Any, Mapping
from uuid import uuid4
from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_analysis_values

from Quotation_KEKOREA.orchestration.router import DOC_TYPES
from Quotation_KEKOREA.orchestration.workflows.label_typos import canonical_label
from Quotation_KEKOREA.orchestration.workflows.label_typos import normalize_trade_labels

_TERM_KEYS = {"products", "quantity", "unit", "unit_price", "currency", "delivery",
              "payment_trigger", "payment_deadline", "inspection_claims", "scope",
              "contract_date", "governing_law", "dispute_resolution"}
_FAMILIES = {"polysilicon", "wafer", "solar_cell", "solar_module", "cosmetics"}


@traced('contract.analyze')
def extract_candidate(instruction: str, env: Mapping[str, str], *, consent: bool) -> dict[str, Any]:
    """Send only the user-typed instruction; explicit consent is mandatory.

    In particular, do not transfer any stored contracts or saved proprietary clauses.
    """
    if not consent:
        raise PermissionError("Explicit AI processing consent is required")
    if not str(instruction or "").strip():
        raise ValueError("거래조건을 입력해 주세요.")
    if len(instruction) > 12000:
        raise ValueError("입력 길이가 너무 깁니다 (최대 12,000자).")
    api_key = str(env.get("OPENAI_API_KEY") or "")
    model = str(env.get("CONTRACT_OPENAI_MODEL") or env.get("OPENAI_MODEL") or "")
    if not api_key or not model:
        raise ValueError("MASTER GRAPH의 OPENAI_API_KEY 및 OPENAI_MODEL 서버 설정이 필요합니다.")
    from Quotation_KEKOREA.contracts.service import analyze_trade
    from Quotation_KEKOREA.contracts.models import new_snapshot
    snapshot = new_snapshot("temp-ai-intake", "sale", "ko")
    analysis = analyze_trade(
        [{"role": "user", "content": normalize_trade_labels(instruction)}], snapshot, [], env=dict(env),
    )
    return deepcopy(analysis)


def _validated_analysis(analysis: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(analysis, Mapping):
        raise ValueError("추출 결과는 JSON 객체여야 합니다.")
    if analysis.get("contract_type") not in {"sale", "trade_commission", "investment_commission"}:
        raise ValueError("지원하지 않는 계약 유형입니다.")
    parties, terms = analysis.get("parties"), analysis.get("terms")
    if not isinstance(parties, list) or not isinstance(terms, list):
        raise ValueError("당사자/거래조건 목록이 유효하지 않습니다.")
    for party in parties:
        if not isinstance(party, dict) or not isinstance(party.get("roles"), list):
            raise ValueError("당사자 형식이 유효하지 않습니다.")
        party["roles"] = [canonical_label(str(role)) or str(role).strip().casefold() for role in party["roles"]]
        party["roles"] = [role for role in party["roles"] if role in {"buyer", "seller", "agent", "introducer", "payer", "payee"}]
        for field in ("legal_name", "address", "country"):
            if party.get(field) is None:
                party[field] = ""
        # NEVER treat model-produced party data as user-confirmed.
        if party.get("status") == "confirmed":
            raise ValueError("AI가 당사자 확정 상태를 임의로 지정했습니다.")
    for term in terms:
        if (not isinstance(term, dict) or not isinstance(term.get("key"), str)
                or term.get("status", "suggested") not in ("suggested", "missing")):
            raise ValueError("AI가 거래조건을 확정했거나 조건 형식이 유효하지 않습니다.")
    return deepcopy(dict(analysis))


def make_contract_candidate(analysis: Mapping[str, Any], language: str,
                            *, reference: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """New unsigned snapshot; stored contract is context for a human only.

    No previous contract terms/parties/clauses are copied to current agreement.
    """
    from Quotation_KEKOREA.contracts.models import new_snapshot, validate_snapshot
    data = normalize_analysis_values(_validated_analysis(analysis))
    if language not in {"ko", "en"}:
        raise ValueError("계약서 언어는 한국어 또는 영어여야 합니다.")
    snap = new_snapshot("orchestration-" + uuid4().hex, data["contract_type"], language)
    snap["parties"] = []
    for party in data["parties"]:
        p = {k: deepcopy(v) for k, v in party.items() if k in (
            "legal_name", "country", "address", "representative", "roles", "source_refs"
        )}
        p["status"] = "suggested"
        snap["parties"].append(p)
    snap["terms"] = []
    for term in data["terms"]:
        t = {k: deepcopy(v) for k, v in term.items() if k in (
            "key", "value", "unit", "currency", "source_refs"
        )}
        # The upstream service explicitly emits missing terms. Keep absent
        # values unresolved; a supplied value is only a suggestion, matching
        # mail intake's treatment of nonempty terms marked missing.
        value = term.get("value")
        absent = value is None or (isinstance(value, str) and not value.strip())
        t["status"] = "missing" if term.get("status") == "missing" and absent else "suggested"
        snap["terms"].append(t)
    snap["issues"] = deepcopy(data.get("issues", []))
    return validate_snapshot(snap)


def make_trade_candidate(kind: str, analysis: Mapping[str, Any],
                         *, product_family: str = "solar_cell") -> dict[str, Any]:
    """Conservative prefill; all exact commercial data needs user's confirmation."""
    data = normalize_analysis_values(_validated_analysis(analysis))
    kind = str(kind or "").upper()
    if kind not in DOC_TYPES or kind == "CONTRACT":
        raise ValueError("무역 문서 유형은 PI/PO/CI/PL 중 하나여야 합니다.")
    if product_family not in _FAMILIES:
        raise ValueError("상품군을 확인해 주세요.")
    terms = {term["key"]: str(term.get("value") if term.get("value") is not None else "")
             for term in data["terms"] if term.get("key") in _TERM_KEYS}
    parties = {}
    for role in ("seller", "buyer"):
        p = next((p for p in data["parties"] if role in p.get("roles", ())), {})
        parties[role] = {
            "legal_name": str(p.get("legal_name") or ""),
            "address": str(p.get("address") or ""),
            "contact": str(p.get("contact") or p.get("representative") or ""),
            "phone": str(p.get("phone") or ""),
            "email": str(p.get("email") or ""),
        }
    # Do not invent a document number, address, origin, price source, or payment terms.
    result = {
        "document_type": kind,
        "product_family": product_family,
        "document_number": "DRAFT",
        "currency": terms.get("currency", ""),
        "seller": parties["seller"], "buyer": parties["buyer"],
        "incoterms": terms.get("delivery", ""),
        "payment_terms": terms.get("payment_trigger", ""),
        "items": [{
            "product_name": terms.get("products", ""),
            "quantity": terms.get("quantity", ""),
            "unit": terms.get("unit", ""),
            "unit_price": terms.get("unit_price", ""),
            "price_basis": terms.get("unit", ""),
            "price_source": "",  # optional metadata; extraction is not verified provenance
        }],
    }
    return result


def selected_contract_reference(repo, contract_id: str, revision: int) -> dict[str, Any]:
    """Fetch one explicitly selected existing revision for on-screen human viewing."""
    from Quotation_KEKOREA.orchestration.adapters.contract_library import read_contract_versions
    for entry in read_contract_versions(repo, contract_id):
        if entry["revision"] == revision:
            return deepcopy(entry["snapshot"])
    raise ValueError("선택한 계약서 리비전을 찾지 못했습니다.")


@traced('contract.generate')
def generate_contract_draft(snapshot: Mapping[str, Any], env: Mapping[str, str],
                            *, consent: bool, use_library: bool = False) -> dict[str, Any]:
    """Call the existing reviewed drafting graph on a NEW in-memory candidate.

    No saved private contract content is passed. When explicitly opted in,
    only approved anonymized library guidance is retrieved for drafting.
    Results still require manual review and separate approval.
    """
    if not consent:
        raise PermissionError("명시적인 AI 계약서 생성 동의가 필요합니다.")
    if not env.get("OPENAI_API_KEY") or not (
        env.get("CONTRACT_OPENAI_MODEL") or env.get("OPENAI_MODEL")
    ):
        raise ValueError("AI 문서 생성 API 설정이 없습니다.")
    from Quotation_KEKOREA.contracts.models import validate_snapshot
    from Quotation_KEKOREA.contracts.ai_graph import generate_contract_draft_graph
    candidate = validate_snapshot(deepcopy(dict(snapshot)))
    if not str(candidate["contract_id"]).startswith("orchestration-"):
        raise ValueError("기존 계약서를 자동 재작성할 수 없습니다. 새 초안만 지원합니다.")
    if candidate["clauses"]:
        raise ValueError("이미 작성된 계약 조항은 기존 수정·검토 절차를 사용하세요.")
    repo = None
    if use_library:
        from Quotation_KEKOREA.contracts.repository import ContractRepository
        repo = ContractRepository(env)
    generated = generate_contract_draft_graph(
        candidate, [], env=dict(env), reference_context=[],
        transaction_messages=[], repo=repo, use_library=bool(use_library),
    )
    reviewed = validate_snapshot(generated)
    if not reviewed["clauses"]:
        raise ValueError("AI 계약 초안에 실제 조항이 없습니다.")
    return reviewed
