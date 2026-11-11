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

    st.title("KE KOREA · Private Workspace")
    st.caption("MASTER GRAPH · Access controlled by your OIDC identity")
    if not whitelist.strip():
        st.error("접근 가능한 사용자 목록이 아직 설정되지 않았습니다. 관리자에게 문의하세요.")
        st.stop()
    if identity.get("is_logged_in"):
        st.error("이 계정은 접근 권한이 없거나 이메일 인증이 완료되지 않았습니다.")
        if st.button("로그아웃 후 다른 계정 사용", key="master_auth_logout"):
            st.logout()
    else:
        st.info("회사에서 허가한 계정으로 로그인하세요. 로그인하지 않으면 계약서 조회 기능을 포함한 모든 메뉴에 접근할 수 없습니다.")
        if st.button("계정으로 로그인", type="primary", key="master_auth_login"):
            try:
                st.login()
            except (RuntimeError, ValueError, KeyError):
                st.error("OIDC 인증 설정이 누락되었거나 잘못되었습니다. 관리자에게 문의하세요.")
    st.stop()
    raise RuntimeError("Authorization gate must stop unauthenticated execution")
