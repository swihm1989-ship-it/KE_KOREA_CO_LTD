"""Regress OpenAI JSON mode HTTP 400 for scanned-reference OCR."""
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image
from Quotation_KEKOREA.contracts.service import extract_reference_page


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *args):
        body = {"output": [{"content": [{"type": "output_text", "text": json.dumps({"text": "Example", "uncertain": []})}]}]}
        return json.dumps(body).encode("utf-8")


class ReferenceOCRJSONTests(unittest.TestCase):
    def test_json_mode_mentions_json_in_input_message(self):
        image = Image.new("RGB", (100, 100), "white")
        file = io.BytesIO()
        image.save(file, format="PNG")
        seen = []

        def opener(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            seen.append(payload)
            return Response()

        result = extract_reference_page(file.getvalue(), 1, env={"OPENAI_API_KEY": "test", "OPENAI_MODEL": "mock"}, client=opener)
        self.assertEqual(result, "Example")
        self.assertEqual(seen[0]["text"]["format"]["type"], "json_object")
        messages = [part["text"] for message in seen[0]["input"] for part in message["content"] if part["type"] == "input_text"]
        self.assertTrue(any("json" in message.lower() for message in messages))


if __name__ == "__main__":
    unittest.main()
