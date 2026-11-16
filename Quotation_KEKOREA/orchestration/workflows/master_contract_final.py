"""Master bridge to the ORIGINAL KE KOREA contract FINAL PDF/DOCX renderer.

Only explicit, authenticated, revision-bound approvals can reach this bridge.
No private contract samples, mail or attachments are transferred to an AI API.
The original contract layout, signature and seal verifiers are reused as-is.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping

from Quotation_KEKOREA.contracts.final_policy import final_document_blockers
from Quotation_KEKOREA.contracts.models import validate_snapshot


def contract_fingerprint(snapshot: Mapping[str, Any]) -> str:
    """Fingerprint EXACT current words and status; approvals expire on edits."""
    if not isinstance(snapshot, Mapping):
        raise ValueError("계약서 데이터가 유효하지 않습니다.")
    source = json.dumps(dict(snapshot), ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), default=str).encode("utf-8")
    return sha256(source).hexdigest()


def contract_final_blockers(snapshot: Mapping[str, Any], env: Mapping[str, str],
                            *, allow_unresolved_text: bool = False) -> list[str]:
    """Exactly the original KE KOREA FINAL content policy, not a second gate.

    The legacy contract workspace shows AI findings as advice; it does NOT
    require confirming every AI-proposed term and party separately to export.
    MASTER must use the same author-controlled text, unresolved-text opt-in,
    explicit version approval and seal authorization. The extra provenance
    guard below prevents a saved third-party contract from being reissued as
    a new MASTER contract.
    """
    try:
        checked = validate_snapshot(deepcopy(dict(snapshot)))
        policy = final_document_blockers(
            checked, allow_unresolved_text=allow_unresolved_text)
    except (TypeError, ValueError, KeyError, AttributeError):
        return ["계약서 구조가 유효하지 않습니다. 기존 계약서 검토 화면에서 다시 확인하세요."]
    blockers = list(policy)
    if not str(checked.get("contract_id") or "").startswith("orchestration-"):
        blockers.append("Master에서 생성한 신규 계약서 초안만 처리합니다.")
    return list(dict.fromkeys(blockers))

def render_original_final(snapshot: Mapping[str, Any], env: Mapping[str, str], *,
                          principal: str, approved: bool, authorized: bool,
                          expected_fingerprint: str,
                          allow_unresolved_text: bool = False) -> dict[str, dict[str, Any]]:
    """Use the SAME original contracts.exports.export_contract as the legacy app.

    Validation and revision-bound explicit approval are checked again at
    execution, not just by disabling a Streamlit button. Seal is loaded via
    the ORIGINAL _verified_contract_seal, which checks PNG and SHA-256.
    """
    if not principal or not str(principal).strip():
        raise PermissionError("로그인된 사용자만 계약서를 발행할 수 있습니다.")
    if not approved or not authorized:
        raise PermissionError("현재 계약서 승인과 기존 직인 사용 권한 확인이 필요합니다.")
    if (not isinstance(expected_fingerprint, str)
            or contract_fingerprint(snapshot) != expected_fingerprint):
        raise ValueError("계약 정보가 변경되었습니다. 최신 내용을 다시 승인하세요.")
    issues = contract_final_blockers(
        snapshot, env, allow_unresolved_text=allow_unresolved_text)
    if issues:
        raise ValueError("최종 계약서 검증이 완료되지 않았습니다: " + "; ".join(issues[:5]))
    validated = validate_snapshot(deepcopy(dict(snapshot)))
    # Intentionally import at execution time: Streamlit can cache an older
    # workflow module during hot deploys. Never copy or reimplement layout.
    from Quotation_KEKOREA.contracts.ui import _verified_contract_seal
    from Quotation_KEKOREA.contracts.exports import export_contract
    seal_bytes = _verified_contract_seal(dict(env))
    outputs = export_contract(validated, formats=("pdf", "docx"),
                              seal_bytes=seal_bytes)
    for ext in ("pdf", "docx"):
        item = outputs.get(ext)
        blob = item.get("content") if isinstance(item, dict) else None
        if (not isinstance(blob, bytes) or not blob
                or (ext == "pdf" and not blob.startswith(b"%PDF"))
                or (ext == "docx" and not blob.startswith(b"PK"))):
            raise ValueError("기존 계약서 엔진에서 파일 생성이 완료되지 않았습니다.")
    return outputs


def confirm_contract_record(snapshot: Mapping[str, Any], section: str,
                            index: int, expected_value: str) -> dict[str, Any]:
    """A user can confirm one current party/term, never a stale or empty one."""
    if section not in {"parties", "terms"} or not isinstance(index, int) or index < 0:
        raise ValueError("확인할 계약조건이 유효하지 않습니다.")
    result = validate_snapshot(deepcopy(dict(snapshot)))
    records = result.get(section, [])
    if index >= len(records) or not isinstance(records[index], dict):
        raise ValueError("계약조건이 변경되었습니다. 다시 검토하세요.")
    record = records[index]
    value = (json.dumps({
        "roles": record.get("roles"), "legal_name": record.get("legal_name"),
        "address": record.get("address"), "country": record.get("country"),
    }, ensure_ascii=False, sort_keys=True) if section == "parties"
             else str(record.get("value") or ""))
    if value != expected_value:
        raise ValueError("계약조건이 변경되었습니다. 최신 정보를 확인하세요.")
    if section == "parties":
        if not record.get("roles") or any(
                not str(record.get(field) or "").strip()
                for field in ("legal_name", "address", "country")):
            raise ValueError("법인명·주소·설립국을 입력한 뒤 확인하세요.")
    elif not value.strip():
        raise ValueError("비어 있는 계약조건은 확정할 수 없습니다.")
    record["status"] = "confirmed"
    return result


def confirm_contract_issue(snapshot: Mapping[str, Any], index: int,
                           expected_message: str) -> dict[str, Any]:
    """Explicitly acknowledge ONE unchanged AI confirmation issue.

    Block-level findings cannot be silently dismissed by this action.
    """
    if not isinstance(index, int) or index < 0:
        raise ValueError("확인할 검토 항목이 없습니다.")
    revised = validate_snapshot(deepcopy(dict(snapshot)))
    issues = revised.get("issues", [])
    if not isinstance(issues, list) or index >= len(issues):
        raise ValueError("검토 항목이 변경되었습니다. 다시 확인하세요.")
    item = issues[index]
    if (not isinstance(item, dict)
            or item.get("severity") != "confirm"
            or str(item.get("message") or "") != expected_message):
        raise ValueError("승인할 수 없는 검토 항목입니다. 조건을 다시 확인하세요.")
    item["confirmed"] = True
    return revised
