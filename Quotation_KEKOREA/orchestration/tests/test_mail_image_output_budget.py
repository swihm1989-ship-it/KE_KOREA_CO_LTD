"""Regression coverage for long email order images and incomplete OpenAI output.

No API requests or genuine trade/order data are used.
"""
import json
import unittest
import urllib.error
from unittest.mock import patch

from Quotation_KEKOREA.agent.extractor import extract_trade_data


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


IMAGE = [{"name": "synthetic-order.png", "mime_type": "image/png", "data": b"synthetic"}]
INCOMPLETE = {
    "status": "incomplete",
    "incomplete_details": {"reason": "max_output_tokens"},
    "output": [{"content": [{"type": "output_text", "text": '{"items": [}'}]}],
}
COMPLETE = {
    "status": "completed",
    "output": [{"content": [{"type": "output_text", "text": '{"items": [{"product_name": "Synthetic Cream", "quantity": "10"}]}'}]}],
}


class MailImageOutputBudgetTests(unittest.TestCase):
    def test_image_orders_get_budget_for_structured_multi_item_output(self):
        requests = []

        def opener(request, timeout):
            requests.append(json.loads(request.data))
            return Response(COMPLETE)

        draft = extract_trade_data(
            "Make a PI from the attached twenty-row table",
            images=IMAGE, env={"OPENAI_API_KEY": "fake-key"}, opener=opener,
            requested_document_type="PI",
        )
        self.assertEqual(len(requests), 1)
        self.assertGreaterEqual(requests[0]["max_output_tokens"], 16000)
        self.assertEqual(requests[0]["input"][0]["content"][1]["type"], "input_image")
        self.assertEqual(draft["items"][0]["product_name"], "Synthetic Cream")

    def test_max_output_incomplete_retries_once_with_same_source_and_larger_budget(self):
        requests = []
        responses = [INCOMPLETE, COMPLETE]

        def opener(request, timeout):
            requests.append(json.loads(request.data))
            return Response(responses.pop(0))

        result = extract_trade_data(
            "Produce a PI from this order image",
            images=IMAGE, env={"OPENAI_API_KEY": "fake-key"}, opener=opener,
            requested_document_type="PI",
        )
        self.assertEqual(result["items"][0]["quantity"], "10")
        self.assertEqual(len(requests), 2)
        self.assertGreater(requests[1]["max_output_tokens"], requests[0]["max_output_tokens"])
        for field in ("model", "input", "instructions", "text"):
            self.assertEqual(requests[0][field], requests[1][field])

    def test_second_incomplete_does_not_issue_third_request_or_use_partial_json(self):
        requests = []

        def opener(request, timeout):
            requests.append(json.loads(request.data))
            return Response(INCOMPLETE)

        with self.assertRaisesRegex(RuntimeError, "response limit"):
            extract_trade_data(
                "Produce a PI from this order image",
                images=IMAGE, env={"OPENAI_API_KEY": "fake-key"}, opener=opener,
                requested_document_type="PI",
            )
        self.assertEqual(len(requests), 2)

    def test_image_po_waits_longer_than_90_seconds_for_openai_response(self):
        observed = []

        def opener(request, timeout):
            observed.append(timeout)
            return Response(COMPLETE)

        result = extract_trade_data(
            "Create an ECLADO PO for twenty products from the photo",
            images=IMAGE, env={"OPENAI_API_KEY": "synthetic"},
            opener=opener, requested_document_type="PO")
        self.assertEqual(result["items"][0]["quantity"], "10")
        self.assertEqual(observed, [180])

    def test_temporary_timeout_retries_once_with_identical_order_evidence(self):
        observed = []

        def opener(request, timeout):
            observed.append((json.loads(request.data), timeout))
            if len(observed) == 1:
                raise urllib.error.URLError(TimeoutError("never-log-this-private-key"))
            return Response(COMPLETE)

        with patch("Quotation_KEKOREA.agent.extractor.time.sleep") as sleep:
            result = extract_trade_data(
                "Create PO with ECLADO purchase terms",
                images=IMAGE, env={"OPENAI_API_KEY": "synthetic"},
                opener=opener, requested_document_type="PO")
        self.assertEqual(result["items"][0]["product_name"], "Synthetic Cream")
        self.assertEqual(len(observed), 2)
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[0][1], 180)
        sleep.assert_called_once()

    def test_persistent_timeout_is_identified_as_server_side_and_sanitized(self):
        attempts = []

        def opener(request, timeout):
            attempts.append(timeout)
            raise urllib.error.URLError(TimeoutError("secret-upstream-token-should-not-leak"))

        with patch("Quotation_KEKOREA.agent.extractor.time.sleep"):
            with self.assertRaises(RuntimeError) as error:
                extract_trade_data(
                    "Create PO from 20-item source",
                    images=IMAGE, env={"OPENAI_API_KEY": "synthetic"},
                    opener=opener, requested_document_type="PO")
        self.assertEqual(attempts, [180, 180])
        self.assertIn("서버", str(error.exception))
        self.assertIn("시간 초과", str(error.exception))
        self.assertNotIn("secret-upstream", str(error.exception))

    def test_persistent_network_error_is_reported_without_blame_on_phone(self):
        attempts = []

        def opener(request, timeout):
            attempts.append(timeout)
            raise urllib.error.URLError("private DNS hostname internal-db.net")

        with patch("Quotation_KEKOREA.agent.extractor.time.sleep"):
            with self.assertRaises(RuntimeError) as error:
                extract_trade_data("Create PI", env={"OPENAI_API_KEY": "synthetic"}, opener=opener)
        self.assertEqual(attempts, [90, 90])
        self.assertIn("Master 서버", str(error.exception))
        self.assertNotIn("private DNS", str(error.exception))

    def test_other_incomplete_reason_is_not_retried(self):
        requests = []
        def opener(request, timeout):
            requests.append(json.loads(request.data))
            return Response({
                "status": "incomplete", "incomplete_details": {"reason": "content_filter"},
                "output": [],
            })

        with self.assertRaisesRegex(RuntimeError, "content_filter"):
            extract_trade_data(
                "Prepare the PI", images=IMAGE,
                env={"OPENAI_API_KEY": "fake-key"}, opener=opener,
            )
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
