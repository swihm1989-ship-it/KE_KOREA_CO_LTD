"""Signed 12-hour login tokens; intentionally independent of Streamlit UI."""
import base64
import hashlib
import hmac
import json
import secrets
import time

MAX_AGE_SECONDS = 12 * 60 * 60


def password_matches(given, expected):
    """Constant-time string comparison; password must come from server-side Secrets."""
    return bool(expected) and hmac.compare_digest(str(given).encode(), str(expected).encode())


def _encode(value):
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def _decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _sign(payload, key):
    return _encode(hmac.new(str(key).encode('utf-8'), payload.encode('ascii'), hashlib.sha256).digest())


def make_token(username, signing_key, *, now=None):
    if len(str(signing_key)) < 32:
        raise ValueError('AUTH_SESSION_SECRET needs at least 32 characters.')
    now = int(time.time() if now is None else now)
    body = {'sub': username, 'iat': now, 'exp': now + MAX_AGE_SECONDS,
            'nonce': secrets.token_hex(12)}
    encoded = _encode(json.dumps(body, separators=(',', ':'), ensure_ascii=True).encode('utf-8'))
    return f'{encoded}.{_sign(encoded, signing_key)}'


def verify_token(token, username, signing_key, *, now=None):
    if len(str(signing_key)) < 32 or not isinstance(token, str):
        return False
    try:
        encoded, signature = token.split('.')
        if not hmac.compare_digest(signature, _sign(encoded, signing_key)):
            return False
        body = json.loads(_decode(encoded))
        now = int(time.time() if now is None else now)
        return (isinstance(body, dict) and body.get('sub') == username
                and isinstance(body.get('iat'), int) and isinstance(body.get('exp'), int)
                and body['iat'] <= now < body['exp']
                and body['exp'] - body['iat'] == MAX_AGE_SECONDS)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, OverflowError):
        return False
