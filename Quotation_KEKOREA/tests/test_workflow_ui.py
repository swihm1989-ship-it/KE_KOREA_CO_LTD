"""Navigate real Streamlit widgets while extraction/render workers are running."""
from contextlib import ExitStack
import copy
import importlib.util
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_review_fields import complete_draft


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
class WorkspaceUiTests(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.path = Path(__file__).resolve().parents[1] / 'app.py'
        env = {'OPENAI_API_KEY': 'test', **{f'KEKOREA_USD_{key}': 'TEST' for key in
               ('BENEFICIARY', 'BANK_NAME', 'BRANCH', 'SWIFT', 'ACCOUNT_NUMBER', 'BANK_ADDRESS')}}
        self.stack.enter_context(patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env))
        self.stack.enter_context(patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}))
        self.stack.enter_context(patch('Quotation_KEKOREA.agent.branding.resolve_company_seal',
                                      return_value=(self.path, None, None)))
        self.at = AppTest.from_file(str(self.path))

    def run_app(self):
        self.at.run(timeout=15)
        self.assertFalse(self.at.exception)

    def navigate(self, page):
        self.at.radio[0].set_value(page)
        self.run_app()

    def test_document_menus_keep_distinct_prompts_drafts_and_download_state(self):
        self.run_app()
        self.assertNotIn('CIPL 만들기', self.at.radio[0].options)
        for dtype in ('PI', 'PO', 'CI', 'PL'):
            page = dtype + ' 만들기'
            self.navigate(page)
            self.at.text_area[0].set_value('order ' + dtype)
            self.run_app()
            doc = complete_draft()
            doc.update(document_type=dtype, product_family='other',
                       shipment_reference='TEST', country_of_origin='Korea')
            self.at.session_state['trade_draft'] = doc
            self.at.session_state['trade_draft_page'] = page
            self.run_app()
            self.at.session_state['rendered_paths'] = {'pdf': dtype + '.pdf'}
            self.at.session_state['download_format'] = 'pdf'
        self.navigate('계약서 만들기 · 준비 중')
        self.navigate('커미션 계약서 만들기 · 준비 중')
        for dtype in ('PI', 'PO', 'CI', 'PL'):
            self.navigate(dtype + ' 만들기')
            self.assertEqual(self.at.text_area[0].value, 'order ' + dtype)
            self.assertEqual(self.at.session_state['trade_draft']['document_type'], dtype)
            self.assertEqual(self.at.session_state['rendered_paths'], {'pdf': dtype + '.pdf'})

    def test_removed_cipl_selection_falls_back_to_an_available_menu(self):
        self.at.session_state['selected_document_page'] = 'CIPL 만들기'
        self.run_app()
        self.assertEqual(self.at.session_state['selected_document_page'], 'PI 만들기')
        self.assertNotIn('CIPL 만들기', self.at.radio[0].options)

    def test_extract_continues_on_another_menu_and_commits_only_to_origin(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)
        def slow_extract(*args, **kwargs):
            started.set()
            release.wait(5)
            return copy.deepcopy(complete_draft())
        self.stack.enter_context(patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', slow_extract))
        self.run_app()
        self.at.text_area[0].set_value('Create a PI. Quantity 10 PCS at USD 1.').run(timeout=15)
        next(b for b in self.at.button if b.label == '정보 추출 및 초안 검토').click()
        self.run_app()
        self.assertTrue(started.wait(1))
        work = self.at.session_state['_document_workspaces']
        job = work.jobs['PI 만들기', 'extract']
        self.assertFalse(job.future.done())
        self.navigate('PO 만들기')
        self.at.text_area[0].set_value('separate PO input')
        self.run_app()
        release.set()
        job.future.result(timeout=2)
        self.run_app()
        self.assertNotIn('trade_draft', self.at.session_state)
        self.assertEqual(self.at.text_area[0].value, 'separate PO input')
        self.navigate('PI 만들기')
        self.assertEqual(self.at.session_state['trade_draft']['document_type'], 'PI')
        self.assertEqual(self.at.text_area[0].value, 'Create a PI. Quantity 10 PCS at USD 1.')

    def test_render_continues_after_navigation_and_returns_downloads_to_pi(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)
        def slow_render(*args, **kwargs):
            started.set()
            release.wait(5)
            return {'pdf': 'test-pi.pdf'}
        self.stack.enter_context(patch('Quotation_KEKOREA.agent.renderers.render_files', slow_render))
        self.at.session_state['trade_draft'] = complete_draft()
        self.at.session_state['trade_draft_page'] = 'PI 만들기'
        self.run_app()
        next(b for b in self.at.button if b.label == 'Create PDF').click()
        self.run_app()
        self.assertTrue(started.wait(1))
        work = self.at.session_state['_document_workspaces']
        job = work.jobs['PI 만들기', 'render']
        self.assertFalse(job.future.done())
        self.navigate('PO 만들기')
        release.set()
        job.future.result(timeout=2)
        self.run_app()
        self.assertNotIn('download_format', self.at.session_state)
        self.navigate('PI 만들기')
        self.assertEqual(self.at.session_state['rendered_paths'], {'pdf': 'test-pi.pdf'})
        self.assertEqual(self.at.session_state['download_format'], 'pdf')

    def test_supplier_edits_and_unapplied_json_survive_another_menu(self):
        doc = complete_draft()
        doc.update(document_type='PO', product_family='other')
        self.at.session_state['selected_document_page'] = 'PO 만들기'
        self.at.session_state['trade_draft'] = doc
        self.at.session_state['trade_draft_page'] = 'PO 만들기'
        self.run_app()
        next(e for e in self.at.text_input if e.label == 'Supplier legal name').set_value('Edited Supplier')
        next(e for e in self.at.text_input if e.label == 'Supplier address').set_value('Edited Address')
        self.run_app()
        next(e for e in self.at.text_area if e.label == 'Extracted details').set_value('unfinished JSON edit')
        self.run_app()
        self.navigate('CI 만들기')
        self.navigate('PO 만들기')
        self.assertEqual(next(e for e in self.at.text_input if e.label == 'Supplier legal name').value,
                         'Edited Supplier')
        self.assertEqual(next(e for e in self.at.text_input if e.label == 'Supplier address').value,
                         'Edited Address')
        self.assertEqual(next(e for e in self.at.text_area if e.label == 'Extracted details').value,
                         'unfinished JSON edit')

    def test_saved_attachments_return_only_to_their_menu_and_can_be_cleared(self):
        from Quotation_KEKOREA.agent.workflow_state import SavedUpload
        self.run_app()
        work = self.at.session_state['_document_workspaces']
        work.remember_uploads('PI 만들기', [SavedUpload('example.png', 'image/png',
                              (self.path.parent / 'assets' / 'company_logo.png').read_bytes())])
        self.run_app()
        self.assertTrue(any('첨부 이미지 1개' in c.value for c in self.at.caption))
        self.navigate('PO 만들기')
        self.assertFalse(any('첨부 이미지 1개' in c.value for c in self.at.caption))
        self.navigate('PI 만들기')
        self.assertTrue(any('첨부 이미지 1개' in c.value for c in self.at.caption))
        next(b for b in self.at.button if b.label == '첨부 이미지 모두 지우기').click()
        self.run_app()
        self.assertEqual(work.uploads['PI 만들기'], [])
        self.navigate('PO 만들기')
        self.navigate('PI 만들기')
        self.assertFalse(any('첨부 이미지 1개' in c.value for c in self.at.caption))

    def test_packing_approval_survives_navigation_but_resets_after_source_edit(self):
        doc = complete_draft()
        doc.update(document_type='PL', product_family='other', currency=None,
                   shipment_reference='TEST', source_image_attached=True,
                   actual_package_count='1', container_count='1', declared_total_quantity='10',
                   declared_total_quantity_unit='PCS', declared_net_weight_kg='1',
                   declared_gross_weight_kg='1.2', declared_volume_cbm='0.5')
        doc['items'] = [dict(product_name='Test', quantity='10', unit='PCS',
                             package_count='1', package_type='CARTON', net_weight_kg='1',
                             gross_weight_kg='1.2', volume_cbm='0.01')]
        self.at.session_state['selected_document_page'] = 'PL 만들기'
        self.at.session_state['trade_draft'] = doc
        self.at.session_state['trade_draft_page'] = 'PL 만들기'
        self.run_app()
        next(c for c in self.at.checkbox if c.label.startswith('합계를 수정할까요?')).check()
        self.run_app()
        self.assertFalse(next(b for b in self.at.button if b.label == 'Create PDF').disabled)
        self.navigate('PO 만들기')
        self.navigate('PL 만들기')
        self.assertTrue(next(c for c in self.at.checkbox if c.label.startswith('합계를 수정할까요?')).value)
        self.assertFalse(next(b for b in self.at.button if b.label == 'Create PDF').disabled)
        next(e for e in self.at.text_input if e.label == 'Source CBM').set_value('0.6')
        self.run_app()
        self.assertFalse(next(c for c in self.at.checkbox if c.label.startswith('합계를 수정할까요?')).value)
        self.assertTrue(next(b for b in self.at.button if b.label == 'Create PDF').disabled)
