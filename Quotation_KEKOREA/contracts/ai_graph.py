"""First-stage LangGraph runner for *contract AI drafting only*.

Stateless graph: no persistence of confidential contract text outside the
existing repository and no automatic retries or bypass of human approvals.
The audited drafting pipeline remains the sole source of draft-generation logic.
"""
from copy import deepcopy
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END

from Quotation_KEKOREA.contracts.models import validate_snapshot
from Quotation_KEKOREA.contracts.drafting import generate_reviewed_draft


class ContractDraftState(TypedDict, total=False):
    snapshot: dict[str, Any]
    draft: dict[str, Any]


def generate_contract_draft_graph(snapshot, preferred_clauses, *, env,
                                  reference_context=None, transaction_messages=None,
                                  client=None, repo=None, use_library=True,
                                  initial_library_sources=None):
    """Run guarded contract drafting in isolated LangGraph stages.

    Keep the current call signature for the two existing Streamlit entry points.
    A failed node propagates its error and does NOT save any revision.
    """
    def prepare(state: ContractDraftState):
        candidate = validate_snapshot(state["snapshot"])
        if candidate.get("clauses"):
            raise ValueError(
                "Do not automatically regenerate an existing contract; "
                "use the existing revision workflow."
            )
        return {"snapshot": candidate}

    def draft(state: ContractDraftState):
        result = generate_reviewed_draft(
            state["snapshot"], preferred_clauses, env=env,
            reference_context=reference_context,
            transaction_messages=transaction_messages, client=client, repo=repo,
            use_library=use_library, initial_library_sources=initial_library_sources,
        )
        return {"draft": result}

    def verify(state: ContractDraftState):
        verified = validate_snapshot(state["draft"])
        if not verified.get("draft_quality") or not verified.get("clauses"):
            raise ValueError("Reviewed contract draft is incomplete; nothing was saved.")
        return {"draft": verified}

    graph = StateGraph(ContractDraftState)
    graph.add_node("prepare", prepare)
    graph.add_node("generate_and_audit", draft)
    graph.add_node("validate_reviewed_result", verify)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "generate_and_audit")
    graph.add_edge("generate_and_audit", "validate_reviewed_result")
    graph.add_edge("validate_reviewed_result", END)
    result = graph.compile().invoke({"snapshot": deepcopy(snapshot)})
    return result["draft"]
