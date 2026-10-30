"""OpenAI request shape and source-evidence guards; no live API request is made."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("trade_extractor", ROOT / "agent" / "extractor.py")
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class FakeResponse:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.body).encode()


class ExtractorTests(unittest.TestCase):
    def test_packing_image_request_includes_packing_fields_and_source_context(self):
        captured = {}
        def opener(request, timeout):
            captured["body"] = json.loads(request.data)
            return FakeResponse({"output": [{"content": [{"type": "output_text", "text": '{"items":[]}'}]}]})
        extractor.extract_trade_data("Packing list", images=[{"name": "source.png", "mime_type": "image/png", "data": b"image"}],
                                     env={"OPENAI_API_KEY": "test"}, opener=opener,
                                     requested_document_type="PL", packing_source=True)
        body = captured["body"]
        item = body["text"]["format"]["schema"]["properties"]["items"]["items"]
        self.assertIn("volume_cbm", item["properties"])
        self.assertIn("gross_weight_kg", item["properties"])
        self.assertIn("container_count", body["text"]["format"]["schema"]["properties"])
        self.assertIn("supplier document is packing evidence", body["instructions"])
        self.assertEqual(body["input"][0]["content"][1]["type"], "input_image")

    def test_translation_rules_are_in_openai_instructions(self):
        self.assertIn("Chinese", extractor.SYSTEM_PROMPT)
        self.assertIn("(English translation)", extractor.SYSTEM_PROMPT)
        self.assertIn("Indonesian", extractor.SYSTEM_PROMPT)

    def test_verified_translations_are_not_rejected_as_nonverbatim(self):
        source = "买方：华星贸易有限公司，地址：上海市浦东新区。Mohon kirim Solar Cell 20 pcs."
        draft = {
            "buyer": {"legal_name": "华星贸易有限公司 (Huaxing Trading Co., Ltd.)",
                      "address": "上海市浦东新区 (Pudong New Area, Shanghai)"},
            "items": [{"product_name": "Solar Cell", "capacity": None,
                       "quantity": "20", "unit_price": None,
                       "source": "Mohon kirim Solar Cell 20 pcs."}],
            "source_notes": [source], "conflicts": []}
        result = extractor.verify_item_quotes(draft, source)
        self.assertEqual(result["conflicts"], [])

    def test_source_notes_must_be_verbatim_evidence(self):
        draft = {"items": [], "source_notes": ["invented source"], "conflicts": []}
        result = extractor.verify_item_quotes(draft, "Buyer asks for PI")
        self.assertTrue(any("source note" in issue.lower() for issue in result["conflicts"]))

    def test_cloud_secrets_override_file_values_without_printing_them(self):
        with __import__("tempfile").NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".env", delete=False) as file:
            file.write("OPENAI_MODEL=gpt-6-luna\n")
            env_path = Path(file.name)
        try:
            values = extractor.load_env(env_path, secrets={"OPENAI_API_KEY": "cloud-test-secret", "OPENAI_MODEL": "gpt-6-luna"})
            self.assertEqual(values["OPENAI_API_KEY"], "cloud-test-secret")
            self.assertEqual(values["OPENAI_MODEL"], "gpt-6-luna")
        finally:
            env_path.unlink(missing_ok=True)

    def test_requests_structured_output_with_configured_model(self):
        captured = {}
        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["auth_present"] = bool(request.get_header("Authorization"))
            return FakeResponse({"output": [{"content": [{"type": "output_text", "text": '{"items":[]}'}]}]})
        result = extractor.extract_trade_data("Create a PI", env={"OPENAI_API_KEY": "test-only", "OPENAI_MODEL": "gpt-6-luna"}, opener=opener)
        self.assertEqual(captured["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(captured["body"]["model"], "gpt-6-luna")
        self.assertEqual(captured["body"]["text"]["format"]["type"], "json_schema")
        self.assertTrue(captured["body"]["text"]["format"]["strict"])
        self.assertTrue(captured["auth_present"])
        self.assertEqual(result, {"items": []})

    def test_quote_guard_blocks_invented_item_amount(self):
        draft = {"items": [{"product_name": "Solar Cell", "capacity": None, "source": "Solar Cell 10 PCS USD 5.00",
                            "quantity": "10", "unit_price": "50.00"}], "conflicts": []}
        result = extractor.verify_item_quotes(draft, "Solar Cell 10 PCS USD 5.00 FOB Busan")
        self.assertTrue(any("unit price" in issue for issue in result["conflicts"]))

    def test_quote_guard_flags_missing_company_address(self):
        draft = {"items": [], "buyer": {"legal_name": "Buyer Ltd", "address": "55 Fiction Ave"}}
        result = extractor.verify_item_quotes(draft, "Buyer Ltd placed an order")
        self.assertTrue(any("Buyer address" in issue for issue in result["conflicts"]))


if __name__ == "__main__":
    unittest.main()
