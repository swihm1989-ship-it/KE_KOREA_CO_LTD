"""Private persistent PDF archive for MASTER, separate from legacy contract records.

Server-side Supabase credentials only. Never publicly expose file URLs.
All reads are scoped to the authenticated OIDC email; hash-check every download.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping
from uuid import UUID, uuid4

from Quotation_KEKOREA.contracts.repository import ContractRepository

BUCKET = "kekorea-master-pdfs"
TABLE = "kekorea_master_pdf_archive"
KINDS = frozenset({"PI", "PO", "CI", "PL", "CONTRACT"})
STATES = frozenset({"draft", "final"})
MAX_PDF_SIZE = 20 * 1024 * 1024


class PdfArchiveError(RuntimeError):
    pass


def _principal(value: str) -> str:
    identity = str(value or "").strip().lower()
    if not identity or "@" not in identity or len(identity) > 255:
        raise PdfArchiveError("로그인된 계정 정보가 필요합니다.")
    return identity


def owner_key(email: str) -> str:
    return sha256(_principal(email).encode("utf-8")).hexdigest()[:32]


def _repo(env: Mapping[str, str]):
    try:
        return ContractRepository(env)
    except (ValueError, TypeError) as exc:
        raise PdfArchiveError("서버의 비공개 PDF 저장소 연결 설정을 확인하세요.") from exc


def source_fingerprint(source: Mapping[str, Any]) -> str:
    if not isinstance(source, Mapping):
        raise PdfArchiveError("PDF 원본 문서 정보가 유효하지 않습니다.")
    try:
        data = json.dumps(source, ensure_ascii=False, sort_keys=True, default=str,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PdfArchiveError("PDF 원본 데이터를 저장할 수 없습니다.") from exc
    return sha256(data).hexdigest()


def _safe_name(name: str, kind: str, status: str) -> str:
    original = str(name or "").split("/")[-1].split("\\")[-1].strip()
    original = re.sub(r"[\x00-\x1f\x7f]", "", original)
    if not original.lower().endswith(".pdf"):
        original = f"{kind}-{status.upper()}.pdf"
    return original[:180]


def archive_pdf(env: Mapping[str, str], principal: str, kind: str, status: str,
                asset: Mapping[str, Any], source: Mapping[str, Any],
                *, parent_draft_id: str | None = None) -> dict[str, Any]:
    """Upload PDF privately; record its immutable source and status only after upload.

    Failed metadata commits remove orphaned files; no automatic mail sending.
    """
    owner = _principal(principal)
    kind = str(kind).upper()
    if kind not in KINDS or status not in STATES:
        raise PdfArchiveError("문서 종류나 상태가 유효하지 않습니다.")
    content = asset.get("content") if isinstance(asset, Mapping) else None
    if not isinstance(content, bytes) or not content.startswith(b"%PDF") or len(content) > MAX_PDF_SIZE:
        raise PdfArchiveError("유효한 20MB 이하 PDF만 저장할 수 있습니다.")
    if parent_draft_id:
        try:
            UUID(parent_draft_id)
        except (ValueError, TypeError) as exc:
            raise PdfArchiveError("DRAFT 문서 식별자가 유효하지 않습니다.") from exc
    snapshot = json.loads(json.dumps(source, ensure_ascii=False, default=str))
    fingerprint = source_fingerprint(snapshot)
    ident = str(uuid4())
    filename = _safe_name(asset.get("filename", ""), kind, status)
    path = f"{owner_key(owner)}/{datetime.now(timezone.utc):%Y/%m}/{ident}.pdf"
    record = {
        "id": ident, "owner_email": owner, "kind": kind, "status": status,
        "filename": filename, "storage_path": path,
        "content_sha256": sha256(content).hexdigest(),
        "source_fingerprint": fingerprint, "source_snapshot": snapshot,
    }
    if parent_draft_id:
        record["parent_draft_id"] = parent_draft_id
    repo = _repo(env)
    try:
        repo.upload_private_file(BUCKET, path, content, "application/pdf")
    except Exception as exc:
        raise PdfArchiveError("비공개 PDF 업로드에 실패했습니다.") from exc
    try:
        repo.request("POST", TABLE, payload=record,
                     headers={"Prefer": "return=minimal"})
    except Exception as exc:
        try:
            repo.delete_private_file(BUCKET, path)
        except Exception:
            pass
        raise PdfArchiveError("PDF 메타데이터 저장에 실패했습니다. 다시 시도하세요.") from exc
    return record


def list_documents(env: Mapping[str, str], principal: str,
                   status: str) -> list[dict[str, Any]]:
    owner = _principal(principal)
    if status not in STATES:
        raise PdfArchiveError("문서 상태가 유효하지 않습니다.")
    try:
        rows = _repo(env).request("GET", TABLE, query=[
            ("select", "id,kind,status,filename,created_at,content_sha256"),
            ("owner_email", f"eq.{owner}"),
            ("status", f"eq.{status}"),
            ("order", "created_at.desc"),
            ("limit", "200"),
        ])
    except Exception as exc:
        raise PdfArchiveError("PDF 목록을 읽지 못했습니다.") from exc
    return rows if isinstance(rows, list) else []


def load_pdf(env: Mapping[str, str], principal: str, document_id: str
             ) -> tuple[dict[str, Any], bytes]:
    owner = _principal(principal)
    try:
        document_id = str(UUID(str(document_id)))
    except (TypeError, ValueError) as exc:
        raise PdfArchiveError("문서 식별자가 올바르지 않습니다.") from exc
    repo = _repo(env)
    try:
        rows = repo.request("GET", TABLE, query=[
            ("select", "id,kind,status,filename,storage_path,content_sha256,source_snapshot,source_fingerprint,created_at"),
            ("id", f"eq.{document_id}"), ("owner_email", f"eq.{owner}"),
            ("limit", "1"),
        ])
    except Exception as exc:
        raise PdfArchiveError("선택한 PDF를 조회할 수 없습니다.") from exc
    if not isinstance(rows, list) or len(rows) != 1:
        raise PdfArchiveError("현재 계정의 해당 문서를 찾을 수 없습니다.")
    row = rows[0]
    path = str(row.get("storage_path") or "")
    if not path.startswith(owner_key(owner) + "/"):
        raise PdfArchiveError("비공개 PDF 경로가 계정과 일치하지 않습니다.")
    try:
        data = repo.download_private_file(BUCKET, path)
    except Exception as exc:
        raise PdfArchiveError("비공개 PDF 다운로드에 실패했습니다.") from exc
    if (not isinstance(data, bytes) or not data.startswith(b"%PDF")
            or sha256(data).hexdigest() != row.get("content_sha256")):
        raise PdfArchiveError("저장된 PDF 무결성 확인에 실패했습니다.")
    return row, data



def delete_document(env: Mapping[str, str], principal: str,
                    document_id: str) -> None:
    """Owner-verified delete of one archived PDF on explicit user click only.

    First confirm the metadata DELETE, then remove the single private
    storage object. Never delete legacy contract records or RAG references.
    """
    owner = _principal(principal)
    try:
        ident = str(UUID(str(document_id)))
    except (ValueError, TypeError):
        raise PdfArchiveError("삭제할 PDF 식별자가 유효하지 않습니다.") from None
    repo = _repo(env)
    try:
        rows = repo.request("GET", TABLE, query=[
            ("select", "id,kind,status,filename,storage_path"),
            ("id", "eq." + ident), ("owner_email", "eq." + owner),
            ("limit", "1"),
        ])
    except Exception:
        raise PdfArchiveError("삭제할 PDF를 조회하지 못했습니다.") from None
    if not isinstance(rows, list) or len(rows) != 1:
        raise PdfArchiveError("현재 로그인된 계정의 문서를 찾지 못했습니다.")
    row = rows[0]
    current_status = str(row.get("status") or "")
    if current_status not in ("draft", "final", "converted"):
        raise PdfArchiveError("삭제할 PDF 상태를 확인할 수 없습니다.")
    path = str(row.get("storage_path") or "")
    if (not path.startswith(owner_key(owner) + "/") or
            not path.endswith("/" + ident + ".pdf")):
        raise PdfArchiveError("선택한 문서의 비공개 저장 경로가 올바르지 않습니다.")
    try:
        # Self-referencing FKs: remove only this document's links from
        # same-owner PDF metadata before deleting its row.
        repo.request("PATCH", TABLE, payload={"final_document_id": None},
                     query=[("final_document_id", "eq." + ident),
                            ("owner_email", "eq." + owner)],
                     headers={"Prefer": "return=minimal"})
        repo.request("PATCH", TABLE, payload={"parent_draft_id": None},
                     query=[("parent_draft_id", "eq." + ident),
                            ("owner_email", "eq." + owner)],
                     headers={"Prefer": "return=minimal"})
        deleted = repo.request("DELETE", TABLE, query=[
            ("id", "eq." + ident), ("owner_email", "eq." + owner),
            ("status", "eq." + current_status),
        ], headers={"Prefer": "return=representation"})
    except Exception:
        raise PdfArchiveError(
            "PDF 보관 기록을 삭제하지 못했습니다. 저장소를 새로고침하고 다시 확인하세요."
        ) from None
    if not isinstance(deleted, list) or len(deleted) != 1:
        raise PdfArchiveError(
            "다른 화면에서 문서가 변경되었습니다. 다시 조회한 뒤 삭제하세요."
        )
    try:
        repo.delete_private_file(BUCKET, path)
    except Exception:
        # Metadata is gone but the private storage object may remain.
        raise PdfArchiveError(
            "문서 목록 삭제는 완료됐으나 비공개 PDF 파일 정리가 실패했습니다. "
            "저장소 관리자에게 파일 정리를 요청하세요."
        ) from None


def mark_draft_converted(env: Mapping[str, str], principal: str,
                         draft_id: str, final_id: str) -> None:
    owner = _principal(principal)
    try:
        draft_id, final_id = str(UUID(str(draft_id))), str(UUID(str(final_id)))
    except (ValueError, TypeError) as exc:
        raise PdfArchiveError("문서 식별자가 유효하지 않습니다.") from exc
    try:
        rows = _repo(env).request("PATCH", TABLE, query=[
            ("id", f"eq.{draft_id}"), ("owner_email", f"eq.{owner}"),
            ("status", "eq.draft"), ("select", "id"),
        ], payload={"status": "converted", "final_document_id": final_id,
                    "converted_at": datetime.now(timezone.utc).isoformat()},
            headers={"Prefer": "return=representation"})
    except Exception as exc:
        raise PdfArchiveError("최종 문서 전환 상태 저장에 실패했습니다.") from exc
    if rows is not None and (not isinstance(rows, list) or len(rows) != 1):
        raise PdfArchiveError("이미 전환되었거나 현재 계정의 DRAFT가 아닙니다.")
