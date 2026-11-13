"""Small dependency-free PDF, XLSX, and HTML renderers for review drafts."""
from datetime import date, datetime
from html import escape
from pathlib import Path
import re
import zipfile
from xml.sax.saxutils import escape as xml_escape
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .trade_documents import current_issue_date

TRADE_RENDERER_REVISION = 'approved-blank-final-20261113-v1'


def _english(value):
    if value is None:
        return ""
    value = str(value)
    value = value.translate(str.maketrans({"\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}))
    if any(ord(ch) > 255 and not ("\u3400" <= ch <= "\u9fff") for ch in value):
        raise ValueError("Document values must be English or Latin-1; translate non-Chinese text before rendering")
    return value


def _display_value(value, fallback="", *, final=False):
    """Keep explicit values, including zero, while leaving final unknowns empty."""
    if final:
        return "" if value is None or isinstance(value, str) and not value.strip() else value
    return value or fallback


def _final_number(value):
    """Parse a known numeric value without interpreting absence as zero."""
    if value is None or isinstance(value, str) and not value.strip():
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _final_quantities(items):
    """Only display totals when every row has a known quantity and unit."""
    totals = {}
    for item in items:
        if "shipped_quantity" in item:
            quantity = _final_number(item["shipped_quantity"])
        else:
            paid = _final_number(item.get("paid_quantity", item.get("quantity")))
            free = _final_number(item.get("free_quantity", "0"))
            quantity = paid + free if paid is not None and free is not None else None
        unit = str(_display_value(item.get("unit"), final=True)).strip()
        if quantity is None or not unit:
            return None
        key = unit.upper()
        if key not in totals:
            totals[key] = [Decimal("0"), unit]
        totals[key][0] += quantity
    return {unit: format(amount, "f") for amount, unit in totals.values()} or None


def _final_packing_totals(doc):
    """Use caller-prepared totals verbatim, including authoritative unknowns."""
    fields = (("package_count", "actual_package_count"),
              ("net_weight_kg", "declared_net_weight_kg"),
              ("gross_weight_kg", "declared_gross_weight_kg"),
              ("volume_cbm", "declared_volume_cbm"))
    if "_final_packing_totals" in doc:
        supplied = doc.get("_final_packing_totals") or {}
        return {**{field: supplied.get(field) for field, _ in fields},
                "quantities": supplied.get("quantities")}
    from .packing import reconcile_packing
    calculated = reconcile_packing(doc)["calculated"]
    totals = {}
    for field, declared_field in fields:
        total = _final_number(calculated.get(field))
        if total is None:
            total = _final_number(doc.get(declared_field))
        if total is None and field in {"net_weight_kg", "gross_weight_kg"}:
            values = [_final_number(package.get(field)) for package in doc.get("packages") or []]
            if values and all(value is not None for value in values):
                total = sum(values, Decimal("0"))
        totals[field] = format(total, "f") if total is not None else None
    totals["quantities"] = _final_quantities(doc.get("items") or [])
    return totals


def _format_quantity(value, *, final=False):
    if final:
        value = _final_number(value)
        if value is None:
            return ""
    try:
        amount = Decimal(str(value))
        rendered = format(amount, ",f")
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    except Exception:
        return str(value or "")


def format_currency_amount(value, currency, *, final=False):
    """Format transaction money with KRW whole units and two decimal places otherwise."""
    if final:
        value = _final_number(value)
        if value is None:
            return ""
    currency = str(currency or "").upper()
    quantum = Decimal("1") if currency == "KRW" else Decimal("0.01")
    try:
        amount = Decimal(str(value or "0")).quantize(quantum, rounding=ROUND_HALF_UP)
    except Exception:
        return str(value or "")
    rendered = f"{amount:,.0f}" if currency == "KRW" else f"{amount:,.2f}"
    return f"${rendered}" if currency == "USD" else f"{currency} {rendered}".strip()


def _rows(doc, *, final=False):
    if doc.get("document_type") == "PL":
        rows = [["Line", "Product", "Capacity / Specification", "Qty", "Unit", "Package Type", "Packages", "NW (KG)", "GW (KG)", "CBM", "HS Code"]]
        for i, item in enumerate(doc.get("items", []), 1):
            rows.append([str(i), _english(item.get("product_name")), _english(item.get("capacity")),
                         _format_quantity(item.get("display_quantity", item.get("quantity", "")), final=final), _english(item.get("unit")),
                         _english(item.get("package_type")), _english(item.get("package_count")),
                         _english(item.get("net_weight_kg")), _english(item.get("gross_weight_kg")), _english(item.get("volume_cbm")), _english(item.get("hs_code"))])
        return rows
    rows = [["Line", "Product", "Capacity / Specification", "Qty", "Unit", "Unit Price", "Discount", "Amount"]]
    for i, item in enumerate(doc.get("items", []), 1):
        if doc.get("document_type") == "PL":
            price = "N/A"
            amount = "N/A"
        else:
            price = item.get("final_unit_price", "")
            amount = item.get("line_total", "")
            if doc.get("product_family") == "cosmetics":
                price = format_currency_amount(price, doc.get("currency"), final=final)
                amount = format_currency_amount(amount, doc.get("currency"), final=final)
        discount = item.get("discount_percent", "0")
        if final:
            discount = _format_quantity(item.get("discount_percent"), final=True)
        discount = str(discount) + "%" if final and discount != "" else ("" if final else discount + "%")
        free_quantity = (_final_number(item.get("free_quantity")) if final else
                         float(item.get("free_quantity") or 0))
        if free_quantity:
            rows.append([str(i), _english(item.get("product_name")) + " (PAID)", _english(item.get("capacity")),
                         _format_quantity(item.get("paid_quantity", ""), final=final), _english(item.get("unit")), price,
                         discount, amount])
            rows.append([str(i), _english(item.get("product_name")) + " (FREE OF CHARGE)", _english(item.get("capacity")),
                         _format_quantity(item.get("free_quantity", ""), final=final), _english(item.get("unit")),
                         format_currency_amount("0", doc.get("currency")) if doc.get("product_family") == "cosmetics" else "0",
                         "FOC", format_currency_amount("0", doc.get("currency")) if doc.get("product_family") == "cosmetics" else "0"])
        else:
            rows.append([str(i), _english(item.get("product_name")), _english(item.get("capacity")),
                         _format_quantity(item.get("display_quantity", item.get("shipped_quantity", item.get("quantity", ""))), final=final), _english(item.get("unit")), price,
                         discount, amount])
    return rows


def _under_1000(n):
    ones = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
    tens = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]
    words = []
    if n >= 100:
        words += [ones[n // 100], "HUNDRED"]
        n %= 100
    if n >= 20:
        words.append(tens[n // 10])
        if n % 10:
            words.append(ones[n % 10])
    elif n:
        words.append(ones[n])
    return " ".join(words)


def amount_in_english(amount, currency, *, final=False):
    if final:
        amount = _final_number(amount)
        if amount is None or not currency:
            return ""
    value = Decimal(str(amount)).quantize(Decimal("1") if currency == "KRW" else Decimal("0.01"), rounding=ROUND_HALF_UP)
    integer = int(value)
    fraction = int((value - integer) * 100)
    groups = (("TRILLION", 10**12), ("BILLION", 10**9), ("MILLION", 10**6), ("THOUSAND", 10**3))
    words = []
    remainder = integer
    for label, base in groups:
        count, remainder = divmod(remainder, base)
        if count:
            words.extend([_under_1000(count), label])
    if remainder or not words:
        words.append("ZERO" if final and not remainder else _under_1000(remainder))
    major, minor = {"USD": ("US DOLLARS", "CENTS"), "KRW": ("KOREAN WON", "JEON"),
                    "EUR": ("EUROS", "CENTS"), "CNY": ("CHINESE YUAN", "FEN")}.get(currency, (currency, "HUNDREDTHS"))
    result = " ".join(words) + " " + major
    if fraction:
        result += " AND " + _under_1000(fraction) + " " + minor
    return result + " ONLY"


def _render_status(doc, final):
    """Only an explicit rendering option can mark an output as final."""
    if final:
        return "FINAL"
    status = doc.get("status", "DRAFT")
    return "DRAFT" if str(status).strip().upper() == "FINAL" else status


def document_lines(doc, bank_details=None, *, final=False):
    status = _render_status(doc, final)
    dtype = doc.get("document_type", "TRADE DOCUMENT")
    company_heading = "KE KOREA CO. LTD" if final else "KE KOREA CO. LTD - REVIEW DRAFT"
    lines = [status.replace("_", " "), company_heading, "", dtype,
             "Document No.: " + _english(_display_value(doc.get("document_number"), "TBD", final=final)),
             "Issue Date: " + _english(_display_value(doc.get("issue_date"), "TBD", final=final)),
             "Product Family: " + _english(_display_value(doc.get("product_family"), "TBD", final=final)).upper(),
             "Currency: " + _english(_display_value(doc.get("currency"), "TBD", final=final)), "", "SELLER / SUPPLIER"]
    lines.extend([_english((doc.get("seller") or {}).get(k)) for k in ("legal_name", "address", "contact", "phone", "email") if (doc.get("seller") or {}).get(k)])
    lines += ["", "BUYER / CUSTOMER"]
    lines.extend([_english((doc.get("buyer") or {}).get(k)) for k in ("legal_name", "address", "contact", "phone", "email", "registration_details") if (doc.get("buyer") or {}).get(k)])
    for label, field in (("Bill To", "bill_to"), ("Ship To", "ship_to"), ("Incoterms", "incoterms"),
                         ("Payment Terms", "payment_terms"), ("Shipment Reference", "shipment_reference"),
                         ("Country of Origin", "country_of_origin")):
        if doc.get(field):
            lines.append(f"{label}: {_english(doc[field])}")
    rows = _rows(doc, final=final)
    lines += ["", "LINE ITEMS: " + " | ".join(rows[0])]
    for row in rows[1:]:
        lines.append(" | ".join(_english(cell) for cell in row))
    if doc.get("document_type") != "PL":
        total = doc.get("total", None if final else "0")
        total_display = (format_currency_amount(total, doc.get("currency"), final=final)
                         if doc.get("product_family") == "cosmetics"
                         else _english(doc.get("currency") or "") + " " + _english(total))
        if final and _final_number(total) is None:
            total_display = ""
        lines += ["", "TOTAL: " + _english(total_display)]
        lines.append("AMOUNT IN WORDS: " + amount_in_english(total, doc.get("currency") or "", final=final))
    if doc.get("actual_package_count") and doc.get("document_type") != "PL":
        lines.append("Actual Package Count: " + _english(doc["actual_package_count"]))
    for i, package in enumerate(doc.get("packages", []), 1):
        lines.append(f"Package {i}: {_english(package.get('package_type'))}; Count {_english(package.get('package_count'))}; Net {_english(package.get('net_weight_kg'))} kg; Gross {_english(package.get('gross_weight_kg'))} kg")
    if (not final and doc.get("document_type") == "PL" and doc.get("packages") and
            not any(item.get("package_count") or item.get("net_weight_kg") or item.get("gross_weight_kg") or item.get("volume_cbm") for item in doc.get("items", []))):
        try:
            net_total = sum(Decimal(str(p.get("net_weight_kg"))) for p in doc["packages"])
            gross_total = sum(Decimal(str(p.get("gross_weight_kg"))) for p in doc["packages"])
            lines.append(f"TOTAL PACKAGES: {_english(doc.get('actual_package_count'))}; TOTAL NET WEIGHT: {net_total:f} kg; TOTAL GROSS WEIGHT: {gross_total:f} kg")
        except Exception:
            lines.append("TOTAL PACKAGE WEIGHTS: REVIEW REQUIRED")
    if doc.get("document_type") == "PL":
        if final:
            calculated = _final_packing_totals(doc)
            package_total = calculated["package_count"]
            quantities = calculated.get("quantities")
            if quantities:
                for unit, quantity in quantities.items():
                    lines.append(f"Total quantity ({_english(unit)}): {_format_quantity(quantity, final=True)}")
            else:
                lines.append("Total quantity: ")
        else:
            from .packing import reconcile_packing
            packing = reconcile_packing(doc)
            calculated = packing["calculated"]
            package_total = calculated.get("package_count") or doc.get("actual_package_count")
            if packing["quantity_complete"]:
                for unit, quantity in packing["quantities"].items():
                    lines.append(f"Total quantity ({_english(unit)}): {_format_quantity(quantity)}")
        for label, value in (("Containers", doc.get("container_count")),
                             ("HS Code", doc.get("hs_code")),
                             ("Total packages", _format_quantity(package_total, final=final) if final or package_total else None),
                             ("Total net weight (kg)", calculated.get("net_weight_kg") if final else calculated.get("net_weight_kg") or doc.get("declared_net_weight_kg")),
                             ("Total gross weight (kg)", calculated.get("gross_weight_kg") if final else calculated.get("gross_weight_kg") or doc.get("declared_gross_weight_kg")),
                             ("Total volume (CBM)", calculated.get("volume_cbm") if final else calculated.get("volume_cbm") or doc.get("declared_volume_cbm"))):
            lines.append(f"{label}: {_english(_display_value(value, 'TO BE CONFIRMED', final=final))}")
    if doc.get("remarks"):
        lines += ["", "REMARKS", _english(doc["remarks"])]
    if doc.get("document_type") == "PI":
        bank_details = bank_details or {}
        lines += ["", "BANK INFORMATION"]
        for label, key in (("Beneficiary", "BENEFICIARY"), ("Bank Name", "BANK_NAME"),
                           ("Branch Name", "BRANCH"), ("SWIFT Code", "SWIFT"),
                           ("Account Number", "ACCOUNT_NUMBER"), ("Bank Address", "BANK_ADDRESS")):
            value = bank_details.get(key)
            if key == "ACCOUNT_NUMBER" and value:
                value = str(value) + " (USD)"
            lines.append(f"{label}: {_english(_display_value(value, '[BANK DETAIL REQUIRED]', final=final))}")
    lines += ["", "AUTHORIZED SIGNATURE", "DAVID, SEOKWON IHM", "KE KOREA CO. LTD"]
    if not final:
        lines.append("[OFFICIAL COMPANY SEAL TO BE INSERTED]")
    if doc.get("blocking_issues") and not final:
        lines += ["", "OPEN ITEMS - DO NOT ISSUE"]
        for issue in doc["blocking_issues"]:
            if any(ord(ch) > 255 for ch in str(issue)):
                lines.append("- Review a non-English source note in the app")
            else:
                lines.append("- " + _english(issue))
    lines += ["", "Prepared in English. Review all transaction and shipping details before use."]
    return lines


def _pdf_bytes(lines):
    pages = [lines[i:i + 48] for i in range(0, len(lines), 48)] or [[]]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    page_ids = [5 + 2 * i for i in range(len(pages))]
    objects.append(("<< /Type /Pages /Kids [" + " ".join(f"{n} 0 R" for n in page_ids) + f"] /Count {len(pages)} >>").encode())
    objects.append(b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H /DescendantFonts [4 0 R] >>")
    objects.append(b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> /DW 1000 >>")
    for i, page_lines in enumerate(pages):
        page_id, stream_id = 5 + 2 * i, 6 + 2 * i
        commands = ["BT", "/F1 9 Tf", "50 790 Td", "14 TL"]
        for line in page_lines:
            safe = _english(line)[:180].encode("utf-16-be").hex().upper()
            commands.append(f"<{safe}> Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("ascii")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def _xlsx_bytes(doc, bank_details=None, *, seal_path=None, final=False):
    rows = [[doc.get("document_type", "DRAFT"), "STATUS", "FINAL" if final else doc.get("status", "DRAFT")],
            ["Currency", _display_value(doc.get("currency"), "TBD", final=final),
             "Product Family", _display_value(doc.get("product_family"), "TBD", final=final)],
            ["Document Number", _display_value(doc.get("document_number"), "TBD", final=final),
             "Issue Date", _display_value(doc.get("issue_date"), "TBD", final=final)],
            ["Seller", _display_value((doc.get("seller") or {}).get("legal_name"), "TBD", final=final)],
            ["Seller Address", _display_value((doc.get("seller") or {}).get("address"), "TBD", final=final)],
            ["Seller Contact", (doc.get("seller") or {}).get("contact") or ""],
            ["Seller Tel", (doc.get("seller") or {}).get("phone") or ""],
            ["Seller Email", (doc.get("seller") or {}).get("email") or ""],
            ["Buyer", _display_value((doc.get("buyer") or {}).get("legal_name"), "TBD", final=final)],
            ["Buyer Address", _display_value((doc.get("buyer") or {}).get("address"), "TBD", final=final)],
            ["Buyer Contact", (doc.get("buyer") or {}).get("contact") or ""],
            ["Buyer Tel", (doc.get("buyer") or {}).get("phone") or ""],
            ["Buyer Email", (doc.get("buyer") or {}).get("email") or ""],
            ["Buyer Registration Details", (doc.get("buyer") or {}).get("registration_details") or ""], [], *_rows(doc, final=final),
            ["", "", "", "", "", "TOTAL", doc.get("currency") or "",
             format_currency_amount(doc.get("total", None if final else "0"), doc.get("currency"), final=final)
             if doc.get("product_family") == "cosmetics" else doc.get("total", None if final else "0")],
            ["Incoterms", _display_value(doc.get("incoterms"), "TBD", final=final)],
            ["Payment Terms", _display_value(doc.get("payment_terms"), "TBD", final=final)],
            ["Remarks", doc.get("remarks") or ""]]
    if doc.get("document_type") == "PL":
        if final:
            calculated = _final_packing_totals(doc)
            package_total = calculated["package_count"]
            quantities = calculated.get("quantities")
        else:
            from .packing import reconcile_packing
            packing = reconcile_packing(doc)
            calculated = packing["calculated"]
            package_total = calculated.get("package_count") or doc.get("actual_package_count")
            quantities = packing["quantities"] if packing["quantity_complete"] else None
        rows = [row for row in rows if not (len(row) > 5 and row[:5] == ["", "", "", "", ""] and row[5] == "TOTAL")]
        rows += [["Containers", _display_value(doc.get("container_count"), "TO BE CONFIRMED", final=final)],
                 ["HS Code", _display_value(doc.get("hs_code"), "TO BE CONFIRMED", final=final)],
                 ["Total packages", _format_quantity(package_total, final=final) if final or package_total else "TO BE CONFIRMED"]]
        for label, field, declared_field in (("Total net weight (kg)", "net_weight_kg", "declared_net_weight_kg"),
                                              ("Total gross weight (kg)", "gross_weight_kg", "declared_gross_weight_kg"),
                                              ("Total volume (CBM)", "volume_cbm", "declared_volume_cbm")):
            value = calculated.get(field) if final else calculated.get(field) or doc.get(declared_field)
            rows.append([label, _display_value(value, "TO BE CONFIRMED", final=final)])
        if quantities:
            rows += [[f"Total quantity ({unit})", _format_quantity(quantity, final=final)]
                     for unit, quantity in quantities.items()]
        elif final:
            rows.append(["Total quantity", ""])
    if doc.get("document_type") == "PI":
        bank_details = bank_details or {}
        rows += [["Bank Information", "Beneficiary", _display_value(bank_details.get("BENEFICIARY"), "[BANK DETAIL REQUIRED]", final=final)],
                 ["", "Bank Name", _display_value(bank_details.get("BANK_NAME"), "[BANK DETAIL REQUIRED]", final=final)],
                 ["", "Branch Name", _display_value(bank_details.get("BRANCH"), "[BANK DETAIL REQUIRED]", final=final)],
                 ["", "SWIFT Code", _display_value(bank_details.get("SWIFT"), "[BANK DETAIL REQUIRED]", final=final)],
                 ["", "Account Number (USD)", _display_value(bank_details.get("ACCOUNT_NUMBER"), "[BANK DETAIL REQUIRED]", final=final)],
                 ["", "Bank Address", _display_value(bank_details.get("BANK_ADDRESS"), "[BANK DETAIL REQUIRED]", final=final)]]
    seal_bytes = Path(seal_path).read_bytes() if seal_path and Path(seal_path).is_file() else None
    if seal_bytes:
        rows += [[], ["Authorized Representative", "DAVID, SEOKWON IHM"], ["KE KOREA CO. LTD"]]
    xml_rows = []
    for ri, row in enumerate(rows, 1):
        cells = []
        for ci, value in enumerate(row, 1):
            if value is None or value == "":
                continue
            col = ""
            n = ci
            while n:
                n, rem = divmod(n - 1, 26)
                col = chr(65 + rem) + col
            cell = f"{col}{ri}"
            cells.append(f'<c r="{cell}" t="inlineStr"><is><t xml:space="preserve">{xml_escape(_english(value))}</t></is></c>')
        xml_rows.append(f'<row r="{ri}">{"".join(cells)}</row>')
    drawing = '<drawing r:id="rId1"/>' if seal_bytes else ""
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetData>' + "".join(xml_rows) + "</sheetData>" + drawing + "</worksheet>")
    sheet_name = "Trade Document Final" if final else "Trade Document Draft"
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="' + sheet_name + '" sheetId="1" r:id="rId1"/></sheets></workbook>'
    with __import__("io").BytesIO() as buf:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            drawing_types = '<Default Extension="png" ContentType="image/png"/><Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' if seal_bytes else ""
            z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' + drawing_types + '</Types>')
            z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr("xl/worksheets/sheet1.xml", sheet)
            if seal_bytes:
                z.writestr("xl/worksheets/_rels/sheet1.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>')
                z.writestr("xl/drawings/drawing1.xml", '<?xml version="1.0" encoding="UTF-8"?><xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>' + str(len(rows)) + '</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:ext cx="4572000" cy="1542000"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="KE KOREA Company Seal"/><xdr:cNvPicPr/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>')
                z.writestr("xl/drawings/_rels/drawing1.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/seal.png"/></Relationships>')
                z.writestr("xl/media/seal.png", seal_bytes)
        return buf.getvalue()


def render_files(doc, output_dir, *, bank_details=None, logo_path=None, seal_path=None, final=False):
    """Write review drafts by default, or final outputs after caller-side approval."""
    # Keep the date and destination defaults consistent across PDF, Excel, and HTML.
    doc = {**doc, "status": _render_status(doc, final), "issue_date": current_issue_date(),
           "ship_to": _display_value(doc.get("ship_to"), "N/A", final=final)}
    dtype = re.sub(r"[^A-Za-z0-9_-]", "_", str(doc.get("document_type") or "DRAFT"))
    stamp = re.sub(r"[^0-9-]", "", str(doc.get("issue_date") or "")) or date.today().isoformat()
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    output_label = "FINAL" if final else "DRAFT"
    stem = f"{dtype}_{stamp}_{output_label}_{run_id}"
    lines = document_lines(doc, bank_details, final=final)
    html_rows = "".join("<tr>" + "".join(f"<td>{escape(_english(v))}</td>" for v in row) + "</tr>" for row in _rows(doc, final=final))
    html_doc = "<!doctype html><meta charset='utf-8'><title>Trade Document " + output_label.title() + "</title><h1>" + escape(dtype) + "</h1><h2>" + escape(doc.get("status", "DRAFT")) + "</h2><table border='1'>" + html_rows + "</table><pre>" + escape("\n".join(lines)) + "</pre>"
    paths = {"pdf": directory / f"{stem}.pdf", "xlsx": directory / f"{stem}.xlsx", "html": directory / f"{stem}.html"}
    try:
        from .pi_pdf import render_trade_document
    except ImportError:
        from Quotation_KEKOREA.agent.pi_pdf import render_trade_document
    paths["pdf"].write_bytes(render_trade_document(
        doc, bank_details or {}, logo_path=logo_path, seal_path=seal_path, final=final))
    paths["xlsx"].write_bytes(_xlsx_bytes(doc, bank_details, seal_path=seal_path, final=final))
    paths["html"].write_text(html_doc, encoding="utf-8")
    return paths
