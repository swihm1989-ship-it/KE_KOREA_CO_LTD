"""Explicit provisional output, separate from the unchanged final export engine."""
import hashlib
import io
import re
from html import escape

from docx import Document
from docx.shared import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from Quotation_KEKOREA.contracts.exports import _safe_name
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
    notice = ('서명용이 아닙니다. 본문은 미확정 제안을 포함하며, 아래 부록과 함께 검토해야 합니다.'
              if korean else 'NOT FOR SIGNATURE. Text may contain unconfirmed proposals; read with the unresolved-items appendix.')
    issues = validate_rules(snapshot, for_export=True, env=env)
    cards = review_cards(issues, language=snapshot['language'])
    lines = [(snapshot.get('title') or 'Contract', True), (notice, False)]
    term_map = {}
    for term in snapshot.get('terms', []):
        for identifier in (term.get('key'), term.get('id')):
            if identifier:
                term_map[str(identifier)] = term
    for clause in sorted(snapshot['clauses'], key=lambda c: c.get('order', 0)):
        lines.append((clause.get('title') or '', True))
        for sentence in clause.get('sentences', []):
            # Scope markers to directly linked, unconfirmed terms only. All other
            # unresolved concerns remain in the complete appendix and DRAFT notice.
            linked = [term_map.get(str(identifier)) for identifier in sentence.get('term_ids', [])]
            unresolved = any(term is None or term.get('status') != 'confirmed'
                             or not str(term.get('value') or '').strip() for term in linked)
            raw_text = sentence['text']
            already_marked = ('[서명 전 확인]' in raw_text or '[확인 필요]' in raw_text
                              or '[TBD' in raw_text or '[TO CONFIRM]' in raw_text)
            prefix = ('[확인 필요] ' if korean else '[TBD / UNCONFIRMED] ') if unresolved and not already_marked else ''
            lines.append((prefix + raw_text, False))
    lines.append(('미확정 사항 부록 / TBD' if korean else 'Unresolved items / TBD', True))
    if cards:
        for card in cards:
            lines.append((f"[{card['kind']}] {card['summary']}", False))
        lines.append(('구조화된 조건과 원문 쟁점은 앱의 BOX 2 및 상세 근거에서 확인하세요. '
                      '이 요약은 법률 검토 완료나 사용자 확정을 뜻하지 않습니다.' if korean else
                      'Review the structured terms and original findings in BOX 2. This summary is not confirmation or legal certification.', False))
        # Retain exact issue evidence in the appendix, never translate or certify it.
        for issue in issues:
            raw = str(issue.get('message') or issue.get('key') or '')
            lines.append((('[미확정 원문] ' if korean else '[UNCONFIRMED SOURCE] ') + raw, False))
    else:
        lines.append(('자동 검사상 미확정 항목 없음. 이 출력은 계속 검토용입니다.' if korean else
                      'No outstanding automatic checks; this output remains a review draft.', False))
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
        paragraph = document.add_heading(text, level=2) if heading else document.add_paragraph(text)
        paragraph.paragraph_format.space_after = Pt(8)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _draft_pdf(lines, label, korean):
    # Original evidence stays in its source language, even in an English draft.
    needs_korean = korean or any(re.search(r'[\uac00-\ud7a3]', text) for text, _ in lines)
    font = 'HYGothic-Medium' if needs_korean else 'Helvetica'
    if needs_korean:
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    body = ParagraphStyle('DraftBody', fontName=font, fontSize=9.5, leading=16, spaceAfter=8)
    heading = ParagraphStyle('DraftHeading', parent=body, fontSize=12, leading=19,
                             spaceBefore=14, keepWithNext=True)
    story = [Paragraph(escape(text).replace('\n', '<br/>'), heading if is_heading else body)
             if text else Spacer(1, 8) for text, is_heading in lines]
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
