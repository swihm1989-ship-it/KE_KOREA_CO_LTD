"""Human review pause/resume for proposals, independent of contract persistence.

This graph NEVER edits a sentence, marks a term confirmed, saves a revision,
or calls an AI model. The existing application performs those operations only
after the user's explicit Apply button and its original validation checks.

The pause/checkpoint is process local. A restart requires creating a new review
thread from the saved proposal before the next explicit user decision.
"""
from uuid import uuid4
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt


class ApprovalState(TypedDict, total=False):
    contract_id: str
    revision: int
    proposal_id: str
    approved: bool


def _await_user_approval(state: ApprovalState):
    answer = interrupt({
        "contract_id": state["contract_id"],
        "revision": state["revision"],
        "proposal_id": state["proposal_id"],
        "question": "Apply the user-selected changes to this contract revision?",
    })
    if not isinstance(answer, dict):
        raise ValueError("Invalid approval response")
    if (answer.get("contract_id") != state["contract_id"]
            or answer.get("proposal_id") != state["proposal_id"]
            or answer.get("revision") != state["revision"]):
        raise ValueError("Stale approval response")
    return {"approved": answer.get("approved") is True}


_BUILDER = StateGraph(ApprovalState)
_BUILDER.add_node("wait_for_user", _await_user_approval)
_BUILDER.add_edge(START, "wait_for_user")
_BUILDER.add_edge("wait_for_user", END)
_SAVER = InMemorySaver()
_GRAPH = _BUILDER.compile(checkpointer=_SAVER)


def start_review(contract_id, revision, proposal_id):
    """Create an interrupt for the explicit proposal currently on screen."""
    thread_id = "review-" + uuid4().hex
    state = {
        "contract_id": str(contract_id),
        "revision": int(revision),
        "proposal_id": str(proposal_id),
    }
    result = _GRAPH.invoke(state, {"configurable": {"thread_id": thread_id}})
    if "__interrupt__" not in result:
        raise RuntimeError("Review did not pause for user approval")
    return thread_id


def complete_review(thread_id, contract_id, revision, proposal_id, *, approved):
    """Resume a previously paused review; does not commit any change."""
    config = {"configurable": {"thread_id": str(thread_id)}}
    saved = _GRAPH.get_state(config)
    values = saved.values or {}
    if (values.get("contract_id") != str(contract_id)
            or values.get("revision") != int(revision)
            or values.get("proposal_id") != str(proposal_id)
            or not saved.next):
        raise ValueError("Review state is stale or missing")
    result = _GRAPH.invoke(Command(resume={
        "contract_id": str(contract_id),
        "revision": int(revision),
        "proposal_id": str(proposal_id),
        "approved": bool(approved),
    }), config=config)
    if result.get("approved") is not bool(approved):
        raise ValueError("Review outcome mismatch")
    # No long-lived copies of proposal metadata in process memory.
    _SAVER.delete_thread(str(thread_id))
    return result["approved"]
