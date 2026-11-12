import unittest
from unittest.mock import Mock
from Quotation_KEKOREA.orchestration.mail_worker.ingest import run, record_from_message
from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailMessage, Attachment


class MailWorkerTests(unittest.TestCase):
    def test_disabled_by_default_never_connects(self):
        fetch = Mock()
        connect = Mock()
        self.assertEqual(run({}, connect=connect, fetch=fetch)["status"], "disabled")
        fetch.assert_not_called()
        connect.assert_not_called()

    def test_record_contains_only_attachment_names(self):
        msg = MailMessage("uid-a", "seller@example.test", "PI",
                          "Please prepare 100 PCS", "today",
                          (Attachment("quotation.pdf", b"secret-pdf-bytes"),))
        row = record_from_message("acct", msg)
        self.assertIn("quotation.pdf", row[6])
        self.assertNotIn("secret-pdf-bytes", str(row))
        self.assertEqual(row[-1], "unreviewed")

    def test_no_worker_without_database_or_principal(self):
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
            run({"MAIL_WORKER_ENABLED": "true"}, connect=Mock(), fetch=Mock())


if __name__ == "__main__":
    unittest.main()
