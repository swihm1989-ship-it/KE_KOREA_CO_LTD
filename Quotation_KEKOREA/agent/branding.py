"""Resolve the requested private company seal in local and cloud deployments."""
import base64
import hashlib
from pathlib import Path
import re


COMPANY_SEAL_SHA256 = "9367225d53b33fbef008623f07f45c4eed38e17b2a001800b8cb96965c695357"


def resolve_company_seal(root, env, *, expected_sha256=COMPANY_SEAL_SHA256):
    """Prefer the local image; accept a cloud secret only for the same PNG."""
    path = Path(root) / "assets" / "image.png"
    if path.is_file():
        return path, None, None
    encoded = str(env.get("KEKOREA_COMPANY_SEAL_BASE64", "")).strip()
    if not encoded:
        return path, None, "KEKOREA_COMPANY_SEAL_BASE64 is missing; configure it from assets/image.png"
    encoded = re.sub(r"\s+", "", encoded)
    encoded = re.sub(r"^data:image/png;base64,", "", encoded, flags=re.IGNORECASE)
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return path, None, "KEKOREA_COMPANY_SEAL_BASE64 is not valid Base64"
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return path, None, "KEKOREA_COMPANY_SEAL_BASE64 does not contain a PNG image"
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        return path, None, "KEKOREA_COMPANY_SEAL_BASE64 does not match assets/image.png; replace it with the new image"
    return path, data, None
