"""Attached PI commercial data reaches CI without catalog/default discount changes."""
import copy
import importlib.util
import json
import struct
import zlib
from pathlib import Path
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.agent.workflow_state import DocumentWorkspaces, SavedUpload
from Quotation_KEKOREA.tests.test_pdf_inputs import PDF
from Quotation_KEKOREA.tests.test_ci_pi_import import pi_source


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
class CiPiImportUiTests(unittest.TestCase):
    def test_pi_conversion_request_preserves_prices_discounts_and_blocks_changed_source_amount(self):
        for mime in ('application/pdf', 'image/png'):
            with self.subTest(mime=mime):
                self._exercise_case(mime)

    def _exercise_case(self, mime):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        doc = pi_source()
        doc.update(ship_to='Test Warehouse', ship_to_source='Ship To: Test Warehouse', shipment_reference='TEST-SHIPMENT',
                   source_notes=['Test Toner 10 PCS USD 2.00 10% 18.00', 'Ship To: Test Warehouse'])
        doc['items'][0]['capacity'] = '50ml'
        catalog = {'products': [{'id': 'p1', 'brand': 'ECLADO', 'item_name': 'Test Toner', 'capacity': '50ml'}],
                   'buyer_prices': [{'product_id': 'p1', 'buyer_key': 'DEAR_GLOW', 'currency': 'USD', 'unit_price': '99'}]}
        work = DocumentWorkspaces()
        def chunk(kind, body):
            return struct.pack('!I', len(body)) + kind + body + struct.pack('!I', zlib.crc32(kind + body) & 0xffffffff)
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff')) + chunk(b'IEND', b''))
        work.remember_uploads('CI 만들기', [SavedUpload('pi.pdf' if mime == 'application/pdf' else 'pi.png', mime,
                                                      PDF if mime == 'application/pdf' else png)])
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value=catalog), \
             patch('Quotation_KEKOREA.agent.counterparties.load_company_profiles', return_value=[]), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            at = AppTest.from_file(str(path))
            at.session_state['_document_workspaces'] = work
            at.session_state['selected_document_page'] = 'CI 만들기'
            at.run(timeout=20)
            at.text_area[0].set_value('첨부한 PI를 CI로 작성해줘.' if mime == 'application/pdf' else 'Create CI from the attached PI').run(timeout=20)
            with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', return_value=copy.deepcopy(doc)) as extract:
                next(b for b in at.button if b.label == '정보 추출 및 초안 검토').click().run(timeout=20)
                job = work.jobs.get(('CI 만들기', 'extract'))
                if job:
                    job.future.result(timeout=3)
                    at.run(timeout=20)
                self.assertTrue(extract.called, [e.value for e in at.error])
            self.assertFalse(at.exception)
            result = json.loads(at.session_state['rendered_json'])['document']
            self.assertEqual(result['total'], '18.00')
            self.assertEqual(result['ship_to'], 'Test Warehouse')
            self.assertEqual(result['items'][0]['unit_price'], '2')
            self.assertEqual(result['items'][0]['discount_percent'], '10')
            self.assertEqual(result['payment_terms'], 'N/A')
            self.assertNotIn('bank_details', result)
            self.assertFalse(next(b for b in at.button if b.label == 'Create PDF').disabled,
                             result['blocking_issues'] + [e.value for e in at.warning])
            corrected = json.loads(next(e for e in at.text_area if e.label == 'Extracted details').value)
            corrected['source_total'] = '19.00'
            next(e for e in at.text_area if e.label == 'Extracted details').set_value(json.dumps(corrected)).run(timeout=20)
            next(b for b in at.button if b.label == 'Apply corrections').click().run(timeout=20)
            self.assertFalse(at.exception)
            self.assertTrue(next(b for b in at.button if b.label == 'Create PDF').disabled)
            self.assertTrue(any('PI import total' in e.value for e in at.error))
