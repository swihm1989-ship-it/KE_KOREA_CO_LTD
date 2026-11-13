"""Bounded, asynchronous private JSON event storage; no payload logging.

No disk spooling and no root/stdout handlers. Supabase owns durable retention;
the volatile, capped fallback is explicit in the dashboard and lost on restart.
"""
from collections import deque
from datetime import datetime, timedelta, timezone
import json
import math
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
import time
import urllib.parse
import urllib.request
from uuid import UUID

from .core import ERRORS, FIELDS, TASKS
from .pricing import PRICE_VERSION, safe_model

RETENTION_DAYS = 30


def validate_event(event):
    if not isinstance(event, dict) or set(event) != FIELDS:
        return False
    try:
        for key in ('event_id', 'run_id', 'span_id', 'parent_span_id'):
            if event[key] is not None:
                UUID(event[key])
        for key in ('started_at', 'ended_at'):
            if event[key] is not None:
                value = datetime.fromisoformat(event[key])
                if value.tzinfo is None:
                    return False
        if event['task'] not in TASKS or event['event_type'] not in {'start', 'finish'}:
            return False
        if event['status'] not in {'running', 'success', 'failure'}:
            return False
        if event['document_kind'] not in {None, 'PI', 'PO', 'CI', 'PL', 'CONTRACT'}:
            return False
        if event['model'] is not None and safe_model(event['model']) != event['model'] and event['model'] != 'other':
            return False
        if event['error_type'] not in ERRORS | {None}:
            return False
        if event['pricing_status'] not in {None, 'estimated', 'missing_usage', 'unknown_model', 'unsupported_tier', 'cache_write_unpriced'}:
            return False
        if event['pricing_version'] not in {None, PRICE_VERSION}:
            return False
        for key in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'retry_count', 'http_status'):
            value = event[key]
            if value is not None and (type(value) is not int or value < 0 or value > 1_000_000_000):
                return False
        for key in ('duration_ms', 'estimated_cost_usd'):
            value = event[key]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                return False
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class EventStore:
    def __init__(self, settings, *, capacity=2000, request=None):
        self.base = str(settings.get('SUPABASE_URL') or '').rstrip('/')
        self.key = str(settings.get('SUPABASE_SECRET_KEY') or '')
        try:
            url = urllib.parse.urlparse(self.base)
            self.configured = bool(url.scheme == 'https' and url.hostname and
                                   url.hostname.endswith('.supabase.co') and
                                   not url.query and not url.fragment and not url.username and
                                   url.path in ('', '/') and self.key)
        except ValueError:
            self.configured = False
        self._request_override = request
        self._buffer = deque(maxlen=capacity)
        self._lock = Lock()
        self._queue = Queue(maxsize=256)
        self._stop = Event()
        self._dropped = self._persisted = 0
        self._last_error = None
        self._last_saved_at = None
        self._thread = None
        if self.configured:
            self._thread = Thread(target=self._worker, name='ke-private-telemetry', daemon=True)
            try:
                self._thread.start()
            except (RuntimeError, OSError):
                self._thread = None
                self.configured = False
                self._last_error = 'storage_unavailable'

    def _prune(self):
        cutoff = (datetime.now(timezone.utc)-timedelta(days=RETENTION_DAYS)).isoformat()
        self._buffer = deque((e for e in self._buffer if e['started_at'] >= cutoff), maxlen=self._buffer.maxlen)

    def emit(self, event):
        if not validate_event(event):
            with self._lock:
                self._dropped += 1
            return
        # JSON serialization is the sole wire format; no arbitrary log extras.
        event = json.loads(json.dumps(event, allow_nan=False))
        with self._lock:
            self._prune()
            self._buffer.append(event)
            self._prune()
        if self.configured and not self._stop.is_set():
            try:
                self._queue.put_nowait(event)
            except Full:
                with self._lock:
                    self._dropped += 1

    def request(self, method, path, *, payload=None, query=None):
        if self._request_override:
            return self._request_override(method, path, payload=payload, query=query)
        url = f'{self.base}/rest/v1/{path}'
        if query:
            url += '?' + urllib.parse.urlencode(query)
        headers = {'apikey': self.key, 'Authorization': f'Bearer {self.key}',
                   'Content-Type': 'application/json', 'Accept': 'application/json',
                   'Prefer': 'resolution=ignore-duplicates,return=minimal'}
        data = json.dumps(payload, allow_nan=False).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=2) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('Telemetry response limit')
        return json.loads(raw) if raw else None

    def _worker(self):
        while not self._stop.is_set():
            try:
                first = self._queue.get(timeout=0.2)
            except Empty:
                continue
            batch = [first]
            while len(batch) < 64:
                try:
                    batch.append(self._queue.get_nowait())
                except Empty:
                    break
            saved = False
            for attempt in range(3):
                try:
                    self.request('POST', 'kekorea_telemetry_events', payload=batch,
                                 query={'on_conflict': 'event_id'})
                    saved = True
                    break
                except Exception:
                    if self._stop.wait(0.1 * (attempt + 1)):
                        break
            with self._lock:
                if saved:
                    self._persisted += len(batch)
                    self._last_saved_at = datetime.now(timezone.utc).isoformat()
                    self._last_error = None
                else:
                    self._last_error = 'storage_unavailable'
                    self._dropped += len(batch)
            for _ in batch:
                self._queue.task_done()

    def recent(self, days=30):
        cutoff = datetime.now(timezone.utc)-timedelta(days=max(1, min(int(days), RETENTION_DAYS)))
        with self._lock:
            self._prune()
            return [dict(e) for e in self._buffer if datetime.fromisoformat(e['started_at']) >= cutoff]

    def health(self):
        with self._lock:
            return {'configured': self.configured, 'pending': self._queue.qsize(),
                    'persisted': self._persisted, 'dropped': self._dropped,
                    'last_error': self._last_error, 'last_saved_at': self._last_saved_at,
                    'retention_days': RETENTION_DAYS}

    def summary(self, days=7):
        if not self.configured:
            raise RuntimeError('Telemetry storage is not configured')
        return self.request('POST', 'rpc/kekorea_telemetry_summary',
                            payload={'p_days': max(1, min(int(days), RETENTION_DAYS))})

    def remote_recent(self, days=7):
        since = datetime.now(timezone.utc)-timedelta(days=max(1, min(int(days), RETENTION_DAYS)))
        rows = self.request('GET', 'kekorea_telemetry_events', query={
            'select': ','.join(sorted(FIELDS)), 'started_at': 'gte.'+since.isoformat(),
            'expires_at': 'gt.'+datetime.now(timezone.utc).isoformat(),
            'order': 'started_at.desc,event_type.asc', 'limit': '200'})
        return [row for row in rows or [] if validate_event(row)]

    def flush(self, timeout=2):
        deadline = time.monotonic()+timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        return not self._queue.unfinished_tasks

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
