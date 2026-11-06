"""Shared samples stay private; only reviewed guidance reaches retrieval."""
from copy import deepcopy
import io
import json
import unittest
import zipfile

from Quotation_KEKOREA.contracts.repository import ContractRepository
from Quotation_KEKOREA.tests import test_contract_repository as repo_fixtures


def tiny_docx():
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>PRIVATE Original Company and negotiated terms</w:t></w:r></w:p></w:body></w:document>')
    return data.getvalue()


class MemoryLibrary:
    def __init__(self):
        self.rows = {}
        self.files = {}

    def get_library_record(self, reference_id):
        return deepcopy(self.rows.get(reference_id))

    def list_library_records(self, approved_only=False):
        return [deepcopy(row) for row in self.rows.values()
                if not approved_only or row['extraction_status'] == 'library_approved']

    def save_reference(self, record):
        self.rows[record['id']] = deepcopy(record)
        return deepcopy(record)

    def update_library_record(self, reference_id, payload, *, expected_revision=None):
        self.rows[reference_id].update(deepcopy(payload))

    def private_bucket(self, bucket):
        return {'id': bucket, 'public': False}

    def upload_private_file(self, bucket, path, data, content_type):
        self.files[path] = data

    def download_private_file(self, bucket, path):
        return self.files[path]


class ContractLibraryTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryLibrary()

    def stage(self, kind='sale', title='Generic supply sample'):
        from Quotation_KEKOREA.contracts.library import register_sample
        return register_sample(self.repo, tiny_docx(), 'source.docx', title=title,
                               contract_types=[kind], language='en')

    def publish(self, row, text='Set measurable delivery and inspection acceptance conditions.', **kwargs):
        from Quotation_KEKOREA.contracts.library import publish_sample
        return publish_sample(self.repo, row['id'],
                              [{'locator': 'paragraph 1', 'topic': 'inspection 검수', 'text': text}],
                              env={}, **kwargs)

    def test_upload_is_private_verified_idempotent_and_pending(self):
        from Quotation_KEKOREA.contracts.library import register_sample, search_library
        first = self.stage()
        second = self.stage()
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.repo.files), 1)
        self.assertEqual(len(self.repo.rows), 1)
        self.assertIsNone(first['contract_id'])
        self.assertEqual(search_library(self.repo, {'contract_type': 'sale'}, 'inspection', env={})['references'], [])
        self.repo.private_bucket = lambda bucket: {'id': bucket, 'public': True}
        with self.assertRaisesRegex(ValueError, 'private'):
            register_sample(self.repo, b'new', 'new.docx', title='New', contract_types=['sale'], language='en')

    def test_korean_filename_is_kept_as_metadata_but_storage_key_is_ascii(self):
        from Quotation_KEKOREA.contracts.library import register_sample
        row = register_sample(self.repo, tiny_docx(), '물품공급계약서.docx', title='Supply sample',
                              contract_types=['sale'], language='ko')
        self.assertEqual(row['filename'], '물품공급계약서.docx')
        self.assertTrue(row['storage_path'].isascii())

    def test_retrieval_uses_only_reviewed_text_and_strict_type_filter(self):
        from Quotation_KEKOREA.contracts.library import search_library
        row = self.stage()
        self.publish(row)
        result = search_library(self.repo, {'contract_type': 'sale'}, 'inspection 검수', env={})
        self.assertEqual(len(result['references']), 1)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('source.docx', json.dumps(result))
        self.assertIn('paragraph 1', result['sources'][0]['locator'])
        self.assertEqual(search_library(self.repo, {'contract_type': 'investment_commission'}, 'inspection', env={})['references'], [])

    def test_publishing_needs_traceable_nonempty_anonymized_guidance(self):
        from Quotation_KEKOREA.contracts.library import publish_sample
        row = self.stage()
        for text in ('', 'Email private@example.com', 'Account 123456789012', 'Commission is 3% of receipts'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                publish_sample(self.repo, row['id'], [{'locator': 'paragraph 1', 'topic': 'Fees', 'text': text}], env={})
        with self.assertRaisesRegex(ValueError, 'location'):
            publish_sample(self.repo, row['id'], [{'locator': 'invented paragraph', 'topic': 'Fees',
                                                 'text': 'Confirm a fee formula for the current transaction.'}], env={})

    def test_embedding_failure_falls_back_without_fabricated_vectors(self):
        from Quotation_KEKOREA.contracts.library import search_library, read_manifest
        row = self.stage()
        self.publish(row)
        def broken(*args, **kwargs):
            raise RuntimeError('provider unavailable')
        result = search_library(self.repo, {'contract_type': 'sale'}, 'inspection',
                                env={'OPENAI_API_KEY': 'test'}, embedder=broken)
        self.assertEqual(result['mode'], 'keyword')
        self.assertTrue(result['notices'])
        self.assertFalse(read_manifest(self.repo.rows[row['id']]).chunks[0].embedding)

    def test_semantic_ranking_rejects_dimension_mismatch_and_inactive_samples(self):
        from Quotation_KEKOREA.contracts.library import search_library, publish_sample, set_sample_active
        row = self.stage()
        def embed(texts, **kwargs):
            return [[1.0, 0.0] for text in texts]
        publish_sample(self.repo, row['id'], [{'locator': 'paragraph 1', 'topic': 'inspection',
                                             'text': 'Define inspection before acceptance of delivered goods.'}],
                       env={}, embedder=embed)
        result = search_library(self.repo, {'contract_type': 'sale'}, 'quality', env={}, embedder=embed)
        self.assertEqual(result['mode'], 'hybrid')
        self.assertEqual(len(result['references']), 1)
        set_sample_active(self.repo, row['id'], False)
        self.assertEqual(search_library(self.repo, {'contract_type': 'sale'}, 'quality', env={}, embedder=embed)['references'], [])

    def test_repository_queries_cannot_mix_contract_and_library_references(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            return repo_fixtures.FakeResponse([])
        repo = ContractRepository({'SUPABASE_URL': 'https://example.supabase.co', 'SUPABASE_SECRET_KEY': 'secret'}, opener=opener)
        repo.list_library_records(approved_only=True)
        from urllib.parse import parse_qs, urlparse
        query = parse_qs(urlparse(calls[0]).query)
        self.assertEqual(query['contract_id'], ['is.null'])
        self.assertEqual(query['extraction_status'], ['eq.library_approved'])


if __name__ == '__main__':
    unittest.main()
