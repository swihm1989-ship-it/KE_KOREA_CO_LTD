"""Read the locally prepared private ECLADO price seed without exposing prices in logs."""
import json
from pathlib import Path
import re
from decimal import Decimal, InvalidOperation


def load_local_seed(seed_path=None):
    path = Path(seed_path) if seed_path else Path(__file__).resolve().parents[1] / "private" / "eclado" / "002_eclado_catalog_seed.sql"
    if not path.exists():
        return {"products": [], "purchase_prices": [], "buyer_prices": []}
    sql = path.read_text(encoding="utf-8")
    match = re.search(r"\$kekorea_seed\$(.*?)\$kekorea_seed\$", sql, re.S)
    if not match:
        raise ValueError("Local catalog seed is malformed")
    return json.loads(match.group(1))


def load_local_catalog(seed_path=None):
    return load_local_seed(seed_path).get("products", [])


def match_eclado_product(name, capacity=None, products=None):
    """Match exact English item and, when supplied, exact capacity. Never fuzzy-match."""
    products = products if products is not None else load_local_catalog()
    key = " ".join(str(name or "").split()).casefold()
    capacity_key = " ".join(str(capacity or "").split()).casefold() or None
    exact = [p for p in products if p.get("brand") == "ECLADO" and
             " ".join(str(p.get("item_name") or "").split()).casefold() == key]
    if capacity_key is not None:
        exact = [p for p in exact if " ".join(str(p.get("capacity") or "").split()).casefold() == capacity_key]
    if len(exact) != 1:
        return {"status": "not_found" if not exact else "ambiguous", "matches": exact}
    return {"status": "matched", "product": exact[0]}


def resolve_price(product_id, prices=None, role="sale", currency=None):
    """Resolve a locally seeded price only on exact product, role and currency."""
    if prices is None:
        prices = load_local_seed()
    table = "buyer_prices" if role == "sale" else "purchase_prices"
    rows = [p for p in prices.get(table, []) if p.get("product_id") == product_id and
            (currency is None or p.get("currency") == currency)]
    if len(rows) != 1:
        return None
    return rows[0] if len(rows) == 1 else None


def apply_verified_eclado_prices(draft, seed=None):
    """Replace ECLADO candidate price with exact catalog price or mark the uncertainty."""
    seed = seed if seed is not None else load_local_seed()
    products = seed.get("products", [])
    price_table = "purchase_prices" if draft.get("document_type") == "PO" else "buyer_prices"
    default_currency = "KRW" if draft.get("document_type") == "PO" else None
    counterparty_role = "seller" if draft.get("document_type") == "PO" else "buyer"
    counterparty = re.sub(r"\b(CO|COMPANY|LTD|LIMITED|INC|CORP|CORPORATION)\b", " ",
                          str((draft.get(counterparty_role) or {}).get("legal_name") or "").upper())
    counterparty = " ".join(re.findall(r"[A-Z0-9]+", counterparty))
    expected_party = "ECLADO" if draft.get("document_type") == "PO" else "DEAR GLOW"
    party_matches = counterparty in {expected_party, expected_party.replace(" ", "")}
    for item in draft.get("items", []):
        if draft.get("product_family") != "cosmetics":
            item["master_price"] = False
            continue
        match = match_eclado_product(item.get("product_name"), item.get("capacity"), products)
        if match["status"] != "matched":
            item["master_price"] = False
            draft.setdefault("missing_fields", []).append(
                f"Exact ECLADO product match for {item.get('product_name') or 'item'}; capacity/SKU may be needed")
            continue
        product = match["product"]
        if not party_matches:
            item["master_price"] = False
            if item.get("source") and item.get("unit_price") not in (None, ""):
                item["price_override_confirmed"] = True
                item["price_source"] = "User-provided price; counterparty is outside the local catalog price profile"
            else:
                draft.setdefault("missing_fields", []).append(
                    f"Confirm a transaction-specific price for {product.get('item_name')}; local catalog price is only for {expected_party}")
            continue
        currency = draft.get("currency") or default_currency
        price = resolve_price(product["id"], seed, "purchase" if draft.get("document_type") == "PO" else "sale", currency)
        if not price:
            item["master_price"] = False
            draft.setdefault("missing_fields", []).append(
                f"Verified {currency or 'currency'} catalog price for {product.get('item_name')}")
            continue
        provided = item.get("unit_price")
        try:
            price_differs = provided not in (None, "") and Decimal(str(provided)) != Decimal(str(price["unit_price"]))
        except (InvalidOperation, TypeError, ValueError):
            price_differs = True
        if item.get("price_override_confirmed"):
            draft["conflicts"] = [c for c in draft.get("conflicts", [])
                                  if not (product.get("item_name", "") in c and "stated price differs from the verified catalog" in c)]
        if price_differs and not item.get("price_override_confirmed"):
            draft.setdefault("conflicts", []).append(
                f"{product.get('item_name')} stated price differs from the verified catalog; confirm transaction override")
        if not price_differs:
            item["product_id"] = product["id"]
            item["unit_price"] = str(price["unit_price"])
            item["price_source"] = "Verified local ECLADO catalog; source workbook row " + str(price.get("source_row"))
            item["master_price"] = True
        elif item.get("price_override_confirmed"):
            item["price_source"] = "User-confirmed transaction-specific override"
            item["master_price"] = False
