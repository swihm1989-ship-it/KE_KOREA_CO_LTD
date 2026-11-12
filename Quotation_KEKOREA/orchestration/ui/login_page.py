"""KE KOREA's public welcome screen. No workspace data or auth bypass."""
import base64
from .ke_theme import logo_path

LOGIN_STYLE = '''<style>
.stApp:has(.ke-login-hero) {background:#f3f7fb;color:#172b3d;}
.stApp:has(.ke-login-hero) .block-container {max-width:1080px;padding:3rem 2rem 2rem;}
.st-key-ke_login_shell {background:#fff;border:1px solid #dce6ee;border-radius:20px;overflow:hidden;gap:0!important;box-shadow:0 16px 48px #092b4c0a;}
.ke-login-hero {position:relative;overflow:hidden;padding:32px 48px 40px;color:#fff;background:linear-gradient(115deg,#092b4c 0%,#075a92 65%,#0877c9 100%);}
.ke-login-hero::after {content:'';position:absolute;width:750px;height:750px;border:1px solid #ffffff26;border-radius:50%;top:-230px;right:-390px;box-shadow:0 0 0 70px #ffffff06,0 0 0 140px #ffffff05;pointer-events:none;}
.ke-login-hero>* {position:relative;z-index:1;}
.ke-login-brandbar {display:flex;align-items:center;justify-content:space-between;gap:24px;}
.ke-login-brand {display:flex;align-items:center;gap:12px;font-size:21px;font-weight:650;letter-spacing:.015em;}
.ke-login-mark {width:40px;height:40px;display:grid;place-items:center;background:#ffffff1a;border:1px solid #ffffff22;border-radius:12px;font-size:25px;font-weight:400;}
.ke-login-logo {width:142px;height:71px;object-fit:contain;border-radius:8px;background:#fff;}
.ke-login-eyebrow {font-size:12px;letter-spacing:.22em;color:#d0eafa;margin:36px 0 14px;font-weight:550;}
.ke-login-hero h1 {font-size:clamp(2.2rem,4vw,3.2rem);line-height:1.28;letter-spacing:-.055em;font-weight:750;margin:0 0 20px;padding:0;color:#fff;word-break:keep-all;}
.ke-login-summary {font-size:16px;line-height:1.8;max-width:660px;color:#e3f2fc;margin:0;word-break:keep-all;}
.st-key-ke_login_panel {padding:36px 48px 40px;background:#fff;}
.ke-login-welcome {font-size:12px;color:#0877c9;letter-spacing:.2em;font-weight:650;margin:0 0 12px;}
.ke-login-intro h2 {font-size:32px;letter-spacing:-.04em;color:#172b3d;margin:0 0 12px;padding:0;}
.ke-login-intro p {font-size:16px;line-height:1.7;color:#596b7a;margin:0 0 24px;word-break:keep-all;}
.st-key-ke_login_panel button {width:100%;min-height:58px;border:1px solid #d3dfe9;border-radius:12px;background:#fff;color:#172b3d;font-weight:650;}
.st-key-ke_login_panel button:hover {background:#f0f8fd;border-color:#0877c9;color:#092b4c;}
.st-key-ke_login_panel button:focus-visible {outline:3px solid #0877c9;outline-offset:3px;}
.st-key-master_auth_login button::before {content:'G';font-family:Arial,sans-serif;font-size:23px;font-weight:700;color:#0877c9;margin-right:12px;}
.ke-login-footnote {text-align:center;color:#596b7a;font-size:12px;line-height:1.7;margin:20px 0 0;}
@media(max-width:640px) {
 .stApp:has(.ke-login-hero) .block-container {padding:1rem .75rem 1.5rem;}
 .st-key-ke_login_shell {border-radius:16px;}
 .ke-login-hero {padding:22px 24px 30px;}
 .ke-login-brand {font-size:17px;gap:8px;}
 .ke-login-mark {width:32px;height:32px;border-radius:10px;font-size:21px;}
 .ke-login-logo {width:110px;height:55px;}
 .ke-login-eyebrow {font-size:10px;letter-spacing:.16em;margin-top:32px;}
 .ke-login-hero h1 {font-size:clamp(1.9rem,8vw,2.6rem);line-height:1.35;}
 .ke-login-summary {font-size:14px;line-height:1.75;}
 .st-key-ke_login_panel {padding:28px 24px 30px;}
 .ke-login-intro h2 {font-size:29px;}
 .ke-login-intro p {font-size:14px;}
}
@media(max-width:360px) {
 .ke-login-brand {font-size:14px;}
 .ke-login-logo {width:90px;height:45px;}
 .ke-login-brandbar {gap:12px;}
 .ke-login-mark {display:none;}
}
</style>'''


def render_login(st, *, configured: bool, logged_in: bool) -> str:
    """Return the requested auth action; authorization remains in auth_gate."""
    path=logo_path()
    logo=('data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()) if path.is_file() else ''
    logo_html=f'<img class="ke-login-logo" src="{logo}" alt="KE KOREA Co. Ltd. 로고">' if logo else '<span>KE KOREA</span>'
    st.markdown(LOGIN_STYLE,unsafe_allow_html=True)
    action=''
    with st.container(key='ke_login_shell'):
        st.markdown('<section class="ke-login-hero"><div class="ke-login-brandbar">'
            '<div class="ke-login-brand"><span class="ke-login-mark" aria-hidden="true">↗</span>MASTER GRAPH</div>'
            +logo_html+'</div><div class="ke-login-eyebrow">TRADE DOCUMENT WORKSPACE</div>'
            '<h1>업무는 한눈에,<br>문서는 정확하게.</h1>'
            '<p class="ke-login-summary">시장 정보부터 견적서와 무역 문서 작업까지,<br>필요한 업무를 한곳에서 확인하세요.</p></section>',unsafe_allow_html=True)
        with st.container(key='ke_login_panel'):
            st.markdown('<div class="ke-login-intro"><div class="ke-login-welcome">WELCOME BACK</div>'
                '<h2>로그인</h2><p>Google 계정으로 로그인해 업무를 이어가세요.</p></div>',unsafe_allow_html=True)
            if not configured:
                st.error('접근 가능한 사용자 목록이 아직 설정되지 않았습니다. 관리자에게 문의하세요.')
            elif logged_in:
                st.error('이 계정은 접근 권한이 없거나 인증이 만료되었습니다. 허용된 계정으로 다시 로그인하세요.')
                if st.button('로그아웃 후 다른 계정 사용',key='master_auth_logout',use_container_width=True):action='logout'
            elif st.button('Google 계정으로 계속하기',key='master_auth_login',use_container_width=True):
                action='login'
            st.markdown('<p class="ke-login-footnote">회사에서 허용한 계정으로만 접속할 수 있습니다.<br>'
                'KE KOREA CO. LTD · PRIVATE WORKSPACE</p>',unsafe_allow_html=True)
    return action
