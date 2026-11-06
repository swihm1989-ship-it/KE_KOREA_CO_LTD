import json
import urllib.error
import unittest
from io import BytesIO

from Quotation_KEKOREA.contracts.repository import (
    ContractRepository, ContractRepositoryError,
)


class FakeResponse:
    def __init__(self, value=None, status=200):
        self.value = value
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return b"" if self.value is None else json.dumps(self.value).encode()


class ContractRepositoryTests(unittest.TestCase):
    def test_revision_commit_uses_expected_revision_and_server_key_header(self):
        captured = {}
        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["authorization"] = request.get_header("Authorization")
            return FakeResponse({"revision": 2})
        repo = ContractRepository({
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "server-only",
        }, opener=opener)
        result = repo.commit_revision("contract-id", 1, {"revision": 1}, "edit")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(captured["body"]["p_expected_revision"], 1)
        self.assertEqual(captured["authorization"], "Bearer server-only")
        self.assertNotIn("server-only", captured["url"])

    def test_revision_conflict_is_reported_without_success_shape(self):
        repo = ContractRepository({
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "server-only",
        }, opener=lambda *_args, **_kwargs: FakeResponse({"error": "revision_conflict"}))
        with self.assertRaisesRegex(ContractRepositoryError, "changed in another session"):
            repo.commit_revision("contract-id", 1, {"revision": 1}, "stale")

    def test_http_conflict_is_reported_as_stale_revision(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 409, "conflict", {}, BytesIO())
        repo = ContractRepository({
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "server-only",
        }, opener=opener)
        with self.assertRaisesRegex(ContractRepositoryError, "changed in another session"):
            repo.commit_revision("contract-id", 1, {"revision": 1}, "stale")

    def test_invalid_project_url_and_missing_secret_are_rejected(self):
        with self.assertRaises(ValueError):
            ContractRepository({"SUPABASE_URL": "http://example.supabase.co",
                                "SUPABASE_SECRET_KEY": "secret"})
        with self.assertRaises(ValueError):
            ContractRepository({"SUPABASE_URL": "https://example.supabase.co"})


if __name__ == "__main__":
    unittest.main()
