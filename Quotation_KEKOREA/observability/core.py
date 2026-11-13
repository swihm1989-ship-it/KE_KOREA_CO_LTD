"""Allowlisted execution spans: no arguments, return values or exception text.

The optional recorder receives only JSON-compatible metadata. Recorder errors
are isolated from business code. No root logger, SDK callbacks or payload tracing.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import time
import urllib.error
from uuid import uuid4

from .pricing import PRICE_VERSION, estimate, safe_model, token_count

TASKS = frozenset({'mail.collect', 'ai.request', 'contract.analyze',
                   'contract.generate', 'trade.extract', 'document.generate',
                   'monitor.health', 'other'})
ERRORS = frozenset({'timeout', 'rate_limit', 'authentication', 'permission',
                    'provider_unavailable', 'invalid_request', 'network',
                    'invalid_response', 'incomplete_response', 'provider_error',
                    'validation', 'mail_transport', 'unexpected'})
FIELDS = frozenset({'event_id', 'run_id', 'span_id', 'parent_span_id', 'event_type',
                    'task', 'document_kind', 'status', 'started_at', 'ended_at',
                    'duration_ms', 'model', 'input_tokens', 'output_tokens',
                    'cached_input_tokens', 'estimated_cost_usd', 'pricing_status',
                    'pricing_version', 'error_type', 'http_status', 'retry_count'})
_current = ContextVar('ke_operational_span', default=None)
_retry = ContextVar('ke_ai_retry', default=0)
_recorder = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def set_recorder(recorder):
    global _recorder
    old, _recorder = _recorder, recorder
    return old


def error_category(error):
    status = getattr(error, 'code', None)
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    if status is not None:
        category = {401: 'authentication', 403: 'permission', 429: 'rate_limit'}.get(status)
        return category or ('provider_unavailable' if status >= 500 else 'invalid_request'), status
    if isinstance(error, TimeoutError) or isinstance(getattr(error, 'reason', None), TimeoutError):
        return 'timeout', None
    if isinstance(error, urllib.error.URLError):
        return 'network', None
    if isinstance(error, (json.JSONDecodeError, UnicodeDecodeError)):
        return 'invalid_response', None
    if isinstance(error, PermissionError):
        return 'permission', None
    if isinstance(error, (ValueError, TypeError)):
        return 'validation', None
    if type(error).__module__.endswith('.whois_mail') and type(error).__name__ == 'MailConnectionError':
        return 'mail_transport', None
    return 'unexpected', None


def _emit(event):
    if _recorder is not None:
        try:
            # A new JSON-only object prevents later mutation and disallows NaN.
            _recorder(json.loads(json.dumps(event, allow_nan=False)))
        except Exception:
            # Never print exceptions here: transports often include secret URLs.
            pass


class Span:
    def __init__(self, task, *, model=None, document_kind=None):
        self.task = task if task in TASKS else 'other'
        self.model = safe_model(model) if model is not None else None
        self.document_kind = document_kind if document_kind in {'PI', 'PO', 'CI', 'PL', 'CONTRACT'} else None
        self.input_tokens = self.output_tokens = self.cached_tokens = None
        self.cost = None
        self.pricing_status = 'missing_usage' if self.task == 'ai.request' else None
        self.error = self.http_status = None

    def __enter__(self):
        parent = _current.get()
        self.run_id = parent[0] if parent else str(uuid4())
        self.parent_id = parent[1] if parent else None
        self.span_id = str(uuid4())
        self.started_at = utc_now()
        self.tick = time.perf_counter()
        self.retry_count = _retry.get() if self.task == 'ai.request' else 0
        self.token = _current.set((self.run_id, self.span_id))
        _emit(self._event('start'))
        return self

    def failure(self, error):
        if self.error is None:
            self.error, self.http_status = error_category(error)

    def fail_code(self, code):
        if self.error is None:
            self.error = code if code in ERRORS else 'unexpected'

    def usage(self, response):
        """Malformed metadata must never change legacy response handling."""
        try:
            self._usage(response)
        except Exception:
            self.cost = None
            self.pricing_status = 'missing_usage'

    def _usage(self, response):
        """Read numeric counters only, never serialize the provider response."""
        if not isinstance(response, dict):
            self.fail_code('invalid_response')
            return
        usage = response.get('usage')
        if isinstance(usage, dict):
            self.input_tokens = token_count(usage.get('input_tokens'))
            self.output_tokens = token_count(usage.get('output_tokens'))
            details = usage.get('input_tokens_details')
            details = details if isinstance(details, dict) else {}
            self.cached_tokens = token_count(details.get('cached_tokens', 0))
            self.cost, self.pricing_status = estimate(
                self.model, self.input_tokens, self.output_tokens, self.cached_tokens,
                cache_write_tokens=token_count(details.get('cache_write_tokens', 0)),
                tier=response.get('service_tier', 'default'),
            )
        if response.get('status') == 'incomplete':
            self.fail_code('incomplete_response')
        elif response.get('error') or (isinstance(response.get('status'), str) and response['status'] in {'failed', 'cancelled'}):
            self.fail_code('provider_error')

    def _event(self, event_type):
        ended = event_type == 'finish'
        return {
            'event_id': str(uuid4()), 'run_id': self.run_id, 'span_id': self.span_id,
            'parent_span_id': self.parent_id, 'event_type': event_type, 'task': self.task,
            'document_kind': self.document_kind,
            'status': ('failure' if self.error else 'success') if ended else 'running',
            'started_at': self.started_at, 'ended_at': utc_now() if ended else None,
            'duration_ms': round(max(0, (time.perf_counter() - self.tick) * 1000), 3) if ended else None,
            'model': self.model, 'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens, 'cached_input_tokens': self.cached_tokens,
            'estimated_cost_usd': self.cost, 'pricing_status': self.pricing_status,
            'pricing_version': PRICE_VERSION if self.task == 'ai.request' else None,
            'error_type': self.error, 'http_status': self.http_status, 'retry_count': self.retry_count,
        }

    def __exit__(self, typ, error, traceback):
        try:
            if error is not None:
                self.failure(error)
            _emit(self._event('finish'))
        finally:
            _current.reset(self.token)
        return False


def operation(task, *, model=None, document_kind=None):
    return Span(task, model=model, document_kind=document_kind)


def traced(task, *, kind_argument=False):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            kind = (kwargs.get('kind') if 'kind' in kwargs else args[0] if args else None) if kind_argument else None
            # Only canonical enum strings are logged, never arbitrary inputs.
            kind = kind.upper() if isinstance(kind, str) and len(kind) <= 8 else None
            with operation(task, document_kind=kind):
                return function(*args, **kwargs)
        return wrapped
    return decorate


@contextmanager
def retry_attempt(count):
    value = count if type(count) is int and 0 <= count <= 100 else 0
    token = _retry.set(value)
    try:
        yield
    finally:
        _retry.reset(token)
