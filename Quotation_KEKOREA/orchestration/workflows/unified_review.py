"""Isolated orchestration: route -> legacy draft -> review -> email-review handoff.

No real mail connection, durable persistence, invoice finalization or PDF signing.
Approval here is a *review marker* for non-sendable DRAFT files only.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Any, Mapping
from uuid import uuid4

from ..router import classify
from .document_preview import build_preview
from .draft_files import create_review_files


@dataclass(frozen=True)
class ReviewDocument:
    kind: str
    blockers: tuple[str, ...] = ()
    files: Mapping[str, Mapping[str, Any]] | None = None
    source_hash: str = ""
    reviewed_hash: str = ""
    approved: bool = False


@dataclass(frozen=True)
class ReviewRun:
    run_id: str
    instruction: str
    kinds: tuple[str, ...]
    sources: Mapping[str, Any]
    documents: tuple[ReviewDocument, ...] = ()
    status: str = "needs_preparation"
    email_to: str = ""
    email_subject: str = ""
    email_body: str = ""
    email_approved: bool = False
    email_review_hash: str = ""
    can_send: bool = False
    history: tuple[str, ...] = ()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str).encode("utf-8")


def _hash(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _file_digest(files: Mapping[str, Mapping[str, Any]]) -> str:
    rows = []
    for ext, asset in sorted(files.items()):
        payload = asset.get("content")
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("Document bytes are unavailable")
        actual = sha256(payload).hexdigest()
        if asset.get("sha256") != actual or asset.get("final") or asset.get("sendable"):
            raise ValueError("Review file failed integrity or DRAFT-only policy")
        rows.append((ext, asset.get("filename"), actual))
    if not rows:
        raise ValueError("No review documents generated")
    return _hash(rows)


def new_request(instruction: str, candidates: Mapping[str, Any]) -> ReviewRun:
    if not isinstance(candidates, Mapping):
        raise ValueError("Document inputs must be a kind-to-JSON mapping")
    kinds = tuple(classify("", instruction))
    # Untrusted natural-language text only chooses kinds. Data is supplied separately.
    sources = deepcopy(dict(candidates))
    return ReviewRun(run_id=str(uuid4()), instruction=instruction, kinds=kinds,
                     sources=sources, status="needs_preparation" if kinds else "needs_input",
                     history=("요청 분류 완료 (키워드 기반, AI API 미연결)",))


def prepare_documents(run: ReviewRun) -> ReviewRun:
    documents = []
    for kind in run.kinds:
        source = run.sources.get(kind)
        if not isinstance(source, Mapping):
            documents.append(ReviewDocument(kind=kind, blockers=("구조화된 거래/계약 조건이 필요합니다.",)))
            continue
        digest = _hash(source)
        try:
            preview = build_preview(kind, source)
            blockers = tuple(preview.blockers)
            files = create_review_files(kind, source) if (
                kind == "CONTRACT" and any(c.get("sentences") for c in source.get("clauses", []) or [])
                or kind != "CONTRACT" and not blockers
            ) else {}
            # Draft contracts may legitimately have unresolved terms, but cannot be approved.
            documents.append(ReviewDocument(kind=kind, blockers=blockers,
                                             files=files, source_hash=digest))
        except (ValueError, TypeError, KeyError) as exc:
            documents.append(ReviewDocument(kind=kind, blockers=(str(exc),),
                                             source_hash=digest, files={}))
    needs_input = not documents or any(d.blockers or not d.files for d in documents)
    return replace(run, documents=tuple(documents),
                   status="needs_input" if needs_input else "awaiting_document_approval",
                   email_approved=False, email_review_hash="",
                   history=run.history + ("기존 엔진 검증 및 DRAFT 파일 생성",))


def _document_valid(run: ReviewRun, doc: ReviewDocument) -> bool:
    if doc.kind not in run.sources or doc.source_hash != _hash(run.sources[doc.kind]):
        return False
    try:
        return bool(doc.files) and _file_digest(doc.files) == doc.reviewed_hash
    except ValueError:
        return False


def approve_document(run: ReviewRun, kind: str) -> ReviewRun:
    target = next((d for d in run.documents if d.kind == kind), None)
    if target is None or target.blockers or not target.files:
        raise ValueError("Review file is missing or requires confirmed terms")
    if target.source_hash != _hash(run.sources.get(kind)):
        raise ValueError("Document inputs changed; regenerate before reviewing")
    fingerprint = _file_digest(target.files)
    docs = tuple(replace(d, approved=True, reviewed_hash=fingerprint)
                 if d.kind == kind else d for d in run.documents)
    all_reviewed = bool(docs) and all(d.approved and _document_valid(run, d) for d in docs)
    return replace(run, documents=docs, email_approved=False, email_review_hash="",
                   status="awaiting_email_review" if all_reviewed else "awaiting_document_approval",
                   history=run.history + (f"{kind} DRAFT 검토 확인",))


def change_request(run: ReviewRun, candidates: Mapping[str, Any]) -> ReviewRun:
    if not isinstance(candidates, Mapping):
        raise ValueError("Document inputs must be an object")
    return replace(run, sources=deepcopy(dict(candidates)), documents=(),
                   status="needs_preparation", email_approved=False, email_review_hash="",
                   history=run.history + ("문서 입력 변경; 모든 승인 무효화",))


def set_email_draft(run: ReviewRun, recipient: str, subject: str, body: str) -> ReviewRun:
    return replace(run, email_to=recipient.strip(), email_subject=subject.strip(),
                   email_body=body, email_approved=False, email_review_hash="",
                   status="awaiting_email_review" if _all_reviewed(run) else run.status,
                   history=run.history + ("이메일 초안 편집; 메일 승인 무효화",))


def _all_reviewed(run: ReviewRun) -> bool:
    return bool(run.documents) and len(run.documents) == len(run.kinds) and all(
        d.approved and not d.blockers and _document_valid(run, d) for d in run.documents
    )


def _email_fingerprint(run: ReviewRun) -> str:
    return _hash({"to": run.email_to, "subject": run.email_subject,
                  "body": run.email_body,
                  "files": [(d.kind, d.reviewed_hash) for d in run.documents]})


def approve_email_review(run: ReviewRun) -> ReviewRun:
    if not _all_reviewed(run):
        raise ValueError("Approve all unchanged DRAFT files first")
    if not run.email_to or not run.email_subject or not run.email_body.strip():
        raise ValueError("Recipient, subject, and message are required")
    if (run.email_to.count("@") != 1 or "\n" in run.email_to or
            "\r" in run.email_to or "," in run.email_to):
        raise ValueError("Invalid email recipient")
    return replace(run, email_approved=True,
                   email_review_hash=_email_fingerprint(run),
                   status="review_complete_not_sendable",
                   history=run.history + ("이메일 초안 검토 확인 (SMTP 연결 없음)",))


def verify_handoff(run: ReviewRun) -> bool:
    return bool(_all_reviewed(run) and run.email_approved
                and run.email_review_hash == _email_fingerprint(run)
                and not run.can_send)
