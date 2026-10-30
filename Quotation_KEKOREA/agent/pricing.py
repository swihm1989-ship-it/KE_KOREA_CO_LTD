"""Read the locally prepared private ECLADO price seed without exposing prices in logs."""
import json
from pathlib import Path
import re
from decimal import Decimal, InvalidOperation
import json as json_module
import urllib.error
import urllib.parse
import urllib.request


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


def load_supabase_catalog(env, *, opener=urllib.request.urlopen, timeout=20):
    """Load one consistent catalog snapshot using a server-only Supabase secret key."""
    base_url = str(env.get("SUPABASE_URL", "")).rstrip("/")
    secret_key = str(env.get("SUPABASE_SECRET_KEY", ""))
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co") or parsed.query or parsed.fragment:
        raise ValueError("SUPABASE_URL must be the HTTPS URL of this Supabase project")
    if not secret_key:
        raise ValueError("SUPABASE_SECRET_KEY is not configured")

    def get_rows(table, params):
        query = urllib.parse.urlencode(params)
        url = f"{base_url}/rest/v1/{table}?{query}"
        request = urllib.request.Request(url, headers={"apikey": secret_key, "Accept": "application/json"}, method="GET")
        try:
            with opener(request, timeout=timeout) as response:
                rows = json_module.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Supabase catalog request failed (HTTP {exc.code}); check the server key, API exposure, and table permissions") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError("Supabase could not be reached; check the project URL and network") from None
        except (UnicodeDecodeError, json_module.JSONDecodeError):
            raise RuntimeError("Supabase returned an invalid catalog response") from None
        if not isinstance(rows, list):
            raise RuntimeError("Supabase returned an unexpected catalog response")
        return rows

    imports = get_rows("kekorea_catalog_imports", [
        ("select", "id,source_label,imported_at,payload_sha256"),
        ("order", "imported_at.desc"), ("limit", "1")])
    if not imports:
        raise RuntimeError("No ECLADO catalog import was found in Supabase")
    import_id = imports[0].get("id")
    if not import_id:
        raise RuntimeError("The latest Supabase catalog import has no ID")

    products = get_rows("kekorea_products", [
        ("select", "id,brand,kind,source_code,item_name,capacity,group_name,metadata"),
        ("brand", "eq.ECLADO"), ("limit", "1000")])
    prices_query = [("select", "id,import_id,product_id,supplier_key,currency,unit_price,price_basis,source_row,source_column,effective_from,effective_to"),
                    ("import_id", f"eq.{import_id}"), ("limit", "1000")]
    purchase_prices = get_rows("kekorea_purchase_prices", prices_query)
    buyer_query = [("select", "id,import_id,product_id,buyer_key,currency,unit_price,price_basis,reference_discount_percent,reference_discounted_price,source_row,source_column,effective_from,effective_to"),
                   ("import_id", f"eq.{import_id}"), ("limit", "1000")]
    buyer_prices = get_rows("kekorea_buyer_prices", buyer_query)

    product_ids = {row.get("id") for row in products}
    if not product_ids:
        raise RuntimeError("No ECLADO products were found in Supabase")
    for table, rows in (("purchase", purchase_prices), ("buyer", buyer_prices)):
        if not rows:
            raise RuntimeError(f"The latest Supabase import has no {table} prices")
        for row in rows:
            if row.get("import_id") != import_id or row.get("product_id") not in product_ids:
                raise RuntimeError(f"Supabase {table} prices do not match the selected catalog import")
            try:
                amount = Decimal(str(row.get("unit_price")))
            except (InvalidOperation, TypeError, ValueError):
                raise RuntimeError(f"Supabase {table} catalog contains an invalid price") from None
            if not amount.is_finite() or amount < 0:
                raise RuntimeError(f"Supabase {table} catalog contains an invalid price")

    return {"import": imports[0], "products": products,
            "purchase_prices": purchase_prices, "buyer_prices": buyer_prices}


def match_eclado_product(name, capacity=None, products=None):
    """Match exact English item ignoring whitespace and exact capacity ignoring whitespace."""
    products = products if products is not None else load_local_catalog()
    key = re.sub(r"\s+", "", str(name or "")).casefold()
    capacity_key = re.sub(r"\s+", "", str(capacity or "")).casefold() or None
    exact = [p for p in products if p.get("brand") == "ECLADO" and
             re.sub(r"\s+", "", str(p.get("item_name") or "")).casefold() == key]
    if capacity_key is not None:
        exact = [p for p in exact if re.sub(r"\s+", "", str(p.get("capacity") or "")).casefold() == capacity_key]
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
    counterparty = re.sub(r"\b(CO|COMPANY|PTE|LTD|LIMITED|INC|CORP|CORPORATION)\b", " ",
                          str((draft.get(counterparty_role) or {}).get("legal_name") or "").upper())
    counterparty = "".join(re.findall(r"[A-Z0-9]+", counterparty))
    expected_party = "ECLADO" if draft.get("document_type") == "PO" else "DEAR GLOW"
    party_matches = ("ECLADO" in counterparty if draft.get("document_type") == "PO"
                     else "DEARGLOW" in counterparty)
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
        if not draft.get("currency"):
            # When an exact product/counterparty catalog lookup returns one
            # currency only, use that catalog currency instead of asking the
            # model to infer it from the order screenshot.
            draft["currency"] = price.get("currency")
        provided = item.get("unit_price")
        provided_amount = None
        try:
            if provided not in (None, ""):
                candidate_amount = Decimal(str(provided))
                if candidate_amount.is_finite() and candidate_amount > 0:
                    provided_amount = candidate_amount
        except (InvalidOperation, TypeError, ValueError):
            pass
        price_differs = (provided_amount is not None and
                         provided_amount != Decimal(str(price["unit_price"])))
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
