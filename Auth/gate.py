"""KE KOREA theme login gate, with refresh-resistant signed cookie sessions.

Requires streamlit-cookies-controller 0.0.4, cookie is not HttpOnly (community
component). Use a proper identity provider before granting third-party access.
"""
import hmac
import time
from datetime import datetime, timedelta, timezone

from Auth.session import MAX_AGE_SECONDS, create_token, validate_token

COOKIE_NAME = "ke_korea_auth_v1"
STATE_NAME = "_ke_korea_auth_token"


def _secrets(st):
    try:
        username = str(st.secrets.get('KEKOREA_AUTH_USERNAME') or '')
        password = str(st.secrets.get('KEKOREA_AUTH_PASSWORD') or '')
        secret = str(st.secrets.get('KEKOREA_AUTH_SESSION_SECRET') or '')
    except (KeyError, FileNotFoundError, AttributeError):
        username = password = secret = ''
    if not username or not password or len(secret) < 32:
        return None
    return username, password, secret


def _new_cookie_controller():
    from streamlit_cookies_controller import CookieController
    return CookieController(key='kekorea_auth_cookie_widget')



def is_authenticated(st):
    """An active, signed browser-login token, not a bare session boolean."""
    config = _secrets(st)
    if not config:
        return False
    return validate_token(st.session_state.get(STATE_NAME), *config)

def require_login(st, root):
    """Stop running app before sidebar, Supabase, AI or exports if not signed in."""
    conf = _secrets(st)
    if not conf:
        st.error('로그인 설정이 없습니다. 관리자에게 Streamlit Secrets의 KEKOREA_AUTH_* 설정을 요청하세요.')
        st.stop()
    username, password, secret = conf
    controller = _new_cookie_controller()
    now = int(time.time())
    token = st.session_state.get(STATE_NAME)
    revoked_token = st.session_state.get('_ke_revoked_token')
    revoked_token = st.session_state.get('_ke_revoked_token')
    revoked_token = st.session_state.get('_ke_revoked_token')
    # st.context.cookies is loaded from the browser on refresh (read-only).
    # Controller fallback supports Streamlit versions without st.context.cookies.
    if not validate_token(token, username, password, secret, now=now):
        try:
            token = st.context.cookies.get(COOKIE_NAME)
        except (AttributeError, KeyError, RuntimeError):
            token = None
        if not validate_token(token, username, password, secret, now=now):
            token = controller.get(COOKIE_NAME)
        if token != revoked_token and validate_token(token, username, password, secret, now=now):
            st.session_state[STATE_NAME] = token
    if token == revoked_token:
        token = None
    if validate_token(token, username, password, secret, now=now):
        with st.sidebar:
            if st.button('로그아웃', key='ke_logout'):
                controller.remove(COOKIE_NAME)
                st.session_state.pop(STATE_NAME, None)
                st.session_state['_ke_revoked_token'] = token
                st.session_state['_ke_logout_just_now'] = True
                st.rerun()
        return
    if st.session_state.get('_ke_logout_just_now'):
        # Avoid st.context.cookies' initial-request snapshot immediately after logout.
        token = None
        st.session_state.pop('_ke_logout_just_now', None)
    with st.container():
        st.markdown('<div class="ke-header"><div class="ke-eyebrow">KE KOREA CO. LTD</div>'
                    '<h1>CONTRACT WORKSPACE</h1><p>안전한 무역·계약 문서 관리 · 최대 12시간 로그인</p></div>',
                    unsafe_allow_html=True)
        _, center, _ = st.columns([1, 1.4, 1])
        with center:
            logo = root / 'assets' / 'company_logo.png'
            if logo.is_file():
                st.image(str(logo), width=180)
            with st.form('ke_auth_login'):
                name = st.text_input('아이디')
                pw = st.text_input('비밀번호', type='password')
                submit = st.form_submit_button('KE KOREA 로그인', type='primary', use_container_width=True)
            if submit:
                if hmac.compare_digest(name, username) and hmac.compare_digest(pw, password):
                    token = create_token(username, password, secret)
                    st.session_state[STATE_NAME] = token
                    st.session_state.pop('_ke_revoked_token', None)
                    expires = datetime.now(timezone.utc) + timedelta(seconds=MAX_AGE_SECONDS)
                    # JS-set cookie is SameSite Strict; secure on Streamlit Cloud HTTPS.
                    try:
                        secure = st.context.url.startswith('https://')
                    except (AttributeError, RuntimeError):
                        secure = False
                    controller.set(COOKIE_NAME, token, expires=expires.replace(tzinfo=None),
                                   max_age=MAX_AGE_SECONDS, secure=secure, same_site='strict')
                    # Render the cookie component fully before switching pages.
                    return
                else:
                    st.error('아이디 또는 비밀번호가 올바르지 않습니다.')
    st.stop()
