"""Branded KE KOREA login and encrypted browser-cookie session recovery."""
import os
from pathlib import Path

import streamlit as st
from streamlit_cookies_manager import EncryptedCookieManager

from .session import make_token, password_matches, verify_token

COOKIE_NAME = 'session_v1'
PREFIX = 'KEKOREA/contract-app/'


def _setting(name, default=''):
    try:
        value = st.secrets.get(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return str(os.environ.get(name, default))


def require_login(root):
    """Stop any app UI/DB access until a valid token is found in browser cookies."""
    username = _setting('KEKOREA_AUTH_USERNAME', 'kekorea')
    password = _setting('KEKOREA_AUTH_PASSWORD')
    key = _setting('KEKOREA_AUTH_SESSION_SECRET')
    if not password or len(key) < 32:
        st.error('관리자 인증 설정이 필요합니다. Streamlit Secrets의 KEKOREA_AUTH_PASSWORD와 KEKOREA_AUTH_SESSION_SECRET을 확인하세요.')
        st.stop()
    cookies = EncryptedCookieManager(prefix=PREFIX, password=key)
    if not cookies.ready():
        st.caption('보안 로그인 정보를 확인하고 있습니다...')
        st.stop()

    # Cookie is encrypted for storage and independently HMAC-verified on every rerun.
    if verify_token(cookies.get(COOKIE_NAME), username, key):
        st.session_state['kekorea_auth_verified'] = True
        with st.sidebar:
            st.caption(f'로그인: {username} · 최대 12시간')
            if st.button('로그아웃', key='kekorea_logout'):
                if COOKIE_NAME in cookies:
                    del cookies[COOKIE_NAME]
                cookies.save()
                st.session_state.clear()
                st.rerun()
        return
    st.session_state.pop('kekorea_auth_verified', None)
    if COOKIE_NAME in cookies:
        del cookies[COOKIE_NAME]
        cookies.save()

    st.markdown('''
    <style>
    .login-brand {text-align:center; margin:36px auto 8px;max-width:440px}
    .login-eyebrow {color:#0877c9;font-size:.78rem;letter-spacing:.16em;font-weight:700}
    .login-title {color:#092b4c;font-size:2rem;font-weight:800;margin:12px 0}
    .login-sub {color:#5b6b78;font-size:.9rem;margin-bottom:24px}
    div[data-testid="stForm"] {border:1px solid #dbe8f2;border-top:4px solid #0877c9;background:white;border-radius:14px;padding:26px}
    </style>
    ''', unsafe_allow_html=True)
    logo = Path(root) / 'assets' / 'company_logo.png'
    if logo.is_file():
        _, logo_col, _ = st.columns([2, 1.25, 2])
        with logo_col:
            st.image(str(logo), use_container_width=True)
    st.markdown('<div class="login-brand"><div class="login-eyebrow">KE KOREA CO. LTD</div>'
                '<div class="login-title">CONTRACT WORKSPACE</div>'
                '<div class="login-sub">안전한 무역·계약 문서 관리 로그인</div></div>', unsafe_allow_html=True)
    _, form_col, _ = st.columns([1, 1.4, 1])
    with form_col:
        with st.form('kekorea_login', clear_on_submit=True):
            entered_id = st.text_input('아이디', autocomplete='username')
            entered_pw = st.text_input('비밀번호', type='password', autocomplete='current-password')
            submitted = st.form_submit_button('KE KOREA 로그인', use_container_width=True, type='primary')
        if submitted:
            valid_user = password_matches(entered_id, username)
            valid_pass = password_matches(entered_pw, password)
            if valid_user and valid_pass:
                cookies[COOKIE_NAME] = make_token(username, key)
                cookies.save()
                st.rerun()
            st.error('아이디 또는 비밀번호가 올바르지 않습니다.')
        st.caption('인증은 브라우저 새로고침 후에도 유지되며, 로그인 시점부터 최대 12시간입니다.')
    st.stop()
