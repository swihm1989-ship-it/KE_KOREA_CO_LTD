"""Authenticated mailbox UI; credentials come only from server configuration."""
from datetime import datetime
import hashlib
import importlib
import marshal
import os
import sys
import time
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


def _use_for_ai(message, extract=False, attachments=(), requested=None):
    from Quotation_KEKOREA.orchestration.workflows.mail_intake import queue_handoff
    queue_handoff(st.session_state, message, extract=extract, attachments=attachments, requested=requested)


def _ensure_smtp_adapter_current():
    """Reload a stale imported module after a Streamlit hot deployment.

    Streamlit may rerun the UI source while keeping imported modules cached.
    Only reload when the adapter declares a different revision; never reload
    on every fragment poll or touch secrets.
    """
    global mail_config, probe_pop, probe_smtp, fetch_messages, MailConnectionError
    module = sys.modules.get(probe_smtp.__module__)
    expected = "smtp-starttls-20261112-v3"
    pop_expected = "pop-health-20261113-v4"
    fetch_expected = "pop-fetch-older-fallback-20261113-v1"
    if module is None:
        return False
    if (getattr(module, "SMTP_DIAGNOSTIC_REVISION", None) == expected
            and getattr(module, "POP_DIAGNOSTIC_REVISION", None) == pop_expected
            and getattr(module, "POP_FETCH_REVISION", None) == fetch_expected
            and callable(getattr(module, "probe_pop_diagnostics", None))):
        return False
    try:
        importlib.invalidate_caches()
        refreshed = importlib.reload(module)
    except (ImportError, OSError, SyntaxError):
        return False
    if (getattr(refreshed, "SMTP_DIAGNOSTIC_REVISION", None) != expected
            or getattr(refreshed, "POP_DIAGNOSTIC_REVISION", None) != pop_expected
            or getattr(refreshed, "POP_FETCH_REVISION", None) != fetch_expected
            or not callable(getattr(refreshed, "probe_pop_diagnostics", None))):
        return False
    mail_config = refreshed.mail_config
    probe_pop = refreshed.probe_pop
    probe_smtp = refreshed.probe_smtp
    fetch_messages = refreshed.fetch_messages
    MailConnectionError = refreshed.MailConnectionError
    # Old session data could refer to prior dataclass implementations.
    for key in ("whois_mail_bundle", "whois_poll_account",
                "whois_last_poll", "whois_refresh_failed"):
        st.session_state.pop(key, None)
    return True


def _smtp_runtime_diagnostics():
    """Identify the callable actually used by the button, never read secrets."""
    module = sys.modules.get(probe_smtp.__module__)
    revision = getattr(module, "SMTP_DIAGNOSTIC_REVISION", "미등록(이전 버전)")
    current = getattr(module, "probe_smtp", None) is probe_smtp
    try:
        fingerprint = hashlib.sha256(marshal.dumps(probe_smtp.__code__)).hexdigest()[:12]
    except (AttributeError, TypeError, ValueError):
        fingerprint = "확인 불가"
    return revision, fingerprint, current


def render_mailbox(principal):
    if not principal: raise PermissionError('로그인이 필요합니다.')
    refreshed_smtp_module = _ensure_smtp_adapter_current()
    st.subheader('후이즈 회사 메일함')
    if refreshed_smtp_module:
        st.success("이전 메일 연결 모듈을 감지하여 최신 POP3/SMTP 코드로 다시 로딩했습니다.")
    adapter_module = sys.modules.get(probe_pop.__module__)
    running_pop_revision = getattr(adapter_module, "POP_DIAGNOSTIC_REVISION", "이전/미확인")
    running_fetch_revision = getattr(adapter_module, "POP_FETCH_REVISION", "이전/미확인")
    st.caption("실행 중 POP3 모듈: " + str(running_pop_revision) +
               " · 수신 복구 코드: " + str(running_fetch_revision) +
               " · 함수 연결: " +
               ("일치" if getattr(adapter_module, "fetch_messages", None) is fetch_messages
                else "불일치 · 앱 재시작 필요"))
    st.caption('메일 동기화 버전: 2026-11-13-RECOVERY · 화면 열림 중 60초마다 자동 갱신')
    st.caption('화면이 열려 있는 동안 60초마다 새 메일을 확인합니다. 최근 메일은 현재 로그인 세션에서만 보관하며 원본은 서버에 보존합니다.')
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
    if config.pop:
        # Owner-only view, after mail_config authorization. This is the
        # configured POP3 login, not a claim that RETR succeeded.
        st.caption('설정된 POP3 수신 계정: ' + config.pop.username)
        if config.pop.username.strip().casefold() != 'david.ihm@ke-korea.com':
            st.warning('현재 POP3 설정 계정은 david.ihm@ke-korea.com과 다릅니다. Streamlit Secrets의 WHOIS_POP_USERNAME을 확인하세요.')
        else:
            st.info('POP3 수신 계정 설정은 david.ihm@ke-korea.com입니다. 실제 본문 조회 가능 여부는 아래 POP3 상세 진단으로 확인하세요.')
        if st.button('POP3 상세 진단 · 메일 발송/삭제 없음', key='whois_pop_diagnostics'):
            # Streamlit hot deployment can keep an older adapter in sys.modules.
            # Never let a missing diagnostic callable crash the owner's mailbox.
            module = sys.modules.get(probe_pop.__module__)
            diagnostic_callable = getattr(module, 'probe_pop_diagnostics', None)
            try:
                if not callable(diagnostic_callable):
                    if _ensure_smtp_adapter_current():
                        module = sys.modules.get(probe_pop.__module__)
                        diagnostic_callable = getattr(module, 'probe_pop_diagnostics', None)
                if not callable(diagnostic_callable):
                    st.warning('POP3 진단 모듈이 이전 버전입니다. 앱 Manage app에서 Reboot 후 다시 시도하세요.')
                else:
                    report = diagnostic_callable(config.pop)
                    st.session_state['whois_pop_diagnostic_result'] = (account, report)
            except MailConnectionError as exc:
                st.session_state['whois_pop_diagnostic_result'] = None
                st.error(str(exc))
        diagnostic = st.session_state.get('whois_pop_diagnostic_result')
        if diagnostic and diagnostic[0] == account:
            report = diagnostic[1]
            st.caption('POP3 진단 · UIDL 메일 수: ' + str(report['message_count']) +
                       ' · LIST 항목 수: ' + str(report['list_count']) +
                       ' · 본문 RETR: ' + report['retr'] +
                       ' · 크기 검사: ' + str(report['size']))
            if report['stage'] == 'empty':
                st.warning('POP3 서버가 현재 수신 계정의 메일을 0건으로 보고합니다. 웹메일의 실제 수신함과 POP3 제공 범위·설정을 비교하세요.')
            elif report['retr'] != 'success':
                st.warning('POP3 본문 조회가 정상 완료되지 않았습니다. UIDL/LIST와 RETR 단계를 구분해 확인하세요. 서버 원문은 출력하지 않습니다.')
            else:
                st.success('POP3 UIDL/LIST와 최근 메일 1건의 RETR 조회에 성공했습니다. 본문 내용은 출력하거나 저장하지 않았습니다.')
    if config.pop:
        if st.button('POP3 교차 진단 (최신·중간·오래된 메일, 읽기 전용)',
                     key='whois_pop_cross_diagnostics'):
            adapter = sys.modules.get(probe_pop.__module__)
            cross_diagnostic = getattr(adapter, 'probe_pop_cross_diagnostics', None)
            if not callable(cross_diagnostic):
                _ensure_smtp_adapter_current()
                adapter = sys.modules.get(probe_pop.__module__)
                cross_diagnostic = getattr(adapter, 'probe_pop_cross_diagnostics', None)
            if not callable(cross_diagnostic):
                st.warning('새 POP3 교차 진단 모듈을 아직 불러오지 못했습니다. Manage app에서 Reboot 후 다시 시도하세요.')
            else:
                try:
                    report = cross_diagnostic(config.pop)
                    st.session_state['whois_pop_cross_result'] = (account, report)
                except MailConnectionError as exc:
                    st.error(str(exc))
        cross = st.session_state.get('whois_pop_cross_result')
        if cross and cross[0] == account:
            report = cross[1]
            st.caption('POP3 교차 진단 · UIDL 총 ' + str(report['message_count']) +
                       '건 · 최대 3건 검사 · 개인정보/메일 원문 표시 없음')
            if report['samples']:
                st.table([{'위치': {'newest':'최신', 'middle':'중간', 'oldest':'오래된'}[row['position']],
                           '크기': row['size'], 'RETR 본문': row['retr'],
                           'TOP 헤더': row['top']} for row in report['samples']])
                st.caption('서버가 TOP 명령을 지원하지 않을 수도 있습니다. TOP 거부만으로 본문 조회 장애를 확정하지 않습니다.')
            else:
                st.warning('POP3 UIDL에서 메일이 0건으로 응답했습니다.')
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
    st.caption('후이즈 공식 SMTP: smtp.whoisworks.com · 587 · STARTTLS. '
               '실패하면 DNS/TCP/TLS/인증 단계만 표시하고 비밀번호는 표시하지 않습니다.')
    revision, fingerprint, current = _smtp_runtime_diagnostics()
    with st.expander("실행 중 SMTP 모듈 진단", expanded=True):
        st.text("실행 중 SMTP 모듈 버전: " + revision)
        st.text("실제 사용 함수 SHA256(코드): " + fingerprint)
        st.text("모듈 함수 연결: " + ("일치" if current else "불일치 (캐시 모듈 점검 필요)"))
        st.text("SMTP 단계별 진단 코드: " +
                ("적용됨" if revision == "smtp-starttls-20261112-v3" else "이전/미확인"))
        if revision != "smtp-starttls-20261112-v3":
            st.warning("재로딩 후에도 이전 모듈입니다. Streamlit Cloud의 배포 커밋과 Python 프로세스를 점검하세요.")
        st.caption("진단값은 현재 실행 중인 Python 함수에서 계산합니다. "
                   "SMTP 비밀번호, 서버 응답 원문, 메일 내용은 표시하지 않습니다.")
    if b.button('발신 연결 테스트 · 발송 없음',key='whois_probe_smtp',disabled=config.smtp is None):
        try:
            probe_smtp(config.smtp)
            st.success('발신 서버 TLS 인증 성공. 실제 메일은 발송하지 않았습니다.')
        except MailConnectionError as exc: st.error(str(exc))
    st.caption('실제 메일 발송이나 앱을 닫은 상태의 24시간 수집은 별도 서버 작업자가 필요합니다.')
    _live_mailbox(config.pop, account)


def _merge_messages(previous, incoming, max_count=30):
    """Stable server UIDL based deduplication; keep previous entries when a poll fails."""
    merged = {}
    # A failed POP3 RETR used to create an anonymous placeholder. Never let
    # those records displace actual content, including older cached messages.
    for item in incoming:
        if item.notice and 'RETR' in item.notice and not (item.sender or item.subject or item.body):
            continue
        merged[item.uid] = item
    for item in previous:
        if item.notice and 'RETR' in item.notice and not (item.sender or item.subject or item.body):
            continue
        merged.setdefault(item.uid, item)
    return tuple(list(merged.values())[:max_count])


@st.fragment(run_every="60s")
def _live_mailbox(pop, account):
    """Per-session near-real-time inbox, without a shared background reader."""
    if st.session_state.get("whois_poll_account") != account:
        st.session_state["whois_poll_account"] = account
        st.session_state.pop("whois_mail_bundle", None)
        st.session_state.pop("whois_last_poll", None)
        st.session_state.pop("whois_refresh_failed", None)

    now = time.monotonic()
    due = (pop is not None and (
        "whois_last_poll" not in st.session_state
        or now - st.session_state["whois_last_poll"] >= 55
    ))
    if st.button("지금 동기화", key="whois_refresh", disabled=pop is None):
        due = pop is not None
    if due:
        # An attempted poll is rate-limited even after failure.
        st.session_state["whois_last_poll"] = now
        try:
            # Small POP3 batches avoid long-lived connections on hosted webmail.
            # Each poll fetches the newest 5 and retains up to 30 known UIDs.
            incoming = fetch_messages(pop, limit=5)
            old = st.session_state.get("whois_mail_bundle")
            previous = old[1] if old and old[0] == account else ()
            result = _merge_messages(previous, incoming)
            timestamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
            st.session_state["whois_mail_bundle"] = (account, result, timestamp)
            st.session_state.pop("whois_refresh_failed", None)
        except MailConnectionError as exc:
            st.session_state["whois_refresh_failed"] = True
            st.warning("자동 동기화 실패: " + str(exc))
    bundle = st.session_state.get("whois_mail_bundle")
    if bundle and bundle[0] == account:
        # Clean placeholders left in an already-open session by older deploys,
        # even when every new RETR still fails and the poll raises an error.
        cleaned = _merge_messages((), bundle[1])
        if cleaned != bundle[1]:
            bundle = (bundle[0], cleaned, bundle[2])
            st.session_state["whois_mail_bundle"] = bundle
    st.caption("자동 갱신 주기: 60초 · 한 번에 최신 5건 확인 · 세션 내 최대 30건 보관")
    if not pop:
        st.info("수신 서버 설정이 필요합니다.")
        return
    if not bundle:
        st.info("초기 동기화가 완료되지 않았습니다. 다음 자동 확인 또는 지금 동기화를 이용하세요.")
        return
    st.caption("마지막 POP3 동기화 완료: " + bundle[2] +
               " · 표시 가능한 메일 " + str(len(bundle[1])) + "건")
    if not bundle[1] and not st.session_state.get("whois_refresh_failed"):
        st.info("이번 동기화에서 표시 가능한 메일이 0건입니다. POP3 서버에 실제 메일이 0건인지, 본문 조회가 차단됐는지는 위 'POP3 상세 진단'에서 구분해 확인하세요.")
    if st.session_state.get("whois_refresh_failed"):
        st.warning("최근 동기화에 실패해 마지막 성공 메일을 유지합니다.")
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
                    f"{prefix}{sender[:62]}{attachment}\n{subject[:92]}",
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
            from Quotation_KEKOREA.orchestration.workflows.mail_intake import prepare_mail_request
            try:
                detected = prepare_mail_request(selected.subject, selected.body)
                detected_kinds = detected.kinds
                st.caption("문서 요청 인식: " + (", ".join(detected_kinds) or "문서 종류를 AI 업무 요청에서 선택하세요"))
            except ValueError as exc:
                detected_kinds = ()
                st.warning(str(exc))
            from Quotation_KEKOREA.orchestration.router import DOC_TYPES
            # Explicit correction also supports valid mails without recognizable
            # document names. Keep choices isolated per selected message UID.
            chosen_kinds = st.multiselect(
                "준비할 문서 종류 (자동 인식 오류 시 직접 선택)",
                list(DOC_TYPES), default=list(detected_kinds),
                key='whois_ai_kinds_' + selected.uid,
            )
            available = [(i,a) for i,a in enumerate(selected.attachments)
                         if a.mime in {'application/pdf','image/png','image/jpeg','image/webp'}]
            chosen = []
            if available:
                indexes = st.multiselect("AI에 함께 보낼 첨부파일 (선택)", [i for i,a in available],
                    format_func=lambda i:selected.attachments[i].filename,
                    key='whois_ai_attachments_'+selected.uid)
                chosen = [{'name':selected.attachments[i].filename,
                           'mime_type':selected.attachments[i].mime,
                           'data':selected.attachments[i].content} for i in indexes]
            st.caption("아래 추출 버튼을 누르면 선택한 메일 제목·본문과 직접 선택한 첨부만 외부 AI에 전송합니다. "
                       "CIPL은 CI·PL을 각각 준비하며 CI 출력에는 원본 PI가 필요합니다.")
            st.button("AI로 거래조건 추출·문서 준비", key='whois_ai_extract_'+selected.uid,
                      disabled=not bool(chosen_kinds) or not bool(selected.body and selected.body.strip()), type='primary', width='stretch',
                      on_click=_use_for_ai, args=(selected,True,chosen,chosen_kinds))
            st.button(
                "이 메일로 AI 업무 요청 작성",
                key="whois_ai_" + selected.uid,
                disabled=not bool(selected.body),
                type="primary",
                use_container_width=True,
                on_click=_use_for_ai,
                args=(selected,),
            )
            st.caption("위 ‘요청 작성’ 버튼은 입력창으로만 이동합니다. 메일 열람·동기화만으로는 AI를 실행하지 않습니다.")
