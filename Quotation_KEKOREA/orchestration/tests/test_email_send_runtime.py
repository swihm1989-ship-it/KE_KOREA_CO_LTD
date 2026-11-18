"""No-network checks for stale SMTP send module and ambiguous send handling.

A long-lived Streamlit process can retain an old send_approved function lacking
the new signature_text argument. All tests use only synthetic records: no SMTP
credentials, transport, or real customer messages.
"""
import inspect
import unittest
from unittest.mock import Mock, patch

from Quotation_KEKOREA.orchestration.ui import email_outbox_page as page
from Quotation_KEKOREA.orchestration.workflows import email_outbox as engine


class SendRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fake_record={
            "id":"00000000-0000-4000-8000-000000000001",
            "status":"draft",
            "send_started_at":None,
            "approved_sha256":None,
        }
        self.no_smtp=Mock()

    def test_current_send_signature_is_usable(self):
        fn=page._resolve_send_approved()
        self.assertIs(fn,engine.send_approved)
        self.assertTrue({"confirmed","signature_text","language"}.issubset(
            inspect.signature(fn).parameters))
        self.no_smtp.assert_not_called()

    def test_cached_legacy_sender_is_reloaded_before_any_db_or_smtp(self):
        # Simulate an old in-memory sender that does not accept signature_text:
        # the exact scenario responsible for a generic TypeError before claim.
        def old_send(_env,_principal,_ident,_config,_to,_subject,_body):
            self.no_smtp()
            raise AssertionError("outdated sender must never execute")
        with patch.object(engine,"send_approved",old_send),patch.object(
            engine,"EMAIL_SEND_RUNTIME_REVISION","old-version"
        ):
            fn=page._resolve_send_approved()
            self.assertNotEqual(fn,old_send)
            self.assertIn("signature_text",inspect.signature(fn).parameters)
            self.no_smtp.assert_not_called()

    def test_preclaim_exception_is_classified_as_not_smtp(self):
        with patch.object(page,"get_reply",return_value=self.fake_record):
            msg=page._safe_send_failure_status({},"owner@example.test",
                self.fake_record["id"],
                TypeError("unexpected keyword argument signature_text SECRET"))
        self.assertIn("발송 시작 기록이 없습니다",msg)
        self.assertIn("SMTP 전송 전에",msg)
        self.assertIn("TypeError",msg)
        self.assertNotIn("SECRET",msg)
        self.no_smtp.assert_not_called()

    def test_sent_status_warns_against_resending(self):
        data={**self.fake_record,"status":"sent","send_started_at":"2026-11-18T00:00:00Z"}
        with patch.object(page,"get_reply",return_value=data):
            msg=page._safe_send_failure_status({}, "owner@example.test",
                                                data["id"],RuntimeError("hidden"))
        self.assertIn("발송 완료 기록",msg)
        self.assertIn("다시 발송하지 마세요",msg)

    def test_ambiguous_send_never_claims_unsent(self):
        data={**self.fake_record,"status":"send_unknown",
              "send_started_at":"2026-11-18T00:00:00Z"}
        with patch.object(page,"get_reply",return_value=data):
            msg=page._safe_send_failure_status({}, "owner@example.test",
                                                data["id"],OSError("hidden"))
        self.assertIn("전송 여부가 불확실",msg)
        self.assertIn("재발송하지",msg)

    def test_database_unreachable_after_exception_fails_closed(self):
        with patch.object(page,"get_reply",side_effect=Exception("DB secret")):
            msg=page._safe_send_failure_status({},"owner@example.test",
                  self.fake_record["id"],TypeError("API key secret"))
        self.assertIn("상태도 확인하지 못했습니다",msg)
        self.assertIn("중복 발송하지",msg)
        self.assertNotIn("secret",msg)


if __name__=="__main__":
    unittest.main()
