"""Contract-only DOCX and PDF exports from an approved snapshot."""
import hashlib
import io
from html import escape
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, Cm
from pathlib import Path
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Table as PdfTable, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
)


from Quotation_KEKOREA.contracts.sale_scope_render import scope_display_items
from Quotation_KEKOREA.contracts.signature_layout import (
    authored_clauses_for_final, signature_blocks,
)

def _pdf_font_pair():
    # Malgun Gothic can be supplied by the host OS; never bundle licensed fonts.
    regulars = ["/usr/share/fonts/truetype/malgun.ttf",
                "C:/Windows/Fonts/malgun.ttf",
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]
    bolds = ["/usr/share/fonts/truetype/malgunbd.ttf",
             "C:/Windows/Fonts/malgunbd.ttf",
             "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"]
    for regular, bold in zip(regulars, bolds):
        if Path(regular).is_file() and Path(bold).is_file():
            pdfmetrics.registerFont(TTFont("ContractBodyFont", regular))
            pdfmetrics.registerFont(TTFont("ContractBoldFont", bold))
            return "ContractBodyFont", "ContractBoldFont"
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    return "HYGothic-Medium", "HYGothic-Medium"


def _stamp_width_height(image, target_width=283.46, max_height=115):
    width = target_width
    height = width * image.imageHeight / image.imageWidth
    if height > max_height:
        width *= max_height / height
        height = max_height
    return width, height


def _setup_docx_fonts(document):
    from docx.oxml.ns import qn
    for name, size, bold in (("Normal", 10, False), ("Title", 18, True),
                             ("Heading 1", 18, True), ("Heading 2", 12, True)):
        style = document.styles[name]
        style.font.name = "Malgun Gothic"
        style.font.size = Pt(size)
        style.font.bold = bold
        rpr = style.element.get_or_add_rPr()
        fonts = rpr.rFonts
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.insert(0, fonts)
        for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            fonts.set(qn(attribute), "Malgun Gothic")


def _plain_lines(snapshot):
    lines = [snapshot.get("title") or "Contract", ""]
    for title, sentences in authored_clauses_for_final(snapshot):
        if title:
            lines.append(title)
        lines.extend(sentence["text"] for sentence in sentences)
        lines.append("")
    lines.extend(["SIGNATURES", ""])
    for block in signature_blocks(snapshot):
        lines.extend([f"{block['label']} - Company: {block['company']}",
                      f"Name / Title: {block['name_title']}",
                      f"Date: {block['date']}", "Signature: __________________", ""])
    return lines


def _docx_signature_section(document, snapshot, seal_bytes):
    """Keep both signers together, and place the authorized seal on its signature row."""
    heading = document.add_heading("서명" if snapshot.get("language") == "ko" else "SIGNATURES", level=1)
    heading.paragraph_format.keep_with_next = True
    heading.paragraph_format.space_before = Pt(18)
    heading.paragraph_format.space_after = Pt(14)
    blocks = signature_blocks(snapshot)
    table = document.add_table(rows=0, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(6.25)
    table.columns[1].width = Cm(10.0)
    content_rows = []
    for index, block in enumerate(blocks):
        if index:
            row = table.add_row()
            row.cells[0].text = " "
            row.cells[1].text = ""
            content_rows.append(row)
        label_row = table.add_row()
        label_row.cells[0].text = block['label']
        for para in label_row.cells[0].paragraphs:
            para.style = document.styles['Heading 2']
        content_rows.append(label_row)
        fields = (
            ("Company", block['company']), ("Name / Title", block['name_title']),
            ("Date", block['date']), ("Signature", "________________________")
        )
        for field, value in fields:
            row = table.add_row()
            row.cells[0].text = f"{field}: {value}"
            row.cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            row.cells[1].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if field == "Signature" and seal_bytes is not None and _is_ke_korea_party(block['party']):
                row.cells[1].paragraphs[0].add_run().add_picture(
                    io.BytesIO(seal_bytes), width=Cm(10.0))
            content_rows.append(row)
    for index, row in enumerate(content_rows):
        row_pr = row._tr.get_or_add_trPr()
        row_pr.append(OxmlElement('w:cantSplit'))
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(5)
                paragraph.paragraph_format.keep_with_next = index < len(content_rows) - 1


def _docx(snapshot, seal_bytes=None):
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)
    _setup_docx_fonts(document)
    title = document.add_paragraph(snapshot.get("title") or "Contract", style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(20)
    for title, sentences in authored_clauses_for_final(snapshot):
        if title:
            heading = document.add_heading(title, level=2)
            heading.paragraph_format.keep_with_next = True
        entries = (scope_display_items(sentences, snapshot.get("language", "en"))
                   if any(item.get("sale_spec_field") for item in sentences)
                   else [("paragraph", item["text"]) for item in sentences])
        for kind, data in entries:
            if kind == "table":
                table = document.add_table(rows=0, cols=2)
                table.style = "Table Grid"
                table.autofit = False
                table.columns[0].width = Cm(4)
                table.columns[1].width = Cm(11)
                for label, value in data:
                    row = table.add_row()
                    row.cells[0].text = label
                    row.cells[1].text = value
                    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
                document.add_paragraph().paragraph_format.space_after = Pt(3)
            else:
                paragraph = document.add_paragraph(data)
                paragraph.paragraph_format.space_after = Pt(9)
                paragraph.paragraph_format.line_spacing = 1.55
                paragraph.paragraph_format.widow_control = True
    _docx_signature_section(document, snapshot, seal_bytes)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf_signature_section(snapshot, heading_style, body_style, seal_bytes):
    """Flowable signature section; use current page if it all fits, else next."""
    blocks = signature_blocks(snapshot)
    signature_style = ParagraphStyle(
        "ContractSignatures", parent=heading_style, fontSize=18, leading=25,
        spaceBefore=16, spaceAfter=14,
    )
    label_style = ParagraphStyle(
        "ContractSignerLabel", parent=heading_style, fontSize=12, leading=18,
        spaceBefore=8, spaceAfter=8,
    )
    section = [Paragraph("서명" if snapshot.get("language") == "ko" else "SIGNATURES",
                         signature_style)]
    for index, block in enumerate(blocks):
        if index:
            section.append(Spacer(1, 14))
        section.append(Paragraph(escape(block['label']), label_style))
        for field, value in (
            ("Company", block['company']), ("Name / Title", block['name_title']),
            ("Date", block['date'])
        ):
            section.append(Paragraph(escape(f"{field}: {value}"), body_style))
        stamp = ""
        if seal_bytes is not None and _is_ke_korea_party(block['party']):
            stamp = PdfImage(io.BytesIO(seal_bytes))
            stamp.drawWidth, stamp.drawHeight = _stamp_width_height(stamp)
            stamp.hAlign = 'LEFT'
        signature = PdfTable(
            [[Paragraph("Signature: __________________________", body_style), stamp]],
            colWidths=[155, 315], hAlign='LEFT')
        signature.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        section.append(signature)
    return KeepTogether(section)


def _pdf(snapshot, seal_bytes=None):
    font_name, bold_font = _pdf_font_pair()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ContractTitle", parent=styles["Title"], fontName=bold_font,
                                 fontSize=18, leading=26, alignment=TA_CENTER, spaceAfter=22)
    heading_style = ParagraphStyle("ContractHeading", parent=styles["Heading2"], fontName=bold_font,
                                   fontSize=12, leading=19, textColor=colors.black,
                                   spaceBefore=16, spaceAfter=9, keepWithNext=True)
    body_style = ParagraphStyle("ContractBody", parent=styles["BodyText"], fontName=font_name,
                                fontSize=10, leading=17, spaceAfter=10, splitLongWords=True)
    story = [Paragraph(escape(snapshot.get("title") or "Contract"), title_style)]
    for title, authored_sentences in authored_clauses_for_final(snapshot):
        entries = (scope_display_items(authored_sentences, snapshot.get("language", "en"))
                   if any(item.get("sale_spec_field") for item in authored_sentences)
                   else [("paragraph", item["text"]) for item in authored_sentences])
        rendered = []
        for kind, data in entries:
            if kind == "table":
                table = PdfTable(
                    [[Paragraph(escape(label), body_style),
                      Paragraph(escape(value).replace("\n", "<br/>"), body_style)]
                     for label, value in data],
                    colWidths=[130, 355], hAlign="LEFT", repeatRows=0)
                table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8bec5")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f4f6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                rendered.append(table)
            else:
                rendered.append(Paragraph(escape(data).replace("\n", "<br/>"), body_style))
        if title:
            heading = Paragraph(escape(title), heading_style)
            if rendered:
                story.append(KeepTogether([heading, rendered[0]]))
                story.extend(rendered[1:])
            else:
                story.append(heading)
        else:
            story.extend(rendered)
    story.append(Spacer(1, 12))
    story.append(_pdf_signature_section(snapshot, heading_style, body_style, seal_bytes))
    output = io.BytesIO()
    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.drawCentredString(A4[0] / 2, 20, str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(output, pagesize=A4, rightMargin=55, leftMargin=55,
                      topMargin=55, bottomMargin=45, title=snapshot.get("title") or "Contract").build(
                          story, onFirstPage=page_footer, onLaterPages=page_footer)
    return output.getvalue()


def export_contract(snapshot, *, formats=("docx", "pdf"), seal_bytes=None):
    if not snapshot.get("clauses"):
        raise ValueError("A contract draft is required before export.")
    result = {}
    for file_format in formats:
        if file_format == "docx":
            content = _docx(snapshot, seal_bytes=seal_bytes)
        elif file_format == "pdf":
            content = _pdf(snapshot, seal_bytes=seal_bytes)
        else:
            raise ValueError(f"Unsupported contract export format: {file_format}")
        result[file_format] = {
            "filename": _safe_name(snapshot) + f"-r{snapshot.get('revision', 1)}.{file_format}",
            "content": content,
            "sha256": hashlib.sha256(content).hexdigest(),
            "revision": snapshot.get("revision", 1),
        }
    return result


def _safe_name(snapshot):
    value = re.sub(r"[^\w-]+", "-", str(snapshot.get("title") or "contract").strip(), flags=re.UNICODE)
    return value.strip("-")[:80] or "contract"


def _has_authored_signature_clause(snapshot):
    titles = {'서명', '서명란', 'signatures', 'signature', 'signing'}
    return any(str(c.get('title') or '').strip().casefold() in titles
               for c in snapshot.get('clauses', []))

def _is_ke_korea_party(party):
    """Never place KE KOREA's company seal on another signatory."""
    name = re.sub(r'[^a-z0-9]', '', str(party.get('legal_name') or '').casefold())
    return name in {'kekorea', 'kekorealtd', 'kekoreacoltd', 'kekoreacolimited'}
