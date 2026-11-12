"""Authenticated mailbox UI; credentials come only from server configuration."""
from datetime import datetime
import os
from zoneinfo import ZoneInfo
import streamlit as st
from Quotation_KEKOREA.orchestration.adapters.whois_mail import (
    mail_config, probe_pop, probe_smtp, fetch_messages, MailConnectionError,
)

SECRETS_TEMPLATE = '''# Master 앱 Settings → Secrets의 최상위에 추가 (실제 값은 이곳에만 입력)
WHOIS_MAIL_OWNER_EMAILS = "YOUR_OIDC_LOGIN_EMAIL"
WHOIS_POP_HOST = "YOUR_ACTUAL_POP_SERVER"
WHOIS_POP_PORT = 995
WHOIS_POP_SECURITY = "ssl"
WHOIS_POP_USERNAME = "YOUR_MAILBOX_ADDRESS"
WHOIS_POP_PASSWORD = "YOUR_MAIL_PASSWORD"
WHOIS_SMTP_HOST = "YOUR_ACTUAL_SMTP_SERVER"
WHOIS_SMTP_PORT = 587
WHOIS_SMTP_SECURITY = "starttls"
WHOIS_SMTP_USERNAME = "YOUR_MAILBOX_ADDRESS"
WHOIS_SMTP_PASSWORD = "YOUR_MAIL_PASSWORD"
'''

def _settings():
    values = dict(os.environ)
    try:
        secrets = dict(st.secrets)
    except (FileNotFoundError, KeyError):
        secrets = {}
    # Streamlit TOML places keys after [auth] inside that table, not at
    # top level. Only import WHOIS_* from that known section; never treat
    # an arbitrary nested value as an access grant or override top-level keys.
    auth = secrets.get("auth")
    if hasattr(auth, "items"):
        for key, value in auth.items():
            if isinstance(key, str) and key.startswith("WHOIS_") and key not in secrets:
                secrets[key] = value
    values.update(secrets)
    values["WHOIS_MAIL_OWNER_EMAILS"] = ",".join(filter(None, (
        str(values.get("WHOIS_MAIL_OWNER_EMAILS", "")),
        str(values.get("WHOIS_MAIL_EXTRA_OWNER_EMAILS", "")),
    )))
    return values


def _use_for_ai(message):
    # Callback runs before the sidebar/AI widgets are instantiated.
    for key in list(st.session_state):
        if (key.startswith('ai_intake_') and key not in {'ai_intake_language','ai_intake_family'}) or key.startswith('master_pdf_') or key=='master_legacy_files':
            st.session_state.pop(key,None)
    st.session_state['ai_intake_instruction']=('메일 제목: '+message.subject+'\n\n'+message.body)[:20000]
    st.session_state['ai_intake_consent']=False
    st.session_state['master_page']='AI 업무 요청'


def render_mailbox(principal):
    if not principal: raise PermissionError('로그인이 필요합니다.')
    st.subheader('후이즈 회사 메일함')
    st.caption('메일 진단 버전: 2026-11-12-B · POP3 LIST/RETR 분리 · SMTP 단계별 진단')
    st.caption('원본 메일은 서버에 보존합니다. 최신 30건을 직접 가져오며, 본문과 첨부는 현재 로그인 세션에서만 보관합니다.')
    with st.expander('메일 연결 설정 안내'):
        st.write('후이즈 웹메일 환경설정에서 POP/SMTP 사용을 활성화하고 상품별 실제 서버·보안 설정을 확인하세요.')
        st.write('Master 앱 Settings → Secrets에서 [auth] 등 첫 섹션 위에 아래 최상위 항목을 추가하세요. 기존 인증·AI·DB 설정은 보존하세요. 메일 비밀번호를 채팅이나 GitHub에 넣지 마세요.')
        st.code(SECRETS_TEMPLATE,language='toml')
        st.caption('표시한 포트는 TLS 설정 예시입니다. 상품별 설정을 확인하세요. SECURITY는 ssl 또는 starttls이며 암호화 없는 접속은 지원하지 않습니다.')
        st.link_button('후이즈 POP/SMTP 설정 안내','https://m.whois.co.kr/mail_wmail.php?act=process')
    try:
        config=mail_config(_settings(),principal)
    except PermissionError:
        st.session_state.pop('whois_mail_bundle',None)
        st.info('메일함 접근 권한을 확인할 수 없습니다. WHOIS_MAIL_OWNER_EMAILS에 현재 Master 로그인 계정을 지정하세요. 저장 후 앱을 재시작해야 할 수 있습니다.')
        st.caption('현재 Master 로그인 계정: ' + principal)
        st.caption('Secrets에서 메일함 소유자 설정 읽힘: ' + ('예' if _settings().get('WHOIS_MAIL_OWNER_EMAILS', '').strip() else '아니요'))
        return
    except ValueError as exc:
        st.session_state.pop('whois_mail_bundle',None)
        st.error(str(exc));return
    account=config.pop.account_id if config.pop else None
    bundle=st.session_state.get('whois_mail_bundle')
    if bundle and bundle[0]!=account:
        st.session_state.pop('whois_mail_bundle',None);bundle=None
    a,b=st.columns(2)
    a.caption('수신 서버: '+('설정 있음 · 연결 검사 가능' if config.pop else '설정 필요'))
    b.caption('발신 서버: '+('설정 있음 · 인증 검사 가능' if config.smtp else '설정 필요'))
    if a.button('수신 연결 테스트',key='whois_probe_pop',disabled=config.pop is None):
        try:
            count=probe_pop(config.pop)
            st.success(f'수신 서버 인증 성공 · UIDL {count}건 확인. 메일 본문을 가져오거나 삭제하지 않았습니다.')
        except MailConnectionError as exc: st.error(str(exc))
    if b.button('발신 연결 테스트 · 발송 없음',key='whois_probe_smtp',disabled=config.smtp is None):
        try:
            probe_smtp(config.smtp)
            st.success('발신 서버 TLS 인증 성공. 실제 메일은 발송하지 않았습니다.')
        except MailConnectionError as exc: st.error(str(exc))
    st.caption('실제 메일 발송과 앱을 닫은 상태의 자동 동기화는 아직 활성화하지 않았습니다.')
    limit = st.selectbox('조회할 최근 메일 수', [1, 5, 30], index=0, key='whois_fetch_limit', help='먼저 1건으로 서버 응답을 확인한 다음 5건, 30건으로 늘리세요.')
    if st.button('최신 메일 가져오기',key='whois_refresh',disabled=config.pop is None,type='primary'):
        try:
            with st.spinner('회사 메일을 가져옵니다…'):
                messages=fetch_messages(config.pop, limit=limit)
            stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S KST')
            bundle=(account,messages,stamp)
            st.session_state['whois_mail_bundle']=bundle
            st.session_state.pop('whois_refresh_failed',None)
        except MailConnectionError as exc:
            st.session_state['whois_refresh_failed']=True
            st.error(str(exc))
    if not bundle:
        st.info('서버 설정 후 연결 테스트와 메일 가져오기를 실행하세요. 샘플 메일은 업무 대시보드에서 확인할 수 있습니다.')
        return
    st.caption('마지막 조회 성공: '+bundle[2])
    if st.session_state.get('whois_refresh_failed'):
        st.warning('최근 갱신에 실패해 이전 조회 내용을 표시합니다.')
    render_inbox(bundle[1], account)


def _preview(body):
    """Short, plain-text list preview; no HTML from external messages."""
    return " ".join((body or "").split())[:88]


def _open_message(uid):
    st.session_state["whois_selected_uid"] = uid
    st.session_state.setdefault("whois_opened_uids", set()).add(uid)


def render_inbox(messages, account):
    """Two-pane read-only inbox. Server read/unread flags are never modified."""
    if st.session_state.get("whois_inbox_account") != account:
        st.session_state["whois_inbox_account"] = account
        st.session_state["whois_selected_uid"] = None
        st.session_state["whois_opened_uids"] = set()

    toolbar, order_col = st.columns([4, 1])
    with toolbar:
        query = st.text_input("메일 검색", placeholder="발신자, 제목, 본문 검색",
                              key="whois_mail_search")
    with order_col:
        order = st.selectbox("정렬", ["최신순", "오래된순"], key="whois_inbox_order")

    filtered = [m for m in messages if query.casefold().strip() in (
        m.sender + " " + m.subject + " " + m.body
    ).casefold()]
    if order == "오래된순":
        filtered.reverse()

    st.caption(f"받은메일함 · 이번 조회 {len(messages)}건 / 검색 결과 {len(filtered)}건"
               " · 열람 표시는 현재 세션 기준")
    if not filtered:
        st.info("검색 결과가 없습니다.")
        return

    valid_uids = {m.uid for m in filtered}
    selected_uid = st.session_state.get("whois_selected_uid")
    if selected_uid not in valid_uids:
        selected_uid = filtered[0].uid
    selected = next(m for m in filtered if m.uid == selected_uid)

    left, right = st.columns([2, 3], gap="medium")
    with left:
        st.markdown("**메일 목록**")
        for idx, mail in enumerate(filtered):
            attachment = " 📎" if mail.attachments else ""
            opened = mail.uid in st.session_state.get("whois_opened_uids", set())
            prefix = "● " if not opened else ""
            sender = mail.sender or "(발신자 없음)"
            subject = mail.subject or "(제목 없음)"
            preview = _preview(mail.body) or (mail.notice or "본문 없음")
            with st.container(border=True):
                st.button(
                    f"{prefix}{sender[:62]}{attachment}\\n{subject[:92]}",
                    key=f"whois_select_{idx}_{mail.uid}",
                    type="primary" if mail.uid == selected_uid else "secondary",
                    use_container_width=True,
                    on_click=_open_message,
                    args=(mail.uid,),
                )
                st.caption(preview)
                st.caption(mail.received_at or "날짜 없음")

    with right:
        st.markdown("**선택한 메일**")
        with st.container(border=True):
            st.text(selected.subject or "(제목 없음)")
            st.caption("보낸사람: " + (selected.sender or "(발신자 없음)"))
            st.caption("날짜: " + (selected.received_at or "날짜 없음"))
            if selected.notice:
                st.warning(selected.notice)
            st.divider()
            with st.container(height=390, border=False):
                st.text(selected.body or "(본문 없음)")
            if selected.attachments:
                st.markdown("**첨부파일**")
                for i, attachment in enumerate(selected.attachments):
                    st.download_button(
                        "📎 " + attachment.filename, attachment.content,
                        file_name=attachment.filename, mime=attachment.mime,
                        key=f"whois_attachment_{selected.uid}_{i}"
                    )
            st.divider()
            st.button(
                "이 메일로 AI 업무 요청 작성",
                key="whois_ai_" + selected.uid,
                disabled=not bool(selected.body),
                type="primary",
                use_container_width=True,
                on_click=_use_for_ai,
                args=(selected,),
            )
            st.caption("메일을 선택해도 AI가 자동 실행되지 않습니다. "
                       "요청을 검토하고 별도로 전송 동의해야 합니다. "
                       "첨부파일은 AI에 자동 전송하지 않습니다.")
