"""Regression coverage for long email order images and incomplete OpenAI output.

No API requests or genuine trade/order data are used.
"""
import json
import unittest

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
