from Quotation_KEKOREA.contracts.clause_terms import clause_evidence, merge_clause_candidates
"""Streamlit UI for private contract drafting, review, revision and export."""
import hashlib
import re
from copy import deepcopy
from html import escape
from uuid import NAMESPACE_URL, uuid4, uuid5

import streamlit as st

from Quotation_KEKOREA.contracts.editing import (
    RevisionConflict, apply_proposal, restore_revision,
)
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.draft_exports import export_draft
from Quotation_KEKOREA.contracts.workspace import collect_notes, propose_notes_revision
from Quotation_KEKOREA.contracts.final_merge import merge_revision_requests
from Quotation_KEKOREA.contracts.risk_review_ui import render_risk_review
from Quotation_KEKOREA.contracts.models import new_snapshot, validate_snapshot
from Quotation_KEKOREA.contracts.library import search_library
from Quotation_KEKOREA.contracts.review_summary import review_cards
from Quotation_KEKOREA.contracts.library_ui import render_library_admin, show_library_sources
from Quotation_KEKOREA.contracts.commission_policy import (
    COMMISSION_TYPES, apply_payment_policy,
)
from Quotation_KEKOREA.contracts.references import (
    MAX_FILES_PER_REQUEST, candidate_clauses, extract_reference,
)
from Quotation_KEKOREA.contracts.repository import (
    ContractRepository, ContractRepositoryError,
)
from Quotation_KEKOREA.contracts.rules import (
    LABELS, TYPE_REQUIRED, apply_analysis, validate_snapshot as validate_rules,
)
from Quotation_KEKOREA.contracts.service import (
    analyze_trade, conversation_response_language, extract_reference_page, generate_draft, language_conflict,
    propose_revision, propose_term_revision,
)
from Quotation_KEKOREA.contracts.flow import should_generate_draft, select_new_questions


TYPE_LABELS = {
    "sale": "매매 계약",
    "trade_commission": "Buyer–Seller 거래 중개 커미션 계약",
    "investment_commission": "투자 유치 커미션 계약",
}
ROLE_LABELS = {
    "buyer": "Buyer", "seller": "Seller", "client": "의뢰인",
    "intermediary": "중개인", "commission_payer": "커미션 지급자",
    "fundraiser": "투자 유치 담당자", "investor": "투자자",
}
PARTY_FIELDS = ("legal_name", "country", "address", "representative")
STATUS_LABELS = {"confirmed": "확정", "suggested": "AI 제안", "missing": "미정"}
EDITOR_STATUS_LABELS = {"confirmed": "확정", "suggested": "AI 제안", "missing": "확인 필요"}


def _editor_status(status, value):
    if status == 'missing' and value not in (None, ''):
        return 'TBD 유지'
    return EDITOR_STATUS_LABELS.get(status, '확인 필요')


def _stored_status(value):
    return {'확정': 'confirmed', 'AI 제안': 'suggested', '확인 필요': 'missing',
            'TBD 유지': 'missing'}.get(value, value if value in {'confirmed', 'suggested', 'missing'} else 'missing')


def _repository(env):
    return ContractRepository(env)


def _records(repo):
    try:
        return repo.list_contracts()
    except ContractRepositoryError as exc:
        st.error(str(exc))
        return []


def _delete_contract(repo, contract_id):
    for reference in repo.contract_references(contract_id):
        if reference.get("storage_path"):
            repo.delete_private_file("kekorea-contracts", reference["storage_path"])
    for output in repo.list_exports(contract_id):
        repo.delete_private_file("kekorea-contracts", output["storage_path"])
    repo.delete_contract(contract_id)


def _render_contract_delete_confirmation(repo, contract_id, title):
    with st.container(border=True):
        st.warning(f"정말 삭제하시겠습니까?\n\n**{title}** 계약과 연결된 기록 및 비공개 파일이 삭제됩니다.")
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button("확인", key=f"contract_delete_confirm_{contract_id}",
                          type="primary"):
        try:
            _delete_contract(repo, contract_id)
            st.session_state.pop("contract_delete_pending_id", None)
            st.session_state.pop(f"contract_snapshot_{contract_id}", None)
            st.session_state.pop(f"contract_pending_analysis_{contract_id}", None)
            if st.session_state.get("contract_active_id") == contract_id:
                st.session_state.pop("contract_active_id", None)
            for key in (
                f"contract_prompt_{contract_id}",
                f"contract_ai_consent_{contract_id}",
                f"contract_context_refs_{contract_id}",
                f"contract_use_library_{contract_id}",
                f"contract_pending_analysis_{contract_id}",
            ):
                st.session_state.pop(key, None)
            for key in ("contract_revisions", "contract_pending_proposal",
                        "contract_pending_terms", "contract_pending_proposal_key"):
                st.session_state.pop(key, None)
            st.success("계약과 연결 기록을 삭제했습니다.")
            st.rerun()
        except ContractRepositoryError as exc:
            st.error(f"삭제가 완전히 확인되지 않았습니다. 다시 확인해 주세요. {exc}")
    if cancel_col.button("취소", key=f"contract_delete_cancel_{contract_id}"):
        st.session_state.pop("contract_delete_pending_id", None)
        st.rerun()


def _save_snapshot(repo, snapshot, summary, *, expected_revision=None):
    previous_revision = (int(expected_revision) if expected_revision is not None
                         else int(snapshot.get("revision", 1)))
    committed = repo.commit_revision(snapshot["contract_id"], previous_revision,
                                     snapshot, summary)
    saved = deepcopy(snapshot)
    saved["revision"] = int(committed["revision"])
    return validate_snapshot(saved)


def _load_snapshot(repo, contract_id):
    revisions = repo.load_contract(contract_id)
    if not revisions:
        raise ContractRepositoryError("No saved contract revision was found.")
    row = max(revisions, key=lambda value: int(value.get("revision", 0)))
    snapshot = row.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ContractRepositoryError("Saved contract data is not a valid snapshot.")
    return validate_snapshot(snapshot), revisions


def _rows(value):
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict(orient="records")
        except TypeError:
            pass
    return [dict(row) for row in value]


def _term_rows(snapshot):
    terms = {term.get("key"): term for term in snapshot.get("terms", [])}
    keys = list(dict.fromkeys(list(TYPE_REQUIRED[snapshot["contract_type"]]) +
                              list(terms.keys())))
    if snapshot['contract_type'] in COMMISSION_TYPES:
        keys = list(dict.fromkeys(keys + ['payment_trigger', 'late_interest_legal_review', 'late_interest_source']))
    rows = []
    for key in keys:
        term = terms.get(key, {})
        rows.append({
            "key": key,
            "항목": LABELS.get(key, key.replace("_", " ")),
            "value": term.get("value") or "",
            "unit": term.get("unit") or "",
            "currency": term.get("currency") or "",
            "status": _editor_status(term.get("status", "missing"), term.get('value')),
        })
    return rows


def _party_rows(snapshot):
    return [{
        "id": party.get("id") or f"party_{index + 1}",
        "legal_name": party.get("legal_name") or "",
        "country": party.get("country") or "",
        "address": party.get("address") or "",
        "representative": party.get("representative") or "",
        "roles": ", ".join(party.get("roles") or []),
        "status": _editor_status(party.get("status", "missing"), party.get('legal_name')),
    } for index, party in enumerate(snapshot.get("parties", []))]


def _merge_edited_data(snapshot, term_rows, party_rows):
    updated = deepcopy(snapshot)
    old_terms = {term.get("key"): term for term in updated.get("terms", [])}
    terms = []
    for row in term_rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        term = deepcopy(old_terms.get(key, {"id": f"term_{uuid4().hex}",
                                           "key": key, "source_refs": []}))
        term.update({
            "key": key,
            "value": str(row.get("value") or "").strip() or None,
            "unit": str(row.get("unit") or "").strip() or None,
            "currency": str(row.get("currency") or "").strip() or None,
            "status": _stored_status(row.get("status")),
        })
        if term["value"] is None:
            term["status"] = "missing"
        terms.append(term)
    updated["terms"] = terms
    parties = []
    for row in party_rows:
        roles = [role.strip() for role in str(row.get("roles") or "").split(",") if role.strip()]
        if not roles and not any(str(row.get(field) or "").strip() for field in PARTY_FIELDS):
            continue
        parties.append({
            "id": str(row.get("id") or f"party_{uuid4().hex}"),
            **{field: str(row.get(field) or "").strip() or None for field in PARTY_FIELDS},
            "roles": roles,
            "status": _stored_status(row.get("status")),
        })
    updated["parties"] = parties
    return updated


def _changed_terms(old_snapshot, new_snapshot):
    before_terms = {term.get("key"): term for term in old_snapshot.get("terms", [])}
    after_terms = {term.get("key"): term for term in new_snapshot.get("terms", [])}
    changes = []
    for key, new_term in after_terms.items():
        if before_terms.get(key) != new_term:
            changes.append(new_term)
    before_parties = {role: party for party in old_snapshot.get("parties", [])
                      for role in party.get("roles", [])}
    after_parties = {role: party for party in new_snapshot.get("parties", [])
                     for role in party.get("roles", [])}
    for role, party in after_parties.items():
        old = before_parties.get(role, {})
        for field in (*PARTY_FIELDS, "status"):
            if old.get(field) != party.get(field):
                changes.append({"key": f"party.{role}.{field}", "value": party.get(field),
                                "status": party.get("status", "confirmed")})
    for role in before_parties.keys() - after_parties.keys():
        changes.append({"key": f"party.{role}._remove", "value": "true",
                        "status": "confirmed"})
    for key in {"governing_law", "dispute_resolution"}:
        old_omission = old_snapshot.get("omissions", {}).get(key)
        new_omission = new_snapshot.get("omissions", {}).get(key)
        if old_omission != new_omission:
            changes.append({
                "key": f"omission.{key}",
                "value": new_omission.get("reason") if new_omission else None,
                "status": "confirmed" if new_omission else "missing",
            })
    return changes


def _new_contract(repo, title, contract_type, language, initial_snapshot=None):
    snapshot = deepcopy(initial_snapshot) if initial_snapshot else new_snapshot(
        str(uuid4()), contract_type, language)
    snapshot["contract_id"] = str(uuid4())
    snapshot["revision"] = 1
    snapshot["contract_type"] = contract_type
    snapshot["language"] = language
    record = {"title": title.strip() or "Untitled contract",
              "contract_type": contract_type, "language": language, "status": "draft"}
    snapshot["title"] = record["title"]
    created = repo.create_contract(record, snapshot)
    snapshot["contract_id"] = str(created["id"])
    snapshot["revision"] = int(created.get("current_revision", 1))
    snapshot["title"] = record["title"]
    st.session_state["contract_active_id"] = snapshot["contract_id"]
    st.session_state[f"contract_snapshot_{snapshot['contract_id']}"] = validate_snapshot(snapshot)
    st.session_state.pop("contract_revisions", None)
    return snapshot


def _ensure_active_snapshot(repo, active_id):
    state_key = f"contract_snapshot_{active_id}"
    if state_key in st.session_state:
        snapshot = validate_snapshot(st.session_state[state_key])
        return snapshot
    snapshot, revisions = _load_snapshot(repo, active_id)
    st.session_state[state_key] = snapshot
    st.session_state["contract_revisions"] = revisions
    return snapshot


def _references_panel(repo, contract_id, env):
    with st.expander("참고 계약서와 선호 조항", expanded=False):
        st.warning("참고 계약서 원문에는 민감정보가 포함될 수 있습니다. 텍스트 추출은 로컬에서 수행하며, AI 분석을 선택하면 선택한 계약 설명과 참고 문구가 OpenAI API로 전송됩니다. 서명/직인 이미지는 새 계약에 재사용하지 않습니다.")
        files = st.file_uploader("참고 PDF 또는 DOCX (요청당 최대 5개, 파일당 20MB)",
                                 type=["pdf", "docx"], accept_multiple_files=True,
                                 key=f"contract_reference_upload_{contract_id}")
        allow_ocr = st.checkbox("스캔 PDF의 텍스트 영역(페이지 상단 78%)을 OpenAI로 전송해 OCR 분석하는 데 동의합니다.",
                                key=f"contract_reference_ocr_consent_{contract_id}")
        if files and len(files) > MAX_FILES_PER_REQUEST:
            st.error("한 번에 최대 5개 파일을 선택해 주세요.")
        elif files and st.button("참고 자료 분석 및 비공개 저장",
                                 key=f"contract_reference_process_{contract_id}"):
            try:
                for uploaded in files:
                    data = uploaded.getvalue()
                    existing = [row for row in repo.contract_references(contract_id)
                                if row.get("content_hash") == hashlib.sha256(data).hexdigest()]
                    if existing:
                        st.info(f"{uploaded.name}: 이미 이 계약에 저장되어 있습니다.")
                        continue
                    vision = None
                    if allow_ocr:
                        vision = lambda image, page, _env=env: extract_reference_page(
                            image, page, env=_env)
                    reference = extract_reference(data, uploaded.name, vision_client=vision)
                    reference_id = str(uuid4())
                    safe_name = re.sub(r"[^\w.-]+", "_", uploaded.name, flags=re.UNICODE)[:100]
                    storage_path = f"{contract_id}/references/{reference['content_hash']}/{safe_name}"
                    repo.upload_private_file("kekorea-contracts", storage_path, data,
                                             "application/pdf" if uploaded.name.lower().endswith(".pdf")
                                             else "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                    repo.save_reference({
                        "id": reference_id, "contract_id": contract_id,
                        "filename": uploaded.name, "content_hash": reference["content_hash"],
                        "storage_path": storage_path,
                        "extraction_status": reference["extraction_status"],
                        "extracted_text": reference["extracted_text"],
                        "source_locations": reference["source_locations"],
                    })
                st.success("참고 자료가 비공개 저장되었습니다.")
                st.rerun()
            except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                st.error(str(exc))

        references = repo.contract_references(contract_id)
        if references:
            for reference in references:
                st.markdown(f"**{reference['filename']}** · {reference['extraction_status']}")
                if reference["extraction_status"] == "scanned_requires_ocr":
                    st.warning("읽을 수 있는 텍스트가 없습니다. OCR 전송 동의를 선택해 다시 분석하거나 내용을 직접 입력하세요.")
                with st.expander(f"출처 문구 보기: {reference['filename']}"):
                    st.text((reference.get("extracted_text") or "")[:12000])
                candidates = candidate_clauses(reference)
                if candidates:
                    labels = [f"{i + 1}. {candidate['text'][:90]}" for i, candidate in enumerate(candidates)]
                    selected = st.selectbox("선호 조항 후보 (선택만으로 승인되지 않음)",
                                            range(len(candidates)),
                                            format_func=lambda index: labels[index],
                                            key=f"contract_clause_candidate_{reference['id']}")
                    category = st.text_input("분류 (예: 지급, 책임, 비밀유지)",
                                             key=f"contract_clause_category_{reference['id']}")
                    if st.button("선택한 문구를 선호 조항으로 승인",
                                 key=f"contract_clause_approve_{reference['id']}"):
                        candidate = candidates[selected]
                        repo.save_preferred_clause({
                            "text": candidate["text"], "language": st.session_state.get(
                                f"contract_snapshot_{contract_id}", {}).get("language", "ko"),
                            "contract_types": [st.session_state.get(
                                f"contract_snapshot_{contract_id}", {}).get("contract_type", "sale")],
                            "roles": [], "category": category.strip() or "기타",
                            "source_refs": [{"document_id": reference["id"],
                                             "locator": candidate["locator"],
                                             "quote": candidate["text"]}],
                            "active": True,
                        })
                        st.success("사용자가 승인한 선호 조항으로 저장했습니다.")
                        st.rerun()
                if st.button(f"참고 자료 삭제: {reference['filename']}",
                             key=f"contract_reference_delete_{reference['id']}"):
                    if reference.get("storage_path"):
                        repo.delete_private_file("kekorea-contracts", reference["storage_path"])
                    repo.delete_reference(reference["id"])
                    st.rerun()
        preferred = repo.list_preferred_clauses()
        if preferred:
            st.markdown("**승인된 선호 조항**")
            for clause in preferred:
                columns = st.columns([5, 1, 1])
                columns[0].write(f"{clause['category']} · {clause['text'][:180]}")
                columns[1].write("사용" if clause["active"] else "비활성")
                if columns[2].button("사용 전환", key=f"preferred_toggle_{clause['id']}"):
                    repo.set_preferred_clause_active(clause["id"], not clause["active"])
                    st.rerun()


def _proposal_panel(repo, snapshot, proposal, state_key):
    st.markdown("#### 수정안 비교")
    stale = proposal.get("base_revision") != snapshot.get("revision")
    if stale:
        st.warning("이 수정안은 이전 revision을 기준으로 합니다. 최신 문서에 다시 제안해 주세요.")
    if proposal.get("explanation"):
        st.info(proposal["explanation"])
    selected_ids = []
    for change in proposal["changes"]:
        is_required = bool(change.get("required_to_resolve_conflict"))
        with st.container(border=True):
            if change.get("term_key"):
                st.markdown(f"**조건: {LABELS.get(change['term_key'], change['term_key'])}**")
            else:
                st.markdown(f"**관련 문장: {change.get('sentence_id')}**")
            st.caption("수정 전")
            st.write(change.get("original_text") or "—")
            st.caption("수정 후")
            st.write(change.get("proposed_text") or "—")
            if change.get("reason"):
                st.caption("변경 이유: " + change["reason"])
            if is_required:
                if change.get("term_key"):
                    st.caption("입력한 조건을 본문의 관련 변경과 함께 적용합니다.")
                else:
                    st.warning("관련 문장과 함께 적용해야 하는 수정입니다. 적용하거나 전체 제안을 취소해 주세요.")
            checked = st.checkbox(
                "이 변경 적용" if not is_required else "필수 변경 적용",
                value=True, disabled=is_required,
                key=f"proposal_change_{proposal['id']}_{change['id']}")
            if checked:
                selected_ids.append(change["id"])
    batch_reviewed = True
    if len(proposal.get('note_ids', [])) > 1:
        st.caption("같은 문장·조건의 충돌은 자동 차단합니다. 서로 다른 문장의 의미 충돌은 금액·기한·역할을 함께 대조해 확인하세요.")
        batch_reviewed = st.checkbox(
            "선택한 수정안 사이의 금액·기한·역할 충돌을 확인했습니다",
            key=f"contract_batch_review_{proposal['id']}")
    col_apply, col_cancel = st.columns(2)
    if col_apply.button("선택한 변경을 하나의 revision으로 적용",
                        disabled=stale or not batch_reviewed,
                        type="primary", key=f"proposal_apply_{proposal['id']}"):
        try:
            updated = apply_proposal(snapshot, proposal, selected_ids)
            if proposal.get("note_ids"):
                # Only fully approved requests are consumed. Others remain visible
                # as prior-revision notes for explicit re-review, never silent reuse.
                if set(selected_ids) == {change['id'] for change in proposal['changes']}:
                    updated['applied_note_ids'] = list(dict.fromkeys(
                        updated.get('applied_note_ids', []) + proposal['note_ids']))
                updated['issues'].extend(deepcopy(proposal.get('issues', [])))
            saved = _save_snapshot(repo, updated, "Applied contract revision proposal",
                                   expected_revision=snapshot["revision"])
            # The revision RPC is the authoritative atomic save. A separate
            # annotation-log failure must never leave this session on the old base.
            st.session_state[state_key] = saved
            st.session_state.pop("contract_pending_proposal", None)
            st.session_state.pop("contract_pending_terms", None)
            try:
                repo.save_annotation({
                    "id": proposal["id"].replace("proposal_", ""),
                    "contract_id": snapshot["contract_id"],
                    "sentence_id": proposal.get("target_sentence_id") or "term-reconciliation",
                    "base_revision": proposal["base_revision"],
                    "instruction": proposal.get("instruction", ""),
                    "proposal": proposal, "status": "applied",
                })
            except ContractRepositoryError:
                st.session_state[f"contract_commit_notice_{snapshot['contract_id']}"] = (
                    "계약서 revision은 저장됐지만 수정 이력 메모의 상태 기록은 확인이 필요합니다. 본문을 다시 적용하지 마세요.")
            st.success(f"Revision {saved['revision']}로 저장했습니다.")
            st.rerun()
        except (ValueError, RevisionConflict, ContractRepositoryError) as exc:
            st.error(str(exc))
    if col_cancel.button("수정안 취소", key=f"proposal_cancel_{proposal['id']}"):
        repo.save_annotation({
            "id": proposal["id"].replace("proposal_", ""),
            "contract_id": snapshot["contract_id"],
            "sentence_id": proposal.get("target_sentence_id") or "term-reconciliation",
            "base_revision": proposal["base_revision"],
            "instruction": proposal.get("instruction", ""),
            "proposal": proposal, "status": "dismissed",
        })
        st.session_state.pop("contract_pending_proposal", None)
        st.session_state.pop("contract_pending_terms", None)
        st.rerun()


def _note_buffer_key(snapshot):
    return f"contract_note_buffer_{snapshot['contract_id']}_{snapshot['revision']}"


def _note_changed(buffer_key, sentence_id, widget_key, contract_id):
    st.session_state.setdefault(buffer_key, {})[sentence_id] = st.session_state.get(widget_key, '')
    # A changed request cannot reuse an earlier proposal.
    proposal = st.session_state.get('contract_pending_proposal') or {}
    if proposal.get('contract_id') == contract_id and proposal.get('note_ids'):
        st.session_state.pop('contract_pending_proposal', None)


def _remove_note(repo, snapshot, sentence_id, saved_notes, buffer_key, open_key, widget_key):
    try:
        if sentence_id in saved_notes:
            repo.save_annotation(dict(saved_notes[sentence_id], status='dismissed'))
        st.session_state.get(buffer_key, {}).pop(sentence_id, None)
        if sentence_id in st.session_state.get(open_key, []):
            st.session_state[open_key].remove(sentence_id)
        st.session_state.pop(widget_key, None)
        proposal = st.session_state.get('contract_pending_proposal') or {}
        if proposal.get('contract_id') == snapshot['contract_id'] and proposal.get('note_ids'):
            st.session_state.pop('contract_pending_proposal', None)
    except ContractRepositoryError as exc:
        st.session_state[f"contract_note_error_{snapshot['contract_id']}"] = str(exc)


def _render_draft(repo, snapshot, state_key, env):
    st.caption(f"Revision {snapshot.get('revision')} · DRAFT / 검토용 · 문장을 클릭해 옆에 메모를 작성하세요.")
    contract_id, revision = snapshot['contract_id'], snapshot['revision']
    annotations = repo.list_annotations(contract_id)
    pending = collect_notes(snapshot, annotations)
    saved_notes = {row['sentence_id']: row for row in pending['notes']}
    open_key = f"contract_open_notes_{contract_id}_{revision}"
    buffer_key = _note_buffer_key(snapshot)
    opened = st.session_state.setdefault(open_key, [])
    buffers = st.session_state.setdefault(buffer_key, {})
    error = st.session_state.pop(f"contract_note_error_{contract_id}", None)
    if error:
        st.error(f"메모를 삭제하지 못했습니다. {error}")
    # RAG review can select a sentence using the existing navigation key.
    selected = st.session_state.pop(f"contract_selected_sentence_{contract_id}", None)
    if selected and selected not in opened:
        opened.append(selected)
    st.markdown("""<style>
    .st-key-contract_document_surface {background:#eef1f4;padding:clamp(.5rem,2vw,2rem);}
    .st-key-contract_document_paper {background:#fff;color:#172b3a;max-width:64rem;
        margin:auto;padding:clamp(1rem,4vw,3rem);border:1px solid #dbe3ea;border-radius:2px;}
    .st-key-contract_document_paper h2 {text-align:center;font-size:1.5rem;line-height:1.6;}
    .st-key-contract_document_paper h4 {color:#092b4c;font-size:1rem;margin-top:1.5rem;}
    /* Word-style comment gutter: stable row alignment and visible note cards. */
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] {
        align-items:flex-start;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child {
        min-width:0;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child [data-testid="stTextArea"] {
        border-radius:8px;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child textarea {
        background:#fffcf4;border:1px solid #eadbb8;min-height:96px;color:#243746;
        border-radius:6px;font-size:.88rem;line-height:1.5;}
    .st-key-contract_document_paper [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child textarea:focus {
        background:#fff;border-color:#0877c9;box-shadow:0 0 0 1px #0877c9;}
    .st-key-contract_document_paper [data-testid="stButton"] button {
        background:transparent;border:1px solid transparent;color:#172b3a;border-radius:2px;
        text-align:left;justify-content:flex-start;padding:.35rem .5rem;min-height:0;}
    .st-key-contract_document_paper [data-testid="stButton"] button p {
        font-family:Georgia,"Malgun Gothic",serif;font-size:1rem;line-height:1.85;text-align:left;}
    .st-key-contract_document_paper [data-testid="stButton"] button:hover {
        background:#f0f7fc;border-color:#b9d6ea;}
    .st-key-contract_document_paper [data-testid="stButton"] button:focus-visible {
        outline:2px solid #0877c9;outline-offset:2px;}
    .st-key-contract_document_paper button[kind="primary"] {background:#e7f2fa;
        border-left:3px solid #0877c9;color:#092b4c;}
    /* Contract sentence alignment: consistent left edge for short and long clauses. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button {
        justify-content:flex-start!important;text-align:left!important;
        align-items:flex-start!important;flex-direction:row!important;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] {
        width:100%!important;min-width:0!important;text-align:left!important;
        margin:0!important;padding:0!important;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button p {
        width:100%!important;max-width:none!important;min-width:0!important;
        margin:0!important;padding:0!important;text-align:left!important;
    }
    /* Sentence text is real left-aligned document prose; the button is a click target only. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] {
        position:relative;min-width:0;
    }
    .st-key-contract_document_paper .contract-sentence-body {
        display:block;width:100%;box-sizing:border-box;margin:0;padding:.35rem .5rem;
        text-align:left!important;white-space:pre-wrap;overflow-wrap:anywhere;
        word-break:break-word;font:normal clamp(.8rem,1vw,1rem)/1.7 Georgia,"Malgun Gothic",serif;
        color:#172b3a;cursor:pointer;border-radius:2px;min-height:2rem;
    }
    /* Keep original button key and accessible label, but use it only as a full-surface hit area. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button {
        position:absolute!important;inset:0!important;z-index:3;
        display:block!important;width:100%!important;height:100%!important;
        min-height:0!important;opacity:0!important;margin:0!important;
        cursor:pointer!important;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:hover) .contract-sentence-body {
        background:#f0f7fc;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:focus-visible) .contract-sentence-body {
        outline:2px solid #0877c9;outline-offset:2px;
    }
    .st-key-contract_document_paper .contract-sentence-body.is-open {
        background:#e7f2fa;border-left:3px solid #0877c9;padding-left:calc(.5rem - 3px);
    }
    /* Long clause readability: never shrink below a usable font size or clip text. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] {
        position:relative;min-width:0;}
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button {
        height:auto!important;max-height:none!important;min-height:2rem;
        white-space:normal!important;overflow:visible!important;text-overflow:clip!important;
        width:100%;align-items:flex-start;}
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button p {
        display:block!important;white-space:pre-wrap!important;overflow:visible!important;
        max-height:none!important;text-overflow:clip!important;overflow-wrap:anywhere;
        word-break:break-word;font-size:clamp(.8rem,1vw,1rem)!important;
        line-height:1.7!important;}
    .st-key-contract_document_paper .contract-full-sentence-hover {
        display:none;position:absolute;left:0;top:100%;z-index:50;
        width:min(38rem,80vw);max-height:65vh;overflow-y:auto;pointer-events:none;
        background:#fffdf6;color:#172b3a;border:1px solid #a6bdcc;
        border-radius:8px;box-shadow:0 12px 35px rgba(0,0,0,.17);
        padding:1rem;white-space:pre-wrap;overflow-wrap:anywhere;
        font:normal max(.875rem,11pt)/1.7 Georgia,"Malgun Gothic",serif;}
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:hover) .contract-full-sentence-hover,
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"]:has(button:focus-visible) .contract-full-sentence-hover {
        display:block;}
    @media(max-width:640px) {.st-key-contract_document_surface {padding:.25rem;}
        .st-key-contract_document_paper {padding:1rem;}}
    </style>""", unsafe_allow_html=True)
    # The AI risk-review panel is rendered BELOW this document. Surface its
    # session-only edits here too, so they cannot be mistaken for saved clauses.
    active_preview = st.session_state.get(f'contract_risk_preview_{contract_id}') or {}
    preview_texts = (active_preview.get('sentences', {})
                     if active_preview.get('revision') == revision else {})
    with st.container(key="contract_document_surface"):
        with st.container(key="contract_document_paper"):
            st.markdown(f"<h2>{escape(snapshot.get('title') or 'Contract')}</h2>", unsafe_allow_html=True)
            st.caption("DRAFT / 검토용 · 미확정 내용은 최종 합의가 아닙니다.")
            if preview_texts:
                st.info(f"AI 위험 검토 수정안 {len(preview_texts)}개를 아래 문장에 미리 반영했습니다. "
                        "아직 저장된 계약서가 아닙니다. 아래 'AI 핵심 위험 검토'에서 "
                        "'선택한 수정안 비교·승인'을 완료해야 새 revision으로 저장됩니다.")
            for clause in sorted(snapshot.get('clauses', []), key=lambda item: item.get('order', 0)):
                st.markdown(f"<h4>{escape(clause.get('title', ''))}</h4>", unsafe_allow_html=True)
                for sentence in clause.get('sentences', []):
                    sentence_id = sentence['id']
                    displayed_text = preview_texts.get(sentence_id, sentence['text'])
                    is_open = sentence_id in opened
                    # A stable two-column row, even before the note is opened.
                    # Keeps document text aligned with a Word-style comment gutter.
                    text_col, note_col = st.columns([7, 3], gap="medium", vertical_alignment="top")
                    with text_col:
                        with st.container(key=f"contract_sentence_display_{contract_id}_{sentence_id}"):
                            if sentence_id in preview_texts:
                                st.caption("✎ AI 추천 수정안 미리보기 · 확정 저장 전")
                            # Render document prose independently of Streamlit's button label alignment.
                            # The same keyed button remains the clickable, keyboard-accessible hit area.
                            st.markdown(
                                '<div class="contract-sentence-body' + (' is-open' if is_open else '') + '">'
                                + escape(displayed_text).replace('\n', '<br/>') + '</div>',
                                unsafe_allow_html=True)
                            if st.button(displayed_text, key=f"contract_sentence_{contract_id}_{sentence_id}",
                                         help=(displayed_text if len(displayed_text) > 180 else
                                               "클릭해 이 문장의 메모를 열거나 선택합니다."),
                                         type='primary' if is_open else 'secondary', use_container_width=True):
                                if sentence_id not in opened:
                                    opened.append(sentence_id)
                                st.rerun()
                            # Full original text on mouse hover / keyboard focus for very long sentences.
                            # escape() prevents user-supplied contract text from injecting markup.
                            if len(displayed_text) > 180:
                                st.markdown(
                                    '<div class="contract-full-sentence-hover" role="tooltip">'
                                    + escape(displayed_text).replace('\n', '<br/>') + '</div>',
                                    unsafe_allow_html=True)
                    with note_col:
                        if not is_open:
                            st.caption("✎ 메모 추가 · 문장 클릭")
                            continue
                        with st.container(border=True):
                            st.caption("✎ 이 문장의 수정 메모")
                            widget_key = f"contract_note_{contract_id}_{revision}_{sentence_id}"
                            old_note = next((row for row in annotations
                                             if row.get('sentence_id') == sentence_id and row.get('status') == 'note'
                                             and row.get('base_revision') != revision
                                             and row.get('id') not in snapshot.get('applied_note_ids', [])), {})
                            prior_buffers = [(key, value) for key, value in st.session_state.items()
                                             if key.startswith(f'contract_note_buffer_{contract_id}_')
                                             and key != buffer_key and isinstance(value, dict)
                                             and str(value.get(sentence_id) or '').strip()]
                            prior_text = old_note.get('instruction', '')
                            if not prior_text and prior_buffers:
                                prior_text = prior_buffers[-1][1][sentence_id]
                            initial = buffers.get(sentence_id, saved_notes.get(sentence_id, {}).get('instruction', prior_text))
                            if prior_text and sentence_id not in saved_notes and sentence_id not in buffers:
                                st.caption('이전 revision의 메모입니다. 현재 문장을 확인하고 수정하거나 저장해야 새 요청에 포함됩니다.')
                            if widget_key not in st.session_state:
                                st.session_state[widget_key] = initial
                            note = st.text_area("수정 메모 / 원하는 변경을 입력하세요", key=widget_key,
                                                label_visibility='collapsed', height=100,
                                                placeholder='이 문장을 어떻게 수정할까요?',
                                                on_change=_note_changed,
                                                args=(buffer_key, sentence_id, widget_key, contract_id))
                            with st.expander("메모 저장·개별 수정", expanded=False):
                                if st.button("메모 저장", key=f"contract_save_note_{contract_id}_{sentence_id}"):
                                    if not note.strip():
                                        st.error("메모를 입력해 주세요.")
                                    else:
                                        try:
                                            row = _note_row(snapshot, sentence_id, note, saved_notes)
                                            repo.save_annotation(row)
                                            buffers[sentence_id] = note
                                            st.success("메모를 저장했습니다.")
                                            st.rerun()
                                        except ContractRepositoryError as exc:
                                            st.error(str(exc))
                                if st.button("AI 수정안 만들기", disabled=not note.strip() or not st.session_state.get(f'contract_ai_consent_{contract_id}', False),
                                             key=f"contract_make_revision_{contract_id}_{sentence_id}"):
                                    try:
                                        proposal = propose_revision(snapshot, sentence_id, note, env=env)
                                        repo.save_annotation({
                                            'id': proposal['id'].replace('proposal_', ''), 'contract_id': contract_id,
                                            'sentence_id': sentence_id, 'base_revision': revision,
                                            'instruction': note, 'proposal': proposal, 'status': 'proposed'})
                                        st.session_state['contract_pending_proposal'] = proposal
                                        st.session_state['contract_pending_proposal_key'] = state_key
                                        st.rerun()
                                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                                        st.error(str(exc))
                                st.button("메모 삭제", key=f"contract_note_remove_{contract_id}_{sentence_id}",
                                          on_click=_remove_note, args=(repo, snapshot, sentence_id, saved_notes,
                                                                      buffer_key, open_key, widget_key))
                            if st.button("메모 닫기", key=f"contract_note_close_{contract_id}_{sentence_id}"):
                                buffers[sentence_id] = note
                                opened.remove(sentence_id)
                                st.rerun()
    # 2026-11-09 통합 최종 수정 요청 UI: the final action is placed after AI risk review.
    return pending, buffers


def _note_row(snapshot, sentence_id, instruction, saved_notes):
    return {'id': saved_notes.get(sentence_id, {}).get('id') or str(uuid5(
                NAMESPACE_URL, f"{snapshot['contract_id']}:{snapshot['revision']}:{sentence_id}:note")),
            'contract_id': snapshot['contract_id'], 'sentence_id': sentence_id,
            'base_revision': snapshot['revision'], 'instruction': instruction.strip(),
            'proposal': None, 'status': 'note'}


def _restore_previous_revision_note(contract_id, revision, sentence_id, instruction):
    """Explicitly recover a previous note without silently approving old text."""
    buffer_key = f'contract_note_buffer_{contract_id}_{revision}'
    st.session_state.setdefault(buffer_key, {})[sentence_id] = str(instruction).strip()
    widget_key = f'contract_note_{contract_id}_{revision}_{sentence_id}'
    # Streamlit on_click runs before widgets are created on the next rerun.
    st.session_state[widget_key] = str(instruction).strip()
    open_key = f'contract_open_notes_{contract_id}_{revision}'
    opened = st.session_state.setdefault(open_key, [])
    if sentence_id not in opened:
        opened.append(sentence_id)
    proposal = st.session_state.get('contract_pending_proposal') or {}
    if proposal.get('contract_id') == contract_id and proposal.get('note_ids'):
        st.session_state.pop('contract_pending_proposal', None)


def _batch_request_panel(repo, snapshot, state_key, env, pending, buffers):
    saved_notes = {row['sentence_id']: row for row in pending['notes']}
    instructions = {sentence_id: row['instruction'] for sentence_id, row in saved_notes.items()}
    instructions.update(buffers)
    notes = [_note_row(snapshot, sentence_id, instruction, saved_notes)
             for sentence_id, instruction in instructions.items() if str(instruction).strip()]
    st.markdown("#### 수정 메모")
    st.caption(f"현재 revision에 요청할 메모 {len(notes)}개 · 여러 문장에 메모를 작성한 뒤 한 번에 요청하세요.")
    if pending['excluded']:
        with st.expander(f"이전·중복·제외 메모 ({len(pending['excluded'])})", expanded=False):
            valid_ids = {s.get('id') for c in snapshot.get('clauses', [])
                         for s in c.get('sentences', [])}
            restored_ids = set()
            for item in pending['excluded']:
                old = item['note']
                sentence_id = old.get('sentence_id')
                st.caption(f"{sentence_id} · {item['reason']}")
                st.write(old.get('instruction', ''))
                # Only same-contract, existing-sentence, non-consumed old notes
                # may be copied. The user must explicitly request restoration.
                recoverable = (old.get('contract_id') == snapshot['contract_id']
                               and old.get('base_revision') != snapshot['revision']
                               and old.get('status') == 'note'
                               and sentence_id in valid_ids
                               and sentence_id not in restored_ids
                               and sentence_id not in instructions
                               and old.get('id') not in snapshot.get('applied_note_ids', [])
                               and str(old.get('instruction') or '').strip())
                if recoverable:
                    restored_ids.add(sentence_id)
                    st.button('이 메모를 현재 revision에서 다시 사용',
                              key=f"contract_restore_note_{snapshot['contract_id']}_{snapshot['revision']}_{sentence_id}",
                              on_click=_restore_previous_revision_note,
                              args=(snapshot['contract_id'], snapshot['revision'],
                                    sentence_id, old['instruction']))
    preview_state = st.session_state.get(f"contract_risk_preview_{snapshot['contract_id']}") or {}
    risk_previews = (preview_state.get('sentences', {})
                     if preview_state.get('revision') == snapshot['revision'] else {})
    risk_previews = {sid: str(value).strip() for sid, value in risk_previews.items()
                     if str(value or '').strip()}
    st.caption(f'현재 revision의 문장 메모 {len(notes)}건 + 위험 검토 선택안 {len(risk_previews)}건을 함께 검토합니다.')
    st.caption('최종 수정 요청은 AI 수정안을 준비하는 단계입니다. 본문은 비교·승인 후 새 revision으로 저장됩니다.')
    consent = st.session_state.get(f"contract_ai_consent_{snapshot['contract_id']}", False)
    existing_proposal = st.session_state.get('contract_pending_proposal') or {}
    other_proposal = existing_proposal.get('contract_id') == snapshot['contract_id']
    if not notes and not risk_previews:
        st.info('현재 revision에 수정할 내용이 없습니다. 문장 옆 메모 또는 위의 AI 위험 검토에서 추천안을 적용하세요.')
    if notes and not consent:
        st.caption('문장 메모의 AI 통합 수정에는 BOX 1의 AI 전송 동의가 필요합니다.')
    if other_proposal:
        st.caption('이미 생성한 수정안이 있습니다. 아래에서 비교·승인하거나 취소한 다음 요청하세요.')
    overlap = set(n['sentence_id'] for n in notes) & set(risk_previews)
    if overlap:
        st.warning('같은 문장에 메모와 위험 검토 추천안이 함께 있습니다: '
                   + ', '.join(sorted(overlap)) + '. 한쪽을 제거하거나 메모를 통합하세요.')
    if st.button('최종 수정 요청', type='primary',
                 disabled=(not (notes or risk_previews) or (notes and not consent) or other_proposal or bool(overlap)),
                 key=f"contract_batch_request_{snapshot['contract_id']}_{snapshot['revision']}"):
        try:
            # Persist all edited notes first. A failure prevents any AI request or contract revision.
            for note in notes:
                if note['instruction'] != saved_notes.get(note['sentence_id'], {}).get('instruction'):
                    repo.save_annotation(note)
            for sentence_id, instruction in buffers.items():
                if not str(instruction).strip() and sentence_id in saved_notes:
                    dismissed = dict(saved_notes[sentence_id], status='dismissed')
                    repo.save_annotation(dismissed)
            with st.spinner('문장 메모와 위험 검토 추천안을 하나의 수정안으로 통합하고 있습니다...'):
                proposal = merge_revision_requests(
                    snapshot, notes, risk_previews,
                    propose_notes=propose_notes_revision, env=env)
            repo.save_annotation({
                'id': proposal['id'].replace('proposal_', ''), 'contract_id': snapshot['contract_id'],
                'sentence_id': 'batch-revision', 'base_revision': snapshot['revision'],
                'instruction': proposal.get('instruction', ''), 'proposal': proposal, 'status': 'proposed'})
            st.session_state['contract_pending_proposal'] = proposal
            st.session_state['contract_pending_proposal_key'] = state_key
            st.rerun()
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))


def _review_panel(repo, snapshot, state_key, issues):
    language = st.session_state.get('contract_review_language', 'ko')
    cards = review_cards(issues, language=language)
    if not cards and not snapshot.get('issues'):
        return
    with st.expander("고급 검토 기록 · 확정 근거 확인 (선택)", expanded=False):
        st.caption("분류는 작업 안내입니다. TBD 유지는 미확정을 보존하며 최종 검증을 해제하지 않습니다.")
        for card in cards:
            st.markdown(f"**{card['kind']} · {card['summary']}**")
            destination = "parties" if card['target'] == 'parties' else "terms"
            st.markdown(f"[BOX 2에서 해당 조건 확인](#contract-{destination})")
        with st.expander("원본 쟁점 및 항목별 확인 근거", expanded=False):
            updates = []
            # Original evidence appears ONCE, only here; controls never repeat it.
            for index, raw in enumerate(snapshot.get('issues', [])):
                issue = raw if isinstance(raw, dict) else {'message': str(raw)}
                st.write(issue.get('message', ''))
                effective_severity = issue.get('original_severity', issue.get('severity'))
                if effective_severity not in {'confirm', 'block'}:
                    continue
                item_key = f"{snapshot['contract_id']}_{snapshot['revision']}_{index}"
                action = st.radio("이 항목 처리", ['TBD 유지', '확정', '수정'], horizontal=True,
                                  index=1 if issue.get('confirmed') or issue.get('resolved_by_user') else 0,
                                  key=f"contract_issue_action_{item_key}")
                if action == '수정':
                    st.markdown('[BOX 2에서 값 수정 및 본문 영향 검토](#contract-terms)')
                reason = st.text_input("이 항목만 확인한 근거 (조건표 값은 별도로 저장)",
                                       value=issue.get('resolution') or '', key=f"contract_issue_evidence_{item_key}")
                updates.append((index, action, reason))
            if updates and st.button("항목별 검토 상태 저장", key=f"contract_review_save_{snapshot['contract_id']}_{snapshot['revision']}"):
                updated = deepcopy(snapshot)
                invalid = False
                for index, action, reason in updates:
                    issue = updated['issues'][index]
                    severity = issue.get('original_severity', issue.get('severity'))
                    if action in {'TBD 유지', '수정'}:
                        if severity == 'confirm' and issue.get('confirmed'):
                            issue['confirmed'] = False
                        elif issue.get('resolved_by_user'):
                            issue['severity'] = severity
                            issue['resolved_by_user'] = False
                        continue
                    if severity == 'confirm':
                        issue['confirmed'] = True
                    elif not reason.strip():
                        invalid = True
                    else:
                        issue.update(resolved_by_user=True, resolution=reason.strip(),
                                     original_severity=severity, severity='info')
                if invalid:
                    st.error("차단 쟁점은 해당 항목의 확인 근거를 입력해야 합니다.")
                elif updated == snapshot:
                    st.info("변경된 검토 상태가 없습니다. 현재 revision과 메모를 유지했습니다.")
                else:
                    try:
                        saved = _save_snapshot(repo, updated, 'User reviewed individual contract findings')
                        st.session_state[state_key] = saved
                        st.rerun()
                    except ContractRepositoryError as exc:
                        st.error(str(exc))
            other = [i for i in issues if i not in snapshot.get('issues', [])]
            if other:
                st.caption("현재 최종 검사 원문 — 위 조건표에서 값을 수정·확정해야 합니다.")
                for issue in other:
                    st.write(issue.get('message', ''))


def _export_panel(repo, snapshot, env):
    issues = validate_rules(snapshot, for_export=True, env=env)
    st.markdown("#### 문서 다운로드")
    st.caption("검토용 DRAFT PDF/Word는 미확정 정보가 있어도 만들 수 있습니다. "
               "FINAL은 필수 조건을 실제로 확인해야 생성됩니다. 검토 목록을 숨겨도 최종 검증 결과는 달라지지 않습니다.")
    draft_col, final_col = st.columns(2)
    for column, mode, title in ((draft_col, 'draft', '검토용 초안'), (final_col, 'final', '최종 계약서')):
        with column:
            st.markdown(f"**{'DRAFT / 검토용' if mode == 'draft' else 'FINAL / 최종 검증'}**")
            if mode == 'final' and issues:
                st.caption(f"최종 확인이 필요한 항목 {len(issues)}건. BOX 2에서 실제 조건을 입력·확정하고, "
                           "필요하면 아래 '고급 검토 기록'에서 AI 쟁점 근거를 확인하세요.")
            for extension in ('pdf', 'docx'):
                if st.button(f"{title} {extension.upper()}",
                             disabled=bool(issues) if mode == 'final' else False,
                             key=f"contract_export_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}"):
                    try:
                        # Separate paths; final validation is always recomputed here.
                        if mode == 'final' and validate_rules(snapshot, for_export=True, env=env):
                            raise ValueError("최종 검증을 통과하지 못했습니다.")
                        outputs = (export_draft(snapshot, formats=(extension,), env=env) if mode == 'draft'
                                   else export_contract(snapshot, formats=(extension,)))
                        # Render first, then save privately. Do not conflate a valid PDF
                        # with a failed Supabase upload or export-record write.
                        local_key = f"contract_unsaved_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}"
                        saved_key = f"contract_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}"
                        try:
                            _persist_contract_outputs(repo, snapshot, outputs, mode)
                        except ContractRepositoryError as storage_exc:
                            # _persist_contract_outputs already performs its normal
                            # partial-upload rollback. Keep bytes only in this session,
                            # not in the DB or a public location.
                            st.session_state[local_key] = outputs[extension]
                            st.session_state.pop(saved_key, None)
                            st.warning("파일은 생성됐지만 비공개 저장소 기록에 실패했습니다. "
                                       "아래 '직접 다운로드'로 받을 수 있습니다. "
                                       f"서버 저장 실패 원인: {storage_exc}")
                        else:
                            st.session_state.pop(local_key, None)
                            st.session_state[saved_key] = outputs[extension]
                            st.success("현재 revision의 파일을 비공개 저장했습니다.")
                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                        st.error(f"파일 생성 단계에서 실패했습니다. {exc}")
                output = st.session_state.get(f"contract_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
                if output and not (mode == 'final' and issues):
                    st.download_button(f"{title} {extension.upper()} 다운로드", data=output['content'],
                                       file_name=output['filename'], mime=_contract_mime(extension),
                                       key=f"contract_download_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
                local_output = st.session_state.get(
                    f"contract_unsaved_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
                if local_output and not (mode == 'final' and issues):
                    st.download_button(f"{title} {extension.upper()} 직접 다운로드 (서버 미저장)",
                                       data=local_output['content'], file_name=local_output['filename'],
                                       mime=_contract_mime(extension),
                                       key=f"contract_local_download_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
    try:
        current_exports = [item for item in repo.list_exports(snapshot['contract_id'])
                           if item.get('revision') == snapshot['revision']]
    except ContractRepositoryError as exc:
        st.caption(f"비공개 출력 기록을 조회하지 못했습니다. 서버 저장 상태를 확인해 주세요: {exc}")
        current_exports = []
    if current_exports:
        with st.expander("현재 revision의 비공개 출력 기록", expanded=False):
            for item in current_exports:
                draft = '/exports/draft/' in item['storage_path']
                if not draft and issues:
                    continue
                label = 'DRAFT / 검토용' if draft else 'FINAL'
                if st.button(f"{label} · {item['format'].upper()} 파일 다시 받기",
                             key=f"contract_saved_export_{item['id']}"):
                    try:
                        content = repo.download_private_file('kekorea-contracts', item['storage_path'])
                        st.download_button(f"{label} 다운로드", data=content,
                                           file_name=item['storage_path'].rsplit('/', 1)[-1],
                                           mime=_contract_mime(item['format']), key=f"contract_redownload_{item['id']}")
                    except ContractRepositoryError as exc:
                        st.error(str(exc))
    # Optional audit/reconciliation controls are still reachable, but never
    # interrupt DRAFT download or masquerade as the FINAL export validator.
    _review_panel(repo, snapshot, f"contract_snapshot_{snapshot['contract_id']}", issues)


def _contract_mime(extension):
    return ('application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            if extension == 'docx' else 'application/pdf')


def _persist_contract_outputs(repo, snapshot, outputs, mode):
    uploaded_paths, saved_records = [], []
    try:
        for extension, output in outputs.items():
            path = (f"{snapshot['contract_id']}/exports/{mode}/r{snapshot['revision']}/"
                    f"{uuid4().hex}-{output['filename']}")
            repo.upload_private_file('kekorea-contracts', path, output['content'], _contract_mime(extension))
            uploaded_paths.append(path)
            saved_records.append((extension, path))
            repo.save_export({
                'contract_id': snapshot['contract_id'], 'revision': snapshot['revision'],
                'language': snapshot['language'], 'format': extension,
                'storage_path': path, 'content_hash': output['sha256'],
            })
    except (ValueError, RuntimeError, ContractRepositoryError):
        for extension, path in saved_records:
            try:
                repo.delete_export(snapshot['contract_id'], snapshot['revision'], extension, path)
            except ContractRepositoryError:
                st.error("부분 생성 기록의 정리가 필요합니다. 출력 기록을 확인하세요.")
        for path in uploaded_paths:
            try:
                repo.delete_private_file('kekorea-contracts', path)
            except ContractRepositoryError:
                st.error("부분 생성 파일의 정리가 필요합니다. 비공개 저장소를 확인하세요.")
        raise


def _run_editor(repo, snapshot, state_key, env):
    st.markdown('<span id="contract-terms"></span>', unsafe_allow_html=True)
    st.markdown("#### 거래금액·수수료·지급·기간·법률 및 기타 조건")
    candidate_key = f"contract_clause_candidates_{snapshot['contract_id']}_{snapshot['revision']}"
    editor_version_key = f"contract_terms_editor_version_{snapshot['contract_id']}_{snapshot['revision']}"
    st.caption('계약서 본문과 구조화 조건표는 별도 데이터입니다. 이미 본문에 있는 정보만 AI가 다시 추출해 입력 후보로 보여줍니다.')
    can_extract = bool(clause_evidence(snapshot)) and st.session_state.get(f"contract_ai_consent_{snapshot['contract_id']}", False)
    if st.button('계약서 본문에서 조건 후보 불러오기', disabled=not can_extract,
                 key=f"contract_clause_extract_{snapshot['contract_id']}_{snapshot['revision']}"):
        try:
            with st.spinner('현재 계약서 본문에서 거래조건 후보를 찾는 중입니다...'):
                analysis = analyze_trade([{'role': 'user', 'content': clause_evidence(snapshot)}],
                                         snapshot, [], env=env)
            if analysis['contract_type'] != snapshot['contract_type']:
                raise ValueError('계약 유형이 달라 기존 조건을 보존했습니다.')
            staged = merge_clause_candidates(snapshot, analysis)
            st.session_state[candidate_key] = staged
            st.session_state[editor_version_key] = st.session_state.get(editor_version_key, 0) + 1
            st.rerun()
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(f'본문 거래조건 후보 추출 실패: {exc}')
    editor_snapshot = st.session_state.get(candidate_key) or snapshot
    if candidate_key in st.session_state:
        st.info('본문에서 찾은 조건이 입력표에 AI 제안으로 나타납니다. 실제 값과 당사자 정보를 검토하고 상태를 확정한 뒤 기존 저장 버튼을 누르세요. 아직 원본은 변경되지 않았습니다.')
        for conflict in editor_snapshot.get('clause_extraction_conflicts', []):
            st.warning(f"서로 다른 추출값이 발견되었습니다: {conflict['key']} · {conflict['first']} / {conflict['other']}. 원문을 확인하세요.")
        if st.button('불러온 후보 취소', key=f"contract_clause_cancel_{snapshot['contract_id']}_{snapshot['revision']}"):
            st.session_state.pop(candidate_key, None)
            st.session_state[editor_version_key] = st.session_state.get(editor_version_key, 0) + 1
            st.rerun()
    editor_version = st.session_state.get(editor_version_key, 0)
    state_key_terms = f"contract_terms_table_{snapshot['contract_id']}_{snapshot['revision']}"
    if editor_version:
        state_key_terms += f"_{editor_version}"
    terms_rows = st.data_editor(
        _term_rows(editor_snapshot), key=state_key_terms, hide_index=True,
        num_rows="dynamic", width="stretch",
        column_config={
            "key": st.column_config.TextColumn("내부 키", disabled=True),
            "항목": st.column_config.TextColumn("조건 항목", disabled=True),
            "value": st.column_config.TextColumn("값"),
            "unit": st.column_config.TextColumn("단위"),
            "currency": st.column_config.TextColumn("통화"),
            "status": st.column_config.SelectboxColumn(
                "상태", options=["확인 필요", "AI 제안", "확정", "TBD 유지"],
                required=True, help="확정은 명시적으로 승인한 값만 선택하세요. TBD는 최종본을 차단하는 미확정 상태입니다."),
        },
    )
    st.caption("확정=사용자 승인, AI 제안=미승인 후보, 확인 필요·TBD 유지=미확정. 검토용 초안은 가능하며 최종본만 검증합니다.")
    st.markdown('<span id="contract-parties"></span>', unsafe_allow_html=True)
    st.markdown("#### 당사자 및 역할")
    party_rows = st.data_editor(
        _party_rows(editor_snapshot), key=f"contract_parties_table_{snapshot['contract_id']}_{snapshot['revision']}_{st.session_state.get(editor_version_key, 0)}",
        hide_index=True, num_rows="dynamic", use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn("ID", disabled=True),
            "legal_name": st.column_config.TextColumn("법인명"),
            "country": st.column_config.TextColumn("국가"),
            "address": st.column_config.TextColumn("주소"),
            "representative": st.column_config.TextColumn("대표/서명권자"),
            "roles": st.column_config.TextColumn("역할 (쉼표 구분)"),
            "status": st.column_config.SelectboxColumn(
                "상태", options=["확인 필요", "AI 제안", "확정", "TBD 유지"], required=True),
        },
    )
    omitted = deepcopy(snapshot.get("omissions", {}))
    invalid_omission_reason = False
    with st.expander("준거법·분쟁 해결 조항 제외 결정"):
        st.caption("AI는 이 내용을 임의로 정하지 않습니다. 제외 결정은 법적 적정성 확인을 대신하지 않습니다.")
        for key, label in (("governing_law", "준거법"), ("dispute_resolution", "분쟁 해결")):
            omit = st.checkbox(f"{label} 조항을 이번 문서에서 제외하기로 결정",
                               value=key in omitted,
                               key=f"contract_omit_{snapshot['contract_id']}_{key}")
            reason = st.text_input(f"{label} 제외 사유",
                                   value=omitted.get(key, {}).get("reason", ""),
                                   key=f"contract_omit_reason_{snapshot['contract_id']}_{key}")
            reason_text = str(reason or "").strip()
            if omit and reason_text:
                omitted[key] = {"reason": reason_text, "confirmed": True}
            else:
                omitted.pop(key, None)
                if omit:
                    invalid_omission_reason = True
    if st.button("조건표 변경 저장 / 초안 영향 확인",
                 key=f"contract_save_terms_{snapshot['contract_id']}_{snapshot['revision']}"):
        try:
            updated = _merge_edited_data(snapshot, _rows(terms_rows), _rows(party_rows))
            updated["omissions"] = omitted
            term_changes = _changed_terms(snapshot, updated)
            if invalid_omission_reason:
                raise ValueError("조항 제외를 선택한 경우 사유를 입력해 주세요.")
            if not term_changes:
                st.info("저장할 변경 사항이 없습니다.")
            elif snapshot.get("clauses"):
                proposal = propose_term_revision(snapshot, term_changes,
                                                 env=env)
                st.session_state["contract_pending_proposal"] = proposal
                st.session_state["contract_pending_terms"] = term_changes
                st.session_state["contract_pending_proposal_key"] = state_key
                repo.save_annotation({
                    "id": proposal["id"].replace("proposal_", ""),
                    "contract_id": snapshot["contract_id"],
                    "sentence_id": proposal["target_sentence_id"] or "term-reconciliation",
                    "base_revision": snapshot["revision"],
                    "instruction": "Reconcile edited contract terms with the draft",
                    "proposal": proposal, "status": "proposed",
                })
                st.rerun()
            else:
                saved = _save_snapshot(repo, updated, "User edited contract parties and terms")
                st.session_state[state_key] = saved
                st.success(f"조건을 revision {saved['revision']}로 저장했습니다.")
                st.rerun()
        except (ValueError, RuntimeError, RevisionConflict, ContractRepositoryError) as exc:
            st.error(str(exc))


def _chat_history_window(messages, *, recent_limit=20):
    """Return older and recent chat messages without mutating persisted history."""
    if recent_limit < 1:
        raise ValueError("recent_limit must be positive")
    return messages[:-recent_limit], messages[-recent_limit:]


def _contract_chat(repo, snapshot, state_key, env):
    st.markdown("### 거래 내용과 AI 분석")
    if snapshot['contract_type'] in COMMISSION_TYPES:
        st.caption("거래 조건과 주의사항을 입력하세요. 참고 계약의 구조를 응용해 양사 권리를 조정합니다. 각 트리거 D+7 달력일 이내 TT 지급을 적용하며, 연체이율은 지급자 국가와 준거법상 적용 가능성을 확인합니다.")
    st.caption("원하는 계약조건을 입력한 뒤 '계약서 초안을 작성해줘'라고 요청하세요. "
               "반복 질문 대신 초안을 먼저 만들고, 문장 클릭으로 수정할 수 있습니다.")
    messages = repo.list_messages(snapshot["contract_id"])
    # Recent messages form the conversation; earlier records stay available on demand.
    older_messages, recent_messages = _chat_history_window(messages)
    if older_messages:
        with st.expander(f"이전 대화 {len(older_messages)}개 보기", expanded=False):
            for message in older_messages:
                with st.chat_message(message["role"]):
                    st.write(message["content"])
    with st.container(height=420, border=True):
        if not recent_messages:
            st.caption("대화를 시작해 거래 조건과 확인 사항을 입력하세요.")
        for message in recent_messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
    use_library = st.checkbox('승인된 공통 샘플에서 관련 조항 자동 참고', value=True,
                              key=f"contract_use_library_{snapshot['contract_id']}")
    refs = repo.contract_references(snapshot["contract_id"])
    selected_refs = []
    if refs:
        selected_refs = st.multiselect(
            "AI에 참고 문구로 전달할 계약서",
            options=[row["id"] for row in refs],
            format_func=lambda value: next(row["filename"] for row in refs if row["id"] == value),
            key=f"contract_context_refs_{snapshot['contract_id']}")
    consent = st.checkbox("입력한 거래 내용과 선택한 참고 문구·승인된 샘플 메모를 설정된 OpenAI API로 전송하는 데 동의합니다.",
                          key=f"contract_ai_consent_{snapshot['contract_id']}")
    prompt = st.chat_input(
        "거래 내용, 추가 조건 또는 답변을 입력하세요",
        key=f"contract_prompt_{snapshot['contract_id']}",
        disabled=not consent,
    )
    if prompt and prompt.strip():
        try:
            repo.add_message(snapshot["contract_id"], "user", prompt.strip())
            with st.chat_message("user"):
                st.write(prompt.strip())
            selected_context = [{"id": row["id"], "filename": row["filename"],
                                 "extracted_text": (row.get("extracted_text") or "")[:12000]}
                                for row in refs if row["id"] in selected_refs]
            library_result = {'references': [], 'sources': [], 'notices': []}
            if use_library:
                library_result = search_library(repo, snapshot, prompt, env=env)
                selected_context += library_result['references']
                for message in library_result['notices']:
                    st.warning(message)
            prior_messages = messages + [{"role": "user", "content": prompt.strip()}]
            with st.spinner("AI가 거래조건을 분석하고 있습니다..."):
                analysis = analyze_trade(prior_messages, snapshot, selected_context, env=env)
            if analysis["contract_type"] != snapshot["contract_type"]:
                raise ValueError("AI가 다른 계약 유형으로 분류했습니다. 새 계약 유형을 선택한 뒤 다시 분석해 주세요.")
            # First conversation response can ask up to two questions; after the
            # user's next message generate the draft instead of asking again.
            make_draft = should_generate_draft(
                prompt, prior_messages, has_clauses=bool(snapshot.get("clauses")))
            analysis["questions"] = ([] if make_draft else
                                     select_new_questions(analysis.get("questions", []), prior_messages))
            updated = apply_analysis(snapshot, analysis)
            updated['library_sources'] = library_result['sources']
            updated["reference_ids"] = sorted(set(
                updated.get("reference_ids", []) + selected_refs
            ))
            made_draft = False
            if make_draft:
                preferred = [clause for clause in repo.list_preferred_clauses()
                             if clause.get("active")
                             and updated["contract_type"] in clause.get("contract_types", [])
                             and clause.get("language") == updated["language"]]
                with st.spinner("확인되지 않은 항목을 표시하고 계약서 초안을 작성합니다..."):
                    updated = generate_draft(
                        updated, preferred, env=env, reference_context=selected_context,
                        transaction_messages=prior_messages)
                updated["library_sources"] = library_result["sources"]
                made_draft = True
            if snapshot.get("clauses"):
                st.session_state[f"contract_pending_analysis_{snapshot['contract_id']}"] = {
                    "snapshot": updated,
                    "changes": _changed_terms(snapshot, updated),
                    "base_revision": snapshot["revision"],
                }
                st.info("기존 초안은 유지했습니다. 분석 결과는 별도 후보로 저장되며, 아래에서 선택적으로 수정안 생성 후 적용하세요.")
            else:
                saved = _save_snapshot(repo, updated, "AI extracted candidate contract terms")
                st.session_state[state_key] = saved
            response_language = conversation_response_language(prompt)
            if made_draft:
                response = ("Draft generated. Review the contract below and click individual sentences to request edits."
                            if response_language == "en" else
                            "계약서 초안을 작성했습니다. 아래 본문을 검토하고 수정할 문장을 클릭해 명령해 주세요. "
                            "미확정 사항은 검토 항목으로 남겨두었습니다.")
                repo.add_message(snapshot["contract_id"], "assistant", response)
                st.rerun()
            if response_language == "en":
                response = (f"Trade terms analyzed: {len(analysis.get('terms', []))} candidates, "
                            f"{len(analysis.get('questions', []))} questions to clarify.")
            else:
                response = (f"거래조건을 분석했습니다. 조건 후보 {len(analysis.get('terms', []))}개, "
                            f"확인할 질문 {len(analysis.get('questions', []))}개입니다.")
            if analysis.get("questions"):
                response += ("\n\nQuestions to clarify:\n" if response_language == "en"
                             else "\n\n확인할 사항:\n") + "\n".join(
                    f"- {question}" for question in analysis["questions"][:5])
            if snapshot.get("clauses"):
                response += ("\n\nThe existing draft was not overwritten. Review the analysis candidates below before applying them."
                             if response_language == "en"
                             else "\n\n기존 계약 내용은 자동 덮어쓰지 않았습니다. 아래 분석 후보를 검토해 적용하세요.")
            repo.add_message(snapshot["contract_id"], "assistant", response)
            st.rerun()
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))
    pending = st.session_state.get(f"contract_pending_analysis_{snapshot['contract_id']}")
    if pending:
        with st.expander("기존 초안과 새 분석 후보 비교", expanded=True):
            if pending.get("base_revision") != snapshot.get("revision"):
                st.warning("새 분석 이후 계약 revision이 변경되어 이 후보는 오래되었습니다.")
                if st.button("오래된 분석 후보 폐기",
                             key=f"contract_discard_analysis_{snapshot['contract_id']}"):
                    st.session_state.pop(f"contract_pending_analysis_{snapshot['contract_id']}", None)
                    st.rerun()
                return
            st.write("선택한 분석 후보만 수정안으로 만들며, 기존 조건/본문은 사용자가 적용할 때까지 바뀌지 않습니다.")
            selected_changes = []
            candidate_snapshot = pending["snapshot"]
            party_map = {role: party for party in candidate_snapshot.get("parties", [])
                         for role in party.get("roles", [])}
            term_map = {term.get("key"): term for term in candidate_snapshot.get("terms", [])}
            for index, change in enumerate(pending["changes"]):
                key = change.get("key")
                if key and key.startswith("party."):
                    _, role, field = key.split(".", 2)
                    proposed_value = (party_map.get(role, {}).get(field)
                                      if field != "status" else "확인 필요")
                    label = f"{ROLE_LABELS.get(role, role)} · {field}: {proposed_value or '미정'}"
                else:
                    term = term_map.get(key, change)
                    label = (f"{LABELS.get(key, key)}: {term.get('value') or '미정'} "
                             f"{term.get('unit') or ''} {term.get('currency') or ''} "
                             f"({STATUS_LABELS.get(term.get('status'), term.get('status'))})")
                if st.checkbox(label, value=False,
                               key=f"contract_candidate_{snapshot['contract_id']}_{snapshot['revision']}_{index}"):
                    if key and key.startswith("party."):
                        _, role, field = key.split(".", 2)
                        if field == "status":
                            selected_changes.append({"key": key, "value": "confirmed",
                                                     "status": "confirmed"})
                        elif role in party_map:
                            selected_changes.append({"key": key,
                                                     "value": party_map[role].get(field),
                                                     "status": "confirmed"})
                            selected_changes.append({"key": f"party.{role}.status",
                                                     "value": "confirmed",
                                                     "status": "confirmed"})
                    else:
                        term = deepcopy(term_map.get(key, change))
                        term["status"] = "confirmed"
                        selected_changes.append(term)
            if st.button("선택 후보로 본문 영향 수정안 만들기",
                         disabled=not selected_changes,
                         key=f"contract_candidate_reconcile_{snapshot['contract_id']}"):
                try:
                    unique_changes = {change["key"]: change for change in selected_changes}
                    proposal = propose_term_revision(
                        snapshot, list(unique_changes.values()), env=env)
                    st.session_state["contract_pending_proposal"] = proposal
                    st.session_state["contract_pending_proposal_key"] = state_key
                    repo.save_annotation({
                        "id": proposal["id"].replace("proposal_", ""),
                        "contract_id": snapshot["contract_id"],
                        "sentence_id": "analysis-reconciliation",
                        "base_revision": snapshot["revision"],
                        "instruction": "Reconcile selected AI analysis candidates",
                        "proposal": proposal, "status": "proposed",
                    })
                    st.session_state.pop(f"contract_pending_analysis_{snapshot['contract_id']}", None)
                    st.rerun()
                except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                    st.error(str(exc))
    questions = snapshot.get("questions", [])
    if questions and not snapshot.get("clauses"):
        with st.expander("초안 작성 전 확인할 핵심 질문 (선택)", expanded=False):
            for question in questions:
                st.write(f"- {question}")


def render_contract_page(page, env):
    """Render a contract workflow without changing the existing sidebar definition."""
    st.markdown('<div class="ke-header"><div class="ke-eyebrow">KE KOREA · CONTRACT WORKSPACE</div>'
                '<h1>계약서 작성 및 검토</h1><p>AI 초안은 제안이며, 조건 확인과 사용자 적용 없이는 최종 검토 파일을 내보낼 수 없습니다.</p></div>',
                unsafe_allow_html=True)
    st.warning("이 계약 화면은 비밀번호 없이 공개 접근됩니다. 앱 주소를 아는 누구나 저장된 계약과 참고 파일을 열람·수정·삭제할 수 있습니다.")
    try:
        repo = _repository(env)
    except (ValueError, ContractRepositoryError) as exc:
        st.error(str(exc))
        return
    render_library_admin(repo, env)
    st.markdown("### 새 계약")
    with st.form(f"contract_create_{page}"):
        title = st.text_input("계약 제목", value="")
        contract_type = st.selectbox(
            "계약 유형", list(TYPE_LABELS), index=None,
            placeholder="계약 내용에 맞는 유형을 선택해 주세요",
            format_func=lambda value: TYPE_LABELS[value],
            key=f"contract_new_type_{page}",
            help="필수 조건과 당사자 역할을 정하는 분류이며, 계약 제목에 추가되지 않습니다.")
        language = st.radio("계약서 출력 언어", ["ko", "en"],
                            format_func=lambda value: "한국어" if value == "ko" else "English",
                            horizontal=True, key=f"contract_new_language_{page}")
        create = st.form_submit_button("새 계약 시작")
    if create:
        try:
            if contract_type is None:
                raise ValueError("계약 유형을 선택해 주세요.")
            _new_contract(repo, title, contract_type, language)
            st.rerun()
        except (ValueError, ContractRepositoryError) as exc:
            st.error(str(exc))

    records = _records(repo)
    if records:
        options = {str(record["id"]): record for record in records}
        st.markdown("### 저장된 계약")
        for record in records:
            contract_id = str(record["id"])
            title_col, delete_col = st.columns([12, 1])
            if title_col.button(
                record["title"], key=f"contract_open_{page}_{contract_id}",
                use_container_width=True,
            ):
                st.session_state["contract_active_id"] = contract_id
                st.session_state.pop(f"contract_snapshot_{contract_id}", None)
                try:
                    _ensure_active_snapshot(repo, contract_id)
                    st.rerun()
                except (ValueError, ContractRepositoryError) as exc:
                    st.error(str(exc))
            if delete_col.button("X", key=f"contract_delete_{contract_id}",
                                 help=f"{record['title']} 삭제"):
                st.session_state["contract_delete_pending_id"] = contract_id
                st.rerun()
        pending_delete_id = st.session_state.get("contract_delete_pending_id")
        if pending_delete_id in options:
            _render_contract_delete_confirmation(
                repo, pending_delete_id, options[pending_delete_id]["title"])
        elif pending_delete_id:
            st.session_state.pop("contract_delete_pending_id", None)

    active_id = st.session_state.get("contract_active_id")
    if not active_id:
        st.info("새 계약을 시작하거나 저장된 계약을 열어 주세요.")
        return
    try:
        snapshot = _ensure_active_snapshot(repo, active_id)
    except (ValueError, ContractRepositoryError) as exc:
        st.error(str(exc))
        return
    state_key = f"contract_snapshot_{active_id}"
    notice = st.session_state.pop(f"contract_commit_notice_{active_id}", None)
    if notice:
        st.warning(notice)
    st.markdown(f"## {snapshot.get('title', 'Untitled contract')}")
    st.caption(f"ID: {active_id} · Revision: {snapshot['revision']} · "
               f"언어: {'한국어' if snapshot['language'] == 'ko' else 'English'}")

    with st.expander("계약 정보 수정"):
        with st.form(f"contract_metadata_{active_id}_{snapshot['revision']}"):
            edited_title = st.text_input("계약 제목 수정", value=snapshot.get("title", ""))
            edited_type = st.selectbox(
                "현재 계약 유형", list(TYPE_LABELS),
                index=list(TYPE_LABELS).index(snapshot['contract_type']),
                format_func=lambda value: TYPE_LABELS[value])
            save_metadata = st.form_submit_button("계약 정보 저장")
        if save_metadata:
            try:
                if not edited_title.strip():
                    raise ValueError("계약 제목을 입력해 주세요.")
                updated = deepcopy(snapshot)
                updated['title'] = edited_title.strip()
                updated['contract_type'] = edited_type
                if edited_type != snapshot['contract_type'] and snapshot.get('clauses'):
                    updated['issues'].append({
                        'id': f"issue_{uuid4().hex}", 'severity': 'block',
                        'code': 'contract_type_changed',
                        'message': '계약 유형이 변경되었습니다. 기존 조항과 거래조건이 새 유형에 맞는지 검토하고 필요한 내용을 수정해 주세요.',
                    })
                if updated != snapshot:
                    saved = _save_snapshot(repo, updated, "Updated contract title/type")
                    st.session_state[state_key] = saved
                    for key in ('contract_revisions', 'contract_pending_proposal',
                                'contract_pending_terms', f'contract_pending_analysis_{active_id}'):
                        st.session_state.pop(key, None)
                    st.rerun()
            except (ValueError, ContractRepositoryError) as exc:
                st.error(str(exc))

    st.selectbox("검토 화면 언어", ['ko', 'en'],
                 format_func=lambda value: '한국어' if value == 'ko' else 'English',
                 key='contract_review_language')
    with st.container(border=True, key='contract_box_1'):
        st.markdown("### BOX 1 · 계약조건 입력 및 AI 대화")
        _contract_chat(repo, snapshot, state_key, env)
        show_library_sources(snapshot.get('library_sources', []))
        refs = repo.contract_references(active_id)
        preferred = [clause for clause in repo.list_preferred_clauses()
                     if clause.get("active") and snapshot["contract_type"] in clause.get("contract_types", [])
                     and clause.get("language") == snapshot["language"]]
        conversation_messages = repo.list_messages(active_id)
        prompt_value = next(
            (str(message.get("content") or "") for message in reversed(conversation_messages)
             if message.get("role") == "user"),
            "",
        )
        has_language_conflict = language_conflict(prompt_value, snapshot["language"])
        use_selected_language = True
        if has_language_conflict:
            use_selected_language = st.checkbox(
                "요청 문구의 언어와 다르지만 현재 선택한 출력 언어를 사용합니다.",
                key=f"contract_language_override_{active_id}_{snapshot['revision']}")
        if st.button("현재 조건으로 계약서 초안 만들기",
                     disabled=(not st.session_state.get(f"contract_ai_consent_{active_id}", False)
                               or (has_language_conflict and not use_selected_language)
                               or bool(snapshot.get("clauses"))),
                     key=f"contract_generate_{active_id}_{snapshot['revision']}"):
            if has_language_conflict and not use_selected_language:
                st.error("요청 언어와 선택 언어가 다릅니다. 선택 언어 사용을 확인해 주세요.")
            else:
                try:
                    preferred_reference_ids = {
                        str(source_ref.get("document_id"))
                        for clause in preferred
                        for source_ref in clause.get("source_refs", [])
                        if isinstance(source_ref, dict) and source_ref.get("document_id")
                    }
                    selected_reference_ids = set(
                        st.session_state.get(f"contract_context_refs_{active_id}", [])
                    ) | preferred_reference_ids
                    reference_context = [
                        {
                            "id": reference["id"],
                            "filename": reference["filename"],
                            "extracted_text": (reference.get("extracted_text") or "")[:12000],
                        }
                        for reference in refs if reference["id"] in selected_reference_ids
                    ]
                    library_result = {'references': [], 'sources': [], 'notices': []}
                    if st.session_state.get(f'contract_use_library_{active_id}', True):
                        library_result = search_library(repo, snapshot, prompt_value or snapshot.get('title', ''), env=env)
                        reference_context += library_result['references']
                        for message in library_result['notices']:
                            st.warning(message)
                    draft = generate_draft(
                        snapshot, preferred, env=env, reference_context=reference_context,
                        transaction_messages=repo.list_messages(active_id),
                    )
                    draft['library_sources'] = library_result['sources']
                    saved = _save_snapshot(repo, draft, "AI generated contract draft")
                    st.session_state[state_key] = saved
                    st.success(f"초안을 revision {saved['revision']}로 저장했습니다.")
                    st.rerun()
                except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                    st.error(str(exc))
        _references_panel(repo, active_id, env)

    with st.container(border=True, key='contract_box_2'):
        st.markdown("### BOX 2 · 상세조건 직접 입력")
        st.caption("값과 상태를 직접 수정하세요. 확정은 해당 값만 승인하고, TBD 유지는 미확정으로 남깁니다.")
        _run_editor(repo, snapshot, state_key, env)
        if snapshot.get('clauses') and snapshot['contract_type'] in COMMISSION_TYPES:
            with st.expander("수수료 지급조건 수정", expanded=False):
                st.caption("상업조건을 수정하고 저장하면 계약서 지급 조항도 함께 갱신됩니다. 미검증 계좌·법률 정보는 임의로 확정하지 않습니다.")
                from Quotation_KEKOREA.contracts.commission_policy import _confirmed, _custom_deadline, _negotiated_interest
                import re as _payment_re
                current_deadline = _custom_deadline(snapshot)
                days = int(_payment_re.search(r'D\+(\d+)', current_deadline).group(1))
                current_rate = _negotiated_interest(snapshot)
                payer = next((p for p in snapshot.get('parties', [])
                              if 'commission_payer' in p.get('roles', [])), {})
                current_country = str(payer.get('country') or '')
                current_trigger = _confirmed(snapshot, 'payment_trigger') or _confirmed(snapshot, 'success_trigger')
                default_trigger = '실제 투자금 입금' if not current_trigger else current_trigger
                with st.form(f"contract_payment_edit_{active_id}_{snapshot['revision']}"):
                    trigger = st.text_input("커미션 지급 트리거", value=default_trigger,
                                            help="예: 투자금이 지급자 계좌에 실제 입금된 날")
                    payment_days = st.number_input("지급기한 (트리거 후 달력일)", min_value=1,
                                                    max_value=90, value=days, step=1)
                    chosen_rate = st.text_input("서면 합의 연체이율 (연 %, 선택)",
                                                value=str(current_rate or ''),
                                                help="예: 6 또는 6.5. 입력한 상업조건이며 법적 유효성은 별도 검토합니다.")
                    payer_country = st.text_input("지급자 설립국가 (확인 전에는 미확정)", value=current_country)
                    country_verified = st.checkbox("지급자 설립국가를 등록서류로 확인했습니다",
                        value=payer.get('status') == 'confirmed' and bool(current_country))
                    st.caption("계좌정보는 서버에 등록된 KE KOREA 명의 USD 계좌만 사용할 수 있습니다. "
                               "계좌정보가 미검증이면 [수취 계좌 확인 필요]로 남깁니다.")
                    save_payment = st.form_submit_button("지급조건 저장 및 조항 갱신", type="primary")
                if save_payment:
                    try:
                        if not str(trigger).strip():
                            raise ValueError("커미션 지급 트리거를 입력해 주세요.")
                        cleaned = str(chosen_rate).strip().removesuffix('%').strip()
                        if cleaned and not _payment_re.fullmatch(r'\d{1,2}(?:\.\d{1,2})?', cleaned):
                            raise ValueError("연체이율은 0~30 범위의 숫자로 입력해 주세요.")
                        if cleaned and not (0 <= float(cleaned) <= 30):
                            raise ValueError("연체이율은 0~30% 범위로 입력해 주세요.")
                        updated = deepcopy(snapshot)
                        def set_term(key, value, status='confirmed'):
                            term = next((x for x in updated.get('terms', []) if x.get('key') == key), None)
                            if term is None:
                                term = {'id': f'term_{uuid4().hex}', 'key': key,
                                        'source_refs': [], 'status': status}
                                updated.setdefault('terms', []).append(term)
                            term.update(value=value, status=status, source_refs=[])
                        set_term('payment_trigger', str(trigger).strip())
                        set_term('payment_deadline', f'D+{int(payment_days)} calendar days')
                        if cleaned:
                            set_term('late_interest_rate', f'{cleaned}%')
                        else:
                            updated['terms'] = [t for t in updated.get('terms', [])
                                                if t.get('key') != 'late_interest_rate']
                        current_payer = next((p for p in updated.get('parties', [])
                                              if 'commission_payer' in p.get('roles', [])), None)
                        if current_payer is not None and str(payer_country).strip():
                            current_payer['country'] = str(payer_country).strip()
                            current_payer['status'] = 'confirmed' if country_verified else 'suggested'
                        elif str(payer_country).strip():
                            st.warning("지급자 역할이 지정되지 않아 국가를 저장하지 못했습니다. 상세 거래조건에서 지급자 역할을 등록해 주세요.")
                        updated = apply_payment_policy(updated, env=env)
                        saved = _save_snapshot(repo, updated, "Updated agreed payment conditions and regenerated clauses")
                        st.session_state[state_key] = saved
                        for cache_key in ('contract_revisions', 'contract_pending_proposal',
                                          'contract_pending_terms', f'contract_pending_analysis_{active_id}',
                                          f'contract_rag_risk_{active_id}'):
                            st.session_state.pop(cache_key, None)
                        st.rerun()
                    except (ValueError, ContractRepositoryError) as exc:
                        st.error(str(exc))

    with st.container(border=True, key='contract_box_3'):
        st.markdown("### BOX 3 · 계약서 미리보기")
        if not snapshot.get('clauses'):
            st.info("BOX 1에서 초안을 만들면 이곳에서 문장을 클릭해 수정 메모를 남길 수 있습니다.")
        else:
            pending, buffers = _render_draft(repo, snapshot, state_key, env)
        if snapshot.get('clauses'):
            render_risk_review(repo, snapshot, state_key, env)
            with st.expander("Revision 기록 및 복원", expanded=False):
                revisions = st.session_state.get("contract_revisions")
                if not revisions:
                    try:
                        revisions = repo.load_contract(active_id)
                        st.session_state["contract_revisions"] = revisions
                    except ContractRepositoryError as exc:
                        st.error(str(exc))
                        revisions = []
                prior = [row for row in revisions if int(row.get("revision", 0)) < snapshot["revision"]]
                if prior and st.button("직전 revision으로 되돌리기 (새 revision 기록)",
                                       key=f"contract_undo_{active_id}_{snapshot['revision']}"):
                    try:
                        previous = max(prior, key=lambda row: int(row["revision"]))["snapshot"]
                        restored = restore_revision(snapshot, previous)
                        saved = _save_snapshot(repo, restored, "Restored prior contract revision",
                                               expected_revision=snapshot["revision"])
                        st.session_state[state_key] = saved
                        st.session_state.pop("contract_pending_proposal", None)
                        st.success(f"복구 내용을 revision {saved['revision']}로 저장했습니다.")
                        st.rerun()
                    except (ValueError, RevisionConflict, ContractRepositoryError) as exc:
                        st.error(str(exc))
            # Final action follows the risk panel and revision history.
            _batch_request_panel(repo, snapshot, state_key, env, pending, buffers)
            proposal = st.session_state.get('contract_pending_proposal')
            if proposal and proposal.get('contract_id') == active_id:
                _proposal_panel(repo, snapshot, proposal, state_key)
            _export_panel(repo, snapshot, env)

    with st.expander("저장·복사·언어 버전 관리", expanded=False):
        st.markdown("### 저장·복사·삭제")
        copy_col, language_col = st.columns(2)
        if copy_col.button("거래 조건 초기화 후 새 계약으로 복사",
                           key=f"contract_copy_{active_id}"):
            try:
                copied = deepcopy(snapshot)
                copied["clauses"] = []
                copied["issues"] = []
                copied["reference_ids"] = []
                copied["omissions"] = {}
                copied["parties"] = []
                copied["terms"] = [{
                    "id": f"term_{uuid4().hex}", "key": term.get("key"),
                    "value": None, "unit": None, "currency": None,
                    "status": "missing", "source_refs": [],
                } for term in snapshot.get("terms", [])]
                _new_contract(repo, f"{snapshot.get('title', 'Contract')} (copy)",
                              snapshot["contract_type"], snapshot["language"], copied)
                st.rerun()
            except (ValueError, ContractRepositoryError) as exc:
                st.error(str(exc))
        new_language = "en" if snapshot["language"] == "ko" else "ko"
        if language_col.button(f"{'English' if new_language == 'en' else '한국어'} 버전 새로 만들기",
                               key=f"contract_language_version_{active_id}"):
            try:
                translated = deepcopy(snapshot)
                translated["clauses"] = []
                translated["issues"] = []
                translated["language"] = new_language
                _new_contract(repo, f"{snapshot.get('title', 'Contract')} ({new_language})",
                              snapshot["contract_type"], new_language, translated)
                st.rerun()
            except (ValueError, ContractRepositoryError) as exc:
                st.error(str(exc))
