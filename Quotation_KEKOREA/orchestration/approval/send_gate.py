"""Pure email approval fingerprint; no actual sending or persistence.

Production must add per-user authorization, durable approval records and an
atomic SendIntent claim before connecting a real sender.
"""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Mapping, Any

_FIELDS = ("from", "to", "cc", "bcc", "subject", "body", "in_reply_to", "references")

def envelope_digest(envelope: Mapping[str, Any], attachment_fingerprints: list[str]) -> str:
    if not isinstance(envelope, Mapping):
        raise ValueError("Email envelope missing")
    if not str(envelope.get("from", "")).strip() or not envelope.get("to"):
        raise ValueError("Sender and recipient required")
    if not isinstance(attachment_fingerprints, list) or any(
        not isinstance(x, str) or len(x) != 64 for x in attachment_fingerprints
    ):
        raise ValueError("Invalid approved attachment fingerprints")
    canonical = {key: envelope.get(key, "") for key in _FIELDS}
    canonical["attachments_sha256"] = attachment_fingerprints
    data = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(data.encode("utf-8")).hexdigest()

def requires_reapproval(approved_digest: str, envelope: Mapping[str, Any], attachment_fingerprints: list[str]) -> bool:
    return envelope_digest(envelope, attachment_fingerprints) != approved_digest
