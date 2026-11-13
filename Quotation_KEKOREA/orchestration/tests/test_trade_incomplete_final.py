"""Owner-approved finals keep unknown facts blank without losing numerical checks."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import importlib
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi
from Quotation_KEKOREA.orchestration.workflows import trade_export_review as review
from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as exports


class IncompleteFinalTests(unittest.TestCase):
    def setUp(self):
        self.doc = complete_pi()
        self.doc['document_number'] = 'PI-SYNTHETIC-002'
        self.doc['items'][0]['quantity'] = '100'

    def report(self, doc=None, kind='PI'):
        return review.review_trade_document(kind, doc or self.doc, final=True,
                                            allow_incomplete=True)

    def test_missing_facts_are_named_warnings_and_strict_default_still_blocks(self):
        self.doc['buyer']['legal_name'] = ''
        self.doc['buyer']['email'] = 'Not provided'
        self.doc['payment_terms'] = ''
        self.doc['missing_fields'] = ['Check the payment date in the source']
        before = deepcopy(self.doc)
        report = self.report()
        self.assertTrue(report['ready'], report['issues'])
        self.assertEqual(report['issues'], [])
        self.assertTrue({'buyer.legal_name', 'buyer.email', 'payment_terms'} <=
                        {issue['key'] for issue in report['warnings']})
        self.assertTrue(any(row['code'] == 'ai_missing' for row in report['warnings']))
        self.assertFalse(review.review_trade_document('PI', self.doc, final=True)['ready'])
        self.assertEqual(self.doc, before)

    def test_placeholders_and_draft_number_become_blanks_not_optional_na(self):
        self.doc['document_number'] = 'DRAFT'
        self.doc['buyer']['legal_name'] = 'N/A'
        self.doc['buyer']['email'] = 'TBD'
        self.doc['payment_terms'] = 'TO_BE_CONFIRMED'
        report = self.report()
        self.assertTrue(report['ready'], report['issues'])
        rendered = report['render_data']
        self.assertEqual(rendered['document_number'], '')
        self.assertEqual(rendered['buyer']['legal_name'], '')
        self.assertEqual(rendered['buyer']['email'], '')
        self.assertEqual(rendered['buyer']['phone'], 'N/A')
        self.assertEqual(rendered['payment_terms'], '')

    def test_optional_printed_placeholders_are_blank_but_real_text_is_preserved(self):
        self.doc.update(remarks='Not provided', bill_to='TBD', hs_code='TO_BE_CONFIRMED')
        self.doc['items'][0]['specification'] = 'TO_BE_CONFIRMED'
        self.doc['buyer']['registration_details'] = 'unknown'
        rendered = self.report()['render_data']
        self.assertEqual(rendered['remarks'], '')
        self.assertEqual(rendered['bill_to'], '')
        self.assertEqual(rendered['hs_code'], '')
        self.assertEqual(rendered['items'][0]['specification'], '')
        self.assertEqual(rendered['buyer']['registration_details'], '')
        self.doc.update(remarks='Not provided by the carrier yet', bill_to='N/A')
        rendered = self.report()['render_data']
        self.assertEqual(rendered['remarks'], 'Not provided by the carrier yet')
        self.assertEqual(rendered['bill_to'], 'N/A')

    def test_missing_quantity_never_becomes_zero_or_reuses_old_total(self):
        self.doc['items'][0].update(quantity='', line_total='9999', display_quantity='9999')
        self.doc.update(total='9999', subtotal='9999')
        report = self.report()
        self.assertTrue(report['ready'], report['issues'])
        row = report['render_data']['items'][0]
        for key in ('quantity', 'paid_quantity', 'shipped_quantity', 'display_quantity', 'line_total'):
            self.assertIsNone(row[key], key)
        self.assertIsNone(report['render_data']['total'])
        self.assertIsNone(report['render_data']['subtotal'])

    def test_explicit_zero_quantity_remains_calculable(self):
        for zero in (0, '0'):
            with self.subTest(zero=zero):
                self.doc['items'][0]['quantity'] = zero
                report = self.report()
                self.assertTrue(report['ready'], report['issues'])
                self.assertEqual(report['render_data']['items'][0]['quantity'], '0')
                self.assertEqual(report['render_data']['total'], '0.00')

    def test_known_grouped_shipped_quantity_is_preserved_when_paid_quantity_is_unknown(self):
        self.doc['items'][0].update(quantity='', shipped_quantity='1,000')
        report = self.report()
        self.assertTrue(report['ready'], report['issues'])
        self.assertEqual(report['render_data']['items'][0]['display_quantity'], '1000')
        self.assertIsNone(report['render_data']['items'][0]['paid_quantity'])
        self.assertIsNone(report['render_data']['total'])

    def test_missing_price_discount_or_currency_blanks_dependent_amounts(self):
        for field in ('unit_price', 'discount_percent', 'currency'):
            with self.subTest(field=field):
                doc = deepcopy(self.doc)
                (doc if field == 'currency' else doc['items'][0])[field] = ''
                report = self.report(doc)
                self.assertTrue(report['ready'], report['issues'])
                self.assertIsNone(report['render_data']['items'][0]['line_total'])
                self.assertIsNone(report['render_data']['total'])

    def test_known_rows_keep_amounts_but_partial_sum_is_not_a_total(self):
        self.doc['items'].append(dict(self.doc['items'][0], quantity=''))
        report = self.report()
        self.assertTrue(report['ready'], report['issues'])
        self.assertEqual(report['render_data']['items'][0]['line_total'], '20.00')
        self.assertIsNone(report['render_data']['items'][1]['line_total'])
        self.assertIsNone(report['render_data']['total'])

    def test_entered_invalid_numbers_remain_blocked(self):
        for field, value in (('quantity', '-1'), ('quantity', 'NaN'),
                             ('quantity', 'Infinity'), ('quantity', 'bad'),
                             ('unit_price', '0'), ('unit_price', '-1'),
                             ('discount_percent', '101')):
            with self.subTest(field=field, value=value):
                doc = deepcopy(self.doc)
                doc['items'][0][field] = value
                report = self.report(doc)
                self.assertFalse(report['ready'])
                self.assertTrue(report['issues'])

    def test_partial_mode_cannot_hide_conflicts_wrong_parties_or_unit_mismatch(self):
        for change in ('conflict', 'seller', 'unit'):
            with self.subTest(change=change):
                doc = deepcopy(self.doc)
                doc['buyer']['email'] = ''
                if change == 'conflict':
                    doc['conflicts'] = ['Two different transaction currencies']
                elif change == 'seller':
                    doc['seller']['legal_name'] = 'OTHER COMPANY LTD'
                else:
                    doc['items'][0]['price_basis'] = 'KG'
                self.assertFalse(self.report(doc)['ready'])

    def test_unknown_product_family_cannot_hide_known_unit_mismatch(self):
        self.doc['product_family'] = ''
        self.doc['items'][0]['price_basis'] = 'KG'
        self.assertFalse(self.report()['ready'])
        self.doc['items'][0]['price_basis'] = 'PCS'
        self.assertTrue(self.report()['ready'], self.report()['issues'])

    def test_explicit_invalid_values_cannot_be_overwritten_by_promotion_or_paid_quantity(self):
        for key, value in (('free_quantity', '-5'), ('free_quantity', 'NaN'),
                           ('shipped_quantity', '-5'), ('shipped_quantity', 'Infinity'),
                           ('quantity', '-2')):
            with self.subTest(key=key, value=value):
                doc = deepcopy(self.doc)
                doc['items'][0].update(promotion='2+1', paid_quantity='100')
                doc['items'][0][key] = value
                self.assertFalse(self.report(doc)['ready'])

    def test_ci_original_price_source_still_required(self):
        ci = deepcopy(self.doc)
        ci.update(document_type='CI', country_of_origin='', shipment_reference='')
        report = self.report(ci, kind='CI')
        self.assertFalse(report['ready'])
        self.assertTrue(any('attached PI' in row['message'] for row in report['issues']))

    def test_ci_invalid_source_amounts_are_not_waived_when_quantity_is_unknown(self):
        for key in ('source_total', 'source_line_total'):
            for value in ('-1', 'bad', 'NaN'):
                with self.subTest(key=key, value=value):
                    ci = deepcopy(self.doc)
                    ci.update(document_type='CI', _ci_from_pi=True, source_document_type='PI')
                    ci['items'][0].update(quantity='', source='Attached synthetic PI', _pi_import_price=True)
                    (ci if key == 'source_total' else ci['items'][0])[key] = value
                    report = self.report(ci, kind='CI')
                    self.assertFalse(report['ready'])
                    self.assertTrue(any('source amount' in row['message'] for row in report['issues']))

    def test_pl_declared_quantity_is_not_compared_to_a_fabricated_zero(self):
        pl = deepcopy(self.doc)
        pl.update(document_type='PL', declared_total_quantity='100',
                  declared_total_quantity_unit='PCS', container_count='0')
        pl['items'][0]['quantity'] = ''
        report = self.report(pl, kind='PL')
        self.assertTrue(report['ready'], report['issues'])
        self.assertIsNone(report['render_data']['_final_packing_totals']['quantities'])
        pl['declared_total_quantity_unit'] = 'KG'
        self.assertFalse(self.report(pl, kind='PL')['ready'])

    def test_pl_unknown_counts_and_weights_are_blank_and_invalid_values_stay_blocked(self):
        pl = deepcopy(self.doc)
        pl.update(document_type='PL', shipment_reference='', container_count='')
        report = self.report(pl, kind='PL')
        self.assertTrue(report['ready'], report['issues'])
        packing = report['render_data']['_final_packing_totals']
        self.assertIsNone(packing['package_count'])
        self.assertIsNone(packing['net_weight_kg'])
        self.assertEqual(packing['quantities'], {'PCS': '100'})
        pl['items'][0].update(net_weight_kg='10', gross_weight_kg='9')
        self.assertFalse(self.report(pl, kind='PL')['ready'])
        pl['items'][0].update(net_weight_kg='', gross_weight_kg='', package_count='bad')
        self.assertFalse(self.report(pl, kind='PL')['ready'])

    def test_pl_invalid_supplied_package_volume_is_not_treated_as_missing(self):
        pl = deepcopy(self.doc)
        pl.update(document_type='PL', actual_package_count='1', container_count='0',
                  packages=[{'package_count': '1', 'net_weight_kg': '1',
                             'gross_weight_kg': '2', 'volume_cbm': 'bad'}])
        report = self.report(pl, kind='PL')
        self.assertFalse(report['ready'])
        self.assertTrue(any('volume' in row['message'] for row in report['issues']))

    def test_sample_missing_facts_can_be_blank_but_invalid_supplied_quantity_cannot(self):
        self.doc['items'][0].update(is_sample=True, product_name='', quantity='', unit_price='')
        self.assertTrue(self.report()['ready'], self.report()['issues'])
        self.doc['items'][0]['quantity'] = '-1'
        self.assertFalse(self.report()['ready'])

    def test_cosmetics_missing_price_stays_blank_without_inventing_verified_price(self):
        self.doc['product_family'] = 'cosmetics'
        self.doc['items'][0]['unit_price'] = ''
        report = self.report()
        self.assertTrue(report['ready'], report['issues'])
        self.assertIsNone(report['render_data']['items'][0]['unit_price'])
        self.assertIsNone(report['render_data']['total'])
        self.doc['items'][0]['unit_price'] = '10'
        self.assertFalse(self.report()['ready'])

    def test_blank_document_with_no_items_does_not_fabricate_totals(self):
        doc = {'document_type': 'PI', 'items': []}
        report = self.report(doc)
        self.assertTrue(report['ready'], report['issues'])
        self.assertEqual(report['render_data']['items'], [])
        self.assertIsNone(report['render_data']['total'])

    def test_final_approval_is_bound_to_incomplete_option_and_current_input(self):
        self.doc['buyer']['email'] = ''
        digest = review.trade_export_fingerprint('PI', self.doc, allow_incomplete=True)
        self.assertNotEqual(digest, review.trade_export_fingerprint('PI', self.doc))
        with self.assertRaisesRegex(ValueError, '승인'):
            exports.render_master_trade_final('PI', self.doc, {}, approved=False,
                expected_fingerprint=digest, allow_incomplete=True)
        with self.assertRaisesRegex(ValueError, '변경'):
            exports.render_master_trade_final('PI', self.doc, {}, approved=True,
                expected_fingerprint=digest, allow_incomplete=False)

    def test_partial_final_uses_same_renderer_and_allows_blank_bank_data(self):
        self.doc['buyer']['email'] = ''
        self.doc['payment_terms'] = ''
        self.doc['items'][0]['quantity'] = ''
        digest = review.trade_export_fingerprint('PI', self.doc, allow_incomplete=True)
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            paths = {}
            for extension in ('pdf', 'xlsx', 'html'):
                path = Path(directory) / ('PI-FINAL.' + extension)
                path.write_bytes(b'synthetic output')
                paths[extension] = path
            with patch.object(exports, 'resolve_company_seal', return_value=(Path('/missing/seal.png'), b'synthetic seal', None)), \
                    patch.object(exports, 'render_files', return_value=paths) as render:
                files = exports.render_master_trade_final('PI', self.doc, {}, approved=True,
                    expected_fingerprint=digest, allow_incomplete=True)
        self.assertTrue(files['pdf']['final'])
        self.assertFalse(files['pdf']['sendable'])
        rendered = render.call_args.args[0]
        self.assertEqual(rendered['payment_terms'], '')
        self.assertIsNone(rendered['total'])
        self.assertTrue(render.call_args.kwargs['final'])
        self.assertTrue(all(value == '' for value in render.call_args.kwargs['bank_details'].values()))

    def test_ci_adapter_preserves_reviewed_blank_discount_and_payment(self):
        ci = deepcopy(self.doc)
        ci.update(document_type='CI', _ci_from_pi=True, source_document_type='PI', payment_terms='')
        ci['items'][0].update(discount_percent='', source='Attached synthetic PI', _pi_import_price=True)
        digest = review.trade_export_fingerprint('CI', ci, allow_incomplete=True)
        captured = {}
        def render(document, directory, **kwargs):
            captured.update(document)
            directory.mkdir(parents=True)
            paths = {}
            for extension in ('pdf', 'xlsx', 'html'):
                path = directory / ('CI-FINAL.' + extension)
                path.write_bytes(b'synthetic output')
                paths[extension] = path
            return paths
        with patch.object(exports, 'resolve_company_seal', return_value=(Path('/missing/seal.png'), b'synthetic seal', None)), \
                patch.object(exports, 'render_files', side_effect=render):
            exports.render_master_trade_final('CI', ci, {}, approved=True,
                expected_fingerprint=digest, allow_incomplete=True)
        self.assertEqual(captured['payment_terms'], '')
        self.assertIsNone(captured['items'][0]['discount_percent'])
        self.assertIsNone(captured['total'])

    def test_verified_seal_is_still_required_for_branded_final(self):
        self.doc['buyer']['email'] = ''
        digest = review.trade_export_fingerprint('PI', self.doc, allow_incomplete=True)
        with patch.object(exports, 'resolve_company_seal', return_value=(Path('/missing/seal.png'), None, 'not configured')):
            with self.assertRaisesRegex(ValueError, '직인'):
                exports.render_master_trade_final('PI', self.doc, {}, approved=True,
                    expected_fingerprint=digest, allow_incomplete=True)

    def test_hot_deploy_refreshes_old_shared_renderer_and_pdf_dependencies(self):
        from PIL import Image
        from Quotation_KEKOREA.agent import renderers, pi_pdf
        image = BytesIO()
        Image.new('RGB', (2, 2), 'red').save(image, format='PNG')
        digest = review.trade_export_fingerprint('PI', self.doc, allow_incomplete=True)
        def old_render_files(doc, output_dir, *, bank_details=None, logo_path=None, seal_path=None):
            raise AssertionError('The cached pre-FINAL renderer must be refreshed')
        def old_pdf(document, *, bank_details=None, logo_path=None, seal_path=None):
            raise AssertionError('The cached pre-FINAL PDF must be refreshed')
        for module, name, replacement, revision in (
                (renderers, 'render_files', old_render_files, 'TRADE_RENDERER_REVISION'),
                (pi_pdf, 'render_trade_document', old_pdf, 'TRADE_PDF_REVISION')):
            with self.subTest(dependency=name), patch.object(module, name, replacement), \
                    patch.object(module, revision, 'pre-final-version', create=True):
                importlib.reload(exports)
                with patch.object(exports, 'resolve_company_seal', return_value=(Path('/missing/seal.png'), image.getvalue(), None)):
                    files = exports.render_master_trade_final('PI', self.doc, {}, approved=True,
                        expected_fingerprint=digest, allow_incomplete=True)
                self.assertTrue(files['pdf']['content'].startswith(b'%PDF'))


if __name__ == '__main__':
    unittest.main()
