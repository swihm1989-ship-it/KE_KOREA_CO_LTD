"""KE Korea blue-brand Proforma Invoice PDF layout with PI-only bank details."""
from io import BytesIO
from pathlib import Path
import re
import textwrap
import struct
import zlib


PAGE_W, PAGE_H = 612, 792
NAVY = (0.035, 0.15, 0.28)
BRAND_BLUE = (0.02, 0.43, 0.75)
INK = (0.18, 0.18, 0.18)
MUTED = (0.43, 0.43, 0.42)
PALE = (0.95, 0.975, 0.995)
MID_BLUE = (0.10, 0.32, 0.50)
WARNING = (0.69, 0.29, 0.18)


def _pdf_escape(value):
    return str(value).encode("ascii", "replace").decode("ascii").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Canvas:
    def __init__(self):
        self.commands = []
        self.images = []

    @staticmethod
    def _rgb(color):
        return "%.3f %.3f %.3f" % color

    def rect(self, x, top, w, h, color=None, stroke=None, line_width=0.7):
        y = PAGE_H - top - h
        if color:
            self.commands.extend([self._rgb(color) + " rg", f"{x} {y} {w} {h} re f"])
        if stroke:
            self.commands.extend([self._rgb(stroke) + " RG", f"{line_width} w {x} {y} {w} {h} re S"])

    def line(self, x1, top1, x2, top2, color=MUTED, width=0.7):
        self.commands.extend([self._rgb(color) + " RG", f"{width} w {x1} {PAGE_H-top1} m {x2} {PAGE_H-top2} l S"])

    def text(self, x, top, value, size=8, bold=False, color=INK):
        value = str(value or "")
        if re.search(r"[\u3400-\u9fff]", value):
            encoded = value.encode("utf-16-be").hex().upper()
            font = "F3"
            command = f"<{encoded}> Tj"
        else:
            font = "F2" if bold else "F1"
            command = f"({_pdf_escape(value)}) Tj"
        self.commands.extend([self._rgb(color) + " rg", f"BT /{font} {size} Tf 1 0 0 1 {x} {PAGE_H-top} Tm {command} ET"])

    def image(self, path, x, top, max_w, max_h, *, watermark=False, crop_box=None):
        if not path or not Path(path).is_file():
            return False
        try:
            width, height, pixels = _read_png_rgb(Path(path))
            if crop_box:
                crop_x, crop_y, crop_w, crop_h = crop_box
                pixels = _crop_rgb(pixels, width, height, crop_x, crop_y, crop_w, crop_h)
                width, height = crop_w, crop_h
            raw = zlib.compress(pixels, level=9)
        except Exception as exc:
            raise ValueError(f"Could not load PI brand PNG: {Path(path).name}") from exc
        crop_x = crop_y = 0
        crop_w, crop_h = width, height
        scale = min(max_w / width, max_h / height)
        draw_w, draw_h = width * scale, height * scale
        self.images.append({"bytes": raw, "width": width, "height": height, "watermark": watermark})
        image_id = len(self.images)
        image_x = x - crop_x * scale
        image_top = top - crop_y * scale
        y = PAGE_H - image_top - draw_h
        clip = ""
        if watermark:
            self.commands.extend(["q", clip + "/GS1 gs", f"{draw_w:.2f} 0 0 {draw_h:.2f} {image_x:.2f} {y:.2f} cm", f"/Im{image_id} Do", "Q"])
        else:
            self.commands.extend(["q", clip + f"{draw_w:.2f} 0 0 {draw_h:.2f} {image_x:.2f} {y:.2f} cm", f"/Im{image_id} Do", "Q"])
        return True


def _read_png_rgb(path):
    """Decode common 8-bit RGB/RGBA PNGs using only the Python standard library."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Expected PNG")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data[16:29])
    if depth != 8 or color not in (2, 6) or interlace != 0:
        raise ValueError("Only non-interlaced 8-bit RGB/RGBA PNGs are supported")
    pos, chunks = 8, []
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]
        payload = data[pos+8:pos+8+length]
        if kind == b"IDAT": chunks.append(payload)
        pos += 12 + length
        if kind == b"IEND": break
    bpp = 3 if color == 2 else 4
    scan = zlib.decompress(b"".join(chunks))
    stride = width*bpp
    rows, offset, previous = [], 0, bytearray(stride)
    for _ in range(height):
        mode = scan[offset]; offset += 1
        row = bytearray(scan[offset:offset+stride]); offset += stride
        for i in range(stride):
            left = row[i-bpp] if i >= bpp else 0
            up = previous[i]
            upper_left = previous[i-bpp] if i >= bpp else 0
            if mode == 1: row[i] = (row[i]+left)&255
            elif mode == 2: row[i] = (row[i]+up)&255
            elif mode == 3: row[i] = (row[i]+((left+up)//2))&255
            elif mode == 4:
                p = left+up-upper_left
                pa,pb,pc=abs(p-left),abs(p-up),abs(p-upper_left)
                predictor=left if pa<=pb and pa<=pc else up if pb<=pc else upper_left
                row[i]=(row[i]+predictor)&255
            elif mode != 0: raise ValueError("Unsupported PNG filter")
        rows.append(row); previous=row
    if color == 2: return width,height,b"".join(rows)
    rgb=bytearray(width*height*3); target=0
    for row in rows:
        for i in range(0,len(row),4):
            alpha=row[i+3]
            for channel in row[i:i+3]:
                rgb[target]=(channel*alpha+255*(255-alpha))//255; target+=1
    return width,height,bytes(rgb)


def _crop_rgb(pixels, width, height, x, y, crop_w, crop_h):
    if min(x,y,crop_w,crop_h)<0 or x+crop_w>width or y+crop_h>height:
        raise ValueError("PNG crop is outside the image")
    row_bytes=crop_w*3
    return b"".join(pixels[((y+line)*width+x)*3:((y+line)*width+x)*3+row_bytes] for line in range(crop_h))


def _wrap(value, width):
    return textwrap.wrap(str(value or ""), width=width, break_long_words=True, break_on_hyphens=False) or [""]


def _draw_party_detail(canvas, x, top, label, value, *, size=7.1, value_offset=62, width=48, leading=9):
    """Draw labels in a fixed column and values from one shared start position."""
    value = str(value or "Not provided")
    lines = _wrap(value, width)
    value_x = x + value_offset
    canvas.text(x, top, label + ":", size, False, INK)
    canvas.text(value_x, top, lines[0], size, False, INK)
    for offset, line in enumerate(lines[1:], 1):
        canvas.text(value_x, top + offset * leading, line, size, False, INK)
    return top + len(lines) * leading


def _money(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value or "0.00")


def render_charcoal_gold_pi(data, bank_details, *, logo_path=None, seal_path=None):
    """Render a one-page premium PI. Bank information is deliberately PI-only."""
    canvas = _Canvas()
    # Use the supplied logo in the header; omit the obscured body watermark.
    canvas.rect(0, 0, PAGE_W, PAGE_H, (1, 1, 1))

    # Header and document identity
    canvas.rect(0, 0, PAGE_W, 116, (1, 1, 1))
    canvas.rect(0, 116, PAGE_W, 3, BRAND_BLUE)
    has_logo = canvas.image(logo_path, 39, 5, 230, 106, watermark=False,
                            crop_box=(290, 145, 1190, 620))
    canvas.text(383, 48, "PROFORMA INVOICE", 15, True, NAVY)
    canvas.rect(383, 63, 190, 24, MID_BLUE)
    pi_number = str(data.get("document_number") or "DRAFT - TBD").strip()
    canvas.text(396, 79, "PI NO.  " + pi_number, 7, True, (0.90, 0.95, 0.99))

    canvas.text(40, 143, "PI NUMBER", 6.5, True, MUTED)
    canvas.text(40, 158, data.get("document_number") or "DRAFT", 9, True, INK)
    canvas.text(190, 143, "ISSUE DATE", 6.5, True, MUTED)
    canvas.text(190, 158, data.get("issue_date") or "TO CONFIRM", 8.5, True, INK)
    canvas.text(357, 143, "CURRENCY", 6.5, True, MUTED)
    canvas.text(357, 158, data.get("currency") or "USD", 8.5, True, INK)
    canvas.text(472, 143, "VALIDITY", 6.5, True, MUTED)
    canvas.text(472, 158, "TO CONFIRM", 7.5, True, WARNING)

    # Seller and buyer panels
    panel_top, panel_h = 174, 153
    canvas.rect(38, panel_top, 261, panel_h, (1, 1, 1), PALE, 0.8)
    canvas.rect(313, panel_top, 261, panel_h, (1, 1, 1), PALE, 0.8)
    canvas.line(38, panel_top, 299, panel_top, BRAND_BLUE, 1.4)
    canvas.line(313, panel_top, 574, panel_top, BRAND_BLUE, 1.4)
    seller = data.get("seller") or {}
    buyer = data.get("buyer") or {}
    canvas.text(50, 192, "SELLER", 6.8, True, BRAND_BLUE)
    canvas.text(50, 211, str(seller.get("legal_name") or "KE KOREA CO. LTD"), 9.5, True)
    seller_y = 227
    for label, value in (
        ("Address", seller.get("address")),
        ("Tel", seller.get("phone")),
        ("Email", seller.get("email")),
        ("Representative", re.sub(r"^\s*representative\s*:\s*", "", str(seller.get("contact") or "DAVID, SEOKWON IHM"), flags=re.I)),
    ):
        seller_y = _draw_party_detail(canvas, 50, seller_y, label, value)

    canvas.text(325, 192, "BUYER", 6.8, True, BRAND_BLUE)
    canvas.text(325, 211, str(buyer.get("legal_name") or "Not provided"), 9.5, True)
    buyer_y = 227
    for label, value in (
        ("Address", buyer.get("address")),
        ("Tel", buyer.get("phone")),
        ("Email", buyer.get("email")),
        ("Representative", buyer.get("contact")),
    ):
        buyer_y = _draw_party_detail(canvas, 325, buyer_y, label, value)
    if buyer.get("registration_details"):
        buyer_y = _draw_party_detail(canvas, 325, buyer_y, "Registration", buyer["registration_details"])

    # Trade terms
    terms_top = 340
    canvas.rect(38, terms_top, 536, 45, PALE)
    canvas.text(51, terms_top+14, "DELIVERY TERM", 6.2, True, MUTED)
    canvas.text(51, terms_top+31, data.get("incoterms") or "TO CONFIRM", 8, True)
    canvas.line(213, terms_top+8, 213, terms_top+37, (0.83,0.82,0.79), 0.6)
    canvas.text(229, terms_top+14, "PAYMENT", 6.2, True, MUTED)
    canvas.text(229, terms_top+31, data.get("payment_terms") or "TO CONFIRM", 7.6, True)
    canvas.line(394, terms_top+8, 394, terms_top+37, (0.83,0.82,0.79), 0.6)
    canvas.text(410, terms_top+14, "EST. CONTAINER LOAD", 6.2, True, MUTED)
    canvas.text(410, terms_top+31, "APPROX. 5", 8, True)

    # Item table
    table_top = 404
    canvas.text(38, table_top, "PRODUCT & PRICING", 7, True, BRAND_BLUE)
    canvas.rect(38, table_top+10, 536, 23, NAVY)
    for x, label in ((49,"DESCRIPTION"),(274,"QUANTITY"),(369,"UNIT PRICE"),(481,"AMOUNT")):
        canvas.text(x, table_top+25, label, 6.3, True, (1,1,1))
    canvas.rect(38, table_top+33, 536, 50, PALE)
    item = (data.get("items") or [{}])[0]
    canvas.text(49, table_top+53, item.get("product_name") or "M10R Yingfa Renhui Solar Cell", 8.2, True)
    canvas.text(49, table_top+70, "Cell type: M10R  |  Price basis: per Wp", 6.6, False, MUTED)
    canvas.text(274, table_top+54, "100 MW", 8, True)
    canvas.text(274, table_top+70, "100,000,000 Wp", 6.1, False, MUTED)
    canvas.text(369, table_top+54, "USD 0.047", 7.7, True)
    canvas.text(369, table_top+70, "per Wp", 6.1, False, MUTED)
    canvas.text(481, table_top+54, _money(data.get("total")), 7.3, True)
    canvas.text(481, table_top+70, "USD", 6.1, False, MUTED)

    # Totals and status notes
    total_top = 504
    canvas.text(38, total_top+14, "100 MW = 100,000,000 Wp", 7, False, MUTED)
    canvas.text(38, total_top+29, "FOUR MILLION SEVEN HUNDRED THOUSAND US DOLLARS ONLY", 7.3, True, INK)
    canvas.rect(360, total_top-2, 214, 49, NAVY)
    canvas.text(376, total_top+14, "TOTAL AMOUNT (USD)", 6.3, True, (0.73,0.87,0.98))
    canvas.text(376, total_top+35, _money(data.get("total")), 14, True, (1,1,1))

    warnings = data.get("conflicts") or data.get("missing_fields") or []
    warning_text = str(warnings[0]) if warnings else "Review all commercial and packing details before issue."
    if len(warning_text) > 92:
        warning_text = warning_text[:89] + "..."
    shipping_note = str(data.get("remarks") or "Confirm loading quantity against final packing specifications.")
    if len(shipping_note) > 92:
        shipping_note = shipping_note[:89] + "..."
    canvas.rect(38, 562, 536, 41, (1.0,0.97,0.94))
    canvas.rect(38, 562, 4, 41, WARNING)
    canvas.text(51, 576, "REVIEW REQUIRED BEFORE ISSUE", 6.3, True, WARNING)
    canvas.text(51, 589, warning_text, 6.0)
    canvas.text(51, 599, shipping_note, 6.0)

    # PI-only USD beneficiary details
    canvas.rect(38, 613, 340, 103, (1,1,1), PALE, 0.8)
    canvas.rect(38, 613, 340, 19, PALE)
    canvas.text(49, 627, "USD BANK INFORMATION", 6.5, True, BRAND_BLUE)
    labels = ["BENEFICIARY", "BANK NAME", "BRANCH NAME", "SWIFT CODE", "ACCOUNT NUMBER", "BANK ADDRESS"]
    keys = ["BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT", "ACCOUNT_NUMBER", "BANK_ADDRESS"]
    for i,(label,key) in enumerate(zip(labels,keys)):
        y=644+i*11
        canvas.text(49,y,label,5.7,True,MUTED)
        val = (bank_details or {}).get(key) or "[CONFIGURE BANK DETAILS]"
        if key == "ACCOUNT_NUMBER" and val != "[CONFIGURE BANK DETAILS]":
            val += " (USD)"
        canvas.text(156,y,val,6.0,key=="ACCOUNT_NUMBER",INK if key!="ACCOUNT_NUMBER" else WARNING)

    # Authorized representative and reserved company seal/logo image
    canvas.rect(392, 613, 182, 103, (1,1,1), PALE, 0.8)
    canvas.text(404, 630, "AUTHORIZED REPRESENTATIVE", 6.0, True, MUTED)
    canvas.text(404, 648, "DAVID, SEOKWON IHM", 7.5, True, INK)
    if not canvas.image(seal_path, 504, 657, 56, 54, watermark=False, crop_box=(748, 148, 120, 120)):
        canvas.rect(398, 654, 170, 58, None, BRAND_BLUE, 0.7)
        canvas.text(441, 686, "COMPANY SEAL", 6.2, True, BRAND_BLUE)

    canvas.line(38, 754, 574, 754, (0.86,0.85,0.82), 0.6)
    canvas.text(38, 770, "DRAFT - NOT FOR ISSUE  |  REVIEW ALL COMMERCIAL AND SHIPPING DETAILS", 6.0, False, MUTED)
    if not has_logo:
        canvas.text(455, 770, "LOGO ASSET PENDING", 5.5, True, BRAND_BLUE)

    # PDF object tree, including the image states used for embedded brand assets.
    image_count = len(canvas.images)
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [" + str(9+image_count).encode() + b" 0 R] /Count 1 >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
               b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H /DescendantFonts [6 0 R] >>",
               b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> /DW 1000 >>",
               b"<< /Type /ExtGState /ca 0.075 /CA 0.075 >>",
               b"<< /Type /ExtGState /ca 1 /CA 1 >>"]
    image_ids=[]
    for image in canvas.images:
        image_ids.append(len(objects)+1)
        raw=image["bytes"]
        objects.append(b"<< /Type /XObject /Subtype /Image /Width "+str(image["width"]).encode()+b" /Height "+str(image["height"]).encode()+b" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length "+str(len(raw)).encode()+b" >>\nstream\n"+raw+b"\nendstream")
    page_id=len(objects)+1
    content_id=page_id+1
    xobjects=" ".join(f"/Im{i+1} {oid} 0 R" for i,oid in enumerate(image_ids))
    resource=(f"<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> /ExtGState << /GS1 7 0 R /GS2 8 0 R >> /XObject << {xobjects} >> >>")
    objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources {resource} /Contents {content_id} 0 R >>".encode())
    stream=("\n".join(canvas.commands)+"\n").encode("ascii")
    objects.append(b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"endstream")
    output=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(output)); output.extend(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=len(output); output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: output.extend(f"{offset:010} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)
