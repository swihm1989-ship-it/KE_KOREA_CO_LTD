"""PI/CI use verified buyer sale prices even if one image row is unresolved."""
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

from Quotation_KEKOREA.agent.pricing import apply_verified_eclado_prices


CATALOG = dict(products=[dict(id='p1', brand='ECLADO', source_code='E-165',
                             item_name='Cell Memory Cream', capacity='50g')],
               purchase_prices=[dict(product_id='p1', supplier_key='ECLADO', currency='KRW', unit_price='1000')],
               buyer_prices=[dict(product_id='p1', buyer_key='DEAR_GLOW', currency='USD', unit_price='12.50')])


def sale_draft(dtype='PI', buyer='Dear Glow', currency=None):
    return dict(document_type=dtype, product_family='other', currency=currency,
                buyer=dict(legal_name=buyer), seller=dict(legal_name='KE KOREA CO. LTD'),
                items=[dict(product_name='Cell Memory Cream (E-165)', capacity='50 g', quantity='10'),
                       dict(product_name='Unconfirmed product', capacity='10ml', quantity='1')])


class SalePartialCatalogTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
    def test_pi_ci_review_requests_only_unmatched_row_price(self):
        from streamlit.testing.v1 import AppTest
        from Quotation_KEKOREA.tests.test_review_fields import complete_draft
        path = Path(__file__).resolve().parents[1] / 'app.py'
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value=CATALOG), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            for dtype in ('PI', 'CI'):
                with self.subTest(dtype=dtype):
                    draft = complete_draft()
                    draft.update(sale_draft(dtype))
                    at = AppTest.from_file(str(path))
                    at.session_state['selected_document_page'] = dtype + ' 만들기'
                    at.session_state['trade_draft_page'] = dtype + ' 만들기'
                    at.session_state['trade_draft'] = draft
                    at.run(timeout=20)
                    self.assertFalse(at.exception)
                    self.assertEqual([e.label for e in at.text_input if 'unit price' in e.label],
                                     ['Item 2: unit price *'])
                    data = __import__('json').loads(at.session_state['rendered_json'])['document']
                    self.assertEqual(data['currency'], 'USD')
                    self.assertEqual(data['items'][0]['unit_price'], '12.50')

    def test_verified_buyer_partial_pi_and_ci_load_sale_prices_without_category_guess(self):
        for dtype in ('PI', 'CI'):
            with self.subTest(dtype=dtype):
                draft = sale_draft(dtype)
                apply_verified_eclado_prices(draft, CATALOG)
                self.assertEqual(draft['product_family'], 'cosmetics')
                self.assertEqual(draft['currency'], 'USD')
                self.assertEqual(draft['items'][0]['unit_price'], '12.50')
                self.assertTrue(draft['items'][0]['master_price'])
                self.assertIsNone(draft['items'][1].get('unit_price'))
                self.assertTrue(any('Unconfirmed product' in issue for issue in draft['missing_fields']))

    def test_unknown_or_missing_buyer_does_not_receive_dear_glow_sale_prices(self):
        for buyer in (None, 'Different buyer'):
            with self.subTest(buyer=buyer):
                draft = sale_draft(buyer=buyer)
                apply_verified_eclado_prices(draft, CATALOG)
                self.assertIsNone(draft['currency'])
                self.assertTrue(all(not row.get('unit_price') for row in draft['items']))
                self.assertEqual(draft['pending_confirmations'], [])

    def test_pi_explicit_krw_never_falls_back_to_po_purchase_price(self):
        draft = sale_draft(currency='KRW')
        apply_verified_eclado_prices(draft, CATALOG)
        self.assertEqual(draft['currency'], 'KRW')
        self.assertIsNone(draft['items'][0].get('unit_price'))
