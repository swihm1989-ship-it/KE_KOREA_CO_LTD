"""Owner-scoped link between a received email reply and generated FINAL PDFs.

Only server-side Supabase REST; attachment bytes are loaded from the private
PDF archive and integrity-verified immediately before an owner-approved send.
No SMTP calls in this module. Deleting an archived PDF cascades its link.
"""
from __future__ import annotations

from hashlib import sha256
import json

from Quotation_KEKOREA.orchestration.workflows import pdf_archive
from Quotation_KEKOREA.orchestration.workflows.email_outbox import (
    OutboxError, _owner, _repo, _safe_id, get_reply,
)

TABLE = "kekorea_master_mail_pdf_links"
MAX_TOTAL = 20 * 1024 * 1024


def link_final_pdf(env, principal, outbox_id, pdf_id):
    """Associate a FINAL with exactly one owner-verified outbox draft."""
    owner = _owner(principal)
    reply = get_reply(env, owner, outbox_id)
    if reply.get("status") != "draft":
        raise OutboxError("이미 발송 중이거나 완료된 메일에는 문서를 추가할 수 없습니다.")
    pdf_id = _safe_id(pdf_id)
    try:
        records = _repo(env).request("GET", pdf_archive.TABLE, query=[
            ("select", "id,status"), ("id", "eq." + pdf_id),
            ("owner_email", "eq." + owner), ("status", "eq.final"), ("limit", "1"),
        ])
        if not isinstance(records, list) or len(records) != 1:
            raise OutboxError("해당 계정의 최종 PDF를 확인할 수 없습니다.")
        _repo(env).request("POST", TABLE, payload={
            "owner_email": owner, "outbox_id": _safe_id(outbox_id), "pdf_id": pdf_id,
        }, query=[("on_conflict", "outbox_id,pdf_id")],
           headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
    except OutboxError:
        raise
    except Exception:
        raise OutboxError("최종 PDF의 메일 첨부 연결을 저장하지 못했습니다.") from None


def copy_links(env, principal, old_id, new_id):
    """Explicitly repeated send: copy current FINAL links to new DRAFT only."""
    for doc in list_attachments(env, principal, old_id):
        link_final_pdf(env, principal, new_id, doc["id"])


def list_attachments(env, principal, outbox_id):
    """Names/hash only for preview; never return sensitive storage URLs."""
    owner = _owner(principal)
    get_reply(env, owner, outbox_id)
    try:
        links = _repo(env).request("GET", TABLE, query=[
            ("select", "pdf_id"), ("owner_email", "eq." + owner),
            ("outbox_id", "eq." + _safe_id(outbox_id)), ("order", "created_at.asc"),
        ]) or []
        documents = []
        for link in links:
            rows = _repo(env).request("GET", pdf_archive.TABLE, query=[
                ("select", "id,filename,kind,status,content_sha256"),
                ("id", "eq." + _safe_id(link["pdf_id"])),
                ("owner_email", "eq." + owner), ("status", "eq.final"), ("limit", "1"),
            ])
            if not isinstance(rows, list) or len(rows) != 1:
                raise OutboxError("연결된 PDF 기록을 확인할 수 없습니다.")
            documents.append(rows[0])
        return documents
    except OutboxError:
        raise
    except Exception:
        raise OutboxError("첨부할 PDF 목록을 확인하지 못했습니다.") from None


def attachment_digest(documents):
    facts = [(str(d["id"]), str(d["content_sha256"])) for d in documents]
    return sha256(json.dumps(facts, separators=(",", ":")).encode()).hexdigest()


def load_approved_attachments(env, principal, outbox_id, expected_digest):
    """Detect deleted/changed files before SMTP claim; return verified bytes."""
    docs = list_attachments(env, principal, outbox_id)
    if attachment_digest(docs) != expected_digest:
        raise OutboxError("승인 후 첨부파일이 변경되었습니다. 목록을 확인하고 다시 승인하세요.")
    result, total = [], 0
    for doc in docs:
        record, data = pdf_archive.load_pdf(env, principal, doc["id"])
        if record.get("status") != "final" or record.get("content_sha256") != doc["content_sha256"]:
            raise OutboxError("연결된 최종 PDF 상태가 변경됐습니다.")
        total += len(data)
        if total > MAX_TOTAL:
            raise OutboxError("첨부파일 총용량이 20MB를 초과했습니다.")
        result.append({"filename": str(record["filename"]), "data": data})
    return result
