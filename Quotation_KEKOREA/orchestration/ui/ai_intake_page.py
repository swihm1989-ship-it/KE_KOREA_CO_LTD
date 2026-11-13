"""Authenticated AI intake screen; no stored private contract sent to the model."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
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
    extract_candidate, make_contract_candidate, make_trade_candidate,
    generate_contract_draft, selected_contract_reference,
)
from Quotation_KEKOREA.orchestration.workflows.unified_review import (
    new_request, prepare_documents,
)
from Quotation_KEKOREA.orchestration.ui.saved_contracts import _server_value
from Quotation_KEKOREA.orchestration.workflows.document_assets import (
    document_export_env, seal_health,
)
from Quotation_KEKOREA.orchestration.workflows.intake_followups import missing_fields, apply_answer


def _fingerprint(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _model_config():
    return {k: _server_value(k) for k in (
        "OPENAI_API_KEY", "OPENAI_MODEL", "CONTRACT_OPENAI_MODEL",
    )}


def _remember_candidate_bundle(digest: str, candidate_map: dict) -> None:
    """Synchronize answer widgets and advanced editor in memory."""
    candidate_map = {kind: normalize_trade_values(data) if kind in {"PI", "PO", "CI", "PL"} else data
                     for kind, data in candidate_map.items()}
    st.session_state["ai_intake_candidates"] = (digest, candidate_map)
    st.session_state.pop("ai_intake_drafts", None)


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
    ("seller.legal_name", "Seller · 판매자 법인명"),
    ("seller.address", "Seller · 판매자 법인 주소"),
    ("currency", "통화 (USD / KRW / EUR / CNY)"),
    ("incoterms", "인도조건 및 장소"),
    ("payment_terms", "결제조건"),
    ("item.product_name", "상품명 및 규격"),
    ("item.quantity", "수량"),
    ("item.unit", "수량 단위"),
    ("item.unit_price", "단가"),
    ("item.price_basis", "단가 기준"),
    ("shipment_reference", "선적 참조번호 (CI / PL)"),
    ("country_of_origin", "제품 원산지 (CI)"),
)


def _shared_current(candidates: dict, field: str) -> str:
    """Read the same document candidates used by preview and PDF export."""
    trade = next((doc for kind, doc in candidates.items()
                  if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)), {})
    contract = candidates.get("CONTRACT") or {}
    if field.startswith(("buyer.", "seller.")):
        role, prop = field.split(".", 1)
        value = str((trade.get(role) or {}).get(prop) or "").strip()
        if value:
            return value
        return next((str(p.get(prop) or "") for p in contract.get("parties", [])
                     if isinstance(p, dict) and role in [
                         canonical_label(str(r)) or str(r)
                         for r in p.get("roles", [])]), "")
    if field.startswith("item."):
        prop = field.split(".", 1)[1]
        value = (trade.get("items") or [{}])[0].get(prop)
        if value is not None and str(value).strip():
            return str(value)
        term = {"product_name": "products", "quantity": "quantity",
                "unit": "unit", "unit_price": "unit_price"}.get(prop)
        if term:
            return next((str(t.get("value") or "") for t in contract.get("terms", [])
                         if t.get("key") == term), "")
        return ""
    value = trade.get(field)
    if value is not None and str(value).strip():
        return str(value)
    term = {"currency": "currency", "incoterms": "delivery",
            "payment_terms": "payment_trigger"}.get(field)
    if term:
        return next((str(t.get("value") or "") for t in contract.get("terms", [])
                     if t.get("key") == term), "")
    return ""


def _apply_shared_input(digest: str, field: str, widget: str) -> None:
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest:
        return
    raw = str(st.session_state.get(widget) or "").strip()
    if field in {"currency", "item.unit", "item.price_basis"}:
        raw = raw.upper()
        if field == "currency":
            raw = {"$": "USD", "US$": "USD", "USD$": "USD", "₩": "KRW"}.get(raw, raw)
    try:
        updated = apply_answer(saved[1], field, raw, allow_blank=True)
    except (ValueError, TypeError) as exc:
        st.session_state["ai_intake_followup_error"] = str(exc)
        return
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state["ai_intake_last_answer"] = field
    st.session_state.pop("ai_intake_followup_error", None)


def _apply_extra_item(digest: str, index: int, field: str, widget: str) -> None:
    saved = st.session_state.get("ai_intake_candidates")
    if not saved or saved[0] != digest:
        return
    raw = str(st.session_state.get(widget) or "").strip()
    # Edit all matching item positions without losing any additional item rows.
    from decimal import Decimal, InvalidOperation
    if raw and field in {"quantity", "unit_price"}:
        try:
            number = Decimal(raw.replace(",", ""))
            if not number.is_finite() or number < 0 or (field == "unit_price" and number == 0):
                raise InvalidOperation
        except (ValueError, InvalidOperation):
            st.session_state["ai_intake_followup_error"] = "수량과 단가는 올바른 0 이상 숫자로 입력하세요."
            return
    updated = deepcopy(saved[1])
    for kind, source in updated.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(source, dict):
            continue
        rows = source.get("items") or []
        if index >= len(rows):
            continue
        rows[index][field] = raw
        if field == "quantity":
            if raw:
                from Quotation_KEKOREA.orchestration.workflows.mail_trade_normalization import apply_quantity_edit
                apply_quantity_edit(rows[index], raw)
            else:
                for derived in ("paid_quantity", "shipped_quantity", "display_quantity"):
                    rows[index].pop(derived, None)
    if isinstance(updated.get("CONTRACT"), dict):
        updated["CONTRACT"]["clauses"] = []
    _remember_candidate_bundle(digest, updated)
    st.session_state.pop("master_legacy_files", None)
    st.session_state["ai_intake_last_answer"] = "item " + str(index + 1)
    st.session_state.pop("ai_intake_followup_error", None)


def _render_single_editor(digest: str, candidates: dict) -> None:
    """One editor is the source of truth for trade/contract and PDF output."""
    trade = next((doc for kind, doc in candidates.items()
                  if kind in {"PI", "PO", "CI", "PL"} and isinstance(doc, dict)), {})
    fields = list(SHARED_FIELDS)
    if not trade:
        fields = [(key, label) for key, label in fields
                  if key not in {"document_number", "incoterms", "payment_terms",
                                 "item.price_basis", "shipment_reference", "country_of_origin"}]
        fields.extend((("buyer.country", "Buyer · 설립국"),
                       ("seller.country", "Seller · 설립국")))
    else:
        requested_kinds = {key for key in candidates if key in {"PI", "PO", "CI", "PL"}}
        if not requested_kinds.intersection({"CI", "PL"}):
            fields = [(k, label) for k, label in fields if k != "shipment_reference"]
        if "CI" not in requested_kinds:
            fields = [(k, label) for k, label in fields if k != "country_of_origin"]
    with st.container(border=True):
        st.markdown("#### ✏️ 거래정보 입력 · 수정 (한 번만)")
        st.caption("한 곳에서 입력한 값이 PI/PO/CI/PL·계약서 후보와 PDF 입력에 함께 반영됩니다. Enter 또는 칸 이동 시 자동 저장됩니다.")
        error = st.session_state.get("ai_intake_followup_error")
        if error:
            st.error(error)
        last = st.session_state.get("ai_intake_last_answer")
        if last:
            st.caption("최근 반영: " + str(last) + " · 이전 PDF 및 검토 상태 무효화")
        for field, label in fields:
            widget = "ai_intake_shared_" + digest[:12] + "_" + field.replace(".", "_")
            kwargs = {} if widget in st.session_state else {
                "value": _shared_current(candidates, field)}
            st.text_input(label, key=widget, on_change=_apply_shared_input,
                          args=(digest, field, widget), **kwargs)
        extra = (trade.get("items") or [])[1:]
        for index, row in enumerate(extra, 1):
            st.markdown("**상품 " + str(index + 1) + "**")
            for field, label in (("product_name", "상품명"), ("quantity", "수량"),
                                 ("unit", "단위"), ("unit_price", "단가"),
                                 ("price_basis", "단가 기준")):
                widget = "ai_intake_shared_" + digest[:12] + "_item_" + str(index) + "_" + field
                kwargs = {} if widget in st.session_state else {
                    "value": str(row.get(field) or "")}
                st.text_input(label, key=widget, on_change=_apply_extra_item,
                              args=(digest, index, field, widget), **kwargs)
        gaps = missing_fields(candidates)
        if gaps:
            st.warning("미확정 항목 " + str(len(gaps)) + "개 · 비어 있어도 검토용 PDF 생성 가능")
        else:
            st.success("기본 거래정보 입력 완료 · 발행 전에 거래조건을 확인하세요.")


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
            _remember_candidate_bundle(digest, updated)
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
            _remember_candidate_bundle(digest, bundle)
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
            _remember_candidate_bundle(digest, candidate_map)
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
                _remember_candidate_bundle(digest, candidate_map)
            except (ValueError, TypeError) as exc:
                st.error("초안 입력 구성 실패: " + str(exc))
    candidates = st.session_state.get("ai_intake_candidates")
    if candidates and candidates[0] == digest:
        _render_single_editor(digest, candidates[1])
        candidates = st.session_state.get("ai_intake_candidates")
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
        edited_key = _fingerprint(digest + raw)
        if st.button("기존 문서 엔진으로 검증·DRAFT 생성", key="ai_intake_prepare"):
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
            from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
            with st.expander("발행 전 추가 확인사항 (검토용 PDF는 다운로드 가능)", expanded=False):
                for kind, trade in trade_data.items():
                    try:
                        checked = validate_and_calculate(trade)
                        problems = checked.get("blocking_issues") or []
                        st.markdown("**" + kind + "**")
                        if problems:
                            for problem in problems:
                                st.write("• " + str(problem))
                        else:
                            st.success("형식 검증 통과 · 직인과 발행 승인은 별도 확인")
                    except (ValueError, TypeError, KeyError) as exc:
                        st.warning(kind + " 확인 필요: " + str(exc)[:200])
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
            if st.button("현재 거래정보로 PDF 생성", key="master_legacy_export", type="primary"):
                st.session_state.pop("master_legacy_files", None)
                try:
                    from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import (
                        render_master_trade_draft, render_incomplete_trade_pdf,
                    )
                    updated = json.loads(raw)
                    if not isinstance(updated, dict):
                        raise ValueError("문서 데이터는 JSON 객체여야 합니다.")
                    env = document_export_env(st.secrets, os.environ)
                    results = {}
                    errors = {}
                    for kind in trade_kinds:
                        try:
                            results[kind] = render_master_trade_draft(kind, updated[kind], env)
                        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                            # Do not weaken the original sealed PDF issuance rules.
                            # Produce a visibly unapproved PDF using exactly the
                            # user's still-unconfirmed facts (no fake bank data).
                            try:
                                results[kind] = render_incomplete_trade_pdf(kind, updated[kind])
                                errors[kind] = "기존 정식 양식의 검증은 통과하지 않았습니다. 아래 PDF는 미확정 항목을 명시한 내부 검토용입니다."
                            except (ValueError, TypeError, KeyError, RuntimeError, OSError) as fallback:
                                errors[kind] = ("PDF 생성 오류: " + str(fallback))[:400]
                    st.session_state["master_legacy_files"] = (edited_key, results, errors)
                except (ValueError, TypeError, KeyError) as exc:
                    st.error("PDF 생성 실패: " + str(exc)[:400])
            export_bundle = st.session_state.get("master_legacy_files")
            if export_bundle and export_bundle[0] != edited_key:
                st.warning("거래조건이 변경되어 이전 PDF·Excel 파일을 무효화했습니다. 다시 생성하세요.")
            if export_bundle and export_bundle[0] == edited_key:
                for kind, reason in export_bundle[2].items():
                    st.warning(kind + " 정식 양식 발행 보류: " + reason)
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
            st.caption("미확정 항목이 있더라도 검토용 PDF 파일은 생성 가능합니다. 정식 발행·직인·전송에는 기존 검증과 승인이 필요합니다.")
        if "CONTRACT" in candidates[1]:
            st.caption("계약서 PDF·DOCX는 아래 기존 계약서 DRAFT 엔진으로 생성합니다. FINAL 계약서의 법률·계좌·승인 검증은 우회하지 않습니다.")
        doc = candidates[1].get("CONTRACT")
        if doc and not doc.get("clauses"):
            st.divider()
            st.markdown("#### 기존 LangGraph로 계약서 AI 초안 작성")
            st.warning("실제 AI 문서 생성에는 API 요금이 발생할 수 있으며, 수정한 계약서 조건이 AI 모델로 전송됩니다.")
            draft_consent = st.checkbox("현재 계약서 조건을 AI에 전송해 검토용 조항을 생성하는 데 동의합니다.",
                                       key="ai_intake_contract_consent")
            if st.button("AI 계약서 초안 작성", disabled=not (draft_consent and ready),
                         key="ai_intake_contract_draft"):
                try:
                    edited = json.loads(raw)
                    current = edited.get("CONTRACT")
                    if not isinstance(current, dict):
                        raise ValueError("현재 계약서 데이터를 입력해 주세요.")
                    with st.spinner("기존 계약서 LangGraph가 검토용 조항을 생성합니다."):
                        generated = generate_contract_draft(current, config, consent=draft_consent)
                    # Use an explicit callback state, never modify saved contract.
                    updated = deepcopy(edited)
                    updated["CONTRACT"] = generated
                    _remember_candidate_bundle(digest, updated)
                    st.success("새 DRAFT 조항을 생성했습니다. 조건과 문구를 확인한 뒤 검증·다운로드하세요.")
                    st.rerun()
                except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                    st.error("AI 계약서 생성 실패: " + str(exc)[:400])
    with st.expander("기존 저장된 계약서 참고 · AI에 전송하지 않음"):
        _reference_panel()
