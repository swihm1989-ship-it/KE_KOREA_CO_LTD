"""Streamlit native OIDC gate for ALL orchestration pages. Fails closed.

Use a real OIDC identity provider, email_verified=true and an explicit,
server-configured email allowlist. No homegrown passwords or auth bypass.
"""
from __future__ import annotations

import os
import time
from collections.abc import Mapping


def authorized_email(user: Mapping, allowed: str) -> str | None:
    """Return authorized email or None. No wildcard/domain or default access."""
    if not isinstance(user, Mapping) or user.get("is_logged_in") is not True:
        return None
    if user.get("email_verified") is not True:
        return None
    # Streamlit OIDC cookies can outlive an ID token. Refuse stale sessions.
    try:
        expiration = int(user.get("exp"))
    except (ValueError, TypeError):
        return None
    if expiration <= int(time.time()):
        return None
    email = str(user.get("email") or "").strip().casefold()
    addresses = {s.strip().casefold() for s in str(allowed).split(",")
                 if s.strip() and "*" not in s and "@" in s}
    if not email or not addresses or email not in addresses:
        return None
    return email


def require_authentication(st) -> str:
    """Called before sidebar, session state, data loads, or main page render."""
    whitelist = os.environ.get("ORCHESTRATION_ALLOWED_EMAILS", "")
    try:
        identity = dict(st.user.to_dict())
        identity["is_logged_in"] = bool(st.user.is_logged_in)
    except (AttributeError, RuntimeError, KeyError, TypeError):
        identity = {}
    principal = authorized_email(identity, whitelist)
    if principal:
        return principal

    from Quotation_KEKOREA.orchestration.ui.login_page import render_login
    action = render_login(st, configured=bool(whitelist.strip()), logged_in=bool(identity.get("is_logged_in")))
    if action == "logout":
        st.logout()
    elif action == "login":
        try:
            st.login()
        except (RuntimeError, ValueError, KeyError):
            st.error("Google 인증 설정이 누락되었거나 잘못되었습니다. 관리자에게 문의하세요.")
    st.stop()
    raise RuntimeError("Authorization gate must stop unauthenticated execution")
