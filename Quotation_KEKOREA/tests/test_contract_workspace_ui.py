"""Exercise contract classification and user titles without external services."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import Quotation_KEKOREA.contracts.ui
from Quotation_KEKOREA.contracts.models import new_snapshot


class MemoryContracts:
    def __init__(self):
        self.records = {}
        self.revisions = {}

    def create_contract(self, record, snapshot):
        contract_id = snapshot['contract_id']
        self.records[contract_id] = dict(record, id=contract_id, current_revision=1)
        self.revisions[contract_id] = [dict(revision=1, snapshot=deepcopy(snapshot))]
        return dict(id=contract_id, current_revision=1)

    def commit_revision(self, contract_id, expected_revision, snapshot, summary):
        assert self.records[contract_id]['current_revision'] == expected_revision
        revision = expected_revision + 1
        saved = dict(deepcopy(snapshot), revision=revision)
        self.revisions[contract_id].append(dict(revision=revision, snapshot=saved))
        self.records[contract_id].update(title=saved['title'],
                                        contract_type=saved['contract_type'], current_revision=revision)
        return dict(revision=revision)

    def list_contracts(self):
        return list(self.records.values())

    def load_contract(self, contract_id):
        return self.revisions[contract_id]

    def list_messages(self, contract_id):
        return []

    def contract_references(self, contract_id):
        return []

    def list_exports(self, contract_id):
        return []

    def delete_contract(self, contract_id):
        self.records.pop(contract_id, None)
        self.revisions.pop(contract_id, None)

    def list_preferred_clauses(self):
        return []

    def list_annotations(self, contract_id):
        return []


class ContractWorkspaceUiTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryContracts()
        patcher = patch('Quotation_KEKOREA.contracts.ui._repository', return_value=self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.at = AppTest.from_string(
            "from Quotation_KEKOREA.contracts.ui import render_contract_page\n"
            "render_contract_page('계약서 만들기', {})")

    def run_app(self):
        self.at.run(timeout=15)
        self.assertFalse(self.at.exception)

    def seed(self, contract_id, contract_type, title):
        snapshot = dict(new_snapshot(contract_id, contract_type, 'en'), title=title)
        self.repo.create_contract(dict(title=title, contract_type=contract_type, language='en'), snapshot)

    def test_new_investment_commission_uses_selected_type_and_exact_title(self):
        self.run_app()
        selectors = [item for item in self.at.selectbox if item.label == '계약 유형']
        self.assertEqual(len(selectors), 1)
        self.assertIsNone(selectors[0].value)
        selectors[0].set_value('investment_commission')
        next(item for item in self.at.text_input if item.label == '계약 제목').set_value('Example FI Agreement')
        next(item for item in self.at.radio if item.label == '계약서 출력 언어').set_value('en')
        next(item for item in self.at.button if item.label == '새 계약 시작').click()
        self.run_app()
        active = self.at.session_state['contract_active_id']
        snapshot = self.at.session_state[f'contract_snapshot_{active}']
        self.assertEqual(snapshot['contract_type'], 'investment_commission')
        self.assertEqual(snapshot['title'], 'Example FI Agreement')
        self.assertIn('## Example FI Agreement', [item.value for item in self.at.markdown])

    def test_missing_type_does_not_create_a_sale_contract(self):
        self.run_app()
        next(item for item in self.at.text_input if item.label == '계약 제목').set_value('Example FI')
        next(item for item in self.at.button if item.label == '새 계약 시작').click()
        self.run_app()
        self.assertFalse(self.repo.records)
        self.assertTrue(self.at.error)

    def test_all_types_can_be_opened_from_one_menu_without_title_decorations(self):
        self.seed('sale', 'sale', 'Example Supply')
        self.seed('investment', 'investment_commission', 'Example FI')
        self.seed('trade', 'trade_commission', 'Example Referral')
        self.run_app()
        titles = {item.label for item in self.at.button}
        self.assertTrue({'Example Supply', 'Example FI', 'Example Referral'}.issubset(titles))
        next(item for item in self.at.button if item.label == 'Example FI').click()
        self.run_app()
        self.assertIn('## Example FI', [item.value for item in self.at.markdown])
        self.assertTrue(any('투자 대상 프로젝트/법인' in item.value['항목'].tolist()
                            for item in self.at.dataframe if '항목' in item.value.columns))

    def test_saved_contract_list_renders_without_undefined_options(self):
        self.seed('first', 'sale', 'First contract')
        self.seed('second', 'trade_commission', 'Second contract')
        self.run_app()
        labels = [item.label for item in self.at.button]
        self.assertIn('First contract', labels)
        self.assertIn('Second contract', labels)
        self.assertEqual(labels.count('X'), 2)

    def test_contract_chat_history_keeps_older_messages_collapsed(self):
        from Quotation_KEKOREA.contracts.ui import _chat_history_window
        messages = [{"role": "user", "content": str(i)} for i in range(25)]
        older, recent = _chat_history_window(messages)
        self.assertEqual(len(older), 5)
        self.assertEqual(len(recent), 20)
        self.assertEqual(recent[0]["content"], "5")
        self.assertEqual(recent[-1]["content"], "24")
        self.assertEqual(len(messages), 25)

    def test_contract_delete_requires_confirmation(self):
        self.seed('delete-me', 'sale', 'Delete this contract')
        self.run_app()
        next(item for item in self.at.button if item.label == 'X').click()
        self.run_app()
        self.assertTrue(any('정말 삭제하시겠습니까?' in item.value
                            for item in self.at.warning))
        self.assertIn('delete-me', self.repo.records)
        next(item for item in self.at.button if item.label == '확인').click()
        self.run_app()
        self.assertNotIn('delete-me', self.repo.records)

    def test_contract_delete_can_be_cancelled(self):
        self.seed('keep-me', 'sale', 'Keep this contract')
        self.run_app()
        next(item for item in self.at.button if item.label == 'X').click()
        self.run_app()
        next(item for item in self.at.button if item.label == '취소').click()
        self.run_app()
        self.assertIn('keep-me', self.repo.records)

    def test_existing_misclassified_contract_can_be_corrected_without_renaming(self):
        self.seed('existing', 'sale', 'Example FI Agreement')
        self.at.session_state['contract_active_id'] = 'existing'
        self.run_app()
        selectors = [item for item in self.at.selectbox if item.label == '현재 계약 유형']
        self.assertEqual(len(selectors), 1)
        selectors[0].set_value('investment_commission')
        next(item for item in self.at.button if item.label == '계약 정보 저장').click()
        self.run_app()
        saved = self.repo.load_contract('existing')[-1]['snapshot']
        self.assertEqual(saved['contract_type'], 'investment_commission')
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(saved['title'], 'Example FI Agreement')
        self.assertIn('## Example FI Agreement', [item.value for item in self.at.markdown])

    def test_type_correction_preserves_draft_and_requires_review(self):
        self.seed('existing', 'sale', 'Example FI')
        original = self.repo.revisions['existing'][0]['snapshot']
        original['clauses'] = [{'id': 'c1', 'title': 'Scope', 'order': 1,
                                'sentences': [{'id': 's1', 'text': 'Agreed scope.',
                                               'term_ids': [], 'source_refs': []}]}]
        original['terms'] = [{'id': 't1', 'key': 'project', 'value': 'Example Project',
                              'status': 'confirmed'}]
        self.at.session_state['contract_active_id'] = 'existing'
        self.run_app()
        next(item for item in self.at.selectbox if item.label == '현재 계약 유형').set_value('investment_commission')
        next(item for item in self.at.button if item.label == '계약 정보 저장').click()
        self.run_app()
        saved = self.repo.load_contract('existing')[-1]['snapshot']
        self.assertEqual(saved['clauses'], original['clauses'])
        self.assertEqual(saved['terms'][0]['value'], 'Example Project')
        from Quotation_KEKOREA.contracts.rules import validate_snapshot
        self.assertIn('contract_type_changed', [issue['code'] for issue in validate_snapshot(saved, for_export=True)])
