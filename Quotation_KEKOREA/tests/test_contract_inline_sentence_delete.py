"""Inline sentence deletion commits only after explicit confirmation."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts.editing import propose_sentence_deletion, RevisionConflict
from Quotation_KEKOREA.contracts.ui import _commit_confirmed_sentence_deletion
from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot


class _Repo:
    def __init__(self, snapshot):
        self.saved = []
        self.annotations = []
        self.snapshot = snapshot

    def commit_revision(self, contract_id, expected_revision, snapshot, summary):
        if expected_revision != self.snapshot["revision"]:
            raise RevisionConflict("Stale revision")
        self.saved.append((contract_id, expected_revision, deepcopy(snapshot), summary))
        self.snapshot = deepcopy(snapshot)
        return {"revision": snapshot["revision"]}

    def save_annotation(self, data):
        self.annotations.append(deepcopy(data))


class InlineSentenceDeleteTests(unittest.TestCase):
    def test_delete_is_only_proposed_before_explicit_confirmation(self):
        snapshot = example_snapshot()
        original = deepcopy(snapshot)
        repo = _Repo(snapshot)
        proposal = propose_sentence_deletion(snapshot, "s1")
        self.assertEqual(repo.saved, [])
        self.assertEqual(snapshot, original)
        self.assertEqual(proposal["changes"][0]["original_text"], "첫 번째 계약 문장입니다.")

    def test_confirm_commits_one_revision_and_preserves_other_sentences(self):
        snapshot = example_snapshot()
        repo = _Repo(snapshot)
        proposal = propose_sentence_deletion(snapshot, "s1")
        saved = _commit_confirmed_sentence_deletion(repo, snapshot, proposal)
        self.assertEqual(saved["revision"], snapshot["revision"] + 1)
        self.assertEqual(len(repo.saved), 1)
        self.assertEqual(repo.saved[0][1], snapshot["revision"])
        self.assertEqual([s["id"] for s in saved["clauses"][0]["sentences"]], ["s2"])
        self.assertEqual(snapshot["clauses"][0]["sentences"][0]["id"], "s1")
        self.assertEqual(repo.annotations[0]["status"], "applied")

    def test_stale_deletion_cannot_commit(self):
        snapshot = example_snapshot()
        repo = _Repo(snapshot)
        proposal = propose_sentence_deletion(snapshot, "s1")
        proposal["base_revision"] = snapshot["revision"] - 1
        with self.assertRaises(RevisionConflict):
            _commit_confirmed_sentence_deletion(repo, snapshot, proposal)
        self.assertEqual(repo.saved, [])

    def test_annotation_failure_does_not_repeat_succeeded_commit(self):
        snapshot = example_snapshot()
        repo = _Repo(snapshot)
        proposal = propose_sentence_deletion(snapshot, "s1")
        from Quotation_KEKOREA.contracts.repository import ContractRepositoryError
        def broken_annotation(*args, **kwargs):
            raise ContractRepositoryError("annotation unavailable")
        repo.save_annotation = broken_annotation
        with patch("Quotation_KEKOREA.contracts.ui.st.session_state", {}):
            saved = _commit_confirmed_sentence_deletion(repo, snapshot, proposal)
        self.assertEqual(saved["revision"], 5)
        self.assertEqual(len(repo.saved), 1)


if __name__ == "__main__":
    unittest.main()
