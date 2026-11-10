"""Exercise document completion, reruns, and stale-download prevention in Streamlit."""
import importlib.util
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_review_fields import complete_draft


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
class ReviewUiTests(unittest.TestCase):
    def test_unconfirmed_ci_product_match_allows_draft_pdf(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        doc = complete_draft()
        doc.update(document_type='CI', source_document_type='PI', _ci_from_pi=True,
                   product_family='cosmetics', shipment_reference='SHIP-001',
                   source_image_attached=True,
                   source_total='100',
                   missing_fields=['HS codes'],
                   conflicts=['Order details were extracted from an image; visually confirm product names, sizes, and quantities'])
        doc['seller'].update(legal_name='KE KOREA CO. LTD', address='Seoul, South Korea')
        doc['items'][0].update(product_name='Unmatched Cream', unit_price='10', price_source='Attached PI transaction price',
                               price_basis='USD/PC', source='Unmatched Cream 10 PCS at USD 10/PCS',
                               source_line_total='100', price_override_confirmed=True, master_price=False,
                               _pi_import_price=True)
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, b'test seal', None)):
            at = AppTest.from_file(str(app_path))
            at.session_state['selected_document_page'] = 'CI 만들기'
            at.session_state['trade_draft'] = doc
            at.session_state['trade_draft_page'] = 'CI 만들기'
            at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertTrue(any('remain marked DRAFT' in warning.value for warning in at.warning))
            effective = __import__('json').loads(at.session_state['rendered_json'])['document']
            self.assertEqual(effective['status'], 'DRAFT')
            self.assertTrue(any('HS codes' in issue for issue in effective['blocking_issues']))
            self.assertTrue(any('Double-check this product' in box.label for box in at.checkbox))
            self.assertFalse(next(button for button in at.button if button.label == 'Create PDF').disabled,
                             effective['blocking_issues'])

    def test_po_unresolved_promotion_does_not_request_all_24_prices(self):
        from streamlit.testing.v1 import AppTest
        from Quotation_KEKOREA.tests.test_po_partial_catalog import partial_order
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        partial, catalog = partial_order()
        doc = complete_draft()
        doc.update(partial)
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value=catalog), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, None, None)):
            at = AppTest.from_file(str(app_path))
            at.session_state['selected_document_page'] = 'PO 만들기'
            at.session_state['trade_draft'] = doc
            at.session_state['trade_draft_page'] = 'PO 만들기'
            at.run(timeout=20)
            self.assertFalse(at.exception)
            price_inputs = [entry.label for entry in at.text_input if 'unit price' in entry.label]
            self.assertEqual(price_inputs, ['Item 25: unit price *'])
            self.assertTrue(next(button for button in at.button if button.label == 'Create PDF').disabled)
            effective = __import__('json').loads(at.session_state['rendered_json'])['document']
            self.assertEqual(effective['currency'], 'KRW')
            self.assertFalse(effective['pending_confirmations'])

    def test_pl_totals_approval_enables_pdf_and_resets_when_source_changes(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        doc = complete_draft()
        doc.update(document_type='PL', product_family='other', currency=None, shipment_reference='TEST',
                   source_image_attached=True, container_count='5 x 40FT Containers', actual_package_count='2.5',
                   declared_total_quantity='12 pcs', declared_total_quantity_unit='PCS',
                   declared_net_weight_kg='3.5', declared_gross_weight_kg='4', declared_volume_cbm='0.031')
        doc['items'] = [dict(product_name='Test A', quantity='10', unit='PCS', package_count='2',
                             package_type='PALLET', net_weight_kg='1', gross_weight_kg='1.2', volume_cbm='0.01'),
                        dict(product_name='Test B', quantity='2.5', unit='KG', package_count='0.5',
                             package_type='PALLET', net_weight_kg='2.5', gross_weight_kg='2.8', volume_cbm='0.02')]
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': [{'id': 'test'}]}), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, None, None)):
            at = AppTest.from_file(str(app_path))
            at.session_state['selected_document_page'] = 'PL 만들기'
            at.session_state['trade_draft'] = doc
            at.session_state['trade_draft_page'] = 'PL 만들기'
            at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertFalse(at.error, [error.value for error in at.error])
            pdf_button = lambda: next(button for button in at.button if button.label == 'Create PDF')
            self.assertTrue(pdf_button().disabled)
            approval = next(box for box in at.checkbox if box.label.startswith('합계를 수정할까요?'))
            self.assertFalse(approval.value)
            approval.check().run(timeout=20)
            self.assertFalse(at.exception)
            self.assertFalse(pdf_button().disabled)
            import json
            effective = json.loads(at.session_state['rendered_json'])['document']
            self.assertEqual(effective['container_count'], '5')
            self.assertEqual(effective['declared_total_quantity'], '10')
            self.assertEqual(effective['declared_volume_cbm'], '0.03')
            self.assertEqual(effective['_packing_original_totals']['declared_total_quantity'], '12 pcs')
            self.assertEqual(effective['_packing_approved_quantities'], {'PCS': '10', 'KG': '2.5'})
            at.session_state['rendered_paths'] = {'pdf': 'previous.pdf'}
            next(entry for entry in at.text_input if entry.label == 'Source CBM').set_value('0.032').run(timeout=20)
            self.assertTrue(pdf_button().disabled)
            self.assertFalse(next(box for box in at.checkbox if box.label.startswith('합계를 수정할까요?')).value)
            self.assertEqual(at.session_state['rendered_paths'], {})
            next(entry for entry in at.text_input if entry.label == 'Containers').set_value('five').run(timeout=20)
            self.assertTrue(at.error)
            self.assertTrue(pdf_button().disabled)
            self.assertTrue(next(box for box in at.checkbox if box.label.startswith('합계를 수정할까요?')).disabled)

    def test_po_supplier_aliases_load_purchase_prices_and_show_recognition(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        catalog = {'products': [{'id': 'p1', 'brand': 'ECLADO', 'item_name': 'Test Cream', 'capacity': '50 ml'}],
                   'purchase_prices': [{'product_id': 'p1', 'supplier_key': 'ECLADO', 'currency': 'KRW',
                                        'unit_price': '1000', 'source_row': 1}]}
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value=catalog), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, None, None)):
            for supplier in ('eclado', 'ECLADO CO. LTD', '에끌라도', '에 끌 라 두 주식회사'):
                with self.subTest(supplier=supplier):
                    doc = complete_draft()
                    doc.update(document_type='PO', product_family='other', currency=None)
                    doc['seller']['legal_name'] = supplier
                    doc['items'] = [{**doc['items'][0], 'product_name': 'Test Cream', 'capacity': '50 ml',
                                     'quantity': str(qty), 'paid_quantity': str(qty), 'shipped_quantity': str(qty),
                                     'unit_price': None} for qty in (0, 5)]
                    at = AppTest.from_file(str(app_path))
                    at.session_state['selected_document_page'] = 'PO 만들기'
                    at.session_state['trade_draft'] = doc
                    at.session_state['trade_draft_page'] = 'PO 만들기'
                    at.run(timeout=20)
                    self.assertFalse(at.exception)
                    metrics = {metric.label: metric.value for metric in at.metric}
                    self.assertEqual(metrics['Total quantity'], '5 PCS')
                    self.assertEqual(metrics['Total amount'], 'KRW 5,000')
                    self.assertFalse(any('unit price' in entry.label for entry in at.text_input))
                    self.assertTrue(any('PO는 ECLADO KRW 매입 카탈로그 기준' in entry.value for entry in at.caption))

    def test_zero_quantity_calculates_but_missing_and_negative_quantities_block_exports(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        env = {'OPENAI_API_KEY': 'test', **{f'KEKOREA_USD_{key}': 'TEST' for key in
               ('BENEFICIARY', 'BANK_NAME', 'BRANCH', 'SWIFT', 'ACCOUNT_NUMBER', 'BANK_ADDRESS')}}
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, None, None)):
            for quantity in ('0', 0, '-1', None):
                with self.subTest(quantity=quantity):
                    doc = complete_draft()
                    doc['product_family'] = 'other'
                    doc['items'][0].update(quantity=quantity, paid_quantity=quantity, shipped_quantity=quantity)
                    at = AppTest.from_file(str(app_path))
                    at.session_state['trade_draft'] = doc
                    at.session_state['trade_draft_page'] = 'PI 만들기'
                    at.run(timeout=20)
                    self.assertFalse(at.exception)
                    metrics = {metric.label: metric.value for metric in at.metric}
                    valid = quantity in ('0', 0)
                    self.assertEqual(metrics['Total quantity'], '0 PCS' if valid else 'Quantity required')
                    self.assertEqual(metrics['Total amount'], '$0.00' if valid else 'Cannot calculate')
                    button = next(button for button in at.button if button.label == 'Create PDF')
                    self.assertEqual(button.disabled, not valid)

    def test_missing_inputs_update_document_and_invalidate_old_downloads(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        doc = complete_draft()
        doc.update(product_family='other', incoterms=None, payment_terms=None)
        doc['buyer']['email'] = None
        env = {'OPENAI_API_KEY': 'test', **{f'KEKOREA_USD_{key}': 'TEST' for key in
               ('BENEFICIARY', 'BANK_NAME', 'BRANCH', 'SWIFT', 'ACCOUNT_NUMBER', 'BANK_ADDRESS')}}
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, None, None)):
            at = AppTest.from_file(str(app_path))
            at.session_state['trade_draft'] = doc
            at.session_state['trade_draft_page'] = 'PI 만들기'
            at.run(timeout=20)
            self.assertFalse(at.exception)
            pdf_button = lambda: next(button for button in at.button if button.label == 'Create PDF')
            self.assertTrue(pdf_button().disabled)
            inputs = {entry.label: entry for entry in at.text_input}
            inputs['Delivery terms / Incoterms and named place *'].set_value('FOB Busan')
            inputs['Payment terms *'].set_value('100% before shipment')
            inputs['Buyer / customer: email'].set_value('N/A')
            at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertFalse(pdf_button().disabled)
            advanced = next(area for area in at.text_area if area.label == 'Extracted details')
            self.assertIn('FOB Busan', advanced.value)
            self.assertIn('100% before shipment', advanced.value)
            options = at.radio[0].options
            at.radio[0].set_value(options[1]).run(timeout=20)
            at.radio[0].set_value(options[0]).run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(next(entry for entry in at.text_input if entry.label.startswith('Delivery terms')).value,
                             'FOB Busan')
            self.assertFalse(pdf_button().disabled)
            at.session_state['rendered_paths'] = {'pdf': 'previous.pdf'}
            at.session_state['download_format'] = 'pdf'
            at.run(timeout=20)
            self.assertEqual(at.session_state['rendered_paths'], {'pdf': 'previous.pdf'})
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            delivery.set_value('CIF Singapore').run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['rendered_paths'], {})
            self.assertIn('CIF Singapore', next(area for area in at.text_area if area.label == 'Extracted details').value)
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            delivery.set_value('TO BE CONFIRMED').run(timeout=20)
            self.assertTrue(pdf_button().disabled)
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            delivery.set_value('CIF Singapore').run(timeout=20)
            self.assertFalse(pdf_button().disabled)
            new_doc = copy.deepcopy(doc)
            with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', return_value=new_doc):
                at.text_area[0].set_value('Create a PI. Cell quantity 10 PCS at USD 1 per PCS. No discount.').run(timeout=20)
                at.button[0].click().run(timeout=20)
            self.assertFalse(at.exception)
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            self.assertEqual(delivery.value, '')
            self.assertTrue(pdf_button().disabled)
