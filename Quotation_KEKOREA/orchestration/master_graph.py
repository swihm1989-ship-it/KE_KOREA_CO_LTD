"""Independent, side-effect-free LangGraph master; NO mailbox or SMTP."""
from __future__ import annotations
from langgraph.graph import END, START, StateGraph
from .adapters.contract_adapter import prepare_contract_task
from .adapters.trade_adapter import prepare_trade_task
from .router import classify
from .state import MasterState

def _classify_node(state: MasterState) -> dict:
    kinds = classify(state.get("subject", ""), state.get("message", ""), state.get("requested_documents"))
    return {"requested_documents": kinds, "status": "classified"}

def _prepare_node(state: MasterState) -> dict:
    tasks = []
    for kind in state.get("requested_documents", []):
        if kind == "CONTRACT":
            tasks.append(prepare_contract_task())
        else:
            trade = prepare_trade_task(kind)
            tasks.append({"kind": trade.kind, "status": trade.status,
                          "approved_revision": trade.approved_revision})
    if not tasks:
        return {"document_tasks": [], "status": "needs_input",
                "needs_input": ["사용자가 요청한 문서 종류와 거래 내용을 확인하세요."]}
    return {"document_tasks": tasks, "status": "needs_input",
            "needs_input": [f"{task['kind']}: 필수 조건 및 사용자 검토가 필요합니다." for task in tasks]}

def build_master_graph():
    graph = StateGraph(MasterState)
    graph.add_node("classify", _classify_node)
    graph.add_node("prepare", _prepare_node)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "prepare")
    graph.add_edge("prepare", END)
    return graph.compile()

def run_dry_run(subject: str, message: str, *, requested_documents: list[str] | None = None) -> MasterState:
    initial: MasterState = {"source": "manual_dry_run", "subject": subject, "message": message}
    if requested_documents is not None:
        initial["requested_documents"] = requested_documents
    return build_master_graph().invoke(initial)
