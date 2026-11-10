"""Explicit provisional output, separate from the unchanged final export engine."""
import hashlib
import io
import re
from html import escape

from docx import Document
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table as PdfTable, TableStyle

from Quotation_KEKOREA.contracts.exports import _safe_name
from Quotation_KEKOREA.contracts.sale_scope_render import scope_display_items
from Quotation_KEKOREA.contracts.models import validate_snapshot
from Quotation_KEKOREA.contracts.review_summary import review_cards
from Quotation_KEKOREA.contracts.rules import validate_snapshot as validate_rules


def export_draft(snapshot, *, formats=('docx', 'pdf'), env=None):
    snapshot = validate_snapshot(snapshot)
    if not any(c.get('sentences') for c in snapshot['clauses']):
        raise ValueError('실제 조항이 있는 계약서 초안이 필요합니다.')
    if not set(formats).issubset({'pdf', 'docx'}):
        raise ValueError('지원하지 않는 초안 형식입니다.')
    korean = snapshot['language'] == 'ko'
    label = 'DRAFT / 검토용' if korean else 'DRAFT / FOR REVIEW'
    # Export only the authored clauses. Review issues stay inside BOX 2/the review panel.
    # Never inject [확인 필요] or append audit data to the contract document.
    lines = [(snapshot.get('title') or 'Contract', True)]
    for clause in sorted(snapshot['clauses'], key=lambda c: c.get('order', 0)):
        lines.append((clause.get('title') or '', True))
        sentences = clause.get('sentences', [])
        if any(sentence.get('sale_spec_field') for sentence in sentences):
            for kind, value in scope_display_items(sentences, snapshot['language']):
                lines.append((value, 'table' if kind == 'table' else False))
        else:
            for sentence in sentences:
                lines.append((sentence['text'], False))
    result = {}
    for extension in formats:
        content = _draft_docx(lines, label) if extension == 'docx' else _draft_pdf(lines, label, korean)
        result[extension] = {
            'filename': f"{_safe_name(snapshot)}-DRAFT-r{snapshot['revision']}.{extension}",
            'content': content, 'sha256': hashlib.sha256(content).hexdigest(),
            'revision': snapshot['revision'],
        }
    return result


def _draft_docx(lines, label):
    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(.8)
    section.header.paragraphs[0].text = label + ' · NOT FOR SIGNATURE'
    document.styles['Normal'].font.name = 'Malgun Gothic'
    document.styles['Normal'].font.size = Pt(10)
    for text, heading in lines:
        if heading == 'table':
            table = document.add_table(rows=0, cols=2)
            table.style = 'Table Grid'
            for field, value in text:
                row = table.add_row()
                row.cells[0].text = field
                row.cells[1].text = value
                row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            continue
        paragraph = document.add_heading(text, level=2) if heading else document.add_paragraph(text)
        paragraph.paragraph_format.space_after = Pt(8)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _draft_pdf(lines, label, korean):
    # Original evidence stays in its source language, even in an English draft.
    needs_korean = korean or any(
        re.search(r'[\uac00-\ud7a3]', str(value))
        for text, kind in lines
        for value in ([cell for row in text for cell in row] if kind == 'table' else [text])
    )
    font = 'HYGothic-Medium' if needs_korean else 'Helvetica'
    if needs_korean:
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    body = ParagraphStyle('DraftBody', fontName=font, fontSize=9.5, leading=16, spaceAfter=8)
    heading = ParagraphStyle('DraftHeading', parent=body, fontSize=12, leading=19,
                             spaceBefore=14, keepWithNext=True)
    story = []
    for text, is_heading in lines:
        if is_heading == 'table':
            table = PdfTable(
                [[Paragraph(escape(field), body), Paragraph(escape(value), body)]
                 for field, value in text], colWidths=[130, 355], hAlign='LEFT')
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#b8bec5')),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f2f4f6')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 9),
                ('RIGHTPADDING', (0, 0), (-1, -1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(table)
        else:
            story.append(Paragraph(escape(text).replace('\n', '<br/>'),
                                   heading if is_heading else body) if text else Spacer(1, 8))
    output = io.BytesIO()
    def watermark(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#dee3e8'))
        canvas.setFont('Helvetica', 68)
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(40)
        canvas.drawCentredString(0, 0, 'DRAFT')
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont(font, 9)
        canvas.drawString(50, A4[1] - 30, label + ' · NOT FOR SIGNATURE')
        canvas.drawCentredString(A4[0] / 2, 22, str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(output, pagesize=A4, topMargin=55, bottomMargin=45,
                      leftMargin=55, rightMargin=55).build(story, onFirstPage=watermark, onLaterPages=watermark)
    return output.getvalue()
