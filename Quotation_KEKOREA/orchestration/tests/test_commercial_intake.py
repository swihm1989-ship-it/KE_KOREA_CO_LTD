"""Explicit units/prices survive MASTER intake without guessed commercial facts."""
import copy
import unittest

from Quotation_KEKOREA.orchestration.workflows.ai_intake import make_trade_candidate, make_contract_candidate
from Quotation_KEKOREA.orchestration.workflows.intake_followups import missing_fields, apply_answer
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate


def analysis(quantity='2325860', price='$0.2/pc', unit='', currency=''):
    return {'contract_type': 'sale', 'parties': [], 'issues': [], 'terms': [
        {'key': key, 'value': value, 'status': 'suggested', 'source_refs': ['user:1']}
        for key, value in dict(products='Hanwha Solar Cell', quantity=quantity,
                               unit_price=price, unit=unit, currency=currency).items()]}


class CommercialIntakeTests(unittest.TestCase):
    def test_old_ai_notes_stay_blocking_until_explicitly_checked(self):
        from Quotation_KEKOREA.orchestration.workflows.intake_followups import (
            acknowledge_prior_source_notice,
        )
        original = {
            "PI": {
                "document_type": "PI", "product_family": "solar_cell",
                "document_number": "DRAFT",
                "buyer": {"legal_name": "SYNTHETIC BUYER LTD",
                          "address": "Seoul, Korea"},
                "seller": {"legal_name": "KE KOREA CO. LTD",
                           "address": "Seoul, Korea"},
                "currency": "USD", "incoterms": "EXW Seoul",
                "payment_terms": "T/T in advance",
                "items": [{"product_name": "TEST CELL", "quantity": "100",
                           "unit": "PCS", "unit_price": "0.2",
                           "price_basis": "PCS"}],
                "conflicts": ["Confirm payment date in synthetic email"],
                "missing_fields": ["Buyer and seller names and addresses"],
            },
        }
        snapshot = copy.deepcopy(original)
        self.assertTrue(any(
            "Resolve conflicting" in item
            for item in validate_and_calculate(original["PI"])["blocking_issues"]
        ))
        cleared = acknowledge_prior_source_notice(
            original, "PI", "missing_fields", 0,
            "Buyer and seller names and addresses",
        )
        self.assertEqual(original, snapshot)
        self.assertEqual(cleared["PI"]["missing_fields"], [])
        self.assertEqual(cleared["PI"]["conflicts"],
                         ["Confirm payment date in synthetic email"])
        self.assertFalse(validate_and_calculate(cleared["PI"])["ready_for_issue"])
        resolved = acknowledge_prior_source_notice(
            cleared, "PI", "conflicts", 0,
            "Confirm payment date in synthetic email",
        )
        self.assertFalse(resolved["PI"]["conflicts"])
        self.assertTrue(validate_and_calculate(resolved["PI"])["ready_for_issue"])

    def test_acknowledging_notes_never_overrides_real_required_fields(self):
        from Quotation_KEKOREA.orchestration.workflows.intake_followups import (
            acknowledge_prior_source_notice,
        )
        sample = {"PI": {"document_type": "PI", "product_family": "solar_cell",
                         "seller": {"legal_name": "KE KOREA CO. LTD"},
                         "buyer": {"legal_name": "TEST BUYER"},
                         "missing_fields": ["historical AI memo"], "items": []}}
        changed = acknowledge_prior_source_notice(
            sample, "PI", "missing_fields", 0, "historical AI memo",
        )
        blockers = validate_and_calculate(changed["PI"])["blocking_issues"]
        self.assertIn("Buyer address is required", blockers)
        self.assertIn("Seller address is required", blockers)
        with self.assertRaisesRegex(ValueError, "변경"):
            acknowledge_prior_source_notice(
                sample, "PI", "missing_fields", 0, "old mismatched message",
            )
        self.assertEqual(sample["PI"]["missing_fields"], ["historical AI memo"])

    def test_scalar_seller_and_buyer_do_not_crash_existing_trade_validation(self):
        from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values
        source = {"document_type": "PI", "product_family": "solar_cell",
                  "seller": "KE KOREA CO. LTD", "buyer": "Smart Solar Systems Co. Ltd",
                  "currency": "USD", "items": [{"product_name": "Synthetic solar cell",
                  "quantity": "10", "unit": "PCS", "unit_price": "0.2",
                  "price_basis": "PCS"}]}
        original = copy.deepcopy(source)
        normalized = normalize_trade_values(source)
        self.assertEqual(source, original)
        self.assertEqual(normalized["seller"]["legal_name"], "KE KOREA CO. LTD")
        self.assertEqual(normalized["buyer"]["legal_name"], "Smart Solar Systems Co. Ltd")
        self.assertEqual(normalized["seller"]["address"], "")
        self.assertIn("Buyer address is required",
                      validate_and_calculate(normalized)["blocking_issues"])
        self.assertIn("Seller address is required",
                      validate_and_calculate(normalized)["blocking_issues"])
        self.assertNotIn("address", normalized["seller"]["legal_name"])

    def test_live_answer_repairs_scalar_parties_across_all_document_types(self):
        source = {"PI": {"seller": "KE KOREA CO. LTD",
                         "buyer": "Smart Solar Systems Co. Ltd",
                         "currency": "USD", "items": [{"product_name": "Cell", "quantity": "2"}]},
                  "PO": {"seller": None, "buyer": "KE KOREA CO. LTD",
                         "items": [{"product_name": "Cell"}]}}
        original = copy.deepcopy(source)
        updated = apply_answer(source, "seller.address",
                               "Synthetic seller address")
        self.assertEqual(source, original)
        for kind in ("PI", "PO"):
            self.assertEqual(updated[kind]["seller"]["address"],
                             "Synthetic seller address")
        self.assertEqual(updated["PI"]["seller"]["legal_name"],
                         "KE KOREA CO. LTD")
        self.assertEqual(updated["PO"]["seller"]["legal_name"], "")
        gaps = [field.key for field in missing_fields(updated)]
        self.assertNotIn("seller.address", gaps)

    def test_nontext_party_values_are_not_treated_as_approved_identity(self):
        from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values
        normalized = normalize_trade_values({
            "buyer": ["unverified-name"], "seller": {"legal_name": 12345,
            "address": {"not": "a string"}}, "items": []})
        self.assertEqual(normalized["buyer"]["legal_name"], "")
        self.assertEqual(normalized["seller"]["legal_name"], "")
        self.assertEqual(normalized["seller"]["address"], "")

    def test_explicit_price_denominator_supplies_unit_currency_and_numeric_price(self):
        for denominator in ('pc', 'piece', 'PCS', '장'):
            with self.subTest(denominator=denominator):
                source = analysis(price='$0.2/' + denominator)
                before = copy.deepcopy(source)
                pi = make_trade_candidate('PI', source)
                self.assertEqual(pi['currency'], 'USD')
                self.assertEqual(pi['items'][0]['unit'], 'PCS')
                self.assertEqual(pi['items'][0]['price_basis'], 'PCS')
                self.assertEqual(pi['items'][0]['unit_price'], '0.2')
                self.assertEqual(source, before)
                self.assertEqual(pi['items'][0]['price_source'], '')

    def test_quantity_suffix_is_parsed_and_zero_preserved(self):
        for quantity, expected in [('2,325,860 장', '2325860'), (0, '0')]:
            pi = make_trade_candidate('PI', analysis(quantity=quantity))
            self.assertEqual(pi['items'][0]['quantity'], expected)
            self.assertEqual(pi['items'][0]['unit'], 'PCS')

    def test_explicit_term_unit_and_currency_metadata_are_not_lost(self):
        source = analysis(price='0.2', quantity='2325860')
        next(t for t in source['terms'] if t['key'] == 'quantity')['unit'] = '장'
        next(t for t in source['terms'] if t['key'] == 'unit_price')['currency'] = 'USD'
        pi = make_trade_candidate('PI', source)
        self.assertEqual(pi['items'][0]['unit'], 'PCS')
        self.assertEqual(pi['currency'], 'USD')

    def test_bare_quantity_never_gets_product_based_default_unit(self):
        pi = make_trade_candidate('PI', analysis(price='0.2', currency='USD'))
        self.assertEqual(pi['items'][0]['unit'], '')
        self.assertIn('item.unit', [field.key for field in missing_fields({'PI': pi})])

    def test_existing_candidate_with_explicit_per_pc_does_not_prompt_for_unit_or_source(self):
        raw = {'PI': {'currency': '', 'items': [{'product_name': 'Hanwha Solar Cell',
               'quantity': '2325860', 'unit': '', 'unit_price': '$0.2/pc',
               'price_basis': '', 'price_source': ''}]}}
        gaps = [field.key for field in missing_fields(raw)]
        for key in ('item.unit', 'item.price_basis', 'item.price_source', 'currency'):
            self.assertNotIn(key, gaps)

    def test_contract_only_missing_unit_has_usable_answer_and_suggested_status(self):
        contract = make_contract_candidate(analysis(price='0.2', currency='USD'), 'en')
        self.assertIn('item.unit', [field.key for field in missing_fields({'CONTRACT': contract})])
        revised = apply_answer({'CONTRACT': contract}, 'item.unit', 'PCS')['CONTRACT']
        term = next(t for t in revised['terms'] if t['key'] == 'unit')
        self.assertEqual(term['value'], 'PCS')
        self.assertEqual(term['status'], 'suggested')

    def test_contract_explicit_unit_retains_extraction_provenance(self):
        contract = make_contract_candidate(analysis(), 'en')
        term = next(t for t in contract['terms'] if t['key'] == 'unit')
        self.assertEqual(term['value'], 'PCS')
        self.assertEqual(term['source_refs'], ['user:1'])
        self.assertEqual(term['status'], 'suggested')

    def test_manual_price_without_source_does_not_block_solar_pi(self):
        pi = make_trade_candidate('PI', analysis())
        pi.update(seller={'legal_name': 'KE KOREA CO. LTD', 'address': 'Seoul'},
                  buyer={'legal_name': 'Example Buyer Ltd', 'address': 'Wuxi'},
                  incoterms='EXW Jincheon', payment_terms='T/T')
        self.assertNotIn('item.price_source', [field.key for field in missing_fields({'PI': pi})])
        checked = validate_and_calculate(pi)
        self.assertEqual(checked['blocking_issues'], [])
        self.assertEqual(checked['total'], '465172.00')

    def test_conflicting_explicit_units_and_currency_remain_blocking(self):
        from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values
        for updates in ({'quantity': '10 KG', 'unit': 'PCS'},
                        {'unit_price': '$0.2/pc', 'price_basis': 'KG'}):
            original = {'currency': 'USD', 'items': [dict(quantity='10', unit='PCS',
                        unit_price='0.2', price_basis='PCS') | updates]}
            normalized = normalize_trade_values(original)
            field = 'quantity' if 'quantity' in updates else 'unit_price'
            self.assertEqual(normalized['items'][0][field], original['items'][0][field])
        normalized = normalize_trade_values({'currency': 'KRW', 'items': [{'unit_price': '$0.2/pc'}]})
        self.assertEqual(normalized['currency'], 'KRW')
        self.assertEqual(normalized['items'][0]['unit_price'], '$0.2/pc')

    def test_price_denominator_cannot_override_declared_quantity_unit(self):
        pi = make_trade_candidate("PI", analysis(unit="KG", price="$0.2/pc"))
        self.assertEqual(pi["items"][0]["unit"], "KG")
        self.assertEqual(pi["items"][0]["unit_price"], "$0.2/pc")
        self.assertTrue(validate_and_calculate(pi)["blocking_issues"])

    def test_catalog_and_attached_pi_rules_are_still_required(self):
        from Quotation_KEKOREA.agent.ci_import import apply_document_prices, ci_import_issues
        ci = make_trade_candidate('CI', analysis())
        self.assertTrue(ci_import_issues(apply_document_prices(ci)))
        pi = make_trade_candidate('PI', analysis(), product_family='cosmetics')
        checked = validate_and_calculate(pi)
        self.assertTrue(any('verified price master' in issue for issue in checked['blocking_issues']))

    def test_quantity_answer_accepts_zero_but_price_must_stay_positive(self):
        self.assertEqual(apply_answer({'PI': {}}, 'item.quantity', '0')['PI']['items'][0]['quantity'], '0')
        with self.assertRaises(ValueError):
            apply_answer({'PI': {}}, 'item.unit_price', '0')

class LegacyCommercialValueTests(unittest.TestCase):
    def test_legacy_export_normalizes_advanced_json_before_validation(self):
        from unittest.mock import patch
        from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_master_trade_draft
        from Quotation_KEKOREA.tests.test_review_fields import complete_draft
        raw = dict(complete_draft(), currency='', items=[
            {'product_name': 'Hanwha Solar Cell', 'quantity': '2325860', 'unit': '',
             'unit_price': '$0.2/pc', 'price_basis': '', 'price_source': '', 'discount_percent': '0'}])
        with patch('Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.validate_and_calculate',
                   return_value={'blocking_issues': [], 'ready_for_issue': True}) as validate:
            with self.assertRaisesRegex(ValueError, '은행정보'):
                render_master_trade_draft('PI', raw, {})
            passed = validate.call_args.args[0]
            self.assertEqual(passed['items'][0]['unit_price'], '0.2')
            self.assertEqual(passed['items'][0]['unit'], 'PCS')
            self.assertEqual(passed['currency'], 'USD')
            self.assertEqual(raw['items'][0]['unit_price'], '$0.2/pc')

    def test_actual_pi_pdf_and_spreadsheet_render_without_price_source(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from PIL import Image
        from Quotation_KEKOREA.orchestration.workflows.legacy_document_exports import render_master_trade_draft, BANK_KEYS
        pi = make_trade_candidate('PI', analysis())
        pi.update(seller={'legal_name': 'KE KOREA CO. LTD', 'address': 'Test address'},
                  buyer={'legal_name': 'Example Buyer Ltd', 'address': 'Wuxi'},
                  incoterms='EXW Jincheon', payment_terms='T/T', doc_no='TEST-UNIT')
        pi.update(ship_to='N/A', country_of_origin='Korea', shipment_reference='N/A')
        for role in ('seller', 'buyer'):
            pi[role].update(contact='N/A', phone='N/A', email='N/A')
        pi['items'][0]['discount_percent'] = '0'
        # Restore the same advanced-JSON notation shown in the reported issue.
        pi['currency'] = ''
        pi['items'][0].update(unit='', unit_price='$0.2/pc', price_basis='')
        with TemporaryDirectory() as directory:
            seal = Path(directory) / 'synthetic-seal.png'
            Image.new('RGB', (10, 10), 'white').save(seal)
            with patch('Quotation_KEKOREA.orchestration.workflows.legacy_document_exports.resolve_company_seal',
                       return_value=(seal, None, None)):
                files = render_master_trade_draft('PI', pi, {'KEKOREA_USD_' + key: 'TEST ONLY' for key in BANK_KEYS})
        self.assertTrue(files['pdf']['content'].startswith(b'%PDF'))
        self.assertTrue(files['xlsx']['content'].startswith(b'PK'))
        self.assertIn(b'465,172.00', files['pdf']['content'])
        self.assertIn(b'PCS', files['pdf']['content'])
