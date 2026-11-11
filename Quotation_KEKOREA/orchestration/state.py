"""Separate master state; existing agent/contract state is never modified."""
from typing import Any, TypedDict

class MasterState(TypedDict, total=False):
    run_id: str
    source: str
    subject: str
    message: str
    requested_documents: list[str]
    document_tasks: list[dict[str, Any]]
    status: str
    needs_input: list[str]
    email_draft: dict[str, Any]
    errors: list[str]
