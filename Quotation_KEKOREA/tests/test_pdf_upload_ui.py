"""All document menus accept and retain PDFs through the existing worker path."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.agent.workflow_state import DocumentWorkspaces, SavedUpload
from Quotation_KEKOREA.tests.test_pdf_inputs import PDF
from Quotation_KEKOREA.tests.test_order_promotions import order


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
class PdfUploadUiTests(unittest.TestCase):
    def test_all_menus_preview_pdf_safely_and_send_complete_attachment_to_extractor(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.counterparties.load_company_profiles', return_value=[]), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            for menu in ('PO', 'PI', 'CI', 'PL', 'CIPL'):
                with self.subTest(menu=menu):
                    page = menu + ' 만들기'
                    work = DocumentWorkspaces()
                    work.remember_uploads(page, [SavedUpload('source.pdf', 'application/pdf', PDF)])
                    at = AppTest.from_file(str(path))
                    at.session_state['_document_workspaces'] = work
                    at.session_state['selected_document_page'] = page
                    at.run(timeout=20)
                    self.assertFalse(at.exception)
                    self.assertIn('.pdf', at.get('file_uploader')[0].proto.type)
                    dtype = 'CI' if menu == 'CIPL' else menu
                    with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', return_value=copy.deepcopy(order(dtype))) as extract:
                        next(b for b in at.button if b.label == '정보 추출 및 초안 검토').click().run(timeout=20)
                        job = work.jobs.get((page, 'extract'))
                        if job:
                            job.future.result(timeout=3)
                            at.run(timeout=20)
                        self.assertFalse(at.exception)
                        self.assertEqual(extract.call_args.kwargs['images'][0]['data'], PDF)
                        self.assertEqual(extract.call_args.kwargs['images'][0]['mime_type'], 'application/pdf')
                        self.assertEqual(extract.call_args.kwargs['requested_document_type'], dtype)
                        self.assertEqual(extract.call_args.kwargs['packing_source'], menu in ('PL', 'CIPL'))
                        self.assertTrue(at.session_state['trade_draft']['source_pdf_attached'])
