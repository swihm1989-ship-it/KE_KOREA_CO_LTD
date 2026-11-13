"""Master-only opt-in startup, after the existing OIDC authorization gate."""
from hashlib import sha256
from threading import Lock

from .core import set_recorder
from .storage import EventStore

_lock = Lock()
_store = None
_identity = None


def configure(settings):
    global _store, _identity
    # Compare without retaining/logging another copy of the server key.
    identity = sha256((str(settings.get('SUPABASE_URL',''))+'\0'+
                       str(settings.get('SUPABASE_SECRET_KEY',''))).encode()).digest()
    with _lock:
        if _store is None or identity != _identity:
            previous = _store
            _store = EventStore(settings)
            _identity = identity
            if previous:
                previous.close()
        set_recorder(_store.emit)
        return _store
