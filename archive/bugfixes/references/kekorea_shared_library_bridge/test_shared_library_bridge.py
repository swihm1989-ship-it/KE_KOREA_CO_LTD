"""Offline tests: no real Supabase, model, or external API calls."""
import hashlib
import unittest
from copy import deepcopy

from Quotation_KEKOREA.contracts.library import read_manifest, search_library
from Quotation_KEKOREA.tests.test_contract_library import MemoryLibrary, tiny_docx
from Quotation_KEKOREA.contracts.promote_reference import promote_contract_reference


class Repo(MemoryLibrary):
    def __init__(self):
        super().__init__()
        self.source = tiny_docx()
        self.path = 'contract-1/references/' + hashlib.sha256(self.source).hexdigest() + '/source.docx'
        self.files[self.path] = self.source
        self.reference = dict(id='ref-1', contract_id='contract-1', filename='source.docx',
                              storage_path=self.path, content_hash=hashlib.sha256(self.source).hexdigest(),
                              extraction_status='extracted')

    def contract_references(self, contract_id):
        return [deepcopy(self.reference)] if contract_id == 'contract-1' else []


class SharedPromotionTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def promote(self):
        return promote_contract_reference(self.repo, 'contract-1', 'ref-1',
                                          title='검수 절차 일반 참고', contract_types=['sale'], language='ko')

    def test_promote_creates_pending_shared_copy_without_altering_private_original(self):
        record = self.promote()
        self.assertIsNone(record['contract_id'])
        self.assertEqual(record['extraction_status'], 'library_pending')
        self.assertEqual(read_manifest(record).approved, False)
        self.assertEqual(self.repo.files[self.repo.path], self.repo.source)
        self.assertEqual(self.repo.reference['contract_id'], 'contract-1')
        self.assertEqual(search_library(self.repo, {'contract_type': 'sale'}, 'inspection', env={})['references'], [])
        self.assertEqual(self.promote()['id'], record['id'])

    def test_cannot_promote_other_contract_or_unknown_reference(self):
        with self.assertRaises(ValueError):
            promote_contract_reference(self.repo, 'another-contract', 'ref-1',
                                       title='safe', contract_types=['sale'], language='ko')
        with self.assertRaises(ValueError):
            promote_contract_reference(self.repo, 'contract-1', 'nope',
                                       title='safe', contract_types=['sale'], language='ko')

    def test_hash_mismatch_blocks_publication(self):
        self.repo.files[self.repo.path] = b'tampered'
        with self.assertRaisesRegex(ValueError, '해시'):
            self.promote()
        self.assertFalse(self.repo.rows)

    def test_wrong_storage_path_blocks_promotion(self):
        self.repo.reference['storage_path'] = 'another-contract/references/secret.docx'
        with self.assertRaisesRegex(ValueError, '경로'):
            self.promote()
        self.assertFalse(self.repo.rows)


if __name__ == '__main__':
    unittest.main()
