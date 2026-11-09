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
    def test_fabricated_quote_rejected(self):
        with self.assertRaisesRegex(ValueError,"not found"):
            self.call([{"kind":"user","quote":"fictional text"}])
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
