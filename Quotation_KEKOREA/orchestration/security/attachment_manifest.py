"""SHA256 over immutable reviewed attachment bytes."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256

@dataclass(frozen=True)
class AttachmentManifest:
    filename: str
    revision: str
    sha256_hex: str
    byte_length: int

def build_manifest(filename: str, revision: str, payload: bytes) -> AttachmentManifest:
    if not filename or not revision or not isinstance(payload, bytes) or not payload:
        raise ValueError("Reviewed attachment requires filename, revision, and nonempty bytes")
    return AttachmentManifest(filename, revision, sha256(payload).hexdigest(), len(payload))

def verify_manifest(manifest: AttachmentManifest, payload: bytes) -> bool:
    return isinstance(payload, bytes) and len(payload) == manifest.byte_length and sha256(payload).hexdigest() == manifest.sha256_hex
