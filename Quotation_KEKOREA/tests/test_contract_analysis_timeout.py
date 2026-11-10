import unittest
import urllib.error
from copy import deepcopy

from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.service import _call, analyze_trade
from Quotation_KEKOREA.tests.test_contract_service import FakeResponse


class ContractAnalysisTimeoutTests(unittest.TestCase):
    env = {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test"}

    def test_analysis_allows_longer_response_without_changing_model_or_snapshot(self):
        snapshot = new_snapshot("test-timeout", "sale", "en")
        original = deepcopy(snapshot)
        observed = []

        def opener(request, timeout):
            observed.append(timeout)
            return FakeResponse({"contract_type": "sale", "parties": [],
                                 "terms": [], "questions": [], "issues": []})

        analyze_trade([], snapshot, [], env=self.env, client=opener)
        self.assertEqual(observed, [180])
        self.assertEqual(snapshot, original)

    def test_timeout_is_identified_without_exposing_request_data(self):
        for error in (TimeoutError("private data"),
                      urllib.error.URLError(TimeoutError("private data"))):
            with self.subTest(error=type(error).__name__):
                def opener(request, timeout):
                    raise error

                with self.assertRaisesRegex(RuntimeError, "timed out after 180 seconds") as caught:
                    _call("Return JSON.", {}, env=self.env, opener=opener, timeout=180)
                self.assertNotIn("private data", str(caught.exception))

    def test_other_calls_keep_default_timeout_and_connection_error(self):
        observed = []

        def opener(request, timeout):
            observed.append(timeout)
            raise urllib.error.URLError("private network details")

        with self.assertRaisesRegex(RuntimeError, "could not be reached") as caught:
            _call("Return JSON.", {}, env=self.env, opener=opener)
        self.assertEqual(observed, [90])
        self.assertNotIn("private network details", str(caught.exception))
