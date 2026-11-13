"""Real editor state, named gaps and owner-approved FINAL PDF behavior."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi

class TradeFinalUiTests(unittest.TestCase):
    def doc(self):
        doc=complete_pi();doc['document_number']='PI-SYNTHETIC-FINAL'
        return doc

    def app(self,doc=None,editor=False,*,bundle=None):
        from Quotation_KEKOREA.orchestration.ui import ai_intake_page
        self.assertTrue(hasattr(ai_intake_page,'_render_trade_final_panel'),'Final export panel missing')
        source='''import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _render_single_editor, _render_trade_final_panel
from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import BANK_KEYS
if 'ai_intake_candidates' not in st.session_state:
    st.session_state['ai_intake_candidates']=('final-ui',DOC)
'''.replace('DOC',repr(bundle if bundle is not None else {'PI':doc}))
        source+="if st.session_state.get('test_editor_visible', True):\n"
        if editor:source+="    _render_single_editor('final-ui',st.session_state['ai_intake_candidates'][1])\n"
        source+="    _render_trade_final_panel('final-ui',st.session_state['ai_intake_candidates'][1],{'KEKOREA_USD_'+k:'SYNTHETIC '+k for k in BANK_KEYS}, edited_matches=st.session_state.get('test_edited_matches', True))\n"
        return AppTest.from_string(source,default_timeout=25).run()

    def seal(self):
        from PIL import Image
        image=BytesIO();Image.new('RGB',(2,2),'red').save(image,format='PNG')
        return patch('Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.resolve_company_seal',
                     return_value=(Path('/not-present/seal.png'),image.getvalue(),None))

    def full_app(self):
        from hashlib import sha256
        from Quotation_KEKOREA.orchestration.ui import ai_intake_page
        instruction='Synthetic PI request'
        digest=sha256((instruction+'|한국어|solar_cell').encode()).hexdigest()
        source='''import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import render_ai_intake
if 'ai_intake_candidates' not in st.session_state:
    st.session_state['ai_intake_instruction']=INSTRUCTION
    st.session_state['ai_intake_candidates']=(DIGEST,DOC)
render_ai_intake('synthetic@example.test')
'''.replace('INSTRUCTION',repr(instruction)).replace('DIGEST',repr(digest)).replace('DOC',repr({'PI':self.doc()}))
        for name, value in (('_model_config',{}),('document_export_env',{}),('_reference_panel',None)):
            replacement=patch.object(ai_intake_page,name,return_value=value)
            replacement.start();self.addCleanup(replacement.stop)
        return AppTest.from_string(source,default_timeout=25).run()

    def approve(self, app, kind='PI'):
        approval=next(c for c in app.checkbox if c.label.startswith(kind+' · 최종 출력'))
        self.assertFalse(approval.disabled)
        approval.check().run()

    def export(self, app, kind='PI'):
        next(b for b in app.button if b.label==kind+' 최종 PDF 생성').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])

    def test_last_gap_warning_names_the_remaining_fields(self):
        doc=self.doc();doc['buyer']['email']='';doc['seller']['phone']=''
        source="from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _render_single_editor\n_render_single_editor('named-gaps',"+repr({'PI':doc})+")"
        app=AppTest.from_string(source).run()
        self.assertFalse(app.exception)
        warning=next(w.value for w in app.warning if '미입력·확인 필요 항목 2개' in w.value)
        self.assertIn('Buyer',warning);self.assertIn('이메일',warning)
        self.assertIn('Seller',warning);self.assertIn('전화번호',warning)

    def test_final_download_requires_approval_and_edit_revokes_it(self):
        from PIL import Image
        image=BytesIO();Image.new('RGB',(2,2),'red').save(image,format='PNG')
        with patch('Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.resolve_company_seal',return_value=(Path('/not-present/seal.png'),image.getvalue(),None)):
            app=self.app(self.doc(),editor=True)
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertTrue(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)
            next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).check().run()
            self.assertFalse(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)
            next(b for b in app.button if b.label=='PI 최종 PDF 생성').click().run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            bundle=app.session_state['master_trade_final_files']['PI']
            self.assertTrue(bundle['files']['pdf']['final'])
            next(t for t in app.text_input if t.label=='단가').set_value('0.25').run()
            self.assertFalse(app.exception)
            self.assertNotIn('master_trade_final_files',app.session_state)
            self.assertTrue(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)

    def test_old_ai_missing_notes_stay_visible_without_blocking_explicit_final_approval(self):
        doc=self.doc();doc['missing_fields']=['Buyer email','Seller phone']
        app=self.app(doc)
        self.assertTrue(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)
        self.assertFalse(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)
        self.assertTrue(any('Buyer email' in t.value for t in app.text))
        self.assertEqual(app.session_state['ai_intake_candidates'][1]['PI']['missing_fields'],
                         ['Buyer email','Seller phone'])
        self.approve(app)
        self.assertFalse(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)

    def test_missing_facts_generate_approved_final_without_invented_placeholders(self):
        import pymupdf
        doc=self.doc();doc['document_number']='DRAFT'
        doc['buyer']['address']='';doc['buyer']['email']='';doc['ship_to']=''
        doc['missing_fields']=['Buyer address','Ship-to not confirmed']
        with self.seal():
            app=self.app(doc,editor=True)
            self.assertFalse(app.exception,[e.message for e in app.exception])
            approval=next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력'))
            self.assertFalse(approval.disabled)
            self.assertIn('빈칸',approval.label)
            self.assertTrue(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)
            self.approve(app);self.export(app)
            asset=app.session_state['master_trade_final_files']['PI']['files']['pdf']
            self.assertTrue(asset['final'])
            with pymupdf.open(stream=asset['content'],filetype='pdf') as pdf:
                text='\n'.join(page.get_text() for page in pdf)
            self.assertNotIn('DRAFT',text)
            self.assertNotIn('NOT PROVIDED',text.upper())
            self.assertNotIn('TBD',text)
            current=app.session_state['ai_intake_candidates'][1]['PI']
            self.assertEqual(current['buyer']['address'],'')
            self.assertEqual(current['buyer']['email'],'')
            self.assertEqual(current['ship_to'],'')

    def test_manual_missing_edit_updates_current_warnings_and_final_input(self):
        doc=self.doc();doc['buyer']['address']=''
        doc['missing_fields']=['Buyer address','Unmapped old extraction note']
        app=self.app(doc,editor=True)
        next(t for t in app.text_input if t.label=='Buyer · 구매자 법인 주소').set_value(
            'SYNTHETIC VERIFIED ADDRESS').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        current=app.session_state['ai_intake_candidates'][1]['PI']
        self.assertEqual(current['buyer']['address'],'SYNTHETIC VERIFIED ADDRESS')
        self.assertEqual(current['missing_fields'],['Unmapped old extraction note'])
        self.assertFalse(any('구매자 법인 주소' in w.value for w in app.warning))
        self.assertTrue(any('Unmapped old extraction note' in t.value for t in app.text))
        self.approve(app)
        self.assertFalse(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)

    def test_other_document_missing_facts_do_not_block_pi_and_conflicts_stay_blocked(self):
        pi=self.doc();pi['buyer']['email']=''
        po=deepcopy(pi);po['document_type']='PO';po['document_number']=''
        po['conflicts']=['Supplier quantity conflicts with source invoice']
        bundle={'PI':pi,'PO':po,'CONTRACT':{'parties':[],'terms':[]}}
        app=self.app(bundle=bundle)
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertFalse(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)
        self.assertTrue(next(c for c in app.checkbox if c.label.startswith('PO · 최종 출력')).disabled)
        self.approve(app)
        self.assertFalse(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)
        self.assertTrue(next(b for b in app.button if b.label=='PO 최종 PDF 생성').disabled)

    def test_withdrawn_approval_revokes_existing_download(self):
        with self.seal():
            app=self.app(self.doc());self.approve(app);self.export(app)
            self.assertTrue(app.get('download_button'))
            next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).uncheck().run()
            self.assertFalse(app.get('download_button'))
            self.assertFalse('master_trade_final_files' in app.session_state and
                             'PI' in app.session_state['master_trade_final_files'])

    def test_pending_json_change_revokes_existing_download_and_approval(self):
        with self.seal():
            app=self.app(self.doc());self.approve(app);self.export(app)
            app.session_state['test_edited_matches']=False;app.run()
            self.assertFalse(app.get('download_button'))
            app.session_state['test_edited_matches']=True;app.run()
            self.assertFalse(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).value)
            self.assertTrue(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)

    def test_rejected_numeric_edit_revokes_final_until_that_input_is_corrected(self):
        with self.seal():
            app=self.app(self.doc(),editor=True);self.approve(app);self.export(app)
            next(t for t in app.text_input if t.label=='단가').set_value('-1').run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertTrue(app.error)
            self.assertEqual(next(t for t in app.text_input if t.label=='단가').value,'-1')
            self.assertFalse(app.get('download_button'))
            self.assertNotIn('master_trade_final_files',app.session_state)
            self.assertTrue(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)
            next(t for t in app.text_input if t.label=='Buyer · 구매자 법인 주소').set_value(
                'SYNTHETIC ADDRESS CHANGED').run()
            self.assertEqual(next(t for t in app.text_input if t.label=='단가').value,'-1')
            self.assertTrue(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)
            next(t for t in app.text_input if t.label=='단가').set_value('0.25').run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertFalse(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)
            self.assertTrue(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)
            self.approve(app)
            self.assertFalse(next(b for b in app.button if b.label=='PI 최종 PDF 생성').disabled)

    def test_committed_json_changes_refresh_single_editor(self):
        app=self.full_app()
        revised=deepcopy(app.session_state['ai_intake_candidates'][1])
        revised['PI']['buyer']['address']='SYNTHETIC JSON ADDRESS'
        next(t for t in app.text_area if t.label=='문서별 JSON 조건 (고급 편집)').set_value(
            json.dumps(revised)).run()
        next(b for b in app.button if b.label=='고급 JSON 변경값 후보에 반영').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.session_state['ai_intake_candidates'][1]['PI']['buyer']['address'],
                         'SYNTHETIC JSON ADDRESS')
        self.assertEqual(next(t for t in app.text_input if t.label=='Buyer · 구매자 법인 주소').value,
                         'SYNTHETIC JSON ADDRESS')

    def test_rejected_input_blocks_each_document_generation_button(self):
        app=self.full_app()
        next(t for t in app.text_input if t.label=='수량').set_value('NaN').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertTrue(app.button(key='ai_intake_prepare').disabled)
        self.assertTrue(app.button(key='master_legacy_export').disabled)
        self.assertTrue(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)

    def test_rejected_input_remains_visible_after_leaving_and_returning_to_editor(self):
        app=self.app(self.doc(),editor=True)
        next(t for t in app.text_input if t.label=='단가').set_value('-1').run()
        app.session_state['test_editor_visible']=False;app.run()
        self.assertFalse(app.text_input)
        app.session_state['test_editor_visible']=True;app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(next(t for t in app.text_input if t.label=='단가').value,'-1')
        self.assertTrue(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)
        next(t for t in app.text_input if t.label=='단가').set_value('0.25').run()
        self.assertFalse(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)

    def test_committed_json_can_correct_a_rejected_visible_input(self):
        app=self.full_app()
        next(t for t in app.text_input if t.label=='단가').set_value('-1').run()
        revised=deepcopy(app.session_state['ai_intake_candidates'][1])
        revised['PI']['items'][0]['unit_price']='0.40'
        next(t for t in app.text_area if t.label=='문서별 JSON 조건 (고급 편집)').set_value(
            json.dumps(revised)).run()
        next(b for b in app.button if b.label=='고급 JSON 변경값 후보에 반영').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(next(t for t in app.text_input if t.label=='단가').value,'0.40')
        self.assertFalse(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)

    def test_cached_review_module_reloads_before_using_partial_final_api(self):
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports, trade_export_review
        with (patch.object(trade_export_review,'TRADE_REVIEW_REVISION','old-release',create=True),
              patch.object(trade_export_review,'review_trade_document',side_effect=AssertionError('stale review used'))):
            app=self.app(self.doc())
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertFalse(next(c for c in app.checkbox if c.label.startswith('PI · 최종 출력')).disabled)

    def test_real_document_number_can_be_generated_in_original_editor(self):
        doc=self.doc();doc['document_number']='DRAFT'
        app=self.app(doc,editor=True)
        next(b for b in app.button if b.label=='문서번호 자동 생성').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        number=app.session_state['ai_intake_candidates'][1]['PI']['document_number']
        self.assertTrue(number.startswith('PI-'));self.assertNotIn('DRAFT',number)

if __name__=='__main__':unittest.main()
