"""Isolated LangGraph checkpoints for contract workflows.

Checkpoints are process-local and deliberately never replace Supabase revisions.
Each AI invocation has a fresh thread_id to prevent reuse of earlier generated
terms or drafts. This adds recovery boundaries without changing the AI output.
A persistent backend can be introduced separately after access-control review.
"""
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver


# Each graph invocation gets an isolated saver that is released when the call
# ends. No accumulating sensitive contract snapshots in application globals.
# Contract revision history remains solely in the existing Supabase RPC.


def invoke_checkpointed(graph, initial_state, *, workflow):
    """Checkpoint each graph node while preserving the original return value."""
    thread_id = f"contract-{workflow}-{uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id}}
    compiled = graph.compile(checkpointer=InMemorySaver())
    return compiled.invoke(initial_state, config=config)
