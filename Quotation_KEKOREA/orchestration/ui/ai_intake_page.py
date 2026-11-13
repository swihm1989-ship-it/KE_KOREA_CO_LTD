"""Authenticated AI intake screen; no stored private contract sent to the model."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from inspect import signature
import hmac
import importlib
import json
import os

import streamlit as st

from Quotation_KEKOREA.orchestration.workflows.mail_intake import (
    extract_mail_candidates, consume_pending, fingerprint as mail_fingerprint,
)
from Quotation_KEKOREA.orchestration.router import DOC_TYPES, classify
from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values
from Quotation_KEKOREA.orchestration.workflows.label_typos import canonical_label
from Quotation_KEKOREA.orchestration.workflows.ai_intake import (
    extract_candidate,
    selected_contract_reference,
)
from Quotation_KEKOREA.orchestration.workflows.unified_review import (
    new_request, prepare_documents,
)
from Quotation_KEKOREA.orchestration.ui.saved_contracts import _server_value
from Quotation_KEKOREA.orchestration.workflows.document_assets import (
    document_export_env, seal_health,
)
# Resolve workflow functions at call time: Streamlit may retain a pre-deploy
# module in sys.modules while reloading this page's source code.
FOLLOWUP_MODULE = "Quotation_KEKOREA.orchestration.workflows.intake_followups"
PDF_EXPORT_MODULE = "Quotation_KEKOREA.orchestration.workflows.legacy_document_exports"
PDF_EXPORT_REVISION = "review-pdf-safe-loader-20261113-v4"
TRADE_REVIEW_MODULE = "Quotation_KEKOREA.orchestration.workflows.trade_export_review"
TRADE_REVIEW_REVISION = "approved-blank-final-20261113-v1"
AI_INTAKE_REVISION = "ai-intake-hot-reload-20261113-v9"


def _current_ai_workflow():
    """Keep pre-deploy workers compatible with the current workflow API."""
    module = importlib.import_module("Quotation_KEKOREA.orchestration.workflows.ai_intake")
    if getattr(module, "AI_WORKFLOW_REVISION", None) != "trade-missing-terms-20261113-v2":
        importlib.invalidate_caches()
        module = importlib.reload(module)
    return module


def make_trade_candidate(*args, **kwargs):
    return _current_ai_workflow().make_trade_candidate(*args, **kwargs)


def make_contract_candidate(*args, **kwargs):
    return _current_ai_workflow().make_contract_candidate(*args, **kwargs)


def generate_contract_draft(*args, **kwargs):
    return _current_ai_workflow().generate_contract_draft(*args, **kwargs)


def _current_intake_followups():
    """Reload a stale editor module without losing the user's session values."""
    try:
        module = importlib.import_module(FOLLOWUP_MODULE)
        func = getattr(module, "apply_answer", None)
        try:
            compatible = callable(func) and "allow_blank" in signature(func).parameters
        except (TypeError, ValueError):
            compatible = False
        if not compatible or getattr(module, "FOLLOWUP_REVISION", None) != "visible-document-fields-20261113-v1":
            importlib.invalidate_caches()
            module = importlib.reload(module)
            func = getattr(module, "apply_answer", None)
            compatible = callable(func) and "allow_blank" in signature(func).parameters
        if (not compatible
                or not callable(getattr(module, "missing_fields", None))
                or not callable(getattr(module, "acknowledge_prior_source_notice", None))):
            importlib.invalidate_caches()
            module = importlib.reload(module)
        if (not callable(getattr(module, "acknowledge_prior_source_notice", None))
                or not callable(getattr(module, "missing_fields", None))
                or "allow_blank" not in signature(module.apply_answer).parameters):
            raise RuntimeError("stale editor")
    except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError):
        raise RuntimeError(
            "거래정보 수정 모듈 버전이 일치하지 않습니다. 앱을 재시작한 후 다시 시도하세요."
        ) from None
    return module


def apply_answer(*args, **kwargs):
    return _current_intake_followups().apply_answer(*args, **kwargs)


def missing_fields(*args, **kwargs):
    return _current_intake_followups().missing_fields(*args, **kwargs)


def _current_trade_export_review():
    """Refresh the review API before rendering a retained Streamlit session."""
    try:
        module = importlib.import_module(TRADE_REVIEW_MODULE)
        def compatible():
            return (
                getattr(module, "TRADE_REVIEW_REVISION", None) == TRADE_REVIEW_REVISION
                and all(callable(getattr(module, name, None))
                        and "allow_incomplete" in signature(getattr(module, name)).parameters
                        for name in ("review_trade_document", "trade_export_fingerprint"))
            )
        if not compatible():
            importlib.invalidate_caches()
            module = importlib.reload(module)
        if not compatible():
            raise RuntimeError("stale review module")
    except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError):
        raise RuntimeError(
            "문서 검토 모듈 버전이 일치하지 않습니다. 앱을 재시작한 후 다시 시도하세요."
        ) from None
    return module


def _current_pdf_export_renderers():
    """Resolve a fresh PDF renderer only for an explicit PDF button click."""
    try:
        module = importlib.import_module(PDF_EXPORT_MODULE)
        if (
            getattr(module, "REVIEW_EXPORT_REVISION", None) != PDF_EXPORT_REVISION
            or not callable(getattr(module, "render_incomplete_trade_pdf", None))
            or not callable(getattr(module, "render_master_trade_draft", None))
            or not callable(getattr(module, "render_master_trade_final", None))
            or "allow_incomplete" not in signature(module.render_master_trade_final).parameters
        ):
            importlib.invalidate_caches()
            module = importlib.reload(module)
        if (
            getattr(module, "REVIEW_EXPORT_REVISION", None) != PDF_EXPORT_REVISION
            or not callable(getattr(module, "render_incomplete_trade_pdf", None))
            or not callable(getattr(module, "render_master_trade_draft", None))
            or not callable(getattr(module, "render_master_trade_final", None))
            or "allow_incomplete" not in signature(module.render_master_trade_final).parameters
        ):
            raise RuntimeError("stale PDF module")
    except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError):
        raise RuntimeError(
            "PDF 모듈 버전이 일치하지 않습니다. 앱을 재시작한 후 다시 시도하세요."
        ) from None
    return module.render_master_trade_draft, module.render_incomplete_trade_pdf


def _formal_pdf_hold_reason(kind: str, error: Exception, env: dict) -> str:
    """Safe, specific category instead of hiding every failure as 'not approved'.

    Never display raw third-party errors, bank data, credentials or seal bytes.
    The strict existing renderer remains authoritative for actual issuance.
    """
    message = str(error)
    if message.startswith("문서 생성 전 누락 정보"):
        return "문서 생성 전 누락 정보가 있습니다. 위 거래정보 입력창에서 연락처 등 표시된 항목을 입력하세요."
    if message.startswith("거래조건을 먼저 보완하세요:"):
        return ("거래조건 검증 미통과입니다. 위 '현재 입력 확인사항'의 "
                "구체적인 오류 및 '이전 AI 추출 기록'의 미확정·충돌 항목을 확인하세요.")
    if kind == "PI" and "은행정보" in message:
        keys = ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT",
                "ACCOUNT_NUMBER", "BANK_ADDRESS")
        missing = sum(not str(env.get("KEKOREA_USD_" + key) or "").strip()
                      for key in keys)
        return ("거래조건과 별개로 PI 발행용 은행정보 " +
                str(missing) + "/6개가 서버 설정에 없습니다. "
                "Streamlit Secrets에서 기존 KE KOREA 은행 설정을 확인해야 합니다.")
    if "직인" in message:
        return ("거래조건과 별개로 회사 직인 확인에 실패했습니다. "
                "'회사 직인 · 기존 서식 연결 확인'을 눌러 연결 상태를 확인하세요.")
    if "attached PI" in message or "원본 PI" in message:
        return "CI 출력에는 검증된 원본 PI 자료가 필요합니다."
    if "Document type mismatch" in message:
        return "문서 종류가 현재 후보와 일치하지 않습니다. 종류를 다시 확인하세요."
    return ("기존 PDF 렌더러 처리 오류가 발생했습니다. "
            "문서 생성 서버 로그에서 원인을 확인해야 합니다. "
            "거래정보가 누락됐다는 의미는 아닙니다.")


def _fingerprint(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _model_config():
    return {k: _server_value(k) for k in (
        "OPENAI_API_KEY", "OPENAI_MODEL", "CONTRACT_OPENAI_MODEL",
    )}


def _invalidate_document_outputs() -> None:
    """Every accepted or rejected visible edit revokes previous output approval."""
    for key in ("ai_intake_drafts", "master_legacy_files",
                "master_contract_final_files", "master_trade_final_files"):
        st.session_state.pop(key, None)
    st.session_state["ai_intake_edit_revision"] = st.session_state.get("ai_intake_edit_revision", 0) + 1


def _pending_input_errors(digest: str) -> dict:
    return {key: value for key, value in
            (st.session_state.get("ai_intake_pending_input_errors") or {}).items()
            if value.get("digest") == digest}


def _record_input_error(digest: str, field: str, widget: str, message: str) -> None:
    pending = dict(st.session_state.get("ai_intake_pending_input_errors") or {})
    pending[widget] = {"digest": digest, "field": field, "message": message,
                       "value": str(st.session_state.get(widget) or "")}
    st.session_state["ai_intake_pending_input_errors"] = pending
    st.session_state["ai_intake_followup_error"] = message
    _invalidate_document_outputs()


def _clear_input_error(widget: str) -> None:
    pending = dict(st.session_state.get("ai_intake_pending_input_errors") or {})
    pending.pop(widget, None)
    if pending:
        st.session_state["ai_intake_pending_input_errors"] = pending
    else:
        st.session_state.pop("ai_intake_pending_input_errors", None)
    st.session_state.pop("ai_intake_followup_error", None)


def _shared_widget_identity(digest: str) -> str:
    generation = (st.session_state.get("ai_intake_editor_generations") or {}).get(digest, 0)
    return digest[:12] + ("_g" + str(generation) if generation else "")


def _is_current_shared_widget(digest: str, widget: str) -> bool:
    """Reject an event from a browser input replaced by a newer candidate."""
    base = "ai_intake_shared_" + digest[:12] + "_"
    return (not widget.startswith(base)
            or widget.startswith("ai_intake_shared_" + _shared_widget_identity(digest) + "_"))


def _initialize_shared_widget(widget: str, value: str) -> None:
    if widget not in st.session_state:
        # A changed default does not replace a keyed browser widget's value.
        # A session-state assignment sends Streamlit's explicit set_value signal.
        st.session_state[widget] = value


def _remember_candidate_bundle(digest: str, candidate_map: dict, *, replace_editor=False) -> None:
    """Synchronize candidate revisions; widgets refresh before their next render."""
    previous = st.session_state.get("ai_intake_candidates")
    if replace_editor:
        snapshot = st.session_state.get("ai_intake_editor_snapshot")
        if ((previous and previous[0] == digest) or (snapshot and snapshot[0] == digest)):
            generations = dict(st.session_state.get("ai_intake_editor_generations") or {})
            generations[digest] = generations.get(digest, 0) + 1
            st.session_state["ai_intake_editor_generations"] = generations
    if replace_editor or not previous or previous[0] != digest:
        st.session_state.pop("ai_intake_pending_input_errors", None)
        st.session_state.pop("ai_intake_followup_error", None)
    candidate_map = {kind: normalize_trade_values(data) if kind in {"PI", "PO", "CI", "PL"} else data
                     for kind, data in candidate_map.items()}
    st.session_state["ai_intake_candidates"] = (digest, candidate_map)
    _invalidate_document_outputs()


def _refresh_shared_widgets(digest: str, candidates: dict) -> None:
    """Reflect committed JSON/cross-document edits without hiding rejected input."""
    current = (digest, _fingerprint(json.dumps(candidates, ensure_ascii=False, sort_keys=True)),
               _shared_widget_identity(digest))
    pending = _pending_input_errors(digest)
    if st.session_state.get("ai_intake_editor_snapshot") != current:
        prefix = "ai_intake_shared_" + digest[:12] + "_"
        for key in list(st.session_state):
            if str(key).startswith(prefix) and key not in pending:
                st.session_state.pop(key, None)
        st.session_state["ai_intake_editor_snapshot"] = current
    # Streamlit removes widget values on menu navigation; keep unsaved errors
    # with the exact visible input until the user corrects or replaces it.
    for key, error in pending.items():
        if key not in st.session_state:
            st.session_state[key] = error["value"]


def _handle_missing_answer(digest: str, key: str, widget_key: str) -> None:
    """On Enter/blur, update both draft types and revoke old previews."""
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest:
        return
    answer = str(st.session_state.get(widget_key, "")).strip()
    if not answer:
        return
    try:
        source = saved[1]
        if not isinstance(source, dict):
            raise ValueError("문서 조건이 올바르지 않습니다.")
        updated = apply_answer(source, key, answer)
    except (ValueError, TypeError) as exc:
        st.session_state["ai_intake_followup_error"] = str(exc)
        return
    _remember_candidate_bundle(digest, updated)
    st.session_state["ai_intake_last_answer"] = key
    st.session_state.pop("ai_intake_followup_error", None)


def _apply_pdf_required_fields(digest: str) -> None:
    """Apply submitted form values before the next Streamlit widget render."""
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest:
        return
    changed = deepcopy(saved[1])
    fields = {name: str(st.session_state.get("master_pdf_" + name) or "").strip()
              for name in ("doc_no", "buyer_name", "buyer_addr", "seller_name",
                           "seller_addr", "currency", "incoterms", "payment",
                           "product", "quantity", "unit", "price", "basis",
                           "shipment", "origin")}
    for kind, trade in changed.items():
        if kind not in ("PI", "PO", "CI", "PL") or not isinstance(trade, dict):
            continue
        currency = fields["currency"].upper()
        trade.update(document_number=fields["doc_no"],
                     currency={"$": "USD", "US$": "USD", "₩": "KRW"}.get(currency, currency),
                     incoterms=fields["incoterms"], payment_terms=fields["payment"],
                     shipment_reference=fields["shipment"], country_of_origin=fields["origin"])
        trade["buyer"] = {**(trade.get("buyer") or {}),
                          "legal_name": fields["buyer_name"], "address": fields["buyer_addr"]}
        trade["seller"] = {**(trade.get("seller") or {}),
                           "legal_name": fields["seller_name"], "address": fields["seller_addr"]}
        items = deepcopy(trade.get("items") or [{}])
        items[0] = {**items[0], "product_name": fields["product"],
                    "quantity": fields["quantity"], "unit": fields["unit"].upper(),
                    "unit_price": fields["price"], "price_basis": fields["basis"].upper()}
        if st.session_state.get('ai_intake_mail_source'):
            from Quotation_KEKOREA.orchestration.workflows.mail_trade_normalization import apply_quantity_edit
            apply_quantity_edit(items[0],fields['quantity'])
        trade["items"] = items
        if st.session_state.get('ai_intake_mail_source'):
            from Quotation_KEKOREA.orchestration.workflows.mail_trade_normalization import resolve_notice_for_answer
            for key in ('buyer.legal_name','buyer.address','seller.legal_name','seller.address',
                        'currency','incoterms','payment_terms','shipment_reference','country_of_origin',
                        'item.product_name','item.quantity','item.unit','item.unit_price','item.price_basis'):
                resolve_notice_for_answer(trade,key)
    _remember_candidate_bundle(digest, changed)
    st.session_state.pop("master_legacy_files", None)
    st.session_state["master_pdf_applied"] = True



SHARED_FIELDS = (
    ("document_number", "문서번호 (미확정은 DRAFT)"),
    ("buyer.legal_name", "Buyer · 구매자 법인명"),
    ("buyer.address", "Buyer · 구매자 법인 주소"),
    ("buyer.contact", "Buyer · 담당자 / 대표자"),
    ("buyer.phone", "Buyer · 전화번호"),
    ("buyer.email", "Buyer · 이메일"),
    ("seller.legal_name", "Seller · 판매자 법인명"),
    ("seller.address", "Seller · 판매자 법인 주소"),
    ("seller.contact", "Seller · 담당자 / 대표자"),
    ("seller.phone", "Seller · 전화번호"),
    ("seller.email", "Seller · 이메일"),
    ("ship_to", "배송지 (해당 없으면 N/A)"),
    ("currency", "통화 (USD / KRW / EUR / CNY)"),
    ("incoterms", "인도조건 및 장소"),
    ("payment_terms", "결제조건"),
    ("item.product_name", "상품명 및 규격"),
    ("item.quantity", "수량"),
    ("item.unit", "수량 단위"),
    ("item.unit_price", "단가"),
    ("item.price_basis", "단가 기준"),
    ("item.discount_percent", "할인율 % (할인이 없으면 0)"),
    ("container_count", "컨테이너 수 (컨테이너 운송이 아니면 0)"),
    ("shipment_reference", "선적 참조번호 (CI / PL 필수 · 해당 없으면 N/A)"),
    ("country_of_origin", "제품 원산지 (CI 필수 · 해당 없으면 N/A)"),
)


def _shared_current(candidates: dict, field: str) -> str:
    """Read the same document candidates used by preview and PDF export."""
    trade = next((doc for kind, doc in candidates.items()
                  if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)), {})
    contract = candidates.get("CONTRACT") or {}
    from Quotation_KEKOREA.agent.review_fields import _missing, missing_review_fields
    # Keep a gap visible even when an earlier document already has a value.
    # Typing into this one shared input then updates every applicable candidate.
    for kind, doc in candidates.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(doc, dict):
            continue
        for pending in missing_review_fields(dict(doc, document_type=kind)):
            path = pending.path
            pending_key = ("item." + (str(path[1]) + "." if path[1] else "") + path[2]
                           if path[0] == "items" else ".".join(path))
            if pending_key == field and field not in {
                    "buyer.legal_name", "seller.legal_name", "buyer.address", "seller.address"}:
                return ""
    if field.startswith(("buyer.", "seller.")):
        role, prop = field.split(".", 1)
        value = str((trade.get(role) or {}).get(prop) or "").strip()
        if not _missing(value, prop in {"legal_name", "address", "country"}):
            return value
        if trade and prop != "country":
            return ""
        return next((str(p.get("representative" if prop == "contact" else prop) or "") for p in contract.get("parties", [])
                     if isinstance(p, dict) and role in [
                         canonical_label(str(r)) or str(r)
                         for r in p.get("roles", [])]), "")
    if field.startswith("item."):
        parts = field.split(".")
        index = int(parts[1]) if len(parts) == 3 else 0
        prop = parts[-1]
        row = next((doc["items"][index] for kind, doc in candidates.items()
                    if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)
                    and len(doc.get("items") or []) > index), {})
        value = row.get(prop)
        if not _missing(value, True):
            return str(value)
        term = {"product_name": "products", "quantity": "quantity",
                "unit": "unit", "unit_price": "unit_price"}.get(prop)
        if term:
            return next((str(t.get("value") or "") for t in contract.get("terms", [])
                         if t.get("key") == term), "")
        return ""
    value = trade.get(field)
    if not _missing(value, field in {"currency", "document_number", "incoterms", "container_count"}):
        return str(value)
    term = {"currency": "currency", "incoterms": "delivery",
            "payment_terms": "payment_trigger"}.get(field)
    if term:
        return next((str(t.get("value") or "") for t in contract.get("terms", [])
                     if t.get("key") == term), "")
    return ""


def _apply_shared_input(digest: str, field: str, widget: str) -> None:
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest or not _is_current_shared_widget(digest, widget):
        return
    raw = str(st.session_state.get(widget) or "").strip()
    if field in {"currency", "item.unit", "item.price_basis"}:
        raw = raw.upper()
        if field == "currency":
            raw = {"$": "USD", "US$": "USD", "USD$": "USD", "₩": "KRW"}.get(raw, raw)
    try:
        updated = apply_answer(saved[1], field, raw, allow_blank=True)
    except (ValueError, TypeError, RuntimeError) as exc:
        _record_input_error(digest, field, widget, str(exc))
        return
    _clear_input_error(widget)
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state.pop("master_contract_final_files", None)
    st.session_state["ai_intake_last_answer"] = field
    st.session_state.pop("ai_intake_followup_error", None)


def _apply_input_to_missing(digest: str, field: str, widget: str) -> None:
    """Fill only absent party facts; retain other documents' named companies."""
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest or not _is_current_shared_widget(digest, widget):
        return
    from Quotation_KEKOREA.agent.review_fields import _missing
    role, prop = field.split(".")
    raw = str(st.session_state.get(widget) or "").strip()
    if role not in {"buyer", "seller"} or prop not in {"legal_name", "address", "country"}:
        return
    updated = deepcopy(saved[1])
    try:
        for kind, doc in list(updated.items()):
            if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict):
                if prop != "country" and _missing((doc.get(role) or {}).get(prop), True):
                    updated[kind] = apply_answer({kind: doc}, field, raw)[kind]
            elif kind == "CONTRACT" and isinstance(doc, dict):
                party = next((p for p in doc.get("parties") or []
                              if role in [canonical_label(str(r)) or str(r)
                                          for r in p.get("roles", [])]), {})
                if _missing(party.get(prop), True):
                    updated[kind] = apply_answer({kind: doc}, field, raw)[kind]
    except (ValueError, TypeError, RuntimeError) as exc:
        st.session_state["ai_intake_followup_error"] = str(exc)
        return
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state.pop("ai_intake_followup_error", None)
    st.session_state["ai_intake_last_answer"] = field + " (누락 항목만 반영)"


def _acknowledge_ai_notice(digest: str, kind: str,
                           category: str, index: int, expected: str) -> None:
    """Explicit one-click acknowledgement in the SAME transaction editor."""
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest:
        return
    try:
        updated = _current_intake_followups().acknowledge_prior_source_notice(
            saved[1], kind, category, index, expected)
    except (ValueError, TypeError, RuntimeError) as exc:
        st.session_state["ai_intake_followup_error"] = str(exc)
        return
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state["ai_intake_last_answer"] = kind + " · 이전 AI 기록 확인"
    st.session_state.pop("ai_intake_followup_error", None)


def _apply_extra_item(digest: str, index: int, field: str, widget: str) -> None:
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest or not _is_current_shared_widget(digest, widget):
        return
    raw = str(st.session_state.get(widget) or "").strip()
    try:
        updated = apply_answer(saved[1], f"item.{index}.{field}", raw, allow_blank=True)
    except (ValueError, TypeError, RuntimeError) as exc:
        _record_input_error(digest, f"item.{index}.{field}", widget, str(exc))
        return
    _clear_input_error(widget)
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state["ai_intake_last_answer"] = "item " + str(index + 1)
    st.session_state.pop("ai_intake_followup_error", None)


def _edit_contract_fact(digest: str, section: str, identity: str,
                        field: str, widget: str) -> None:
    """Edit contract-specific facts in the same input card; revoke AI clauses."""
    saved = st.session_state.get("ai_intake_candidates")
    if (not saved or saved[0] != digest or not isinstance(saved[1].get("CONTRACT"), dict)
            or not _is_current_shared_widget(digest, widget)):
        return
    value = str(st.session_state.get(widget) or "").strip()
    if len(value) > 1500 or section not in {"party", "term"}:
        st.session_state["ai_intake_followup_error"] = "계약조건 입력을 확인하세요."
        return
    updated = deepcopy(saved[1])
    snapshot = updated["CONTRACT"]
    if section == "term":
        if field != "value":
            return
        term = next((t for t in snapshot.get("terms", [])
                     if t.get("key") == identity), None)
        if term is None:
            term = {"key": identity, "value": "", "status": "missing",
                    "source_refs": []}
            snapshot.setdefault("terms", []).append(term)
        term["value"] = value
        term["status"] = "suggested" if value else "missing"
    else:
        if field not in {"legal_name", "address", "country"}:
            return
        party = next((p for p in snapshot.get("parties", [])
                      if identity in p.get("roles", [])), None)
        if party is None:
            party = {"roles": [identity], "legal_name": "", "country": "",
                     "address": "", "status": "missing", "source_refs": []}
            snapshot.setdefault("parties", []).append(party)
        party[field] = value
        party["status"] = "suggested"
    snapshot["clauses"] = []
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state.pop("master_contract_final_files", None)
    st.session_state.pop("ai_intake_followup_error", None)


def _confirm_contract_item(digest: str, section: str, index: int,
                           expected: str) -> None:
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest or not isinstance(saved[1].get("CONTRACT"), dict):
        return
    try:
        from Quotation_KEKOREA.orchestration.workflows.master_contract_final import (
            confirm_contract_record,
        )
        updated = deepcopy(saved[1])
        updated["CONTRACT"] = confirm_contract_record(
            updated["CONTRACT"], section, index, expected)
    except (ImportError, ValueError, TypeError) as exc:
        st.session_state["ai_intake_followup_error"] = (
            "조건 확인 실패: " + str(exc)[:180] if not isinstance(exc, ImportError)
            else "계약서 확인 모듈을 찾지 못했습니다. 앱을 재시작하세요.")
        return
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_contract_final_files", None)
    st.session_state.pop("ai_intake_followup_error", None)


def _confirm_contract_review_issue(digest: str, index: int, expected: str) -> None:
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest or not isinstance(saved[1].get("CONTRACT"), dict):
        return
    try:
        from Quotation_KEKOREA.orchestration.workflows.master_contract_final import (
            confirm_contract_issue,
        )
        updated = deepcopy(saved[1])
        updated["CONTRACT"] = confirm_contract_issue(
            updated["CONTRACT"], index, expected)
    except (ImportError, ValueError, TypeError):
        st.session_state["ai_intake_followup_error"] = (
            "검토 항목을 확인할 수 없습니다. 조건을 다시 확인하세요.")
        return
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("ai_intake_followup_error", None)


def _render_contract_confirmations(digest: str, snapshot: dict) -> None:
    """Use the existing ONE editor for contract facts and explicit approvals."""
    from Quotation_KEKOREA.contracts.rules import COMMON_REQUIRED, TYPE_REQUIRED, LABELS
    from Quotation_KEKOREA.orchestration.workflows.intake_followups import TERM_MAP
    roles = {"sale": ("buyer", "seller"),
             "trade_commission": ("client", "intermediary", "commission_payer"),
             "investment_commission": ("client", "fundraiser", "commission_payer")}
    required_roles = roles.get(snapshot.get("contract_type"), ())
    with st.expander("계약서 전용 조건 입력 · 개별 확정 (FINAL 발행 전)", expanded=False):
        st.caption("입력값은 AI 제안 상태이며 자동으로 확정되지 않습니다. "
                   "각 조건을 원문과 확인한 뒤 '확정'을 누르세요. "
                   "계약조건을 수정하면 AI 작성 조항은 다시 생성해야 합니다.")
        parties = snapshot.get("parties") or []
        for role in required_roles:
            match = next(((i, p) for i, p in enumerate(parties)
                          if role in p.get("roles", [])), None)
            idx, party = match if match else (None, {})
            st.markdown("**" + LABELS.get(role, role) + "**")
            if role not in {"buyer", "seller"}:
                for field, label in (("legal_name", "법인명"), ("address", "주소"),
                                     ("country", "설립국")):
                    widget = f"ai_intake_shared_{_shared_widget_identity(digest)}_contract_{role}_{field}"
                    _initialize_shared_widget(widget, str(party.get(field) or ""))
                    st.text_input(role + " · " + label, key=widget,
                                  on_change=_edit_contract_fact,
                                  args=(digest, "party", role, field, widget))
            else:
                st.caption("회사명·주소·설립국은 위 공통 입력란에서 수정할 수 있습니다.")
            present = bool(party) and all(str(party.get(field) or "").strip()
                                           for field in ("legal_name", "address", "country"))
            if idx is not None:
                expected = json.dumps(
                    {"roles": party.get("roles"), "legal_name": party.get("legal_name"),
                     "address": party.get("address"), "country": party.get("country")},
                    ensure_ascii=False, sort_keys=True)
                if party.get("status") == "confirmed":
                    st.caption("확정됨")
                else:
                    st.button(role + " · 당사자 확정", disabled=not present,
                              key=f"ai_contract_confirm_party_{digest[:12]}_{idx}",
                              on_click=_confirm_contract_item,
                              args=(digest, "parties", idx, expected))
            else:
                st.warning(role + " 당사자 정보를 먼저 입력하세요.")

        existing = snapshot.get("terms") or []
        required = tuple(COMMON_REQUIRED) + tuple(TYPE_REQUIRED.get(
            snapshot.get("contract_type"), ()))
        keys = list(dict.fromkeys(
            [k for k in required if k not in required_roles] +
            [str(term.get("key")) for term in existing if term.get("key")]))
        shared_keys = set(TERM_MAP.values())
        for key in keys:
            match = next(((i, term) for i, term in enumerate(existing)
                          if term.get("key") == key), None)
            idx, term = match if match else (None, {})
            value = str(term.get("value") or "")
            if key not in shared_keys:
                widget = f"ai_intake_shared_{_shared_widget_identity(digest)}_contract_term_{key}"
                _initialize_shared_widget(widget, value)
                st.text_input(LABELS.get(key, key), key=widget,
                              on_change=_edit_contract_fact,
                              args=(digest, "term", key, "value", widget))
            else:
                st.caption(LABELS.get(key, key) + ": " + (value or "미입력") +
                           " (위 공통 입력란에서 변경)")
            if idx is not None and value.strip():
                if term.get("status") == "confirmed":
                    st.caption("확정됨")
                else:
                    st.button(key + " · 조건 확정",
                              key=f"ai_contract_confirm_term_{digest[:12]}_{idx}",
                              on_click=_confirm_contract_item,
                              args=(digest, "terms", idx, value))
            elif idx is None:
                st.caption("미입력 · 위 칸에서 내용을 입력하세요.")
        for issue_idx, issue in enumerate(snapshot.get("issues") or []):
            if not isinstance(issue, dict):
                continue
            if issue.get("severity") == "confirm" and not issue.get("confirmed"):
                msg = str(issue.get("message") or "AI 확인 필요 사항")
                st.warning("계약서 검토: " + msg)
                st.button("이 AI 검토 항목 확인 완료",
                          key=f"ai_contract_issue_{digest[:12]}_{issue_idx}",
                          on_click=_confirm_contract_review_issue,
                          args=(digest, issue_idx, str(issue.get("message") or "")))
            elif issue.get("severity") == "block":
                st.error("계약서 차단 사항: " + str(issue.get("message") or ""))


def _generate_trade_numbers(digest: str, widget: str) -> None:
    from datetime import datetime, timezone, timedelta
    from uuid import uuid4
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest or not _is_current_shared_widget(digest, widget):
        return
    updated = deepcopy(saved[1])
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d-%H%M%S")
    first = None
    for kind, doc in updated.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(doc, dict):
            continue
        value = str(doc.get("document_number") or "").strip()
        from Quotation_KEKOREA.agent.review_fields import _missing
        if _missing(value, True) or value.upper().startswith("DRAFT"):
            doc["document_number"] = kind + "-" + stamp + "-" + uuid4().hex[:6].upper()
        if first is None:
            first = doc["document_number"]
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state[widget] = first or ""


def _render_trade_issue_list(kind: str, report: dict) -> None:
    warnings = report.get("warnings") or []
    issues = report.get("issues") or []
    if warnings:
        st.warning(kind + " · 누락·확인 필요 " + str(len(warnings)) + "건 · 승인 시 빈칸 유지")
        for row in warnings:
            prefix = ("이전 AI 기록 · " if row["code"] in {"ai_missing", "ai_conflict"} else "")
            st.text(prefix + row["message"])
    if issues:
        st.warning(kind + " · 발행 전 수정 필요 " + str(len(issues)) + "건")
        for row in issues:
            prefix = ("이전 AI 기록 · " if row["code"] in {"ai_missing", "ai_conflict"} else "")
            st.text(prefix + row["message"])
    elif not warnings:
        st.success(kind + " · 현재 입력값 검증 통과")


def _discard_trade_final(kind: str) -> None:
    bundle = dict(st.session_state.get("master_trade_final_files") or {})
    bundle.pop(kind, None)
    if bundle:
        st.session_state["master_trade_final_files"] = bundle
    else:
        st.session_state.pop("master_trade_final_files", None)


def _render_trade_final_panel(digest: str, sources: dict, env: dict, *, edited_matches=True) -> None:
    trade = {kind: doc for kind, doc in sources.items()
             if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)}
    if not trade:
        return
    try:
        review = _current_trade_export_review()
    except RuntimeError as exc:
        st.error(str(exc))
        return
    st.divider()
    st.markdown("#### 최종 PDF · 기존 KE KOREA 양식")
    st.caption("현재 문서별 입력·금액을 검증하고 직접 승인한 최종본을 생성합니다. "
               "누락된 값은 승인 후에도 빈칸으로 남고, 계산 근거가 부족한 금액도 빈칸으로 출력합니다. "
               "실제 전송은 하지 않습니다.")
    if not edited_matches:
        st.error("고급 JSON 변경값을 먼저 문서 후보에 반영하세요. 저장되지 않은 값으로 최종 발행하지 않습니다.")
    pending_errors = _pending_input_errors(digest)
    if pending_errors:
        st.error("입력 오류를 먼저 수정하세요. 화면의 변경값이 아직 문서에 저장되지 않아 최종 출력을 보류합니다.")
    revision = st.session_state.get("ai_intake_edit_revision", 0)
    for kind, source in trade.items():
        try:
            report = review.review_trade_document(kind, source, final=True, allow_incomplete=True)
            fingerprint = review.trade_export_fingerprint(kind, source, allow_incomplete=True)
        except (ValueError, TypeError, KeyError, AttributeError):
            st.error(kind + " 문서 형식을 확인해 주세요.")
            _discard_trade_final(kind)
            continue
        with st.container(border=True):
            st.markdown("**" + kind + " · " + str(source.get("document_number") or "미입력") + "**")
            _render_trade_issue_list(kind, report)
            if report['missing']:
                st.caption("누락 항목은 위 거래정보 입력창에서 보완하거나, 아래 승인 후 빈칸으로 출력할 수 있습니다.")
            if source.get('missing_fields'):
                st.caption("이전 AI 미입력 기록은 참고용으로 유지됩니다. 현재 입력값과 위 누락 항목을 확인하세요.")
            key = digest[:12] + "_" + kind + "_" + fingerprint[:18] + "_" + str(revision)
            approval_key = "master_trade_final_approve_" + key
            blocked = bool(report['issues']) or not edited_matches or bool(pending_errors)
            if blocked:
                st.session_state.pop(approval_key, None)
            approved = st.checkbox(
                kind + " · 최종 출력 승인: 현재 입력과 누락 항목을 확인했으며, 미입력값과 계산할 수 없는 금액을 빈칸으로 두고 이 버전의 최종 PDF 생성을 승인합니다.",
                key=approval_key, disabled=blocked)
            if blocked or not approved:
                _discard_trade_final(kind)
            if st.button(kind + " 최종 PDF 생성", key="master_trade_final_export_" + key,
                         disabled=blocked or not approved, type="primary"):
                _discard_trade_final(kind)
                try:
                    _current_pdf_export_renderers()
                    exports = importlib.import_module(PDF_EXPORT_MODULE)
                    files = exports.render_master_trade_final(
                        kind, source, env, approved=approved,
                        expected_fingerprint=fingerprint, allow_incomplete=True)
                    bundle = dict(st.session_state.get("master_trade_final_files") or {})
                    bundle[kind] = {"fingerprint": fingerprint, "revision": revision, "files": files}
                    st.session_state["master_trade_final_files"] = bundle
                except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, OSError) as exc:
                    if isinstance(exc, review.TradeExportValidationError):
                        _render_trade_issue_list(kind, {'issues': exc.issues})
                    elif str(exc).startswith(('승인 후 문서', '최종 PDF 생성에 대한 사용자')):
                        st.error(str(exc))
                    else:
                        st.error(kind + " 최종 PDF 생성 보류: " + _formal_pdf_hold_reason(kind, exc, env))
            saved = (st.session_state.get("master_trade_final_files") or {}).get(kind)
            if (saved and approved and not blocked
                    and saved['fingerprint'] == fingerprint and saved['revision'] == revision):
                for fmt, asset in saved['files'].items():
                    st.download_button(kind + " " + fmt.upper() + " FINAL 다운로드",
                                       data=asset['content'], file_name=asset['filename'],
                                       mime=asset['mime'], key="master_trade_final_download_" + kind + "_" + fmt)


def _render_contact_inputs(digest: str, candidates: dict, field: str, label: str) -> bool:
    """Keep contacts separate when a PO and sales document name different firms."""
    from Quotation_KEKOREA.agent.review_fields import _missing
    role, prop = field.split(".")
    groups = {}
    for kind, doc in candidates.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(doc, dict):
            continue
        name = str((doc.get(role) or {}).get("legal_name") or "").strip().casefold()
        identity = name if not _missing(name, True) else kind
        groups.setdefault(identity, {})[kind] = doc
    if not groups:
        return False
    for bundle in groups.values():
        kind = next(iter(bundle))
        suffix = (kind + "_" if len(groups) > 1 else "") + field.replace(".", "_")
        widget = "ai_intake_shared_" + _shared_widget_identity(digest) + "_" + suffix
        _initialize_shared_widget(widget, _shared_current(bundle, field))
        st.text_input((kind + " · " if len(groups) > 1 else "") + label,
                      key=widget, help="확인한 연락처를 입력하세요. 해당 없으면 N/A를 직접 입력하세요.",
                      on_change=_apply_shared_input,
                      args=(digest, kind + "." + field, widget))
    return True


def _render_single_editor(digest: str, candidates: dict) -> None:
    """One editor is the source of truth for trade/contract and PDF output."""
    _refresh_shared_widgets(digest, candidates)
    trade = next((doc for kind, doc in candidates.items()
                  if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)), {})
    fields = list(SHARED_FIELDS)
    gaps = missing_fields(candidates)
    gap_keys = {gap.key for gap in gaps}
    if not trade:
        fields = [(key, label) for key, label in fields
                  if key not in {"document_number", "incoterms", "payment_terms",
                                 "item.price_basis", "item.discount_percent", "shipment_reference",
                                 "country_of_origin", "container_count", "ship_to"}]
        fields.extend((("buyer.country", "Buyer · 설립국"),
                       ("seller.country", "Seller · 설립국")))
    else:
        requested_kinds = {key for key in candidates if key in {"PI", "PO", "CI", "PL"}}
        if "PL" not in requested_kinds:
            fields = [(k, label) for k, label in fields if k != "container_count"]
    if isinstance(candidates.get("CONTRACT"), dict):
        for country_field, country_label in (("buyer.country", "Buyer · 설립국"),
                                             ("seller.country", "Seller · 설립국")):
            if not any(key == country_field for key, _ in fields):
                fields.append((country_field, country_label))
    with st.container(border=True):
        st.markdown("#### ✏️ 거래정보 입력 · 수정 (한 번만)")
        st.caption("한 곳에서 입력한 값이 PI/PO/CI/PL·계약서 후보와 PDF 입력에 함께 반영됩니다. Enter 또는 칸 이동 시 자동 저장됩니다.")
        st.caption("전화번호·이메일·담당자 등 선택 항목이 해당 없으면 N/A를 직접 입력하세요. "
                   "확인되지 않은 값은 비워둘 수 있으며, 최종 출력 시 빈칸 유지 승인이 필요합니다.")
        if gaps:
            st.warning("누락 정보 · 입력하거나 최종 출력에서 빈칸 유지 승인: " + "; ".join(gap.label for gap in gaps))
        error = st.session_state.get("ai_intake_followup_error")
        if error:
            st.error(error)
        for pending in _pending_input_errors(digest).values():
            if pending["message"] != error:
                st.error(pending["field"] + ": " + pending["message"])
        last = st.session_state.get("ai_intake_last_answer")
        if last:
            st.caption("최근 반영: " + str(last) + " · 이전 PDF 및 검토 상태 무효화")
        for field, label in fields:
            if field.startswith(("buyer.", "seller.")) and field.split(".")[-1] in {"contact", "phone", "email"}:
                if _render_contact_inputs(digest, candidates, field, label):
                    continue
            widget = "ai_intake_shared_" + _shared_widget_identity(digest) + "_" + field.replace(".", "_")
            _initialize_shared_widget(widget, _shared_current(candidates, field))
            help_text = ("누락 정보입니다. 확인한 값 또는 선택 항목의 N/A를 입력하세요."
                         if field in gap_keys else None)
            st.text_input(label, key=widget, help=help_text, on_change=_apply_shared_input,
                          args=(digest, field, widget))
            if field == "document_number":
                st.button("문서번호 자동 생성", key=widget + "_generate",
                          on_click=_generate_trade_numbers, args=(digest, widget))
            if field in gap_keys and _shared_current(candidates, field):
                st.button(label + " · 현재 값으로 누락 항목에도 반영",
                          key=widget + "_apply_to_missing", on_click=_apply_input_to_missing,
                          args=(digest, field, widget))
        item_count = max((len(doc.get("items") or []) for kind, doc in candidates.items()
                          if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)), default=0)
        for index in range(1, item_count):
            st.markdown("**상품 " + str(index + 1) + "**")
            for field, label in (("product_name", "상품명"), ("quantity", "수량"),
                                 ("unit", "단위"), ("unit_price", "단가"),
                                 ("price_basis", "단가 기준"), ("discount_percent", "할인율 % (없으면 0)")):
                widget = "ai_intake_shared_" + _shared_widget_identity(digest) + "_item_" + str(index) + "_" + field
                _initialize_shared_widget(widget, _shared_current(candidates, f"item.{index}.{field}"))
                st.text_input(label, key=widget, on_change=_apply_extra_item,
                              args=(digest, index, field, widget))
        if isinstance(candidates.get("CONTRACT"), dict):
            _render_contract_confirmations(digest, candidates["CONTRACT"])
        # AI may leave free-text conflicts/missing notes that do NOT disappear
        # when required input widgets are filled. Never silently discard them.
        unresolved = [
            (kind, category, index, note)
            for kind, doc in candidates.items()
            if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)
            for category in ("missing_fields", "conflicts")
            for index, note in enumerate(doc.get(category) or [])
            if isinstance(note, str) and note.strip()
        ]
        try:
            gaps = missing_fields(candidates)
        except RuntimeError as exc:
            st.warning(str(exc))
        else:
            if gaps:
                st.warning("미입력·확인 필요 항목 " + str(len(gaps)) +
                           "개 (전체 문서 기준): " + "; ".join(gap.label for gap in gaps))
                st.caption("아래 최종 출력은 선택한 문서별로 다시 검증합니다. 다른 문서의 누락 항목 때문에 PI 출력을 막지 않습니다.")
            if unresolved:
                st.warning("이전 AI 확인 기록 " +
                           str(len(unresolved)) +
                           "건이 남아 있습니다. 아래에서 실제 조건과 대조하세요.")
            elif not gaps:
                st.success("기본 거래정보 입력 및 이전 AI 기록 확인 완료 · "
                           "은행정보·직인 등 정식 발행 검증은 별도입니다.")
        if unresolved:
            with st.expander("이전 AI 추출 기록 · 확인 필요 (" +
                             str(len(unresolved)) + "건)", expanded=True):
                st.caption("기존 메일에서 추출한 미확정·충돌 기록입니다. "
                           "실제 거래조건과 대조하여 해결된 항목만 확인하세요. "
                           "삭제해도 금액·직인·은행정보 등 기존 발행 검증은 생략되지 않습니다.")
                for kind, category, index, note in unresolved[:40]:
                    kind_label = ("충돌" if category == "conflicts" else "미확정")
                    col1, col2 = st.columns([5, 1])
                    col1.write("**" + kind + " · " + kind_label + "**: " + note)
                    note_hash = sha256(
                        (kind + "|" + category + "|" + note).encode("utf-8")
                    ).hexdigest()[:14]
                    col2.button("해소 확인", key="ai_intake_note_" + digest[:12] +
                                "_" + category + "_" + note_hash + "_" + str(index),
                                on_click=_acknowledge_ai_notice,
                                args=(digest, kind, category, index, note))



def _render_original_contract_final(principal: str, snapshot: dict,
                                    edited_matches: bool) -> None:
    """FINAL documents are rendered ONLY with the existing KE KOREA engine."""
    try:
        from Quotation_KEKOREA.orchestration.workflows.master_contract_final import (
            contract_fingerprint, contract_final_blockers, render_original_final,
        )
    except ImportError:
        st.error("기존 계약서 FINAL 연결 모듈을 불러오지 못했습니다. 앱을 재시작하세요.")
        return
    st.divider()
    st.markdown("#### 기존 KE KOREA 계약서 FINAL 양식 · PDF / Word")
    st.caption("기존 ke-korea.streamlit.app의 contracts.exports.export_contract()를 "
               "그대로 사용합니다. 제목 18pt·소제목 12pt·본문 10pt, "
               "서명란과 검증된 회사 직인은 기존 렌더러가 처리합니다.")
    if not snapshot.get("clauses"):
        st.info("최종 계약서 발행 전 AI 계약서 초안을 작성하고 각 조항을 검토하세요.")
        return
    with st.expander("현재 계약서 조항 · FINAL 출력 전 전체 검토", expanded=True):
        for clause in sorted(snapshot.get("clauses") or [],
                             key=lambda value: value.get("order", 0)):
            st.markdown("**" + str(clause.get("title") or "계약 조항") + "**")
            for sentence in clause.get("sentences") or []:
                st.write(str(sentence.get("text") or ""))
    if not edited_matches:
        st.error("입력 변경값이 아직 문서 후보에 저장되지 않았습니다. 위 입력 오류를 수정하고, "
                 "고급 JSON을 수정했다면 '고급 JSON 변경값 후보에 반영'을 클릭하세요.")
        return
    env = document_export_env(st.secrets, os.environ)
    try:
        fingerprint = contract_fingerprint(snapshot)
        blockers = contract_final_blockers(snapshot, env)
    except (TypeError, ValueError, KeyError):
        st.error("최종 계약서 형식 검증에 실패했습니다. 현재 조건을 확인하세요.")
        return
    if blockers:
        st.warning("FINAL 발행 전 미확정 조건 " + str(len(blockers)) + "건")
        with st.expander("발행 전 확인 및 보완 사항", expanded=True):
            for reason in blockers[:50]:
                st.write("• " + str(reason))
    else:
        st.success("계약조건과 원본 FINAL 엔진의 발행 검증을 통과했습니다.")
    approval_key = "master_contract_final_approved_" + fingerprint[:20]
    approved = st.checkbox(
        "현재 계약서의 모든 조항·당사자·거래조건을 원문과 확인하고 이 버전의 FINAL 생성을 승인합니다.",
        key=approval_key)
    # Identical authorization standard as the original contract workspace:
    # an existing administrator login OR its separately configured seal password.
    try:
        from Auth.gate import is_authenticated
        admin_authorized = bool(is_authenticated(st))
    except (ImportError, AttributeError, TypeError, ValueError):
        admin_authorized = False
    if admin_authorized:
        st.caption("기존 KE KOREA 관리자 로그인으로 직인 사용 권한 확인")
        authorized = True
    else:
        password = st.text_input(
            "기존 계약서 FINAL 직인 사용 암호", type="password",
            key="master_contract_seal_access_" + fingerprint[:20])
        configured = _server_value("CONTRACT_FINAL_SEAL_PASSWORD")
        authorized = bool(configured) and hmac.compare_digest(
            str(password), str(configured))
        if not configured:
            st.caption("기존 관리자 로그인 또는 동일한 CONTRACT_FINAL_SEAL_PASSWORD "
                       "서버 설정이 필요합니다. 비밀번호는 저장하거나 출력하지 않습니다.")
    disabled = bool(blockers) or not approved or not authorized
    if st.button("기존 KE KOREA FINAL 양식으로 PDF·Word 생성",
                 disabled=disabled, key="master_contract_final_export_" +
                 fingerprint[:20], type="primary"):
        try:
            results = render_original_final(
                snapshot, env, principal=principal, approved=approved,
                authorized=authorized, expected_fingerprint=fingerprint)
        except (ImportError, ValueError, RuntimeError, TypeError,
                PermissionError, OSError) as exc:
            # Raw third-party errors must not expose secret PNGs or account data.
            st.error("계약서 FINAL 생성 실패: 승인 상태·직인 설정·서버 로그를 확인하세요.")
        else:
            st.session_state["master_contract_final_files"] = (
                fingerprint, results)
            st.success("기존 계약서 FINAL 양식으로 PDF와 Word를 생성했습니다. "
                       "메일 전송은 하지 않았습니다.")
    result = st.session_state.get("master_contract_final_files")
    if result and result[0] == fingerprint and not disabled:
        for ext, mime in (
                ("pdf", "application/pdf"),
                ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")):
            output = result[1].get(ext)
            if output:
                st.download_button(
                    "기존 양식 FINAL 계약서 " + ext.upper() + " 다운로드",
                    data=output["content"], file_name=output["filename"],
                    mime=mime, key="master_contract_final_download_" +
                    fingerprint[:20] + "_" + ext)


def _reference_panel():
    st.markdown("#### 기존 계약서 참고 (서버 내 조회 전용)")
    st.caption("기존 계약서는 모델에 전송하거나 새 계약서에 자동 복사하지 않습니다. 사용자가 직접 비교하기 위한 별도 읽기 전용 화면입니다.")
    try:
        from Quotation_KEKOREA.orchestration.adapters.contract_library import (
            make_reader, read_contract_list,
        )
        env = {key: _server_value(key) for key in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}
        if not all(env.values()):
            st.caption("기존 계약서 조회를 사용하려면 Supabase 서버 연결이 필요합니다.")
            return
        repo = make_reader(env)
        records = read_contract_list(repo)
        if not records:
            st.caption("저장된 계약서가 없습니다.")
            return
        options = {f"{r.get('title') or 'Untitled'} · {r['id']}": str(r["id"])
                   for r in records if r.get("id")}
        selected = st.selectbox("참고할 계약서", ["선택 안 함"] + list(options),
                                key="ai_intake_reference")
        if selected == "선택 안 함":
            return
        identifier = options[selected]
        from Quotation_KEKOREA.orchestration.adapters.contract_library import read_contract_versions
        versions = read_contract_versions(repo, identifier)
        if not versions:
            st.info("선택한 계약서에 저장된 버전이 없습니다.")
            return
        revision = st.selectbox("참고 리비전", [v["revision"] for v in versions],
                                key="ai_intake_reference_revision")
        snapshot = selected_contract_reference(repo, identifier, revision)
        st.markdown("**선택한 기존 계약서의 조항 (참고 전용)**")
        for clause in snapshot.get("clauses", []):
            st.markdown("**" + str(clause.get("title") or "조항") + "**")
            for sentence in clause.get("sentences", []):
                st.write(str(sentence.get("text") or ""))
    except (ValueError, TypeError, KeyError) as exc:
        st.error("기존 계약서 조회에 실패했습니다. 연결 상태와 저장 데이터를 확인하세요.")



def _render_missing_inputs(digest: str, candidate_map: dict) -> None:
    st.markdown("#### 부족한 정보 입력 · 실시간 반영")
    st.caption("확인된 내용을 입력하고 Enter를 누르거나 다른 칸으로 이동하면 PI·계약서에 동시에 반영됩니다.")
    gap_list = missing_fields(candidate_map)
    answered = st.session_state.get("ai_intake_last_answer")
    if answered:
        st.success("입력 반영: " + str(answered) + " · 기존 초안·승인은 무효화되었습니다.")
    error = st.session_state.get("ai_intake_followup_error")
    if error:
        st.error(error)
    if gap_list:
        st.warning(f"현재 누락된 항목 {len(gap_list)}개")
        for gap in gap_list:
            widget_key = "ai_intake_answer_" + gap.key.replace(".", "_")
            st.text_input(
                gap.label, key=widget_key,
                placeholder="정확한 내용을 입력하고 Enter",
                on_change=_handle_missing_answer,
                args=(digest, gap.key, widget_key),
            )
    else:
        st.success("필수 입력칸의 빈값을 모두 보완했습니다. AI 제안에 대한 실무 검토는 별도로 필요합니다.")



def _render_quick_corrections(digest: str, candidate_map: dict) -> None:
    """Always-visible editable commercial facts, even if AI marked them complete.

    Form submit updates both trade and contract candidates. It does not approve
    legal parties or generate any final document.
    """
    st.markdown("#### ✏️ 거래조건 직접 입력 · 수정")
    st.caption("AI가 Buyer/Seller를 잘못 판단했거나 통화를 비워둔 경우 여기서 직접 수정하세요.")
    trade = next((v for k, v in candidate_map.items()
                  if k in {"PI", "PO", "CI", "PL"} and isinstance(v, dict)), {})
    contract = candidate_map.get("CONTRACT") or {}
    def current_party(role: str) -> str:
        from Quotation_KEKOREA.orchestration.workflows.label_typos import canonical_label
        party = trade.get(role) or {}
        name = str(party.get("legal_name") or "").strip()
        if name:
            return name
        return next((str(p.get("legal_name") or "") for p in contract.get("parties", [])
                     if role in [canonical_label(str(x)) or str(x) for x in p.get("roles", [])]), "")
    with st.form("ai_intake_quick_corrections", clear_on_submit=False):
        buyer = st.text_input("Buyer · 구매자 법인명", value=current_party("buyer"))
        seller = st.text_input("Seller · 판매자 법인명", value=current_party("seller"))
        currency = st.text_input("통화 (예: USD)", value=str(trade.get("currency") or ""))
        additional = st.text_area("추가 거래조건 메모 (참고용 · 자동 적용되지 않음)",
                                  placeholder="예: Buyer는 TENGYAO, Seller는 KE KOREA")
        submitted = st.form_submit_button("입력한 거래조건 적용", type="primary")
    if submitted:
        try:
            updated = deepcopy(candidate_map)
            for key, value in (("buyer.legal_name", buyer),
                               ("seller.legal_name", seller),
                               ("currency", currency)):
                if value.strip():
                    updated = apply_answer(updated, key, value)
            _remember_candidate_bundle(digest, updated, replace_editor=True)
            st.session_state["ai_intake_last_answer"] = "Buyer / Seller / 통화"
            st.success("입력 내용이 PI·계약서 후보에 반영됐습니다. 아래 실시간 반영 결과를 확인하세요.")
            st.rerun()
        except (ValueError, TypeError) as exc:
            st.error("거래조건 수정 실패: " + str(exc))



def _render_recovery_inputs(digest: str, analysis: dict, requested: list[str]) -> None:
    """Independent of candidate builders; never hide editing after extraction."""
    st.markdown("#### ✏️ 부족한 거래정보 입력 · 반드시 확인")
    st.caption("아래 칸은 모바일에서도 입력할 수 있습니다. 적용하면 문서 후보를 다시 구성합니다.")
    parties = analysis.get("parties") or []
    def found(role: str) -> str:
        return next((str(p.get("legal_name") or "") for p in parties
                     if isinstance(p, dict) and role in [
                         canonical_label(str(x)) or str(x) for x in (p.get("roles") or [])
                     ]), "")
    terms = analysis.get("terms") or []
    currency = next((str(t.get("value") or "") for t in terms
                     if isinstance(t, dict) and t.get("key") == "currency"), "")
    with st.form("ai_intake_recovery_form", clear_on_submit=False):
        buyer = st.text_input("Buyer · 구매자 법인명", value=found("buyer"))
        seller = st.text_input("Seller · 판매자 법인명", value=found("seller"))
        buyer_address = st.text_input("Buyer · 구매자 법인 주소", value=next((str(p.get("address") or "") for p in parties if isinstance(p, dict) and "buyer" in [canonical_label(str(x)) or str(x) for x in (p.get("roles") or [])]), ""))
        seller_address = st.text_input("Seller · 판매자 법인 주소", value=next((str(p.get("address") or "") for p in parties if isinstance(p, dict) and "seller" in [canonical_label(str(x)) or str(x) for x in (p.get("roles") or [])]), ""))
        currency_value = st.text_input("통화 · USD 등", value=currency)
        submitted = st.form_submit_button("거래조건 저장 및 문서정보 다시 만들기", type="primary")
    if not submitted:
        return
    revised = deepcopy(analysis)
    revised.setdefault("parties", [])
    for role, value, address in (("buyer", buyer, buyer_address), ("seller", seller, seller_address)):
        if not value.strip() and not address.strip():
            continue
        party = next((p for p in revised["parties"] if isinstance(p, dict) and role in [
            canonical_label(str(x)) or str(x) for x in (p.get("roles") or [])
        ]), None)
        if party is None:
            party = {"roles": [role], "legal_name": "", "address": "",
                     "country": "", "status": "suggested", "source_refs": []}
            revised["parties"].append(party)
        if value.strip():
            party["legal_name"] = value.strip()
        if address.strip():
            party["address"] = address.strip()
        party["status"] = "suggested"
    if currency_value.strip():
        revised.setdefault("terms", [])
        term = next((t for t in revised["terms"] if isinstance(t, dict)
                     and t.get("key") == "currency"), None)
        if term is None:
            term = {"key": "currency", "value": "", "status": "suggested", "source_refs": []}
            revised["terms"].append(term)
        term["value"] = currency_value.strip()
    # Recovery is an explicit user edit, not an AI confirmation or legal approval.
    # Normalize *all* AI statuses before reusing the strict candidate builders;
    # otherwise an unrelated confirmed term can block even a valid Buyer edit.
    for party in revised.get("parties", []):
        if isinstance(party, dict):
            party["status"] = "suggested"
    for term in revised.get("terms", []):
        if isinstance(term, dict):
            term["status"] = "suggested"
            if term.get("key") == "currency":
                raw_currency = str(term.get("value") or "").strip()
                currency_aliases = {"$": "USD", "US$": "USD", "USD$": "USD",
                                    "₩": "KRW", "￦": "KRW", "€": "EUR"}
                term["value"] = currency_aliases.get(raw_currency.upper(), raw_currency.upper())
    st.session_state["ai_intake_result"] = (digest, revised)
    st.session_state.pop("ai_intake_drafts", None)
    st.session_state.pop("master_legacy_files", None)
    try:
        bundle = {}
        for kind in requested:
            if kind == "CONTRACT":
                bundle[kind] = make_contract_candidate(revised, "ko" if st.session_state.get("ai_intake_language") == "한국어" else "en")
            else:
                bundle[kind] = make_trade_candidate(kind, revised,
                    product_family=st.session_state.get("ai_intake_family", "solar_cell"))
        current=st.session_state.get('ai_intake_candidates')
        if st.session_state.get('ai_intake_mail_source') and current and current[0]==digest:
            bundle=deepcopy(current[1])
            for role,value,address in (('buyer',buyer,buyer_address),('seller',seller,seller_address)):
                if value.strip():bundle=apply_answer(bundle,role+'.legal_name',value.strip())
                if address.strip():bundle=apply_answer(bundle,role+'.address',address.strip())
            if currency_value.strip():bundle=apply_answer(bundle,'currency',currency_value.strip())
        if bundle:
            _remember_candidate_bundle(digest, bundle, replace_editor=True)
        st.session_state.pop("ai_intake_recovery_error", None)
        st.success("입력한 거래조건을 저장하고 문서정보를 다시 만들었습니다.")
    except (ValueError, TypeError, KeyError, RuntimeError) as exc:
        st.session_state["ai_intake_recovery_error"] = str(exc)[:300]
        st.warning("입력 내용은 저장했습니다. 문서 생성에 필요한 추가 항목을 확인하세요.")
    st.rerun()


def render_ai_intake(principal: str):
    if not principal:
        raise PermissionError("로그인이 필요합니다.")
    st.subheader("AI 거래조건 추출 · 기존 문서 엔진 연결")
    st.caption("문서 작업은 이 화면에서 진행합니다. 검토용 초안과 최종 발행 문서는 기존 검증·승인 규칙에 따라 구분합니다.")
    st.caption("기존 계약서 분석 AI를 사용해 자연어에서 거래조건을 제안합니다. 확정·발행·전송은 자동으로 하지 않습니다.")
    st.info("AI 요청에는 아래 입력 내용과 직접 선택한 참고파일만 전송합니다. 저장된 계약서는 모델에 전달되지 않습니다.")
    mail_source = st.session_state.get('ai_intake_mail_source')
    mail_mode = bool(mail_source)
    mail_processing_mode = None
    if mail_mode:
        st.markdown("#### 메일 업무 처리 방식 선택")
        mail_processing_mode = st.radio(
            "처리 방식", ["AI 자동 분석", "직접 수정 후 분석"],
            index=1, horizontal=True, key="ai_intake_mail_processing_mode",
        )
        if mail_processing_mode == "AI 자동 분석":
            st.info("현재 입력된 요청을 바로 AI로 분석합니다. 내용을 수정하려면 '직접 수정 후 분석'을 선택하세요. 문서 종류 확인과 명시적 동의·실행이 필요합니다.")
        else:
            st.info("메일 내용을 직접 수정하거나 거래조건을 추가한 후 AI 분석을 실행할 수 있습니다.")
    instruction = st.text_area("업무 요청 및 거래조건", height=185,
        placeholder="예: 한화 M10 solar cell 100 PCS, USD 0.20/pc, EXW Seoul 조건으로 PI와 계약서 초안을 만들어줘.",
        key="ai_intake_instruction",
        disabled=mail_mode and mail_processing_mode == "AI 자동 분석")
    if st.session_state.get('ai_intake_mail_notice'):
        st.warning(st.session_state['ai_intake_mail_notice'])
    requested = classify("", instruction)
    attachments = []
    if mail_mode:
        st.caption('선택한 메일에서 가져온 요청입니다. 문서 종류를 수정할 수 있습니다. CIPL = CI + PL.')
        requested = st.multiselect('준비할 문서', list(DOC_TYPES),
            default=mail_source.get('kinds', []), key='ai_intake_mail_kinds')
        attachments = st.session_state.get('ai_intake_mail_attachments', [])
        if attachments:
            st.caption('선택한 첨부: ' + ', '.join(a['name'] for a in attachments))
        if 'CI' in requested:
            st.caption('CI 출력에는 기존 정책에 따라 원본 PI 첨부가 필요합니다. 메일에서 선택하지 않았다면 여기서 추가하세요.')
            uploads=st.file_uploader('원본 PI 등 추가 참고파일',type=['pdf','png','jpg','jpeg','webp'],
                accept_multiple_files=True,key='ai_intake_mail_pi_uploads')
            if uploads:
                from Quotation_KEKOREA.agent.attachments import prepare_uploads
                try:
                    attachments = attachments + prepare_uploads(uploads)
                except ValueError as exc:
                    st.error(str(exc))
                    attachments = None
    st.caption("감지된 문서 종류: " + (", ".join(requested) if requested else "없음 · PI/PO/CI/PL/계약서를 명시하세요"))
    language = st.radio("계약서 언어", ["한국어", "English"], horizontal=True,
                        key="ai_intake_language")
    family = st.selectbox("무역서류 상품군", ["solar_cell", "wafer", "polysilicon",
                                            "solar_module", "cosmetics"], key="ai_intake_family")
    config = _model_config()
    ready = bool(config.get("OPENAI_API_KEY") and
                 (config.get("OPENAI_MODEL") or config.get("CONTRACT_OPENAI_MODEL")))
    if not ready:
        st.warning("AI 모델 연결을 위해 별도 MASTER GRAPH 앱의 Secrets에 OPENAI_API_KEY와 OPENAI_MODEL이 필요합니다.")
    consent = st.checkbox("입력 내용과 직접 선택한 참고파일만 외부 AI API에 전송하는 데 동의합니다. 저장된 계약서는 전송하지 않습니다.",
                          key="ai_intake_consent")
    digest_source = instruction + "|" + language + "|" + family
    if mail_mode:
        digest_source += '|' + ','.join(requested) + '|' + _fingerprint(''.join(
            _fingerprint(a['name']) + sha256(a['data']).hexdigest() for a in attachments or []))
    digest = _fingerprint(digest_source)
    button_text = ("AI 자동 분석 실행" if mail_processing_mode == "AI 자동 분석"
                   else "수정한 내용으로 AI 분석" if mail_mode
                   else "AI 거래조건 추출")
    manual_extract = st.button(button_text, key="ai_intake_extract", type="primary",
                 disabled=not (consent and ready and requested and instruction.strip() and attachments is not None))
    # Consume any pending token from a pre-upgrade mailbox session, but NEVER
    # run the external model until the user explicitly clicks the action here.
    if consume_pending(st.session_state, instruction):
        st.info("기존 메일 요청을 가져왔습니다. 처리 방식과 거래조건을 확인하고 AI 분석을 실행해 주세요.")
    if manual_extract and consent and ready and requested and attachments is not None:
        # A new extraction must not inherit prior editable widget values.
        for key in list(st.session_state):
            if str(key).startswith("ai_intake_shared_"):
                st.session_state.pop(key, None)
        st.session_state.pop("ai_intake_result", None)
        st.session_state.pop("ai_intake_candidates", None)
        st.session_state.pop("ai_intake_drafts", None)
        try:
            with st.spinner("거래조건을 분석합니다."):
                if mail_mode:
                    bundle=extract_mail_candidates(instruction,requested,config,consent=consent,
                        language='ko' if language=='한국어' else 'en',family=family,attachments=attachments)
                    extracted,candidate_map=bundle['analysis'],bundle['candidates']
                else:
                    extracted = extract_candidate(instruction, config, consent=consent)
                    candidate_map = {}
                    for kind in requested:
                        if kind == "CONTRACT":
                            candidate_map[kind] = make_contract_candidate(
                                extracted, "ko" if language == "한국어" else "en")
                        else:
                            candidate_map[kind] = make_trade_candidate(
                                kind, extracted, product_family=family)
            st.session_state["ai_intake_result"] = (digest, extracted)
            _remember_candidate_bundle(digest, candidate_map, replace_editor=True)
        except (PermissionError, ValueError, RuntimeError, TypeError) as exc:
            st.error("AI 거래조건 추출 실패: " + str(exc)[:400])

    result = st.session_state.get("ai_intake_result")
    if result and result[0] != digest:
        st.warning("원래 업무 요청이 변경되었습니다. 기존 AI 추출 결과 및 검토 승인은 사용하지 마세요.")
    if result and result[0] == digest:
        analysis = result[1]
        st.caption("AI 원본 추출은 아래 접힌 참고란에 남기고, 모든 실제 문서정보 수정은 하나의 입력창에서 처리합니다.")
        with st.expander("AI 추출 원본 (수정 전 · 참고용)", expanded=False):
            if analysis.get("parties"):
                st.dataframe([{"역할": ", ".join(canonical_label(str(role)) or str(role) for role in p.get("roles", [])),
                               "회사명": p.get("legal_name") or "미입력",
                               "주소": p.get("address") or "미입력"}
                              for p in analysis["parties"]], width="stretch", hide_index=True)
            if analysis.get("terms"):
                st.dataframe([{"항목": x.get("key"), "값": x.get("value"),
                               "검토 상태": "AI 제안"} for x in analysis["terms"]],
                             width="stretch", hide_index=True)
            if analysis.get("questions"):
                for question in analysis["questions"][:2]:
                    st.warning("필수 확인: " + str(question))
            if analysis.get("issues"):
                st.markdown("**추가 AI 검토 사항**")
                for issue in analysis["issues"]:
                    st.write(str(issue.get("message") or issue))
        st.caption("모든 금액·수량·법인명은 원문과 대조해야 합니다. AI 제안만으로 최종 문서 승인은 할 수 없습니다.")
        if st.button("기존 엔진용 초안 입력 만들기", key="ai_intake_build_candidates"):
            try:
                candidate_map = {}
                for kind in requested:
                    if kind == "CONTRACT":
                        candidate_map[kind] = make_contract_candidate(
                            analysis, "ko" if language == "한국어" else "en")
                    else:
                        candidate_map[kind] = make_trade_candidate(kind, analysis,
                                                                  product_family=family)
                if mail_mode:
                    original = st.session_state.get('ai_intake_candidates')
                    if not original or original[0] != digest:
                        raise ValueError('메일 조건을 다시 추출해 주세요.')
                    candidate_map = deepcopy(original[1])
                _remember_candidate_bundle(digest, candidate_map, replace_editor=True)
            except (ValueError, TypeError) as exc:
                st.error("초안 입력 구성 실패: " + str(exc))
    candidates = st.session_state.get("ai_intake_candidates")
    if candidates and candidates[0] == digest and isinstance(candidates[1], dict):
        # Existing Streamlit sessions can retain AI results from a previous
        # schema version; normalize all PI/PO/CI/PL roles BEFORE any input,
        # strict validator or export uses their nested .get() attributes.
        current_bundle = candidates[1]
        repaired = {kind: normalize_trade_values(value)
                    if kind in {"PI", "PO", "CI", "PL"} and isinstance(value, dict)
                    else value
                    for kind, value in current_bundle.items()}
        if repaired != current_bundle:
            _remember_candidate_bundle(digest, repaired, replace_editor=True)
            candidates = st.session_state.get("ai_intake_candidates")
        _render_single_editor(digest, candidates[1])
        candidates = st.session_state.get("ai_intake_candidates")
        editor_matches = not bool(_pending_input_errors(digest))
        st.markdown("#### 실시간 반영 결과")
        for kind, data in candidates[1].items():
            if kind in ("PI", "PO", "CI", "PL"):
                with st.container(border=True):
                    st.markdown("**" + kind + " · 현재 거래정보**")
                    st.write("Buyer:", (data.get("buyer") or {}).get("legal_name") or "미입력")
                    st.write("Seller:", (data.get("seller") or {}).get("legal_name") or "미입력")
                    if mail_mode and data.get('items'):
                        st.dataframe([{k:row.get(k) for k in ('product_name','quantity','unit','unit_price','price_basis','package_count','net_weight_kg','gross_weight_kg')}
                                      for row in data['items']],hide_index=True,width='stretch')
                    if (data.get("items") or [{}])[0].get("price_source"):
                        st.write("가격 출처 (참고):", data["items"][0]["price_source"])
            elif kind == "CONTRACT":
                st.caption("계약서 당사자와 조건에도 답변을 함께 반영합니다. 생성된 조항은 조건이 바뀌면 무효화됩니다.")
        # A new editor key for each candidate revision prevents stale widget state.
        editor_revision = _fingerprint(json.dumps(candidates[1], ensure_ascii=False, sort_keys=True))[:16]
        with st.expander("고급 설정 · 전체 문서 JSON 직접 수정"):
            raw = st.text_area("문서별 JSON 조건 (고급 편집)",
                value=json.dumps(candidates[1], ensure_ascii=False, indent=2),
                height=310, key="ai_intake_editable_" + editor_revision)
            try:
                pending_json = json.loads(raw)
                json_changed = pending_json != candidates[1]
            except (ValueError, TypeError):
                pending_json = None
                json_changed = True
                st.warning("고급 JSON 문법을 확인해 주세요. 저장 전에는 FINAL 발행에 사용되지 않습니다.")
            if json_changed and st.button("고급 JSON 변경값 후보에 반영",
                                          key="ai_intake_commit_json"):
                try:
                    if not isinstance(pending_json, dict):
                        raise ValueError("문서별 JSON 객체여야 합니다.")
                    from Quotation_KEKOREA.contracts.models import validate_snapshot
                    if "CONTRACT" in pending_json:
                        pending_json["CONTRACT"] = validate_snapshot(
                            pending_json["CONTRACT"])
                        # Arbitrary JSON editing cannot carry over old approvals.
                        for party in pending_json["CONTRACT"]["parties"]:
                            party["status"] = "suggested"
                        for term in pending_json["CONTRACT"]["terms"]:
                            term["status"] = "suggested" if str(term.get("value") or "").strip() else "missing"
                        # A changed contract requires fresh AI clauses or
                        # explicit clause verification before the final approval.
                    st.session_state.pop("ai_intake_pending_input_errors", None)
                    st.session_state.pop("ai_intake_followup_error", None)
                    _remember_candidate_bundle(digest, pending_json, replace_editor=True)
                    st.success("고급 JSON 변경값을 후보에 반영했습니다. 계약조건을 다시 확인하세요.")
                    st.rerun()
                except (TypeError, ValueError, KeyError):
                    st.error("문서 후보 형식이 올바르지 않습니다. 변경값을 검토해 주세요.")
        edited_key = _fingerprint(digest + raw)
        if st.button("기존 문서 엔진으로 검증·DRAFT 생성", key="ai_intake_prepare",
                     disabled=not editor_matches):
            st.session_state.pop("ai_intake_drafts", None)
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("최상위 값은 문서별 JSON 객체여야 합니다.")
                data = {kind: normalize_trade_values(source)
                        if kind in {"PI", "PO", "CI", "PL"} and isinstance(source, dict) else source
                        for kind, source in data.items()}
                run = prepare_documents(new_request(instruction, data, requested=requested if mail_mode else None))
                st.session_state["ai_intake_drafts"] = (edited_key, run)
            except (ValueError, TypeError, KeyError) as exc:
                st.error("문서 생성 실패: " + str(exc))
        drafts = st.session_state.get("ai_intake_drafts")
        if drafts and drafts[0] != edited_key:
            st.warning("거래조건을 수정했습니다. 이전 파일은 더 이상 사용할 수 없습니다. 재검증하세요.")
        if drafts and drafts[0] == edited_key:
            run = drafts[1]
            st.caption("문서 상태: " + run.status)
            for doc in run.documents:
                with st.container(border=True):
                    st.markdown("**" + doc.kind + " · 검토용 초안**")
                    if doc.blockers:
                        with st.expander("누락·확인 필요 사항", expanded=True):
                            for issue in doc.blockers:
                                st.write(str(issue))
                    for fmt, file in (doc.files or {}).items():
                        st.download_button(f"{doc.kind} {fmt.upper()} DRAFT 다운로드",
                            data=file["content"], file_name=file["filename"],
                            mime=file["mime"], key=f"ai_intake_download_{doc.kind}_{fmt}")
            st.caption("생성된 파일은 최종 발행·계약 체결·메일 발송에 사용할 수 없습니다.")
        # One shared editor above owns all commercial facts. The strict
        # validator remains informative, not an additional input window.
        trade_data = {k: v for k, v in candidates[1].items()
                      if k in ("PI", "PO", "CI", "PL") and isinstance(v, dict)}
        if trade_data:
            with st.expander("현재 입력 확인사항 · 누락·오류 상세", expanded=True):
                for kind, trade in trade_data.items():
                    try:
                        report = _current_trade_export_review().review_trade_document(
                            kind, trade, final=True, allow_incomplete=True)
                        _render_trade_issue_list(kind, report)
                    except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
                        # Corrupt historical candidate data should be a review
                        # warning, not an unhandled Streamlit exception.
                        st.warning(kind + " 확인 필요: 거래정보 형식을 다시 확인해 주세요.")
        st.divider()
        st.markdown("#### 기존 KE KOREA 양식 · PI / PO / CI / PL PDF·Excel")
        st.caption("현재 MASTER 앱에서 기존 업무 에이전트의 검증·직인·페이지 분할·PDF/XLSX 엔진을 직접 호출합니다. 기존 앱으로 이동하지 않습니다.")
        trade_kinds = [kind for kind in candidates[1] if kind in ("PI", "PO", "CI", "PL")]
        if trade_kinds:
            if st.button("회사 직인 · 기존 서식 연결 확인", key="master_seal_diagnostic"):
                document_env = document_export_env(st.secrets, os.environ)
                state, explanation = seal_health(document_env)
                if state == "ready":
                    st.success(explanation)
                else:
                    st.warning(explanation)
            st.caption("확인된 거래조건은 기존 KE KOREA 양식과 회사 직인을 사용합니다. "
                       "미확정 항목이 있거나 발행 검증이 통과하지 않으면, 같은 입력값으로 "
                       "직인 없는 '검토용 PDF' 파일을 생성합니다.")
            if st.button("현재 거래정보로 PDF 생성", key="master_legacy_export", type="primary",
                         disabled=not editor_matches):
                try:
                    render_master_trade_draft, render_incomplete_trade_pdf = (
                        _current_pdf_export_renderers()
                    )
                    # Keep existing draft data if a module is unavailable.
                    updated = json.loads(raw)
                    if not isinstance(updated, dict):
                        raise ValueError("문서 데이터는 JSON 객체여야 합니다.")
                    env = document_export_env(st.secrets, os.environ)
                    st.session_state.pop("master_legacy_files", None)
                    results = {}
                    errors = {}
                    for kind in trade_kinds:
                        try:
                            results[kind] = render_master_trade_draft(kind, updated[kind], env)
                        except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, OSError) as exc:
                            # Do not weaken the original sealed PDF issuance rules.
                            # Produce a visibly unapproved PDF using exactly the
                            # user's still-unconfirmed facts (no fake bank data).
                            try:
                                results[kind] = render_incomplete_trade_pdf(kind, updated[kind])
                                errors[kind] = (
                                    _formal_pdf_hold_reason(kind, exc, env) +
                                    " 아래 PDF는 정식 발행본이 아닌 내부 검토용입니다."
                                )
                            except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, OSError) as fallback:
                                errors[kind] = ("PDF 생성 오류: " + str(fallback))[:400]
                    st.session_state["master_legacy_files"] = (edited_key, results, errors)
                except (ValueError, TypeError, KeyError, RuntimeError, ImportError, OSError) as exc:
                    st.error("PDF 생성 실패: " + str(exc)[:400])
            export_bundle = st.session_state.get("master_legacy_files")
            if export_bundle and export_bundle[0] != edited_key:
                st.warning("거래조건이 변경되어 이전 PDF·Excel 파일을 무효화했습니다. 다시 생성하세요.")
            if export_bundle and export_bundle[0] == edited_key:
                for kind, reason in export_bundle[2].items():
                    st.warning(kind + " 정식 양식 발행 보류: " + reason)
                    try:
                        report = _current_trade_export_review().review_trade_document(
                            kind, json.loads(raw)[kind])
                        _render_trade_issue_list(kind, report)
                    except (ValueError, TypeError, KeyError, AttributeError, RuntimeError):
                        st.warning(kind + " 입력 데이터 형식을 확인하세요.")
                for kind, files in export_bundle[1].items():
                    with st.container(border=True):
                        title = ("미확정 내부 검토용 PDF (정식 발행 아님)"
                                 if any(asset.get("review_only") for asset in files.values())
                                 else "기존 KE KOREA 양식 검토용 문서")
                        st.markdown("**" + kind + " · " + title + "**")
                        for fmt, file in files.items():
                            st.download_button(kind + " " + fmt.upper() + " DRAFT 다운로드",
                                               data=file["content"], file_name=file["filename"],
                                               mime=file["mime"], key="master_legacy_" + kind + "_" + fmt)
            st.caption("미확정 항목이 있어도 검토용 PDF를 생성할 수 있습니다. "
                       "아래 최종 PDF에서는 누락 항목을 빈칸으로 유지하도록 직접 승인할 수 있습니다.")
        _render_trade_final_panel(digest, candidates[1], document_export_env(st.secrets, os.environ),
                                  edited_matches=not json_changed)
        if "CONTRACT" in candidates[1]:
            st.caption("계약서 DRAFT는 기존 초안 엔진, FINAL은 기존 원본 계약서 "
                       "출력 엔진을 사용합니다. 두 방식 모두 별도 검토·승인 정책을 유지합니다.")
            try:
                raw_snapshot = json.loads(raw).get("CONTRACT")
            except (TypeError, ValueError, AttributeError):
                raw_snapshot = None
            _render_original_contract_final(
                principal, candidates[1]["CONTRACT"],
                edited_matches=(raw_snapshot == candidates[1]["CONTRACT"] and editor_matches))
        doc = candidates[1].get("CONTRACT")
        if doc and not doc.get("clauses"):
            st.divider()
            st.markdown("#### 기존 LangGraph로 계약서 AI 초안 작성")
            st.warning("실제 AI 문서 생성에는 API 요금이 발생할 수 있으며, 수정한 계약서 조건이 AI 모델로 전송됩니다.")
            draft_consent = st.checkbox("현재 계약서 조건을 AI에 전송해 검토용 조항을 생성하는 데 동의합니다.",
                                       key="ai_intake_contract_consent")
            use_approved_rag = st.checkbox(
                "승인된 공통 RAG 참고 메모를 검색하여 초안 작성에 활용",
                value=True, key="ai_intake_use_approved_rag",
                help="현재 계약의 조건이 우선합니다. 기존 계약서 원문이나 개별 계약 자료는 자동 전송하지 않습니다.",
            )
            if st.button("AI 계약서 초안 작성", disabled=not (draft_consent and ready),
                         key="ai_intake_contract_draft"):
                try:
                    edited = json.loads(raw)
                    current = edited.get("CONTRACT")
                    if not isinstance(current, dict):
                        raise ValueError("현재 계약서 데이터를 입력해 주세요.")
                    with st.spinner("기존 계약서 LangGraph가 검토용 조항을 생성합니다."):
                        draft_config = dict(config)
                        if use_approved_rag:
                            draft_config.update({key: _server_value(key) for key in (
                                "SUPABASE_URL", "SUPABASE_SECRET_KEY",
                                "CONTRACT_LIBRARY_EMBEDDING_MODEL",
                            )})
                        generated = generate_contract_draft(
                            current, draft_config, consent=draft_consent,
                            use_library=use_approved_rag,
                        )
                    # Use an explicit callback state, never modify saved contract.
                    updated = deepcopy(edited)
                    updated["CONTRACT"] = generated
                    _remember_candidate_bundle(digest, updated, replace_editor=True)
                    st.success("새 DRAFT 조항을 생성했습니다. 조건과 문구를 확인한 뒤 검증·다운로드하세요.")
                    st.rerun()
                except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                    st.error("AI 계약서 생성 실패: " + str(exc)[:400])
    with st.expander("기존 저장된 계약서 참고 · AI에 전송하지 않음"):
        _reference_panel()
