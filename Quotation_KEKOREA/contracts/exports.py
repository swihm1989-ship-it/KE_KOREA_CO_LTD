"""Contract-only DOCX and PDF exports from an approved snapshot."""
import hashlib
import io
from html import escape
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from pathlib import Path
from reportlab.platypus import Image as PdfImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
)


def _plain_lines(snapshot):
    lines = [snapshot.get("title") or "Contract", ""]
    for clause in sorted(snapshot.get("clauses", []), key=lambda item: item.get("order", 0)):
        lines.append(clause.get("title") or "")
        lines.extend(sentence["text"] for sentence in clause.get("sentences", []))
        lines.append("")
    lines.extend(["SIGNATURES", ""])
    for party in snapshot.get("parties", []):
        role = ", ".join(party.get("roles", []))
        lines.extend([f"{party.get('legal_name') or role}", "By: ______________________________",
                      "Name / Title: _____________________", "Date: ____________________________", ""])
    return lines


def _docx(snapshot, seal_bytes=None):
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)
    normal = document.styles["Normal"]
    normal.font.name = "Malgun Gothic" if snapshot.get("language") == "ko" else "Arial"
    normal.font.size = Pt(10)
    title = document.add_heading(snapshot.get("title") or "Contract", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for clause in sorted(snapshot.get("clauses", []), key=lambda item: item.get("order", 0)):
        heading = document.add_heading(clause.get("title") or "", level=2)
        heading.paragraph_format.keep_with_next = True
        for sentence in clause.get("sentences", []):
            paragraph = document.add_paragraph(sentence["text"])
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.widow_control = True
    if _has_authored_signature_clause(snapshot):
        if seal_bytes is not None:
            document.add_picture(io.BytesIO(seal_bytes), width=Inches(1.1))
    else:
        document.add_page_break()
        document.add_heading("서명" if snapshot.get("language") == "ko" else "SIGNATURES", level=1)
        for party in snapshot.get("parties", []):
            roles = ", ".join(party.get("roles", []))
            document.add_heading(party.get("legal_name") or roles, level=2)
            if seal_bytes is not None and _is_ke_korea_party(party):
                document.add_picture(io.BytesIO(seal_bytes), width=Inches(1.1))
            document.add_paragraph("By: __________________________________")
            document.add_paragraph("Name / Title: __________________________")
            document.add_paragraph("Date: __________________________________")
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf(snapshot, seal_bytes=None):
    font_name = "Helvetica"
    if snapshot.get("language") == "ko":
        font_name = "HYGothic-Medium"
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ContractTitle", parent=styles["Title"], fontName=font_name,
                                 fontSize=16, leading=22, alignment=TA_CENTER, spaceAfter=24)
    heading_style = ParagraphStyle("ContractHeading", parent=styles["Heading2"], fontName=font_name,
                                   fontSize=11, leading=16, textColor=colors.HexColor("#092b4c"),
                                   spaceBefore=12, spaceAfter=6, keepWithNext=True)
    body_style = ParagraphStyle("ContractBody", parent=styles["BodyText"], fontName=font_name,
                                fontSize=9.5, leading=15, spaceAfter=7, splitLongWords=True)
    story = [Paragraph(escape(snapshot.get("title") or "Contract"), title_style)]
    for clause in sorted(snapshot.get("clauses", []), key=lambda item: item.get("order", 0)):
        heading = Paragraph(escape(clause.get("title") or ""), heading_style)
        sentences = [Paragraph(escape(sentence["text"]).replace("\n", "<br/>"), body_style)
                     for sentence in clause.get("sentences", [])]
        if sentences:
            story.append(KeepTogether([heading, sentences[0]]))
            story.extend(sentences[1:])
        else:
            story.append(heading)
    if _has_authored_signature_clause(snapshot):
        if seal_bytes is not None:
            stamp = PdfImage(io.BytesIO(seal_bytes))
            stamp.drawHeight = 68
            stamp.drawWidth = 68 * stamp.imageWidth / stamp.imageHeight
            story.append(stamp)
    else:
        story.append(PageBreak())
        story.append(Paragraph("서명" if snapshot.get("language") == "ko" else "SIGNATURES",
                               heading_style))
        for party in snapshot.get("parties", []):
            label = party.get("legal_name") or ", ".join(party.get("roles", []))
            story.append(Paragraph(escape(label), heading_style))
            if seal_bytes is not None and _is_ke_korea_party(party):
                stamp = PdfImage(io.BytesIO(seal_bytes))
                stamp.drawHeight = 68
                stamp.drawWidth = 68 * stamp.imageWidth / stamp.imageHeight
                story.append(stamp)
            story.extend([Paragraph("By: __________________________________", body_style),
                          Paragraph("Name / Title: __________________________", body_style),
                          Paragraph("Date: __________________________________", body_style), Spacer(1, 16)])
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
