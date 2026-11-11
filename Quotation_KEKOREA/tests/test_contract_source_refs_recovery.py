import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.service import analyze_trade

class SourceReferenceRecoveryTests(unittest.TestCase):
    def base(self, refs):
        return {"contract_type":"sale","parties":[],"terms":[{"key":"quantity","value":"2324938","unit":"PCS","currency":None,"status":"suggested","source_refs":refs}],"questions":[],"issues":[]}
    def call(self, refs):
        with patch("Quotation_KEKOREA.contracts.service._call",return_value=self.base(refs)):
            return analyze_trade([{"role":"user","content":"2324938 PCS"}],{"revision":1,"contract_type":"sale"},[],env={})
    def test_null_becomes_empty(self):
        self.assertEqual(self.call(None)["terms"][0]["source_refs"],[])
    def test_prose_is_unverified(self):
        result=self.call("user message")
        self.assertEqual(result["terms"][0]["source_refs"],[])
        self.assertTrue(any(x["code"]=="unverified_ai_source_ref" for x in result["issues"]))
    def test_valid_dict_becomes_list(self):
        ref={"kind":"user","quote":"2324938 PCS"}
        self.assertEqual(self.call(ref)["terms"][0]["source_refs"],[ref])
    def test_fabricated_quote_is_removed_and_extraction_requires_review(self):
        result = self.call([{"kind":"user","quote":"fictional text"}])
        self.assertEqual(result["terms"][0]["source_refs"], [])
        self.assertEqual(result["terms"][0]["status"], "suggested")
        self.assertTrue(any(x["code"] == "unverified_ai_source_ref"
                            and x["severity"] == "confirm" for x in result["issues"]))

    def test_party_quote_mismatch_no_longer_blocks_valid_transaction(self):
        data = {"contract_type": "sale", "parties": [
            {"legal_name": "Smart Solar System Co. LTD", "roles": ["seller"],
             "source_refs": [{"kind": "user", "quote": "Supplier: Smart Solar System Co. LTD"}]},
            {"legal_name": "KE KOREA CO. LTD", "roles": ["buyer"],
             "source_refs": [{"kind": "user", "quote": "Buyer: KE KOREA CO., LTD."}]}
        ], "terms": [{"key": "unit_price", "value": "$0.2/pc", "status": "suggested",
                       "source_refs": [{"kind": "user", "quote": "price: $0.2/pc"}]}],
                "questions": [], "issues": []}
        message = ("Supplier: Smart Solar System Co. LTD / Buyer: KE KOREA CO. LTD "
                   "/ price: $0.2/pc")
        with patch("Quotation_KEKOREA.contracts.service._call", return_value=data):
            result = analyze_trade([{"role": "user", "content": message}],
                                   {"revision": 1, "contract_type": "sale"}, [], env={})
        self.assertEqual(result["parties"][0]["source_refs"][0]["quote"],
                         "Supplier: Smart Solar System Co. LTD")
        self.assertEqual(result["parties"][1]["source_refs"], [])
        self.assertEqual(result["parties"][1]["legal_name"], "KE KOREA CO. LTD")
        self.assertEqual(result["terms"][0]["status"], "suggested")
        self.assertTrue(any(x["code"] == "unverified_ai_source_ref" and "party[1]" in x["message"]
                            for x in result["issues"]))

    def test_reference_quote_mismatch_removed_without_fabricating_source(self):
        item = {"contract_type": "sale", "parties": [], "terms": [
            {"key": "products", "value": "Solar Cell", "status": "suggested",
             "source_refs": [{"kind": "reference", "document_id": "ref1",
                              "quote": "fabricated document text"}]}],
                "questions": [], "issues": []}
        with patch("Quotation_KEKOREA.contracts.service._call", return_value=item):
            result = analyze_trade([{"role": "user", "content": "Solar Cell"}],
                                   {"contract_type": "sale"}, [{"id": "ref1",
                                     "extracted_text": "Actual document text"}], env={})
        self.assertEqual(result["terms"][0]["source_refs"], [])
        self.assertTrue(any(x["code"] == "unverified_ai_source_ref" for x in result["issues"]))

    def test_stale_message_id_does_not_discard_exact_verifiable_user_quote(self):
        citation = {"kind": "user", "message_id": "invented-id", "quote": "2324938 PCS"}
        result = self.call([citation])
        self.assertEqual(result["terms"][0]["source_refs"], [citation])
        self.assertEqual(result["issues"], [])
    def test_invalid_nested_ref_rejected(self):
        with self.assertRaisesRegex(ValueError,r"term\[0\]"):
            self.call([42])
    def test_prompt_requires_arrays(self):
        recorded={}
        def responder(instructions,payload,**kwargs):
            recorded["instructions"]=instructions
            return self.base([])
        with patch("Quotation_KEKOREA.contracts.service._call",side_effect=responder):
            analyze_trade([],{"contract_type":"sale"},[],env={})
        self.assertIn("source_refs MUST be a JSON array",recorded["instructions"])
