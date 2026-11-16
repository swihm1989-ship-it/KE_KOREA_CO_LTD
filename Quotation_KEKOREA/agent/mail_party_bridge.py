"""Legacy company-directory rules for MASTER mail -> original trade engine.

No separate account database, invented identity, pricing or authorization.
Prefer a single explicit counterparty match and preserve direct edits.
"""
from copy import deepcopy
from collections.abc import Mapping

from Quotation_KEKOREA.agent.counterparties import (
    apply_company_profiles, apply_ke_korea_company_defaults,
)
from Quotation_KEKOREA.agent.pricing import is_eclado_supplier


def apply_mail_counterparties(candidates, profiles, *, instruction):
    """Reuse KE KOREA default profile and Supabase directory on imported mail.

    In a PI, ECLADO in the *product* context is not automatically the buyer.
    In a PO, DEAR GLOW in the original customer's order is not automatically
    the supplier. If several eligible profiles match, the legacy matcher
    leaves the counterparty blank for human review.
    """
    result = deepcopy(dict(candidates))
    prompt = str(instruction or "")
    for kind, document in result.items():
        if kind not in {"PI", "PO", "CI", "PL"} or not isinstance(document, dict):
            continue
        apply_ke_korea_company_defaults(document, kind)
        role = "seller" if kind == "PO" else "buyer"
        supplied = str((document.get(role) or {}).get("legal_name") or "").strip()
        eligible = list(profiles or ())
        if not supplied:
            skip_key = "DEAR_GLOW" if kind == "PO" else "ECLADO"
            eligible = [p for p in eligible
                        if str(p.get("company_key") or "").upper() != skip_key]
        apply_company_profiles(document, eligible, prompt=prompt)
        resolved = document.get("seller") if kind == "PO" else document.get("buyer")
        name = "".join(ch for ch in str((resolved or {}).get("legal_name") or "").upper()
                       if ch.isalnum())
        recognized_role = (is_eclado_supplier(name) if kind == "PO"
                           else "DEARGLOW" in name)
        if is_eclado_supplier(prompt) and recognized_role:
            # Product family is supported by ECLADO brand + explicit matched
            # counterparty, not guessed from an unrelated company name.
            document["product_family"] = "cosmetics"
            for item in document.get("items") or []:
                if isinstance(item, dict) and not item.get("unit"):
                    item["unit"] = "PCS"
    return result
