"""Authenticated AI intake screen; no stored private contract sent to the model."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os

import streamlit as st

from Quotation_KEKOREA.orchestration.router import classify
from Quotation_KEKOREA.orchestration.workflows.label_typos import canonical_label
from Quotation_KEKOREA.orchestration.workflows.ai_intake import (
    extract_candidate, make_contract_candidate, make_trade_candidate,
    generate_contract_draft, selected_contract_reference,
)
from Quotation_KEKOREA.orchestration.workflows.unified_review import (
    new_request, prepare_documents,
)
from Quotation_KEKOREA.orchestration.ui.saved_contracts import _server_value
from Quotation_KEKOREA.orchestration.workflows.intake_followups import missing_fields, apply_answer


def _fingerprint(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _model_config():
    return {k: _server_value(k) for k in (
        "OPENAI_API_KEY", "OPENAI_MODEL", "CONTRACT_OPENAI_MODEL",
    )}


def _remember_candidate_bundle(digest: str, candidate_map: dict) -> None:
    """Synchronize answer widgets and advanced editor in memory."""
    st.session_state["ai_intake_candidates"] = (digest, candidate_map)
    st.session_state["ai_intake_editable"] = json.dumps(candidate_map, ensure_ascii=False, indent=2)
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
        source = json.loads(st.session_state.get("ai_intake_editable") or "{}")
        if not isinstance(source, dict):
            raise ValueError("JSON 객체 형식이 필요합니다.")
        updated = apply_answer(source, key, answer)
    except (ValueError, TypeError) as exc:
        st.session_state["ai_intake_followup_error"] = str(exc)
        return
    _remember_candidate_bundle(digest, updated)
    st.session_state["ai_intake_last_answer"] = key
    st.session_state.pop("ai_intake_followup_error", None)


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
    st.session_state["ai_intake_result"] = (digest, revised)
    st.session_state.pop("ai_intake_drafts", None)
    try:
        bundle = {}
        for kind in requested:
            if kind == "CONTRACT":
                bundle[kind] = make_contract_candidate(revised, "ko" if st.session_state.get("ai_intake_language") == "한국어" else "en")
            else:
                bundle[kind] = make_trade_candidate(kind, revised,
                    product_family=st.session_state.get("ai_intake_family", "solar_cell"))
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
    st.info("AI 요청에는 아래 입력창에서 직접 작성한 내용만 전송합니다. 저장된 계약서는 모델에 전달되지 않습니다.")
    instruction = st.text_area("업무 요청 및 거래조건", height=185,
        placeholder="예: 한화 M10 solar cell 100 PCS, USD 0.20/pc, EXW Seoul 조건으로 PI와 계약서 초안을 만들어줘.",
        key="ai_intake_instruction")
    requested = classify("", instruction)
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
    consent = st.checkbox("위 입력 내용만 외부 AI API에 전송하는 데 동의합니다. 저장된 계약서는 전송하지 않습니다.",
                          value=False, key="ai_intake_consent")
    digest = _fingerprint(instruction + "|" + language + "|" + family)
    if st.button("AI 거래조건 추출", key="ai_intake_extract", type="primary",
                 disabled=not (consent and ready and requested and instruction.strip())):
        st.session_state.pop("ai_intake_result", None)
        st.session_state.pop("ai_intake_candidates", None)
        st.session_state.pop("ai_intake_drafts", None)
        try:
            with st.spinner("거래조건을 분석합니다."):
                extracted = extract_candidate(instruction, config, consent=consent)
            st.session_state["ai_intake_result"] = (digest, extracted)
            candidate_map = {}
            for kind in requested:
                if kind == "CONTRACT":
                    candidate_map[kind] = make_contract_candidate(
                        extracted, "ko" if language == "한국어" else "en")
                else:
                    candidate_map[kind] = make_trade_candidate(
                        kind, extracted, product_family=family)
            _remember_candidate_bundle(digest, candidate_map)
        except (PermissionError, ValueError, RuntimeError, TypeError) as exc:
            st.error("AI 거래조건 추출 실패: " + str(exc)[:400])

    result = st.session_state.get("ai_intake_result")
    if result and result[0] != digest:
        st.warning("원래 업무 요청이 변경되었습니다. 기존 AI 추출 결과 및 검토 승인은 사용하지 마세요.")
    if result and result[0] == digest:
        analysis = result[1]
        _render_recovery_inputs(digest, analysis, requested)
        if st.session_state.get("ai_intake_recovery_error"):
            st.warning("문서 후보 재생성 오류: " + st.session_state["ai_intake_recovery_error"])
        st.markdown("#### AI가 추출한 조건 · 모두 미확정")
        current = st.session_state.get("ai_intake_candidates")
        if current and current[0] == digest:
            _render_missing_inputs(digest, current[1])
        current = st.session_state.get("ai_intake_candidates")
        if current and current[0] == digest:
            _render_quick_corrections(digest, current[1])
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
            with st.expander("추가 AI 검토 사항"):
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
                _remember_candidate_bundle(digest, candidate_map)
            except (ValueError, TypeError) as exc:
                st.error("초안 입력 구성 실패: " + str(exc))
    candidates = st.session_state.get("ai_intake_candidates")
    if candidates and candidates[0] == digest:
        candidates = st.session_state.get("ai_intake_candidates")
        st.markdown("#### 실시간 반영 결과")
        for kind, data in candidates[1].items():
            if kind in ("PI", "PO", "CI", "PL"):
                with st.container(border=True):
                    st.markdown("**" + kind + " · 현재 거래정보**")
                    st.write("Buyer:", (data.get("buyer") or {}).get("legal_name") or "미입력")
                    st.write("Seller:", (data.get("seller") or {}).get("legal_name") or "미입력")
                    st.write("가격 확인 출처:", (data.get("items") or [{}])[0].get("price_source") or "미입력")
            elif kind == "CONTRACT":
                st.caption("계약서 당사자와 조건에도 답변을 함께 반영합니다. 생성된 조항은 조건이 바뀌면 무효화됩니다.")
        with st.expander("고급 설정 · 전체 문서 JSON 직접 수정"):
            raw = st.text_area("문서별 JSON 조건 (고급 편집)",
                value=json.dumps(candidates[1], ensure_ascii=False, indent=2),
                height=310, key="ai_intake_editable")
        edited_key = _fingerprint(digest + raw)
        if st.button("기존 문서 엔진으로 검증·DRAFT 생성", key="ai_intake_prepare"):
            st.session_state.pop("ai_intake_drafts", None)
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("최상위 값은 문서별 JSON 객체여야 합니다.")
                run = prepare_documents(new_request(instruction, data))
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
        st.divider()
        st.markdown("#### 기존 KE KOREA 양식 · PI / PO / CI / PL PDF·Excel")
        st.caption("현재 MASTER 앱에서 기존 업무 에이전트의 검증·직인·페이지 분할·PDF/XLSX 엔진을 직접 호출합니다. 기존 앱으로 이동하지 않습니다.")
        trade_kinds = [kind for kind in candidates[1] if kind in ("PI", "PO", "CI", "PL")]
        if trade_kinds:
            if st.button("기존 양식으로 무역서류 PDF·Excel 생성", key="master_legacy_export"):
                st.session_state.pop("master_legacy_files", None)
                try:
                    from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_master_trade_draft
                    updated = json.loads(raw)
                    if not isinstance(updated, dict):
                        raise ValueError("문서 데이터는 JSON 객체여야 합니다.")
                    env_keys = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "KEKOREA_COMPANY_SEAL_BASE64",
                                "KEKOREA_USD_BENEFICIARY", "KEKOREA_USD_BANK_NAME", "KEKOREA_USD_BRANCH",
                                "KEKOREA_USD_SWIFT", "KEKOREA_USD_ACCOUNT_NUMBER", "KEKOREA_USD_BANK_ADDRESS")
                    env = {name: _server_value(name) for name in env_keys}
                    results = {}
                    errors = {}
                    for kind in trade_kinds:
                        try:
                            results[kind] = render_master_trade_draft(kind, updated[kind], env)
                        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                            errors[kind] = str(exc)[:450]
                    st.session_state["master_legacy_files"] = (edited_key, results, errors)
                except (ValueError, TypeError, KeyError) as exc:
                    st.error("PDF·Excel 생성 실패: " + str(exc)[:450])
            export_bundle = st.session_state.get("master_legacy_files")
            if export_bundle and export_bundle[0] != edited_key:
                st.warning("거래조건이 변경되어 이전 PDF·Excel 파일을 무효화했습니다. 다시 생성하세요.")
            if export_bundle and export_bundle[0] == edited_key:
                for kind, reason in export_bundle[2].items():
                    st.warning(kind + " 출력 보류: " + reason)
                for kind, files in export_bundle[1].items():
                    with st.container(border=True):
                        st.markdown("**" + kind + " · 기존 양식 검토용 문서**")
                        for fmt, file in files.items():
                            st.download_button(kind + " " + fmt.upper() + " DRAFT 다운로드",
                                               data=file["content"], file_name=file["filename"],
                                               mime=file["mime"], key="master_legacy_" + kind + "_" + fmt)
            st.caption("기존 회사 직인 및 필수 정보 검증을 통과해야 생성됩니다. 생성물은 DRAFT이며 최종 발행·전송되지 않습니다.")
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
