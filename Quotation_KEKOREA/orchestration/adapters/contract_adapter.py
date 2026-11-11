"""No contract signing, finalization, or revision bypass."""
def prepare_contract_task() -> dict[str, str]:
    return {"kind": "CONTRACT", "status": "needs_input",
            "reason": "Existing contract UI must collect verified terms and approval."}
