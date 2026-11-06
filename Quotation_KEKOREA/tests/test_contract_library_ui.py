import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from Quotation_KEKOREA.tests.test_contract_library import MemoryLibrary, tiny_docx
from Quotation_KEKOREA.contracts.library import register_sample
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.tests.test_contract_workspace_ui import MemoryContracts
from Quotation_KEKOREA.tests import test_contract_service as service_fixtures
import json
import urllib.error


class LibraryAdminUiTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryLibrary()
        register_sample(self.repo, tiny_docx(), 'secret.docx', title='Safe generic sample',
                        contract_types=['sale'], language='en')
        patcher = patch('Quotation_KEKOREA.contracts.repository.ContractRepository', return_value=self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.at = AppTest.from_string(
            "from Quotation_KEKOREA.contracts.library_ui import render_library_admin\n"
            "from Quotation_KEKOREA.contracts.repository import ContractRepository\n"
            "render_library_admin(ContractRepository({}), {'CONTRACT_LIBRARY_ADMIN_TOKEN': 'example-admin'})")

    def test_originals_require_separate_admin_auth_and_logout_hides_them(self):
        self.at.run(timeout=15)
        self.assertFalse(self.at.exception)
        self.assertFalse(any('PRIVATE' in item.value for item in self.at.text))
        next(item for item in self.at.text_input if item.label == '샘플 관리 키').set_value('example-admin')
        next(item for item in self.at.button if item.label == '관리 시작').click()
        self.at.run(timeout=15)
        self.assertFalse(self.at.exception)
        self.assertTrue(any('PRIVATE' in item.value for item in self.at.text))
        next(item for item in self.at.button if item.label == '샘플 관리 종료').click()
        self.at.run(timeout=15)
        self.assertFalse(self.at.exception)
        self.assertFalse(any('PRIVATE' in item.value for item in self.at.text))


class LibraryDraftIntegrationTests(unittest.TestCase):
    def test_analysis_and_draft_retrieve_reviewed_guidance_and_persist_sources(self):
        from Quotation_KEKOREA.contracts.library import publish_sample
        class CombinedRepo(MemoryContracts, MemoryLibrary):
            def __init__(self):
                MemoryContracts.__init__(self)
                MemoryLibrary.__init__(self)
                self.messages = []

            def add_message(self, contract_id, role, content):
                self.messages.append(dict(id=str(len(self.messages)), role=role, content=content))

            def list_messages(self, contract_id):
                return self.messages

        repo = CombinedRepo()
        row = register_sample(repo, tiny_docx(), 'secret.docx', title='Generic inspection reference',
                              contract_types=['sale'], language='en')
        publish_sample(repo, row['id'], [{'locator': 'paragraph 1', 'topic': 'inspection',
                                         'text': 'Agree objective inspection criteria and a reasonable written response process.'}], env={})
        snapshot = dict(new_snapshot('contract', 'sale', 'en'), title='Example Supply')
        repo.create_contract(dict(title=snapshot['title'], contract_type='sale', language='en'), snapshot)
        captured = []
        def opener(request, **kwargs):
            if request.full_url.endswith('/embeddings'):
                raise urllib.error.URLError('synthetic offline test')
            data = json.loads(json.loads(request.data)['input'][0]['content'])
            captured.append(data)
            if 'current_snapshot' in data:
                response = dict(contract_type='sale', parties=[], terms=[], questions=[], issues=[])
            else:
                reference = data['reference_context'][0]
                response = {'title': 'AI must not rename this', 'issues': [], 'clauses': [
                    {'id': 'c1', 'title': 'Inspection', 'order': 1, 'sentences': [
                        {'id': 's1', 'text': 'The parties shall confirm objective inspection criteria.', 'term_ids': [],
                         'source_refs': [{'kind': 'reference', 'document_id': reference['id'],
                                         'quote': reference['extracted_text']}]}]}]}
            return service_fixtures.FakeResponse(response)
        with patch('Quotation_KEKOREA.contracts.ui._repository', return_value=repo), \
             patch('urllib.request.urlopen', side_effect=opener):
            at = AppTest.from_string("from Quotation_KEKOREA.contracts.ui import render_contract_page\n"
                                    "render_contract_page('계약서 만들기', {'OPENAI_API_KEY':'test','OPENAI_MODEL':'test'})")
            at.session_state['contract_active_id'] = 'contract'
            at.run(timeout=15)
            self.assertFalse(at.exception)
            # next(item for item in at.text_area if item.label == '거래 내용 / 추가 조건 / 답변').set_value('inspection process')
            # at.checkbox(key='contract_ai_consent_contract').check()
            # next(item for item in at.button if item.label == '거래 내용 분석 및 조건 정리').click()
            at.checkbox(key='contract_ai_consent_contract').check().run(timeout=15)
            at.chat_input(key='contract_prompt_contract').set_value(
    'Please draft a contract with an inspection process'
).run(timeout=15)
            at.run(timeout=15)
            self.assertFalse(at.exception)
            # An explicit draft request now generates the draft during chat processing.
            # The manual generate button is intentionally disabled after clauses exist.
            self.assertTrue(repo.load_contract('contract')[-1]['snapshot']['clauses'])
        self.assertEqual(len(captured), 2)
        self.assertNotIn('PRIVATE', json.dumps(captured))
        saved = repo.load_contract('contract')[-1]['snapshot']
        self.assertEqual(saved['title'], 'Example Supply')
        self.assertEqual(saved['library_sources'][0]['title'], 'Generic inspection reference')
        self.assertTrue(saved['clauses'][0]['sentences'][0]['source_refs'][0]['document_id'].startswith('library:'))
        