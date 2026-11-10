"""Tests for contract-only drafts and explicitly authorized final output."""
import base64
import io
import unittest
from zipfile import ZipFile

from docx import Document
from datetime import datetime, timezone
import fitz
from Quotation_KEKOREA.contracts.draft_exports import export_draft
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.final_policy import final_document_blockers


# Test-only PNG, not the real company seal.
TEST_STAMP = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFklEQVR4nGP8z8DwnwEPYMInOXwUAAASWwIOH0pJXQAAAABJRU5ErkJggg==')


def sample(text='월 인도 일정은 서면 합의로 결정한다.'):
    return {
        'contract_id':'test','revision':1,'contract_type':'sale','language':'ko',
        'title':'공급 계약서',
        'clauses':[{'id':'c1','order':1,'title':'인도 및 일정',
                    'sentences':[{'id':'s1','text':text,'term_ids':[],'source_refs':[]}]}],
        'terms':[], 'issues':[],
        'parties':[{'legal_name':'KE KOREA CO. LTD','roles':['seller']},
                   {'legal_name':'OCI Co. Ltd.','roles':['buyer']}],
    }


class CleanContractExportTests(unittest.TestCase):
    def test_draft_contains_only_authored_terms_no_audit_appendix(self):
        data=export_draft(sample(),formats=('docx',))['docx']['content']
        doc=Document(io.BytesIO(data))
        body='\n'.join(p.text for p in doc.paragraphs)
        self.assertIn('월 인도 일정은 서면 합의로 결정한다.',body)
        self.assertNotIn('미확정 사항 부록',body)
        self.assertNotIn('[미확정 원문]',body)
        self.assertNotIn('[확인 필요]',body)

    def test_final_can_be_prepared_with_missing_structured_details(self):
        self.assertEqual(final_document_blockers(sample()),[])

    def test_final_blocks_authored_placeholder_without_silently_deleting(self):
        errors=final_document_blockers(sample('월 인도일은 [서명 전 확인]으로 한다.'))
        self.assertTrue(errors)
        colon = final_document_blockers(sample('[서명 전 확인: 배상 한도는 양 당사자가 서면 합의한다.]'))
        self.assertTrue(colon)
        self.assertEqual(final_document_blockers(
            sample('[서명 전 확인: 배상 한도는 양 당사자가 서면 합의한다.]'),
            allow_unresolved_text=True), [])

    def test_user_may_explicitly_export_unresolved_authored_text(self):
        original = sample('배상 한도는 [서명 전 확인]으로 한다.')
        self.assertTrue(final_document_blockers(original))
        self.assertEqual(final_document_blockers(original, allow_unresolved_text=True), [])
        # The opt-in never silently deletes or resolves the authored wording.
        docx = export_contract(original, formats=('docx',))['docx']['content']
        body = '\\n'.join(p.text for p in Document(io.BytesIO(docx)).paragraphs)
        self.assertIn('[서명 전 확인]', body)

    def test_opt_in_does_not_bypass_signatories_or_reconciliation(self):
        original = sample('손해배상 한도는 [서명 전 확인]으로 한다.')
        original['parties'] = [{'legal_name': 'Unknown', 'roles': ['seller']}]
        original['pending_reconciliation'] = {'changes': ['pending']}
        problems = final_document_blockers(original, allow_unresolved_text=True)
        self.assertTrue(any('본문 반영' in msg for msg in problems))
        self.assertTrue(any('KE KOREA' in msg for msg in problems))
        self.assertTrue(any('매도인·매수인' in msg for msg in problems))

    def test_final_docx_places_only_one_stamp_on_ke_korea_party(self):
        result=export_contract(sample(),formats=('docx',),seal_bytes=TEST_STAMP)
        data=result['docx']['content']
        with ZipFile(io.BytesIO(data)) as z:
            pictures=[name for name in z.namelist() if name.startswith('word/media/')]
        self.assertEqual(len(pictures),1)

    def test_signature_fields_inline_seal_and_no_duplicate_body_summary(self):
        original = sample()
        original['language'] = 'en'
        original['title'] = 'Cell Supply'
        original['created_at'] = '2026-11-10T08:31:00+09:00'
        original['parties'][0].update(representative='SEOKWON IHM', representative_title='CEO')
        original['parties'][1].update(legal_name='TENGYAO TECHNOLOGY CO. LTD',
                                      representative='ALEX', representative_title='CEO')
        original['clauses'][0]['sentences'].extend([
            {'id': 'sig_s', 'text': 'Supplier: KE KOREA CO. LTD, Representative: SEOKWON IHM, Signature: [signature].'},
            {'id': 'sig_b', 'text': 'Buyer: TENGYAO TECHNOLOGY CO. LTD, Representative: ALEX, Signature: [signature].'},
        ])
        original['clauses'][0]['sentences'].append({
            'id': 'normal', 'text': 'Supplier: KE KOREA shall deliver the goods by December 31.'
        })
        outputs = export_contract(original, seal_bytes=TEST_STAMP)
        document = Document(io.BytesIO(outputs['docx']['content']))
        texts = '\\n'.join(p.text for p in document.paragraphs)
        cell_text = '\\n'.join(cell.text for table in document.tables
                               for row in table.rows for cell in row.cells)
        self.assertNotIn('Representative: SEOKWON IHM, Signature:', texts)
        self.assertIn('Supplier: KE KOREA shall deliver the goods', texts)
        self.assertNotIn('By:', cell_text)
        self.assertIn('Company: KE KOREA CO. LTD', cell_text)
        self.assertIn('Company: TENGYAO TECHNOLOGY CO. LTD', cell_text)
        self.assertIn('Name / Title: SEOKWON IHM, Chief Executive Officer', cell_text)
        self.assertIn('Name / Title: ALEX, Chief Executive Officer', cell_text)
        self.assertEqual(cell_text.count('Date: 2026-11-10'), 2)
        with fitz.open(stream=outputs['pdf']['content'], filetype='pdf') as pdf:
            page_text = [page.get_text() for page in pdf]
            joined = '\\n'.join(page_text)
            self.assertNotIn('Representative: SEOKWON IHM, Signature:', joined)
            self.assertEqual(joined.count('SIGNATURES'), 1)
            self.assertEqual(joined.count('Date: 2026-11-10'), 2)
            self.assertNotIn('By:', joined)
            self.assertIn('Name / Title: ALEX, Chief Executive Officer', joined)
            signature_page = next(i for i, text in enumerate(page_text) if 'SIGNATURES' in text)
            self.assertIn('Company: TENGYAO TECHNOLOGY CO. LTD', page_text[signature_page])
            self.assertIn('Company: KE KOREA CO. LTD', page_text[signature_page])
            self.assertEqual(sum(len(page.get_images()) for page in pdf), 1)

    def test_missing_signatory_details_remain_blank_not_tbd(self):
        original = sample()
        original['language'] = 'en'
        original['created_at'] = '2026-11-10'
        original['parties'][1]['representative'] = ''
        with fitz.open(stream=export_contract(original, formats=('pdf',))['pdf']['content'],
                       filetype='pdf') as pdf:
            text = '\\n'.join(page.get_text() for page in pdf)
            self.assertIn('Name / Title:', text)
            self.assertNotIn('TBD', text)
            self.assertNotIn('By:', text)
            self.assertIn('Date: 2026-11-10', text)

    def test_date_resolver_prioritizes_contract_date_and_does_not_use_effective_date(self):
        from Quotation_KEKOREA.contracts.signature_layout import contract_signature_date
        original = sample()
        original['created_at'] = '2026-11-10'
        original['terms'] = [
            {'key': 'effective_date', 'value': '2027-01-01'},
            {'key': 'contract_date', 'value': '2026-11-09'},
        ]
        self.assertEqual(contract_signature_date(original), '2026-11-09')
        original['terms'].pop()
        self.assertEqual(contract_signature_date(original), '2026-11-10')

    def test_signature_section_uses_current_page_when_it_fits_and_moves_together(self):
        original = sample()
        original['language'] = 'en'
        original['created_at'] = '2026-11-10'
        with fitz.open(stream=export_contract(original, formats=('pdf',))['pdf']['content'],
                       filetype='pdf') as pdf:
            self.assertEqual(len(pdf), 1, 'Short contract should not waste signature-only page')
        long_contract = sample('This is the final contract wording. ' * 250)
        long_contract['language'] = 'en'
        long_contract['created_at'] = '2026-11-10'
        with fitz.open(stream=export_contract(long_contract, formats=('pdf',))['pdf']['content'],
                       filetype='pdf') as pdf:
            signature_pages = [i for i,page in enumerate(pdf) if 'SIGNATURES' in page.get_text()]
            self.assertEqual(len(signature_pages), 1)
            text = pdf[signature_pages[0]].get_text()
            self.assertEqual(text.count('Company:'), 2)
            self.assertEqual(text.count('Signature:'), 2)

    def test_korean_buyer_summary_is_excluded_but_actual_terms_remain(self):
        data = sample("구매자: TENGYAO TECHNOLOGY CO. LTD, 대표자: ALEX, 서명: [서명].")
        data['clauses'][0]['sentences'].append({
            'id': 'business',
            'text': '구매자는 2026년 12월 31일까지 물품을 인수한다.'
        })
        exported = export_contract(data, formats=('docx','pdf'))
        document = Document(io.BytesIO(exported['docx']['content']))
        doc_text = '\\n'.join(p.text for p in document.paragraphs)
        self.assertNotIn('대표자: ALEX, 서명: [서명]', doc_text)
        self.assertIn('2026년 12월 31일까지', doc_text)
        with fitz.open(stream=exported['pdf']['content'], filetype='pdf') as pdf:
            text = '\\n'.join(p.get_text() for p in pdf)
            self.assertNotIn('대표자: ALEX, 서명: [서명]', text)
            self.assertIn('2026년 12월 31일까지', text)

    def test_contract_fonts_and_seal_print_dimensions(self):
        from Quotation_KEKOREA.contracts.exports import _stamp_width_height
        import base64
        from PIL import Image
        stamp_stream = io.BytesIO()
        Image.new('RGB', (1000, 400), 'white').save(stamp_stream, format='PNG')
        realistic_stamp = stamp_stream.getvalue()
        original = sample('The supplier agrees to deliver goods.')
        original['language'] = 'en'
        original['title'] = 'Solar Supply Agreement'
        document = Document(io.BytesIO(
            export_contract(original, formats=('docx',), seal_bytes=realistic_stamp)['docx']['content'
        ]))
        for name, size, bold in [('Normal', 10, False), ('Title', 18, True),
                                 ('Heading 2', 12, True)]:
            style = document.styles[name]
            self.assertEqual(style.font.name, 'Malgun Gothic')
            self.assertEqual(style.font.size.pt, size)
            self.assertEqual(style.font.bold, bold)
        self.assertAlmostEqual(document.inline_shapes[0].width.cm, 10, places=1)
        self.assertAlmostEqual(document.tables[0].columns[1].width.cm, 10, places=1)
        with fitz.open(stream=export_contract(
            original, formats=('pdf',), seal_bytes=realistic_stamp)['pdf']['content'
        ], filetype='pdf') as pdf:
            text_spans = [s for page in pdf for b in page.get_text('dict')['blocks']
                          if 'lines' in b for line in b['lines'] for s in line['spans']]
            title = next(s for s in text_spans if 'Solar Supply Agreement' in s['text'])
            body = next(s for s in text_spans if 'The supplier agrees' in s['text'])
            self.assertAlmostEqual(title['size'], 18, delta=0.2)
            self.assertAlmostEqual(body['size'], 10, delta=0.2)
            img_rects = [rect for page in pdf for img in page.get_images(full=True)
                         for rect in page.get_image_rects(img[0])]
            self.assertEqual(len(img_rects), 1)
            self.assertAlmostEqual(img_rects[0].width * 2.54 / 72, 10, delta=0.2)

    def test_polished_contract_headings_and_signature_labels(self):
        contract = sample('납품 조건은 계약서에 명시된 내용을 따른다.')
        contract['created_at'] = '2026-11-10'
        contract['parties'][0]['representative'] = 'SEOKWON IHM'
        contract['parties'][1]['representative'] = 'ALEX'
        outputs = export_contract(contract, formats=('pdf', 'docx'))
        docx = Document(io.BytesIO(outputs['docx']['content']))
        self.assertEqual(docx.styles['Heading 1'].font.size.pt, 18)
        self.assertTrue(docx.styles['Heading 1'].font.bold)
        self.assertEqual(docx.styles['Heading 2'].font.size.pt, 12)
        self.assertEqual(docx.styles['Normal'].font.size.pt, 10)
        self.assertTrue(any(p.style.name == 'Heading 2' and p.text == 'Supplier'
                            for row in docx.tables[0].rows for cell in row.cells
                            for p in cell.paragraphs))
        self.assertTrue(any(p.style.name == 'Heading 2' and p.text == 'Buyer'
                            for row in docx.tables[0].rows for cell in row.cells
                            for p in cell.paragraphs))
        with fitz.open(stream=outputs['pdf']['content'], filetype='pdf') as pdf:
            spans = [sp for page in pdf for block in page.get_text('dict')['blocks']
                     if 'lines' in block for ln in block['lines'] for sp in ln['spans']]
            self.assertTrue(any(sp['text'] == 'Supplier' and abs(sp['size'] - 12) < .2
                                for sp in spans))
            self.assertTrue(any(sp['text'] == 'Buyer' and abs(sp['size'] - 12) < .2
                                for sp in spans))
            self.assertEqual(sum('서명' in page.get_text() for page in pdf), 1)

    def test_user_entered_signer_title_localized_to_output_language(self):
        from Quotation_KEKOREA.contracts.signature_layout import signature_blocks
        contract = sample()
        contract['parties'][0].update(
            representative='SEOKWON IHM', representative_title='CEO',
            address='157 Yangpyeong-ro, Seoul, Republic of Korea')
        contract['parties'][1].update(
            representative='ALEX', representative_title='대표이사',
            address='Wuxi Economic Free Zone Unit 7, China')
        contract['language'] = 'en'
        blocks = signature_blocks(contract)
        self.assertEqual(blocks[0]['name_title'], 'SEOKWON IHM, Chief Executive Officer')
        self.assertEqual(blocks[1]['name_title'], 'ALEX, Chief Executive Officer')
        contract['language'] = 'ko'
        blocks = signature_blocks(contract)
        self.assertEqual(blocks[0]['name_title'], 'SEOKWON IHM, 대표이사')
        self.assertEqual(blocks[1]['name_title'], 'ALEX, 대표이사')

    def test_non_ceo_roles_and_missing_titles_are_not_invented(self):
        from Quotation_KEKOREA.contracts.signature_layout import signature_blocks
        contract = sample()
        contract['language'] = 'en'
        contract['parties'][0].update(
            representative='SEOKWON IHM', representative_title='이사')
        contract['parties'][1].update(
            representative='ALEX', representative_title='',
            address='Wuxi, China')
        blocks = signature_blocks(contract)
        self.assertEqual(blocks[0]['name_title'], 'SEOKWON IHM, Director')
        self.assertEqual(blocks[1]['name_title'], 'ALEX')
        contract['parties'][1]['representative_title'] = 'Procurator'
        self.assertEqual(signature_blocks(contract)[1]['name_title'], 'ALEX, Procurator')

    def test_exported_pdf_and_docx_use_translated_signer_titles(self):
        data = sample('Delivery shall follow the written schedule.')
        data['language'] = 'en'
        data['parties'][1].update(
            legal_name='TENGYAO TECHNOLOGY CO. LTD',
            representative='ALEX', representative_title='대표이사',
            address='Wuxi, China')
        exported = export_contract(data, formats=('pdf', 'docx'))
        doc = Document(io.BytesIO(exported['docx']['content']))
        cell_text = '\\n'.join(cell.text for table in doc.tables
                                for row in table.rows for cell in row.cells)
        self.assertIn('ALEX, Chief Executive Officer', cell_text)
        self.assertNotIn('ALEX, 대표이사', cell_text)
        with fitz.open(stream=exported['pdf']['content'], filetype='pdf') as pdf:
            text = '\\n'.join(page.get_text() for page in pdf)
            self.assertIn('ALEX, Chief Executive Officer', text)
            self.assertNotIn('ALEX, 대표이사', text)

    def test_final_pdf_still_renders(self):
        data=export_contract(sample(),formats=('pdf',),seal_bytes=TEST_STAMP)['pdf']['content']
        self.assertTrue(data.startswith(b'%PDF-'))


if __name__=='__main__':
    unittest.main()
