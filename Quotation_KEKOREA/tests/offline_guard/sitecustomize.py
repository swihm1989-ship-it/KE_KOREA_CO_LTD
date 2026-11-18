"""Test-only external network guard for full regression runs.

No production module imports this guard. Loaded only with a CI PYTHONPATH.
Allow local Streamlit/browser traffic but never contact OpenAI, Gmail, POP,
SMTP or other external providers with synthetic test keys.
"""
import socket

_CONNECT=socket.socket.connect
_GAI=socket.getaddrinfo
_LOCAL={"127.0.0.1","::1","localhost",None}


def _no_external_connect(self,address):
    if isinstance(address,tuple) and address and address[0] not in _LOCAL:
        raise OSError("External network is disabled in the offline CI suite")
    return _CONNECT(self,address)


def _no_external_lookup(host,*args,**kwargs):
    if host not in _LOCAL:
        raise OSError("External DNS is disabled in the offline CI suite")
    return _GAI(host,*args,**kwargs)


socket.socket.connect=_no_external_connect
socket.getaddrinfo=_no_external_lookup
