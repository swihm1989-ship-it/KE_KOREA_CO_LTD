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


def authentication_issue(user: Mapping, allowed: str) -> str:
    """Explain a denial using fixed codes; never disclose claims or the allowlist."""
    if not isinstance(user, Mapping) or user.get("is_logged_in") is not True:
        return "not_logged_in"
    if user.get("email_verified") is not True:
        return "unverified_email"
    try:
        expiration = int(user.get("exp"))
    except (ValueError, TypeError):
        return "missing_expiration"
    if expiration <= int(time.time()):
        return "expired"
    return "" if authorized_email(user, allowed) else "not_allowlisted"


def require_authentication(st) -> str:
    """Called before sidebar, session state, data loads, or main page render."""
    whitelist = ",".join(filter(None, (
        os.environ.get("ORCHESTRATION_ALLOWED_EMAILS", ""),
        os.environ.get("ORCHESTRATION_EXTRA_ALLOWED_EMAILS", ""),
    )))
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
    if identity.get("is_logged_in"):
        explanation = {
            "not_allowlisted": "현재 Google 계정이 Master 앱의 허용 계정 목록과 일치하지 않습니다.",
            "expired": "Google 인증 유효시간이 지났습니다. 다시 로그인해 주세요.",
            "missing_expiration": "Google 인증 정보에 만료 시각이 없어 접근을 허용할 수 없습니다. 관리자 확인이 필요합니다.",
            "unverified_email": "Google 계정의 이메일 인증이 확인되지 않았습니다.",
        }.get(authentication_issue(identity, whitelist))
        if explanation:
            st.caption(explanation)
    if action == "logout":
        st.logout()
    elif action == "login":
        try:
            st.login()
        except (RuntimeError, ValueError, KeyError):
            st.error("Google 인증 설정이 누락되었거나 잘못되었습니다. 관리자에게 문의하세요.")
    st.stop()
    raise RuntimeError("Authorization gate must stop unauthenticated execution")
