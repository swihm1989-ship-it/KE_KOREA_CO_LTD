"""Streamlit UI for private contract drafting, review, revision and export."""
import hashlib
import re
from copy import deepcopy
from uuid import uuid4

import streamlit as st

from Quotation_KEKOREA.contracts.editing import (
    RevisionConflict, apply_proposal, restore_revision,
)
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.models import new_snapshot, validate_snapshot
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
    analyze_trade, extract_reference_page, generate_draft, language_conflict,
    propose_revision, propose_term_revision,
)


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


def _repository(env):
    return ContractRepository(env)


def _records(repo):
    try:
        return repo.list_contracts()
    except ContractRepositoryError as exc:
        st.error(str(exc))
        return []


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
    rows = []
    for key in keys:
        term = terms.get(key, {})
        rows.append({
            "key": key,
            "항목": LABELS.get(key, key.replace("_", " ")),
            "value": term.get("value") or "",
            "unit": term.get("unit") or "",
            "currency": term.get("currency") or "",
            "status": term.get("status", "missing"),
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
        "status": party.get("status", "missing"),
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
            "status": row.get("status") if row.get("status") in {"confirmed", "suggested", "missing"} else "missing",
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
            "status": row.get("status") if row.get("status") in {"confirmed", "suggested", "missing"} else "missing",
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
                st.warning("충돌 해소에 필요한 변경입니다. 적용하거나 전체 제안을 취소해야 합니다.")
            checked = st.checkbox(
                "이 변경 적용" if not is_required else "필수 변경 적용",
                value=True, disabled=is_required,
                key=f"proposal_change_{proposal['id']}_{change['id']}")
            if checked:
                selected_ids.append(change["id"])
    col_apply, col_cancel = st.columns(2)
    if col_apply.button("선택한 변경을 하나의 revision으로 적용",
                        disabled=stale,
                        type="primary", key=f"proposal_apply_{proposal['id']}"):
        try:
            updated = apply_proposal(snapshot, proposal, selected_ids)
            saved = _save_snapshot(repo, updated, "Applied contract revision proposal",
                                   expected_revision=snapshot["revision"])
            repo.save_annotation({
                "id": proposal["id"].replace("proposal_", ""),
                "contract_id": snapshot["contract_id"],
                "sentence_id": proposal.get("target_sentence_id") or "term-reconciliation",
                "base_revision": proposal["base_revision"],
                "instruction": proposal.get("instruction", ""),
                "proposal": proposal, "status": "applied",
            })
            st.session_state[state_key] = saved
            st.session_state.pop("contract_pending_proposal", None)
            st.session_state.pop("contract_pending_terms", None)
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


def _render_draft(repo, snapshot, state_key, env):
    st.markdown("### 계약서 초안")
    st.caption(f"Revision {snapshot.get('revision')} · "
               + ("한국어" if snapshot["language"] == "ko" else "English"))
    if snapshot.get("issues"):
        with st.expander("AI/검토 참고 사항", expanded=True):
            reviewed_items = []
            for index, issue in enumerate(snapshot["issues"]):
                if not isinstance(issue, dict):
                    st.write(f"- {issue}")
                    continue
                message = issue.get("message", issue)
                if issue.get("severity") == "confirm":
                    confirmed = st.checkbox(
                        f"검토 완료: {message}",
                        value=bool(issue.get("confirmed")),
                        key=f"contract_issue_{snapshot['contract_id']}_{issue.get('id', index)}")
                    reviewed_items.append((index, confirmed, None))
                elif issue.get("severity") == "block":
                    st.error(message)
                    resolved = st.checkbox(
                        f"이 쟁점을 직접 확인하고 해결함: {message}",
                        value=bool(issue.get("resolved_by_user")),
                        key=f"contract_resolve_issue_{snapshot['contract_id']}_{issue.get('id', index)}")
                    reason = st.text_input(
                        "해결 내용/근거",
                        value=issue.get("resolution") or "",
                        key=f"contract_resolve_reason_{snapshot['contract_id']}_{issue.get('id', index)}")
                    reviewed_items.append((index, resolved, reason))
                else:
                    st.info(message)
            if reviewed_items and st.button(
                "검토/해결 상태를 revision으로 저장",
                key=f"contract_confirm_issues_{snapshot['contract_id']}_{snapshot['revision']}"):
                updated = deepcopy(snapshot)
                invalid_resolution = False
                for index, checked, reason in reviewed_items:
                    issue = updated["issues"][index]
                    if issue.get("severity") == "confirm":
                        issue["confirmed"] = bool(checked)
                    elif issue.get("severity") == "block":
                        if checked and not str(reason or "").strip():
                            invalid_resolution = True
                            continue
                        issue["resolved_by_user"] = bool(checked)
                        issue["resolution"] = str(reason or "").strip() or None
                        if checked:
                            issue["severity"] = "info"
                if invalid_resolution:
                    st.error("차단 쟁점을 해결하려면 해결 내용/근거를 입력해 주세요.")
                    return
                try:
                    saved = _save_snapshot(repo, updated, "User confirmed AI review items")
                    st.session_state[state_key] = saved
                    st.rerun()
                except ContractRepositoryError as exc:
                    st.error(str(exc))
    selected_key = f"contract_selected_sentence_{snapshot['contract_id']}"
    for clause in sorted(snapshot.get("clauses", []), key=lambda item: item.get("order", 0)):
        st.markdown(f"#### {clause.get('title', '')}")
        for index, sentence in enumerate(clause.get("sentences", []), 1):
            selected = st.session_state.get(selected_key) == sentence["id"]
            if st.button(
                f"{'▶ ' if selected else ''}{index}. {sentence['text']}",
                key=f"contract_sentence_{snapshot['contract_id']}_{sentence['id']}",
                help="클릭해 문장 메모 및 AI 수정안을 엽니다.",
                use_container_width=True,
            ):
                st.session_state[selected_key] = sentence["id"]
                st.rerun()
    selected_sentence_id = st.session_state.get(selected_key)
    if selected_sentence_id:
        selected_sentence = next((sentence for clause in snapshot["clauses"]
                                  for sentence in clause["sentences"]
                                  if sentence["id"] == selected_sentence_id), None)
        if selected_sentence:
            with st.container(border=True):
                st.markdown(f"**선택 문장 · {selected_sentence_id}**")
                st.write(selected_sentence["text"])
                note = st.text_area("수정 메모 / 원하는 변경을 입력하세요",
                                    key=f"contract_note_{snapshot['contract_id']}_{selected_sentence_id}")
                note_col, revise_col = st.columns(2)
                if note_col.button("메모 저장", key=f"contract_save_note_{snapshot['contract_id']}_{selected_sentence_id}"):
                    if not note.strip():
                        st.error("메모를 입력해 주세요.")
                        return
                    repo.save_annotation({
                        "id": uuid4().hex, "contract_id": snapshot["contract_id"],
                        "sentence_id": selected_sentence_id, "base_revision": snapshot["revision"],
                        "instruction": note, "proposal": None, "status": "note",
                    })
                    st.success("메모를 저장했습니다.")
                if revise_col.button("AI 수정안 만들기", disabled=not note.strip(),
                                     key=f"contract_make_revision_{snapshot['contract_id']}_{selected_sentence_id}"):
                    try:
                        proposal = propose_revision(snapshot, selected_sentence_id, note, env=env)
                        st.session_state["contract_pending_proposal"] = proposal
                        st.session_state["contract_pending_proposal_key"] = state_key
                        repo.save_annotation({
                            "id": proposal["id"].replace("proposal_", ""),
                            "contract_id": snapshot["contract_id"],
                            "sentence_id": selected_sentence_id,
                            "base_revision": snapshot["revision"],
                            "instruction": note, "proposal": proposal, "status": "proposed",
                        })
                        st.rerun()
                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                        st.error(str(exc))
    annotations = repo.list_annotations(snapshot["contract_id"])
    notes = [item for item in annotations if item.get("status") in {"note", "proposed"}]
    if notes:
        with st.expander(f"저장된 문장 메모 및 제안 ({len(notes)})"):
            for annotation in notes:
                st.write(f"Revision {annotation['base_revision']} · "
                         f"{annotation['sentence_id']} · {annotation['status']}")
                st.write(annotation["instruction"])


def _export_panel(repo, snapshot):
    issues = validate_rules(snapshot, for_export=True)
    st.markdown("### 내보내기 검토")
    if issues:
        st.warning("확인되지 않은 조건이나 충돌이 있어 검토용 파일 내보내기를 막았습니다.")
        for issue in issues:
            st.write(f"- {issue['message']}")
        return
    st.info("내보내기 검사를 통과해도 법적 유효성이나 집행 가능성을 보증하지 않습니다. 서명 전 법률 전문가 검토를 권장합니다.")
    if st.button("현재 확정 revision의 DOCX 및 PDF 생성", type="primary",
                 key=f"contract_export_{snapshot['contract_id']}_{snapshot['revision']}"):
        uploaded_paths = []
        saved_records = []
        try:
            outputs = export_contract(snapshot)
            for file_format, output in outputs.items():
                path = (f"{snapshot['contract_id']}/exports/r{snapshot['revision']}/"
                        f"{uuid4().hex}-{output['filename']}")
                mime = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        if file_format == "docx" else "application/pdf")
                repo.upload_private_file("kekorea-contracts", path, output["content"], mime)
                uploaded_paths.append(path)
                saved_records.append((file_format, path))
                repo.save_export({
                    "contract_id": snapshot["contract_id"], "revision": snapshot["revision"],
                    "language": snapshot["language"], "format": file_format,
                    "storage_path": path, "content_hash": output["sha256"],
                })
            for file_format, output in outputs.items():
                mime = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        if file_format == "docx" else "application/pdf")
                st.download_button(
                    f"{file_format.upper()} 다운로드",
                    data=output["content"], file_name=output["filename"], mime=mime,
                    key=f"contract_download_{snapshot['contract_id']}_{snapshot['revision']}_{file_format}",
                )
            st.success("현재 확정 revision의 파일을 비공개 저장했습니다.")
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            for file_format, path in saved_records:
                try:
                    repo.delete_export(snapshot["contract_id"], snapshot["revision"],
                                       file_format, path)
                except ContractRepositoryError:
                    st.error(f"부분 생성 기록을 자동 정리하지 못했습니다: {path}")
            for path in uploaded_paths:
                try:
                    repo.delete_private_file("kekorea-contracts", path)
                except ContractRepositoryError:
                    st.error(f"부분 생성 파일을 자동 정리하지 못했습니다: {path}")
            st.error(f"파일 생성/저장에 실패했습니다. 저장 완료로 처리하지 않았습니다. {exc}")
    current_exports = [item for item in repo.list_exports(snapshot["contract_id"])
                       if item.get("revision") == snapshot["revision"]]
    if current_exports:
        st.caption("현재 revision에 저장된 비공개 출력")
        for item in current_exports:
            if st.button(f"{item['format'].upper()} 파일 다시 받기",
                         key=f"contract_saved_export_{item['id']}"):
                try:
                    content = repo.download_private_file("kekorea-contracts", item["storage_path"])
                    extension = item["format"]
                    mime = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            if extension == "docx" else "application/pdf")
                    st.download_button(
                        f"{extension.upper()} 다운로드",
                        data=content,
                        file_name=f"contract-r{item['revision']}.{extension}",
                        mime=mime,
                        key=f"contract_redownload_{item['id']}",
                    )
                except ContractRepositoryError as exc:
                    st.error(str(exc))


def _run_editor(repo, snapshot, state_key, env):
    state_key_terms = f"contract_terms_table_{snapshot['contract_id']}_{snapshot['revision']}"
    terms_rows = st.data_editor(
        _term_rows(snapshot), key=state_key_terms, hide_index=True,
        num_rows="dynamic", use_container_width=True,
        column_config={
            "key": st.column_config.TextColumn("내부 키", disabled=True),
            "항목": st.column_config.TextColumn("조건 항목", disabled=True),
            "value": st.column_config.TextColumn("값"),
            "unit": st.column_config.TextColumn("단위"),
            "currency": st.column_config.TextColumn("통화"),
            "status": st.column_config.SelectboxColumn(
                "상태", options=["missing", "suggested", "confirmed"],
                required=True, help="미정 / AI 제안 / 사용자가 확인한 조건"),
        },
    )
    st.caption("상태 값: missing=미정, suggested=AI 제안, confirmed=사용자 확인. 제안값은 확정 전까지 내보내기를 막습니다.")
    st.markdown("#### 당사자 및 역할")
    party_rows = st.data_editor(
        _party_rows(snapshot), key=f"contract_parties_table_{snapshot['contract_id']}_{snapshot['revision']}",
        hide_index=True, num_rows="dynamic", use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn("ID", disabled=True),
            "legal_name": st.column_config.TextColumn("법인명"),
            "country": st.column_config.TextColumn("국가"),
            "address": st.column_config.TextColumn("주소"),
            "representative": st.column_config.TextColumn("대표/서명권자"),
            "roles": st.column_config.TextColumn("역할 (쉼표 구분)"),
            "status": st.column_config.SelectboxColumn(
                "상태", options=["missing", "suggested", "confirmed"], required=True),
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


def _contract_chat(repo, snapshot, state_key, env):
    st.markdown("### 거래 내용과 AI 분석")
    st.caption("자연어 입력과 조건표가 함께 사용됩니다. 입력 자료와 선택한 참고 문구는 분석 버튼을 눌렀을 때만 OpenAI로 전송됩니다.")
    messages = repo.list_messages(snapshot["contract_id"])
    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    prompt = st.text_area("거래 내용 / 추가 조건 / 답변", height=120,
                          key=f"contract_prompt_{snapshot['contract_id']}")
    refs = repo.contract_references(snapshot["contract_id"])
    selected_refs = []
    if refs:
        selected_refs = st.multiselect(
            "AI에 참고 문구로 전달할 계약서",
            options=[row["id"] for row in refs],
            format_func=lambda value: next(row["filename"] for row in refs if row["id"] == value),
            key=f"contract_context_refs_{snapshot['contract_id']}")
    consent = st.checkbox("입력한 거래 내용과 위에서 선택한 참고 문구를 설정된 OpenAI API로 전송하는 데 동의합니다.",
                          key=f"contract_ai_consent_{snapshot['contract_id']}")
    if st.button("거래 내용 분석 및 조건 정리",
                 disabled=not prompt.strip() or not consent,
                 key=f"contract_analyze_{snapshot['contract_id']}"):
        try:
            repo.add_message(snapshot["contract_id"], "user", prompt.strip())
            selected_context = [{"id": row["id"], "filename": row["filename"],
                                 "extracted_text": (row.get("extracted_text") or "")[:12000]}
                                for row in refs if row["id"] in selected_refs]
            prior_messages = messages + [{"role": "user", "content": prompt.strip()}]
            analysis = analyze_trade(prior_messages, snapshot, selected_context, env=env)
            if analysis["contract_type"] != snapshot["contract_type"]:
                raise ValueError("AI가 다른 계약 유형으로 분류했습니다. 새 계약 유형을 선택한 뒤 다시 분석해 주세요.")
            updated = apply_analysis(snapshot, analysis)
            updated["reference_ids"] = sorted(set(
                updated.get("reference_ids", []) + selected_refs
            ))
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
            repo.add_message(snapshot["contract_id"], "assistant",
                             f"조건 분석 완료: {len(analysis.get('terms', []))}개 조건 후보, "
                             f"{len(analysis.get('questions', []))}개 확인 질문.")
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
    if questions:
        with st.expander("AI 확인 질문", expanded=True):
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
        st.markdown("### 저장된 계약")
        options = {record["id"]: record for record in records}
        selected_id = st.selectbox(
            "열 계약 선택", list(options),
            format_func=lambda value: options[value]['title'],
            index=(list(options).index(st.session_state["contract_active_id"])
                   if st.session_state.get("contract_active_id") in options else 0),
            key=f"contract_open_select_{page}")
        if st.button("선택한 계약 열기", key=f"contract_open_{page}"):
            st.session_state["contract_active_id"] = selected_id
            st.session_state.pop(f"contract_snapshot_{selected_id}", None)
            try:
                _ensure_active_snapshot(repo, selected_id)
                st.rerun()
            except (ValueError, ContractRepositoryError) as exc:
                st.error(str(exc))

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

    _contract_chat(repo, snapshot, state_key, env)
    st.markdown("### 거래조건표")
    _run_editor(repo, snapshot, state_key, env)

    refs = repo.contract_references(active_id)
    preferred = [clause for clause in repo.list_preferred_clauses()
                 if clause.get("active") and snapshot["contract_type"] in clause.get("contract_types", [])
                 and clause.get("language") == snapshot["language"]]
    prompt_value = st.session_state.get(f"contract_prompt_{active_id}", "")
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
                draft = generate_draft(
                    snapshot, preferred, env=env, reference_context=reference_context,
                )
                saved = _save_snapshot(repo, draft, "AI generated contract draft")
                st.session_state[state_key] = saved
                st.success(f"초안을 revision {saved['revision']}로 저장했습니다.")
                st.rerun()
            except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                st.error(str(exc))
    _references_panel(repo, active_id, env)

    proposal = st.session_state.get("contract_pending_proposal")
    if proposal and proposal.get("contract_id") == active_id:
        _proposal_panel(repo, snapshot, proposal, state_key)

    if snapshot.get("clauses"):
        _render_draft(repo, snapshot, state_key, env)
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
        _export_panel(repo, snapshot)

    st.markdown("### 저장·복사·삭제")
    copy_col, language_col, delete_col = st.columns(3)
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
    delete_confirm = delete_col.checkbox("영구 계약 기록/비공개 파일 삭제를 확인",
                                        key=f"contract_delete_confirm_{active_id}")
    if delete_col.button("계약 삭제", disabled=not delete_confirm,
                         key=f"contract_delete_{active_id}"):
        try:
            for reference in repo.contract_references(active_id):
                if reference.get("storage_path"):
                    repo.delete_private_file("kekorea-contracts", reference["storage_path"])
            for output in repo.list_exports(active_id):
                repo.delete_private_file("kekorea-contracts", output["storage_path"])
            repo.delete_contract(active_id)
            st.session_state.pop(state_key, None)
            st.session_state.pop("contract_active_id", None)
            st.success("계약 기록 및 연결된 비공개 파일 삭제 요청을 완료했습니다. Supabase 백업 보존 정책에 따른 잔여 백업은 별도 적용될 수 있습니다.")
            st.rerun()
        except ContractRepositoryError as exc:
            st.error(f"삭제가 완전히 확인되지 않았습니다. 다시 확인해 주세요. {exc}")
