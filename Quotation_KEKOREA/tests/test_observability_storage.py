import json
import threading
import unittest
from datetime import datetime, timedelta, timezone


class StorageTests(unittest.TestCase):
    def event(self):
        from Quotation_KEKOREA.observability import core
        events = []
        old = core.set_recorder(events.append)
        try:
            with core.operation('monitor.health'):
                pass
        finally:
            core.set_recorder(old)
        return events[-1]

    def test_buffer_is_bounded_expired_events_are_removed_and_only_safe_schema_accepted(self):
        from Quotation_KEKOREA.observability.storage import EventStore
        store = EventStore({}, capacity=2)
        event = self.event()
        for _ in range(3):
            store.emit(event)
        self.assertEqual(len(store.recent()), 2)
        store.emit({**event, 'body': 'secret'})
        self.assertEqual(len(store.recent()), 2)
        self.assertGreater(store.health()['dropped'], 0)
        expired = dict(event, started_at=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat())
        store.emit(expired)
        self.assertTrue(all(e['started_at'] != expired['started_at'] for e in store.recent()))

    def test_async_persistence_uses_json_and_does_not_block_caller(self):
        from Quotation_KEKOREA.observability.storage import EventStore
        entered, release = threading.Event(), threading.Event()
        captured = []
        def request(*args, **kwargs):
            entered.set()
            release.wait(2)
            captured.append((args, kwargs))
            return None
        store = EventStore({'SUPABASE_URL': 'https://unit.supabase.co', 'SUPABASE_SECRET_KEY': 'private-key'}, request=request)
        event = self.event()
        try:
            store.emit(event)
            self.assertTrue(entered.wait(1))
            self.assertEqual(len(store.recent()), 1)
            release.set()
            self.assertTrue(store.flush(2))
            self.assertEqual(captured[0][1]['payload'], [event])
            self.assertEqual(store.health()['persisted'], 1)
        finally:
            release.set()
            store.close()

    def test_failed_persistence_is_bounded_and_failure_is_safe(self):
        from Quotation_KEKOREA.observability.storage import EventStore
        def broken(*args, **kwargs):
            raise RuntimeError('secret-url private-key')
        store = EventStore({'SUPABASE_URL': 'https://unit.supabase.co', 'SUPABASE_SECRET_KEY': 'private-key'}, request=broken)
        try:
            store.emit(self.event())
            self.assertTrue(store.flush(2))
            self.assertEqual(len(store.recent()), 1)
            self.assertEqual(store.health()['last_error'], 'storage_unavailable')
            self.assertNotIn('private-key', json.dumps(store.health()))
        finally:
            store.close()

    def test_remote_reads_are_bounded_and_use_service_role_only_rpc(self):
        from Quotation_KEKOREA.observability.storage import EventStore
        calls = []
        def request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {'models': []}
        store = EventStore({'SUPABASE_URL': 'https://unit.supabase.co', 'SUPABASE_SECRET_KEY': 'private-key'}, request=request)
        try:
            self.assertEqual(store.summary(365), {'models': []})
            self.assertEqual(calls[-1][2]['payload']['p_days'], 30)
            self.assertEqual(calls[-1][1], 'rpc/kekorea_telemetry_summary')
        finally:
            store.close()

    def test_malformed_url_and_unavailable_thread_fall_back_without_crashing_master(self):
        from Quotation_KEKOREA.observability.storage import EventStore
        from unittest.mock import patch
        store = EventStore({'SUPABASE_URL':'https://[invalid','SUPABASE_SECRET_KEY':'PRIVATE'})
        self.assertFalse(store.configured)
        with patch('Quotation_KEKOREA.observability.storage.Thread.start', side_effect=RuntimeError('PRIVATE')):
            store = EventStore({'SUPABASE_URL':'https://unit.supabase.co','SUPABASE_SECRET_KEY':'PRIVATE'})
        self.assertFalse(store.configured)
        store.emit(self.event())
        self.assertEqual(len(store.recent()),1)
        self.assertNotIn('PRIVATE',json.dumps(store.health()))


if __name__ == '__main__':
    unittest.main()
