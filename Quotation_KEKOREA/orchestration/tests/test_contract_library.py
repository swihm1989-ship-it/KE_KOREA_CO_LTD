"""Existing private Supabase contract library is accessed strictly read-only."""
import copy
import unittest
from unittest.mock import Mock

from Quotation_KEKOREA.orchestration.adapters.contract_library import (
    read_contract_list, read_contract_versions, inspect_contract_version,
)


class ContractLibraryTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.list_contracts.return_value = [
            {"id": "contract-one", "title": "Supply Agreement", "language": "en", "status": "draft", "current_revision": 3},
            {"id": "contract-two", "title": "커미션 계약", "language": "ko", "status": "draft", "current_revision": 1}
        ]
        self.snapshot = {"contract_id": "contract-one", "revision": 3, "contract_type": "sale",
                         "language": "en", "parties": [], "terms": [], "clauses": [],
                         "issues": [], "reference_ids": [], "omissions": {}}
        self.repo.load_contract.return_value = [
            {"revision": 3, "snapshot": self.snapshot, "change_summary": "Updated", "created_at": "2026-11-11"},
            {"revision": 2, "snapshot": {**self.snapshot, "revision": 2}, "change_summary": "Initial", "created_at": "2026-11-10"}]

    def test_list_search_korean_english_and_filter(self):
        out = read_contract_list(self.repo, keyword="커미션", language="ko")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "contract-two")
        self.repo.list_contracts.assert_called_once()

    def test_rejects_loading_unknown_id_without_calling_load(self):
        with self.assertRaises(ValueError):
            read_contract_versions(self.repo, "not-known")
        self.repo.load_contract.assert_not_called()

    def test_loads_versions_without_mutating_snapshots(self):
        before = copy.deepcopy(self.snapshot)
        rows = read_contract_versions(self.repo, "contract-one")
        self.assertEqual([r["revision"] for r in rows], [3, 2])
        self.assertEqual(self.snapshot, before)
        self.repo.load_contract.assert_called_once_with("contract-one")
        self.repo.request.assert_not_called()

    def test_rule_based_inspection_has_unresolved_findings_not_ai_claim(self):
        before = copy.deepcopy(self.snapshot)
        report = inspect_contract_version(self.snapshot)
        self.assertTrue(report["issues"])
        self.assertEqual(report["method"], "existing_deterministic_rules")
        self.assertEqual(self.snapshot, before)

    def test_no_mutation_methods_invoked(self):
        read_contract_list(self.repo)
        read_contract_versions(self.repo, "contract-one")
        for name in ("create_contract", "commit_revision", "save_export", "delete_export", "delete_private_file"):
            getattr(self.repo, name).assert_not_called()


if __name__ == "__main__":
    unittest.main()
