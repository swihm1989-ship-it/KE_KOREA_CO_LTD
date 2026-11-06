import json
import unittest

from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.service import analyze_trade, generate_draft
from Quotation_KEKOREA.tests import test_contract_service as service_fixtures


def commission_snapshot(language='en'):
    result = new_snapshot('example', 'investment_commission', language)
    result['title'] = 'Example Introduction'
    result['parties'] = [
        {'legal_name': 'KE KOREA CO., LTD.', 'country': 'KR', 'roles': ['fundraiser'], 'status': 'confirmed'},
        {'legal_name': 'Example Payer', 'country': 'ID', 'roles': ['commission_payer'], 'status': 'confirmed'},
    ]
    result['terms'] = [
        {'key': 'success_trigger', 'value': 'Actual receipt of each funding tranche in the Payer account', 'status': 'confirmed'},
        {'key': 'currency', 'value': 'USD', 'status': 'confirmed'},
    ]
    result['clauses'] = [{'id': 'scope', 'title': 'Scope', 'order': 1,
                          'sentences': [{'id': 's1', 'text': 'Provide introduction services.',
                                         'term_ids': [], 'source_refs': []}]}]
    return result


def example_env():
    return {f'KEKOREA_USD_{key}': value for key, value in {
        'BENEFICIARY': 'KE KOREA CO., LTD.', 'BANK_NAME': 'Example Bank',
        'BRANCH': 'Example Branch', 'SWIFT': 'EXAMPLE0',
        'ACCOUNT_NUMBER': 'TEST-ACCOUNT-ONLY', 'BANK_ADDRESS': 'Example bank address',
    }.items()}


class CommissionPolicyTests(unittest.TestCase):
    def policy(self, snapshot=None, env=None):
        from Quotation_KEKOREA.contracts.commission_policy import apply_payment_policy
        return apply_payment_policy(snapshot or commission_snapshot(), env=env if env is not None else example_env())

    def test_each_trigger_has_calendar_d7_tt_and_law_limited_overdue_interest(self):
        original = commission_snapshot()
        result = self.policy(original)
        text = '\n'.join(s['text'] for c in result['clauses'] for s in c['sentences'])
        for required in ('seven (7) calendar days', 'Telegraphic Transfer', 'each',
                         'Actual receipt of each funding tranche', 'TEST-ACCOUNT-ONLY',
                         'day following', 'written agreement', 'maximum', 'mandatory'):
            self.assertIn(required, text)
        self.assertNotIn('23%', text)
        self.assertNotIn('20%', text)
        self.assertNotIn('1.0%', text)
        self.assertEqual(len(original['clauses']), 1)
        self.assertEqual(result['title'], original['title'])

    def test_usd_account_not_inserted_for_another_currency_or_another_payee(self):
        for field in ('currency', 'payee'):
            with self.subTest(field=field):
                snapshot = commission_snapshot()
                if field == 'currency':
                    snapshot['terms'][1]['value'] = 'EUR'
                else:
                    snapshot['parties'][0]['legal_name'] = 'Other Company'
                result = self.policy(snapshot)
                self.assertNotIn('TEST-ACCOUNT-ONLY', json.dumps(result['clauses']))
                from Quotation_KEKOREA.contracts.commission_policy import payment_policy_issues
                self.assertTrue(payment_policy_issues(result))

    def test_missing_trigger_or_bank_is_visible_and_blocks_export(self):
        snapshot = commission_snapshot()
        snapshot['terms'][0]['status'] = 'suggested'
        result = self.policy(snapshot, {})
        from Quotation_KEKOREA.contracts.rules import validate_snapshot
        codes = {i['code'] for i in validate_snapshot(result, for_export=True)}
        self.assertIn('commission_payment_setup', codes)

    def test_reapply_is_idempotent_and_edits_or_term_changes_require_refresh(self):
        from Quotation_KEKOREA.contracts.commission_policy import payment_policy_issues
        result = self.policy()
        self.assertEqual(result, self.policy(result))
        original_issues = payment_policy_issues(result)
        result['clauses'][-1]['sentences'][0]['text'] = 'No late payment interest.'
        self.assertNotEqual(payment_policy_issues(result), original_issues)
        changed = self.policy()
        changed['terms'][0]['value'] = 'Signing a term sheet'
        self.assertTrue(any(i['code'] == 'commission_payment_changed' for i in payment_policy_issues(changed)))

    def test_korean_policy_and_sale_contracts(self):
        snapshot = commission_snapshot('ko')
        result = self.policy(snapshot)
        self.assertIn('7일', json.dumps(result, ensure_ascii=False))
        sale = dict(snapshot, contract_type='sale')
        self.assertEqual(self.policy(sale), sale)

    def test_legal_review_cannot_be_replaced_by_a_fixed_unverified_rate(self):
        from Quotation_KEKOREA.contracts.commission_policy import payment_policy_issues
        result = self.policy()
        codes = {i['code'] for i in payment_policy_issues(result)}
        self.assertIn('commission_interest_review', codes)
        result['terms'].extend([
            {'key': 'late_interest_legal_review', 'value': 'N/A', 'status': 'confirmed'},
            {'key': 'late_interest_source', 'value': 'N/A', 'status': 'confirmed'},
        ])
        self.assertIn('commission_interest_review', {i['code'] for i in payment_policy_issues(result)})

    def test_review_and_bank_changes_are_checked_again_at_export(self):
        from Quotation_KEKOREA.contracts.commission_policy import payment_policy_issues
        result = self.policy()
        result['terms'].extend([
            {'key': 'late_interest_legal_review', 'value': 'Reviewed payer and governing law for this obligation', 'status': 'confirmed'},
            {'key': 'late_interest_source', 'value': 'Example counsel memorandum, 2026-11-06', 'status': 'confirmed'},
        ])
        self.assertEqual(payment_policy_issues(result, env=example_env()), [])
        changed_env = dict(example_env(), KEKOREA_USD_ACCOUNT_NUMBER='CHANGED-TEST-ACCOUNT')
        self.assertIn('commission_bank_changed', {i['code'] for i in payment_policy_issues(result, env=changed_env)})


class CommissionContextTests(unittest.TestCase):
    def test_saved_bank_policy_is_not_sent_back_in_later_ai_analysis(self):
        from Quotation_KEKOREA.contracts.commission_policy import apply_payment_policy
        snapshot = apply_payment_policy(commission_snapshot(), env=example_env())
        fixture = service_fixtures.ContractServiceTests()
        captured = {}
        response = {'contract_type': 'investment_commission', 'parties': [], 'terms': [],
                    'questions': [], 'issues': []}
        analyze_trade([], snapshot, [], env={'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'},
                      client=fixture.opener_for(response, captured))
        self.assertNotIn('TEST-ACCOUNT-ONLY', captured['request'].data.decode())
        self.assertIn('TEST-ACCOUNT-ONLY', json.dumps(snapshot))

    def test_user_caution_can_be_cited_without_being_a_numeric_term(self):
        fixture = service_fixtures.ContractServiceTests()
        snapshot = commission_snapshot()
        response = {'title': 'Example', 'issues': [], 'clauses': [
            {'id': 'c1', 'title': 'Scope', 'order': 1, 'sentences': [
                {'id': 's1', 'text': 'Investment success is not guaranteed.', 'term_ids': [],
                 'source_refs': [{'kind': 'user', 'message_id': 'm1',
                                  'quote': 'Do not promise investment success.'}]}]}]}
        result = generate_draft(snapshot, [], env={'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'},
                                transaction_messages=[{'id': 'm1', 'role': 'user',
                                                       'content': 'Do not promise investment success.'}],
                                client=fixture.opener_for(response))
        self.assertEqual(result['clauses'][0]['sentences'][0]['text'], 'Investment success is not guaranteed.')

    def test_analysis_and_drafting_use_reference_themes_and_user_cautions(self):
        fixture = service_fixtures.ContractServiceTests()
        snapshot = commission_snapshot()
        captured = {}
        response = {'contract_type': 'investment_commission', 'parties': [], 'terms': [],
                    'questions': [], 'issues': []}
        analyze_trade([{'role': 'user', 'content': 'Do not promise investment success.'}], snapshot, [],
                      env={'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'},
                      client=fixture.opener_for(response, captured))
        request = json.loads(captured['request'].data)
        self.assertIn('reference only', request['instructions'])
        self.assertIn('non-circumvention', request['instructions'])
        self.assertIn('seven (7) calendar days', request['instructions'])
        response = {'title': 'Wrong title', 'issues': [], 'clauses': snapshot['clauses']}
        messages = [{'role': 'user', 'content': 'Protect actual receipts; do not promise investment success.'}]
        result = generate_draft(snapshot, [], env={'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test', **example_env()},
                                transaction_messages=messages, client=fixture.opener_for(response, captured))
        payload = json.loads(captured['request'].data)
        data = json.loads(payload['input'][0]['content'])
        self.assertEqual(data['transaction_messages'], messages)
        self.assertNotIn('TEST-ACCOUNT-ONLY', captured['request'].data.decode())
        self.assertIn('TEST-ACCOUNT-ONLY', json.dumps(result))
