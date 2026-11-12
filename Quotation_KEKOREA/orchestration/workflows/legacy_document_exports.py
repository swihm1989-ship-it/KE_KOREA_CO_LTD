"""MASTER-side adapter to the EXISTING trade-document renderer.

This does not issue final documents or change the legacy app. The existing
validation, seal resolver, PDF pagination and XLSX layout are reused unchanged.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from Quotation_KEKOREA.agent.branding import resolve_company_seal
from Quotation_KEKOREA.agent.ci_import import ci_render_data
from Quotation_KEKOREA.agent.renderers import render_files
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values

TRADE_KINDS = frozenset({"PI", "PO", "CI", "PL"})
BANK_KEYS = ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS")
MIMES = {"pdf": "application/pdf",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "html": "text/html"}


def render_master_trade_draft(kind: str, source: Mapping, env: Mapping[str, str]) -> dict:
    """Generate PDF/XLSX/HTML via the legacy engine, fail closed on missing inputs.

    The branded PDF requires the *original verified* KE KOREA seal. The PI
    additionally requires the same complete USD bank profile as the old app.
    """
    kind = str(kind).upper()
    if kind not in TRADE_KINDS:
        raise ValueError("Only PI, PO, CI and PL are supported")
    if not isinstance(source, Mapping):
        raise ValueError("Trade candidate must be a mapping")
    candidate = normalize_trade_values(source)
    if candidate.get("document_type") and str(candidate["document_type"]).upper() != kind:
        raise ValueError("Document type mismatch")
    candidate["document_type"] = kind
    candidate.pop("ready_for_issue", None)
    candidate.pop("status", None)
    checked = validate_and_calculate(candidate)
    blockers = list(checked.get("blocking_issues") or [])
    if blockers or not checked.get("ready_for_issue"):
        raise ValueError("거래조건을 먼저 보완하세요: " + "; ".join(map(str, blockers[:8])))
    bank = {key: str(env.get("KEKOREA_USD_" + key) or "").strip() for key in BANK_KEYS}
    if kind == "PI" and any(not value for value in bank.values()):
        raise ValueError("기존 업무 에이전트와 동일하게 PI 은행정보 6개 항목이 모두 필요합니다.")
    root = Path(__file__).resolve().parents[2]
    seal_path, seal_bytes, error = resolve_company_seal(root, env)
    if seal_bytes is None and not seal_path.is_file():
        raise ValueError("검증된 KE KOREA 회사 직인이 필요합니다: " + str(error or "설정 없음"))
    checked = ci_render_data(checked)
    with TemporaryDirectory(prefix="ke-master-doc-") as directory:
        actual_seal = seal_path
        if seal_bytes is not None:
            actual_seal = Path(directory) / "company_seal.png"
            actual_seal.write_bytes(seal_bytes)
        # Match the original KE KOREA app: pass the very same logo and seal
        # locations to the unmodified shared PI/PO/CI/PL PDF/XLSX renderer.
        logo_path = root / "assets" / "company_logo.png"
        paths = render_files(checked, Path(directory) / "outputs",
                             bank_details=bank, logo_path=logo_path,
                             seal_path=actual_seal)
        result = {}
        for extension in ("pdf", "xlsx", "html"):
            path = paths[extension]
            data = path.read_bytes()
            if not data:
                raise ValueError("생성된 파일이 비어 있습니다.")
            result[extension] = {
                "filename": path.name,
                "content": data,
                "mime": MIMES[extension],
                "sha256": sha256(data).hexdigest(),
                "final": False,
                "sendable": False,
            }
    return result
