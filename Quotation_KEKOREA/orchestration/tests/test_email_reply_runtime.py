"""Regression: Streamlit cached module, real API diagnostics and manual approval.

Synthetic data only. Never touches a real mailbox or sends an SMTP message.
"""
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from Quotation_KEKOREA.orchestration.workflows import email_reply_runtime as runtime
from Quotation_KEKOREA.orchestration.workflows import email_reply_drafts as draft
from Quotation_KEKOREA.orchestration.workflows import email_reply_handoff as handoff


class FakeResponse:
    def __init__(self, text):
        self.payload=json.dumps({
            "status":"completed",
            "output":[{"content":[{"type":"output_text","text":text}]}]
        }).encode("utf-8")

    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*_args):return self.payload


class ReplyRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env={"OPENAI_API_KEY":"fake-key","CONTRACT_OPENAI_MODEL":"test-model"}

    def test_current_modules_are_imported(self):
        self.assertEqual(runtime._drafts().REPLY_RUNTIME_REVISION,
                         runtime.REPLY_RUNTIME_REVISION)
        self.assertEqual(runtime._handoff().REPLY_RUNTIME_REVISION,
                         runtime.REPLY_RUNTIME_REVISION)

    def test_legacy_draft_module_is_reloaded_on_version_mismatch(self):
        with patch.object(draft,"REPLY_RUNTIME_REVISION","pre-fix"):
            current=runtime._drafts()
            self.assertEqual(current.REPLY_RUNTIME_REVISION,runtime.REPLY_RUNTIME_REVISION)
        self.assertIs(current,draft)

    def test_legacy_handoff_module_is_reloaded_on_version_mismatch(self):
        with patch.object(handoff,"REPLY_RUNTIME_REVISION","old-handoff"):
            current=runtime._handoff()
            self.assertEqual(current.REPLY_RUNTIME_REVISION,runtime.REPLY_RUNTIME_REVISION)
        self.assertIs(current,handoff)

    def test_stale_streamlit_outbox_page_is_reloaded_before_render(self):
        from Quotation_KEKOREA.orchestration.ui import email_outbox_page
        with patch.object(email_outbox_page, "REPLY_RUNTIME_REVISION", "old-ui-module"):
            current=runtime.current_outbox_page()
            self.assertIs(current,email_outbox_page)
            self.assertEqual(current.REPLY_RUNTIME_REVISION,runtime.REPLY_RUNTIME_REVISION)
            self.assertTrue(callable(current.render_email_outbox))

    def test_current_draft_generator_is_injected_in_handoff(self):
        # Regression for default-bound legacy generate_candidates in long
        # running Streamlit processes after a source deployment.
        saved={"id":"fake-uuid","candidate_bodies":[],"status":"draft"}
        candidate=["First reviewed candidate","Second reviewed candidate",
                   "Third reviewed candidate"]
        queue=Mock(return_value=saved)
        gen=Mock(return_value=candidate)
        save=Mock()
        with patch.object(draft,"generate_candidates",gen):
            returned, notice=runtime.prepare_email_handoff(
                {}, "owner@example.test", {"body":"Example"}, {}, self.env,
                "en", ai_consented=True,queue=queue,save=save)
        self.assertIs(returned,saved)
        self.assertIsNone(notice)
        gen.assert_called_once()
        save.assert_called_once()
        self.assertEqual(save.call_args.args[3],candidate)

    def test_no_ai_consent_never_calls_provider(self):
        saved={"id":"fake-uuid","candidate_bodies":[],"status":"draft"}
        gen=Mock()
        with patch.object(draft,"generate_candidates",gen):
            row, notice=runtime.prepare_email_handoff(
                {}, "owner@example.test", {"body":"Example"}, {}, self.env,
                "en", ai_consented=False,queue=Mock(return_value=saved))
        self.assertIs(row,saved)
        self.assertIsNone(notice)
        gen.assert_not_called()

    def test_diagnostic_requires_key_and_model_without_network(self):
        called=Mock()
        self.assertIn("OPENAI_API_KEY",runtime.probe_connection({},opener=called))
        self.assertIn("CONTRACT_OPENAI_MODEL",runtime.probe_connection(
            {"OPENAI_API_KEY":"test"},opener=called))
        called.assert_not_called()

    def test_diagnostic_success_sends_only_dummy_text(self):
        opener=Mock(return_value=FakeResponse('{"ok": true}'))
        result=runtime.probe_connection(self.env,opener=opener)
        self.assertTrue(result.startswith("진단 성공"),result)
        request=opener.call_args.args[0]
        payload=json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"],"test-model")
        self.assertEqual(payload["store"],False)
        self.assertNotIn("buyer",json.dumps(payload).lower())
        self.assertNotIn("real mail",json.dumps(payload).lower())
        self.assertIn("Synthetic connectivity test",json.dumps(payload))

    def test_diagnostic_http_error_exposes_only_status_and_safe_codes(self):
        for code in (400,401,403,404,429,500):
            with self.subTest(code=code):
                exc=urllib.error.HTTPError(
                    "https://api.openai.com/v1/responses",code,"private provider text",
                    None,io.BytesIO(json.dumps({"error":{
                        "code":"unsupported_parameter",
                        "param":"text.format",
                        "message":"private-key fake-secret and customer message"
                    }}).encode("utf-8")))
                opener=Mock(side_effect=exc)
                result=runtime.probe_connection(self.env,opener=opener)
                self.assertIn("HTTP "+str(code),result)
                self.assertIn("unsupported_parameter",result)
                self.assertIn("text.format",result)
                self.assertNotIn("fake-secret",result)
                self.assertNotIn("customer",result)
                self.assertNotIn("private-key",result)

    def test_diagnostic_uses_current_strict_json_schema(self):
        opener=Mock(return_value=FakeResponse('{"ok": true}'))
        self.assertIn("진단 성공",runtime.probe_connection(self.env,opener=opener))
        payload=json.loads(opener.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["text"]["format"]["type"],"json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertFalse(payload["store"])

    def test_diagnostic_retries_plain_text_only_for_format_http400(self):
        error=urllib.error.HTTPError(
            "https://api.openai.com/v1/responses",400,"sensitive error",None,
            io.BytesIO(json.dumps({"error":{
                "code":"unsupported_parameter","param":"text.format",
                "message":"Structured output not supported"
            }}).encode("utf-8"))
        )
        opener=Mock(side_effect=[error,FakeResponse('{"ok": true}')])
        status=runtime.probe_connection(self.env,opener=opener)
        self.assertIn("진단 성공",status)
        self.assertIn("일반 텍스트",status)
        self.assertEqual(opener.call_count,2)
        final=json.loads(opener.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(final["text"]["format"]["type"],"text")
        self.assertFalse(final["store"])

    def test_diagnostics_show_only_configuration_presence(self):
        info=runtime.status(self.env)
        self.assertTrue(info["key_configured"])
        self.assertEqual(info["model"],"test-model")
        self.assertNotIn("fake-key",repr(info))
        self.assertEqual(info["runtime"],runtime.REPLY_RUNTIME_REVISION)

if __name__=="__main__":
    unittest.main()
