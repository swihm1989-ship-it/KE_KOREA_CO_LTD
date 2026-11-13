"""Versioned standard text-token estimates, never billing statements.

Source: https://developers.openai.com/api/docs/pricing (2026-11-13).
Unrecognized models, tiers and cache writes deliberately remain unpriced.
"""
import re

PRICE_VERSION = 'openai-standard-2026-11-13'
# USD per million: uncached input, cached input, output.
RATES = {
    'gpt-6-luna': (0.10, 0.01, 0.50),
    'gpt-6.1-terra': (1.00, 0.05, 5.00),
    'gpt-6.1-sol': (2.00, 0.10, 10.00),
    'gpt-6-astra': (10.00, 1.00, 50.00),
}
_MODEL = re.compile(r'(?:gpt-(?:[0-9](?:\.[0-9])?(?:-(?:mini|nano|pro|sol|terra|luna|astra|codex))?|4o(?:-mini)?)|o[134](?:-mini)?)(?:-\d{4}-\d{2}-\d{2})?\Z')


def safe_model(value):
    return value if isinstance(value, str) and _MODEL.fullmatch(value) else 'other'


def token_count(value):
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def estimate(model, input_tokens, output_tokens, cached_tokens=0, *, cache_write_tokens=0, tier='default'):
    if input_tokens is None or output_tokens is None or cached_tokens is None:
        return None, 'missing_usage'
    if cached_tokens > input_tokens:
        return None, 'missing_usage'
    if tier not in ('default', 'auto', None):
        return None, 'unsupported_tier'
    if cache_write_tokens != 0:
        return None, 'cache_write_unpriced'
    # A dated snapshot is priced only when explicitly added to the rate card.
    rates = RATES.get(model)
    if rates is None:
        return None, 'unknown_model'
    raw, cached, output = rates
    return round(((input_tokens - cached_tokens) * raw + cached_tokens * cached +
                  output_tokens * output) / 1_000_000, 12), 'estimated'
