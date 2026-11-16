"""Reuse the original KE KOREA ECLADO pricing policy in authenticated MASTER.

This adapter never queries Supabase, sets credentials, commits data or approves a
document. The caller supplies the same validated catalog snapshot consumed by
the existing PI/PO/CI/PL application.
"""
from __future__ import annotations

from copy import deepcopy
import re
from collections.abc import Mapping

from Quotation_KEKOREA.agent.pricing import (
    apply_catalog_product_matches,
    apply_verified_eclado_prices,
    is_eclado_supplier,
)

_TRADE = frozenset({"PI", "PO", "CI", "PL"})


def _company_name(doc, role):
    value = doc.get(role) or {}
    return str(value.get("legal_name") or "") if isinstance(value, Mapping) else str(value)


def _is_dear_glow(name):
    return "DEARGLOW" in "".join(re.findall(r"[A-Z0-9]+", str(name).upper()))


def requires_eclado_catalog(candidates):
    """Limit server-side catalog lookup to plausible ECLADO transactions."""
    if not isinstance(candidates, Mapping):
        return False
    for kind, doc in candidates.items():
        if kind not in _TRADE or not isinstance(doc, Mapping):
            continue
        names = " ".join(str(row.get("product_name") or "")
                         for row in doc.get("items") or [] if isinstance(row, Mapping))
        if (doc.get("product_family") == "cosmetics"
                or is_eclado_supplier(_company_name(doc, "seller"))
                or _is_dear_glow(_company_name(doc, "buyer"))
                or is_eclado_supplier(names)):
            return True
    return False


def reuse_legacy_catalog(candidates, catalog):
    """Apply the existing exact SKU/role/currency rules to a private copy.

    PO: only verified ECLADO supplier -> KRW purchase catalogue.
    PI: only named Dear Glow buyer -> its supported sales price profile.
    Other counterparties: matching only, never expose another buyer's prices.
    CI/PL: matching only; source PI / shipping prices must remain unchanged.
    """
    if not isinstance(candidates, Mapping):
        raise ValueError("Document candidates must be a mapping")
    if not isinstance(catalog, Mapping) or not catalog.get("products"):
        raise ValueError("ECLADO catalog is unavailable or empty")
    result = deepcopy(dict(candidates))
    for kind, document in result.items():
        if kind not in _TRADE or not isinstance(document, dict):
            continue
        if ((kind == "PO" and is_eclado_supplier(_company_name(document, "seller")))
                or (kind == "PI" and _is_dear_glow(_company_name(document, "buyer")))):
            # Recompute only catalog-owned price mismatch notes on each edit.
            document["conflicts"] = [
                note for note in document.get("conflicts") or []
                if "stated price differs from the verified catalog; confirm transaction override"
                not in str(note)
            ]
            apply_verified_eclado_prices(document, catalog)
        elif (document.get("product_family") == "cosmetics"
              or is_eclado_supplier(_company_name(document, "seller"))):
            apply_catalog_product_matches(document, catalog)
    return result
