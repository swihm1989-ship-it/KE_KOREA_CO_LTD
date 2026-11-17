"""Authenticated MASTER PDF document list and DRAFT to FINAL action.

The existing KE KOREA renderers own all document content and sealing.
Only browser preview is provided here; no email is ever transmitted.
"""
from __future__ import annotations

import base64
import hmac
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit.errors import StreamlitAPIException

from Quotation_KEKOREA.orchestration.workflows import pdf_archive as archive
from Quotation_KEKOREA.orchestration.workflows.document_assets import document_export_env

KST = ZoneInfo("Asia/Seoul")


def _env() -> dict:
    return document_export_env(st.secrets, os.environ)


def _date(value) -> str:
    if not value:
        return "저장 시각 미확인"
    try:
        date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return date.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    except (ValueError, TypeError):
        return "저장 시각 미확인"


def store_generated(principal: str, kind: str, status: str, files: dict,
                    source: dict, *, parent_draft_id: str | None = None):
    """Archive the actual exported PDF; called after successful render only."""
    pdf = files.get("pdf") if isinstance(files, dict) else None
    if not pdf:
        raise archive.PdfArchiveError("PDF 파일을 생성한 경우에만 보관할 수 있습니다.")
    return archive.archive_pdf(_env(), principal, kind, status, pdf,
                               source, parent_draft_id=parent_draft_id)


def _preview(data: bytes) -> None:
    # st.pdf can exist without its optional streamlit-pdf package on Cloud.
    # A preview failure must never hide the download or DRAFT -> FINAL controls.
    if hasattr(st, "pdf"):
        try:
            st.pdf(data, height=740)
            return
        except (StreamlitAPIException, ImportError):
            pass
    import streamlit.components.v1 as components
    encoded = base64.b64encode(data).decode("ascii")
    components.html(
        '<iframe title="PDF preview" src="data:application/pdf;base64,'
        + encoded + '" width="100%" height="730" style="border:0"></iframe>',
        height=755, scrolling=False,
    )


def _trade_final(principal: str, row: dict) -> None:
    """DRAFT is a snapshot, NOT an approval. Require fresh, explicit issuance consent."""
    kind = row["kind"]
    source = row.get("source_snapshot") or {}
    from Quotation_KEKOREA.orchestration.workflows.trade_export_review import (
        review_trade_document, trade_export_fingerprint,
    )
    from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import (
        render_master_trade_final,
    )
    try:
        report = review_trade_document(kind, source, final=True, allow_incomplete=True)
        fingerprint = trade_export_fingerprint(kind, source, allow_incomplete=True)
    except (ValueError, KeyError, TypeError, AttributeError):
        st.error("문서 거래조건을 검증할 수 없습니다. AI 업무 요청에서 다시 수정하세요.")
        return
    if report.get("issues"):
        st.error("현재 초안은 최종 발행 검증을 통과하지 못했습니다. AI 업무 요청에서 조건을 보완하세요.")
        with st.expander("발행 전 확인"):
            for issue in report["issues"][:30]:
                st.write(str(issue.get("message") or issue))
        return
    if report.get("missing"):
        st.warning("미입력 항목은 빈칸으로 출력됩니다. 최종 발행 시 확인 바랍니다.")
    approved = st.checkbox(
        "현재 DRAFT의 거래조건을 확인했고 미확정값을 빈칸으로 두는 최종 PDF 생성을 승인합니다.",
        key="pdf_final_trade_approve_" + row["id"],
    )
    if st.button("최종문서 생성", type="primary",
                 key="pdf_final_trade_generate_" + row["id"],
                 disabled=not approved):
        try:
            outputs = render_master_trade_final(
                kind, source, _env(), approved=True,
                expected_fingerprint=fingerprint, allow_incomplete=True,
            )
            final = store_generated(principal, kind, "final", outputs, source,
                                    parent_draft_id=row["id"])
            archive.mark_draft_converted(_env(), principal, row["id"], final["id"])
        except Exception:
            st.error("최종 PDF 발행 또는 비공개 저장에 실패했습니다. 기존 원본 엔진 설정과 PDF 저장소를 확인하세요.")
        else:
            st.success("최종 PDF가 생성되어 '저장된 계약서'에 보관되었습니다.")
            st.session_state["master_pdf_final_notice"] = True
            st.rerun()


def _contract_final(principal: str, row: dict) -> None:
    from Quotation_KEKOREA.orchestration.workflows.master_contract_final import (
        contract_fingerprint, contract_final_blockers, render_original_final,
    )
    source = row.get("source_snapshot") or {}
    env = _env()
    try:
        fingerprint = contract_fingerprint(source)
        blockers = contract_final_blockers(source, env)
    except (ValueError, KeyError, TypeError):
        st.error("계약서 원문 형식을 확인할 수 없습니다.")
        return
    allow_unresolved = False
    if any("BOX 3에 임시 확인 문구" in item for item in blockers):
        allow_unresolved = st.checkbox(
            "미확정 계약 조항을 현재 문구 그대로 최종 출력하는 데 동의합니다.",
            key="pdf_contract_unresolved_" + row["id"],
        )
    blockers = contract_final_blockers(
        source, env, allow_unresolved_text=allow_unresolved)
    if blockers:
        st.warning("계약서 최종 발행 전 검증 조건을 확인해야 합니다.")
        with st.expander("검증 결과"):
            for item in blockers:
                st.write(item)
    try:
        from Auth.gate import is_authenticated
        admin_ok = bool(is_authenticated(st))
    except (ImportError, AttributeError, TypeError, ValueError):
        admin_ok = False
    if admin_ok:
        authorized = True
    else:
        password = st.text_input(
            "기존 계약서 FINAL 직인 사용 암호", type="password",
            key="pdf_contract_seal_" + row["id"],
        )
        try:
            configured_secret = st.secrets.get("CONTRACT_FINAL_SEAL_PASSWORD", "")
        except (FileNotFoundError, KeyError):
            configured_secret = ""
        secret = str(os.environ.get("CONTRACT_FINAL_SEAL_PASSWORD") or configured_secret)
        authorized = bool(secret) and hmac.compare_digest(password, secret)
    approved = st.checkbox(
        "계약서 전체 조항·당사자·거래조건을 확인하고 이 버전의 최종 발행을 승인합니다.",
        key="pdf_contract_approve_" + row["id"],
    )
    if st.button("최종문서 생성", type="primary",
                 key="pdf_contract_generate_" + row["id"],
                 disabled=bool(blockers) or not approved or not authorized):
        try:
            outputs = render_original_final(
                source, env, principal=principal, approved=True,
                authorized=True, expected_fingerprint=fingerprint,
                allow_unresolved_text=allow_unresolved,
            )
            final = store_generated(principal, "CONTRACT", "final", outputs, source,
                                    parent_draft_id=row["id"])
            archive.mark_draft_converted(env, principal, row["id"], final["id"])
        except Exception:
            st.error("기존 계약서 최종 엔진 발행 또는 저장에 실패했습니다. 검증·직인 설정을 확인하세요.")
        else:
            st.success("계약서 최종 PDF가 '저장된 계약서'로 이동되었습니다.")
            st.rerun()


def render_pdf_archive(principal: str, status: str) -> None:
    if not principal:
        raise PermissionError("로그인이 필요합니다.")
    if status not in ("draft", "final"):
        raise ValueError("Unknown PDF status")
    st.subheader("발송 대기 · DRAFT PDF" if status == "draft"
                 else "저장된 계약서 · 최종 PDF")
    st.caption("파일명 클릭 시 아래에서 PDF를 미리볼 수 있습니다. 모든 시간은 한국 표준시(KST)입니다.")
    if status == "draft":
        st.info("DRAFT는 내부 검토용입니다. '최종문서 생성'은 별도 발행 승인 후 기존 KE KOREA 엔진으로 수행합니다. 메일은 자동 발송되지 않습니다.")
    try:
        records = archive.list_documents(_env(), principal, status)
    except archive.PdfArchiveError:
        st.error("비공개 PDF 목록을 불러오지 못했습니다. MASTER Supabase 설정을 확인하세요.")
        return
    if not records:
        st.info("저장된 " + ("DRAFT" if status == "draft" else "최종") +
                " PDF가 없습니다. AI 업무 요청에서 PDF를 생성하면 자동 보관됩니다.")
        return
    st.caption(f"총 {len(records)}건 · 최근 생성 순")
    for item in records:
        ident = str(item.get("id") or "")
        name = str(item.get("filename") or "Unnamed PDF")
        col_file, col_time = st.columns([3, 2])
        if col_file.button(name, key="pdf_row_" + ident, use_container_width=True):
            st.session_state["master_pdf_selected_" + status] = ident
        col_time.caption(str(item.get("kind") or "") + " · " + _date(item.get("created_at")))
    chosen = st.session_state.get("master_pdf_selected_" + status)
    if chosen not in {str(r.get("id")) for r in records}:
        return
    try:
        row, data = archive.load_pdf(_env(), principal, chosen)
    except archive.PdfArchiveError:
        st.error("선택한 PDF를 읽거나 무결성을 검증할 수 없습니다.")
        return
    st.divider()
    st.markdown("#### " + str(row["filename"]))
    st.caption("생성 및 저장: " + _date(row.get("created_at")))
    _preview(data)
    st.download_button("PDF 다운로드", data=data,
                       file_name=row["filename"], mime="application/pdf",
                       key="pdf_download_" + chosen)
    if status == "draft":
        st.divider()
        if row["kind"] == "CONTRACT":
            _contract_final(principal, row)
        else:
            _trade_final(principal, row)
