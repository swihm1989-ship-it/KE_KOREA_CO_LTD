"""Pure, in-memory orchestration simulator. All parties and documents are fictitious."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from ..router import classify

Status = Literal["needs_input", "awaiting_document_approval", "awaiting_email_approval", "ready_for_future_integration"]

@dataclass(frozen=True)
class MockMessage:
    id: str
    sender: str
    subject: str
    body: str
    received_at: str

@dataclass(frozen=True)
class MockTask:
    kind: str
    text: str
    approved: bool = False

@dataclass(frozen=True)
class MockRun:
    run_id: str
    source_id: str
    subject: str
    tasks: tuple[MockTask, ...]
    status: Status
    email_to: str = ""
    email_subject: str = ""
    email_body: str = ""
    email_approved: bool = False
    approval_fingerprint: str = ""
    history: tuple[str, ...] = ()

SAMPLE_MESSAGES = (
    MockMessage("demo-001", "buyer@example.test", "PI and Packing List request",
                "Please prepare PI and Packing List for a SAMPLE 100 PCS order. All prices are placeholders.",
                "2026-11-11 09:20"),
    MockMessage("demo-002", "legal@example.test", "Contract draft",
                "Can you prepare a draft contract for internal review? All details need confirmation.",
                "2026-11-11 10:15"),
    MockMessage("demo-003", "contact@example.test", "Hello",
                "Do you have an update on the SAMPLE inquiry?", "2026-11-11 11:05"),
)

def _fingerprint(run: MockRun) -> str:
    data = "\n".join([run.email_to, run.email_subject, run.email_body,
                      *[f"{t.kind}:{t.text}:{t.approved}" for t in run.tasks]])
    return sha256(data.encode("utf-8")).hexdigest()

def start_mock_run(message: MockMessage, requested_documents: list[str] | None = None) -> MockRun:
    kinds = classify(message.subject, message.body, requested_documents)
    tasks = tuple(MockTask(kind, f"[DEMO {kind}] 거래처·단가·수량·계약조건을 확인한 뒤 실제 문서 엔진으로 생성해야 합니다.") for kind in kinds)
    status: Status = "awaiting_document_approval" if tasks else "needs_input"
    return MockRun(run_id=str(uuid4()), source_id=message.id, subject=message.subject,
                   tasks=tasks, status=status, email_to=message.sender,
                   email_subject=f"Re: {message.subject}",
                   email_body="안녕하세요. 요청하신 사항을 검토하겠습니다.\n\n[DEMO: 발송 불가]",
                   history=("샘플 메시지에서 작업 생성",))

def edit_mock_document(run: MockRun, kind: str, new_text: str) -> MockRun:
    if not new_text.strip():
        raise ValueError("문서 초안은 비워둘 수 없습니다.")
    if kind not in [t.kind for t in run.tasks]:
        raise ValueError("존재하지 않는 문서입니다.")
    updated = tuple(replace(t, text=new_text, approved=False) if t.kind == kind else t for t in run.tasks)
    return replace(run, tasks=updated, status="awaiting_document_approval",
                   email_approved=False, approval_fingerprint="", history=run.history + (f"{kind} 수정 및 승인 무효화",))

def approve_mock_document(run: MockRun, kind: str) -> MockRun:
    if kind not in [t.kind for t in run.tasks]:
        raise ValueError("존재하지 않는 문서입니다.")
    updated = tuple(replace(t, approved=True) if t.kind == kind else t for t in run.tasks)
    all_approved = bool(updated) and all(t.approved for t in updated)
    return replace(run, tasks=updated,
                   status="awaiting_email_approval" if all_approved else "awaiting_document_approval",
                   email_approved=False, approval_fingerprint="",
                   history=run.history + (f"{kind} 샘플 검토 확인",))

def update_mock_email(run: MockRun, to: str, subject: str, body: str) -> MockRun:
    return replace(run, email_to=to, email_subject=subject, email_body=body,
                   email_approved=False, approval_fingerprint="",
                   status="awaiting_email_approval" if run.tasks and all(t.approved for t in run.tasks)
                   else run.status,
                   history=run.history + ("샘플 이메일 수정 및 승인 무효화",))

def approve_mock_email(run: MockRun) -> MockRun:
    if not run.tasks or not all(t.approved for t in run.tasks):
        raise ValueError("모든 샘플 문서를 먼저 검토해야 합니다.")
    if not run.email_to.strip() or not run.email_subject.strip() or not run.email_body.strip():
        raise ValueError("메일 수신자, 제목, 본문이 필요합니다.")
    if "\n" in run.email_to or "\r" in run.email_to or "@" not in run.email_to:
        raise ValueError("샘플 수신자 형식이 올바르지 않습니다.")
    fingerprint = _fingerprint(run)
    return replace(run, email_approved=True, approval_fingerprint=fingerprint,
                   status="ready_for_future_integration",
                   history=run.history + ("샘플 이메일 승인 표시 (실제 발송 없음)",))

def is_mock_approval_current(run: MockRun) -> bool:
    return bool(run.email_approved and run.approval_fingerprint == _fingerprint(run)
                and run.tasks and all(t.approved for t in run.tasks))
