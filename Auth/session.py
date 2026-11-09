"""Time-limited HMAC tokens for a single KE KOREA administrator."""
import base64
import hashlib
import hmac
import json
import secrets
import time

MAX_AGE_SECONDS = 12 * 60 * 60


def _key(secret, password):
    if len(secret) < 32:
        raise ValueError("KEKOREA_AUTH_SESSION_SECRET must contain at least 32 characters")
    return hmac.new(secret.encode(), password.encode(), hashlib.sha256).digest()


def create_token(username, password, secret, *, now=None):
    issued = int(time.time() if now is None else now)
    body = {"sub": username, "iat": issued, "exp": issued + MAX_AGE_SECONDS,
            "nonce": secrets.token_hex(12), "v": 1}
    payload = base64.urlsafe_b64encode(json.dumps(body, separators=(',', ':'),
                         sort_keys=True).encode()).decode().rstrip('=')
    signature = hmac.new(_key(secret, password), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def validate_token(token, username, password, secret, *, now=None):
    if not isinstance(token, str) or len(token) > 2000 or '.' not in token:
        return False
    try:
        payload, signature = token.split('.', 1)
        expected = hmac.new(_key(secret, password), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        body = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        current = int(time.time() if now is None else now)
        issued, expiry = body['iat'], body['exp']
        return (body.get('v') == 1 and body.get('sub') == username
                and type(issued) is int and type(expiry) is int
                and issued <= current < expiry
                and expiry - issued == MAX_AGE_SECONDS)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
