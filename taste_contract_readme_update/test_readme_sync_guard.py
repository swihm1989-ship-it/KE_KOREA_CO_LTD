import unittest
from scripts.check_readme_sync import READMES, missing_docs, requires_docs


class DocumentationGuardTests(unittest.TestCase):
    def test_source_changes_require_every_readme(self):
        self.assertEqual(missing_docs({'Quotation_KEKOREA/contracts/ui.py'}), sorted(READMES))

    def test_five_readmes_satisfy_requirement(self):
        self.assertEqual(missing_docs(READMES | {'Quotation_KEKOREA/contracts/ui.py'}), [])

    def test_deletion_and_config_changes_are_detected(self):
        self.assertTrue(requires_docs('Quotation_KEKOREA/agent/pricing.py'))
        self.assertTrue(requires_docs('Quotation_KEKOREA/supabase/migrations/abc.sql'))

    def test_doc_only_and_test_only_commits_need_no_five_file_update(self):
        self.assertEqual(missing_docs({'Quotation_KEKOREA/tests/test_contract_ui.py',
                                       'Quotation_KEKOREA/Team/README.md'}), [])


if __name__ == '__main__':
    unittest.main()
