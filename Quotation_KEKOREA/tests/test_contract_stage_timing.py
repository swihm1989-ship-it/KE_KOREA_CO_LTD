"""UI stage timers must never inspect or transmit contract text."""
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.ui import _timed_contract_progress


class FakeStatus:
    def __init__(self):
        self.messages = []
        self.labels = []
    def write(self, value):
        self.messages.append(value)
    def update(self, **kwargs):
        self.labels.append(kwargs)


class ContractStageTimingTests(unittest.TestCase):
    def test_completed_stage_durations_without_payloads(self):
        status = FakeStatus()
        with patch('Quotation_KEKOREA.contracts.ui.time.perf_counter',
                   side_effect=[0.0, 1.0, 3.5, 5.0]):
            progress, finish = _timed_contract_progress(status)
            progress('초안 작성')
            progress('품질 검토')
            finish()
        self.assertEqual(status.messages, ['초안 작성 · 2.5초', '품질 검토 · 1.5초'])
        self.assertEqual(len(status.labels), 2)
        self.assertEqual(status.labels[1]['label'], '계약서 AI · 품질 검토')


if __name__ == '__main__':
    unittest.main()
