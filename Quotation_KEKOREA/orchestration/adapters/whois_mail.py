"""Read-only TLS mailbox access and SMTP authentication. Never sends or deletes."""
from __future__ import annotations
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import PurePosixPath
from hashlib import sha256
from Quotation_KEKOREA.observability.core import traced
import poplib
import re
import socket
import smtplib
import ssl

SMTP_DIAGNOSTIC_REVISION = "smtp-starttls-20261112-v3"
POP_DIAGNOSTIC_REVISION = "pop-health-20261113-v4"
POP_FETCH_REVISION = "pop-fetch-older-fallback-20261113-v1"

MAX_MESSAGE_BYTES = 5_000_000
MAX_ATTACHMENT_BYTES = 2_000_000
MAX_BATCH_BYTES = 20_000_000

class MailConnectionError(RuntimeError):
    pass

@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    security: str
    username: str
    password: str = field(repr=False)

    @property
    def account_id(self):
        return sha256((self.host+'|'+self.username).encode()).hexdigest()

@dataclass(frozen=True)
class MailConfig:
    pop: Endpoint | None
    smtp: Endpoint | None

@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes = field(repr=False)
    mime: str = 'application/octet-stream'

@dataclass(frozen=True)
class MailMessage:
    uid: str
    sender: str = ''
    subject: str = ''
    body: str = field(default='',repr=False)
    received_at: str = ''
    attachments: tuple[Attachment,...] = ()
    notice: str = ''


def mail_config(values, principal: str) -> MailConfig:
    owners={x.strip().casefold() for x in str(values.get('WHOIS_MAIL_OWNER_EMAILS','')).split(',')
            if '@' in x and '*' not in x}
    if not principal or principal.casefold() not in owners:
        raise PermissionError('메일함 접근 계정이 설정되지 않았거나 권한이 없습니다.')
    def endpoint(kind):
        prefix='WHOIS_'+kind+'_'
        fields={x:str(values.get(prefix+x,'') or '') for x in ('HOST','USERNAME','PASSWORD')}
        for key in ('HOST','USERNAME'): fields[key]=fields[key].strip()
        if not all(fields.values()): return None
        host=fields['HOST']
        security=str(values.get(prefix+'SECURITY','ssl' if kind=='POP' else 'starttls')).lower()
        try: port=int(values.get(prefix+'PORT',995 if kind=='POP' else 587))
        except (TypeError,ValueError): raise ValueError(prefix+'PORT 설정을 확인하세요.') from None
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',host) or '.' not in host:
            raise ValueError(prefix+'HOST에는 URL 대신 실제 서버 호스트명을 입력하세요.')
        if security not in {'ssl','starttls'} or not 1<=port<=65535:
            raise ValueError(prefix+'PORT / SECURITY 설정을 확인하세요. TLS가 필요합니다.')
        if any('\r' in v or '\n' in v for v in fields.values()):
            raise ValueError(prefix+'설정에 줄바꿈을 넣을 수 없습니다.')
        return Endpoint(host,port,security,fields['USERNAME'],fields['PASSWORD'])
    return MailConfig(endpoint('POP'),endpoint('SMTP'))


def _pop(endpoint):
    client=None
    try:
        context=ssl.create_default_context()
        if endpoint.security=='ssl':
            client=poplib.POP3_SSL(endpoint.host,endpoint.port,timeout=12,context=context)
        else:
            client=poplib.POP3(endpoint.host,endpoint.port,timeout=12)
            client.stls(context=context)
        client.user(endpoint.username)
        client.pass_(endpoint.password)
        return client
    except Exception:
        if client is not None:
            try: client.close()
            except Exception: pass
        raise MailConnectionError('POP3 연결·인증에 실패했습니다. 서버, TLS, 계정 및 POP 사용 설정을 확인하세요.') from None


def _uidl(client):
    entries=[]; seen=set()
    for line in client.uidl()[1]:
        number,uid=line.decode('ascii').split()
        number=int(number)
        if number<=0 or uid in seen: raise ValueError('Invalid UIDL')
        seen.add(uid); entries.append((number,uid))
    return sorted(entries,reverse=True)


def _finish(client):
    try: client.quit()
    except Exception:
        try: client.close()
        except Exception: pass


def probe_pop(endpoint: Endpoint) -> int:
    client=_pop(endpoint)
    try: return len(_uidl(client))
    except Exception:
        raise MailConnectionError('POP3 UIDL 조회에 실패했습니다. 메일 서버의 UIDL 지원을 확인하세요.') from None
    finally:
        _finish(client)



def probe_pop_diagnostics(endpoint: Endpoint) -> dict:
    """Owner-invoked, read-only POP3 health probe; never returns message data.

    Each status is based on POP3 protocol results, not guessed from the UI
    cache. Server error text and message IDs remain private.
    """
    client = _pop(endpoint)
    try:
        try:
            entries = _uidl(client)
        except Exception:
            return {'stage': 'uidl_failed', 'message_count': None, 'list_count': None,
                    'retr': 'not_attempted', 'size': None}
        try:
            sizes = {}
            for line in client.list()[1]:
                fields = line.split()
                if len(fields) >= 2:
                    sizes[int(fields[0])] = int(fields[1])
        except Exception:
            return {'stage': 'list_failed', 'message_count': len(entries), 'list_count': None,
                    'retr': 'not_attempted', 'size': None}
        if not entries:
            return {'stage': 'empty', 'message_count': 0, 'list_count': len(sizes),
                    'retr': 'not_attempted', 'size': None}
        number, _uid = entries[0]
        size = sizes.get(number)
        size_group = ('missing' if size is None else
                      'too_large' if size > MAX_MESSAGE_BYTES else
                      'valid' if size >= 0 else 'invalid')
        if size_group != 'valid':
            return {'stage': 'size_blocked', 'message_count': len(entries),
                    'list_count': len(sizes), 'retr': 'not_attempted', 'size': size_group}
        try:
            # Deliberate read-only RETR: discard bytes without parsing, storing,
            # displaying or logging any message content.
            _status, _lines, _octets = client.retr(number)
            retr = 'success'
        except poplib.error_proto:
            retr = 'server_rejected'
        except (TimeoutError, socket.timeout):
            retr = 'timeout'
        except (OSError, EOFError, ssl.SSLError):
            retr = 'connection_error'
        except Exception:
            retr = 'failed'
        return {'stage': 'completed', 'message_count': len(entries),
                'list_count': len(sizes), 'retr': retr, 'size': size_group}
    finally:
        _finish(client)



def probe_pop_cross_diagnostics(endpoint: Endpoint) -> dict:
    """Read-only 3-point diagnostic; returns no UID, header, body, or server text.

    Explicit button only. Each sample opens a fresh TLS connection and resolves
    its message number again by UIDL, so one rejected RETR cannot poison the
    following sample. No writes, send, mail parsing or telemetry payloads.
    """
    client = _pop(endpoint)
    try:
        entries = _uidl(client)
        count = len(entries)
    except Exception:
        raise MailConnectionError("POP3 교차 진단 UIDL 조회 실패") from None
    finally:
        _finish(client)
    if not count:
        return {"message_count": 0, "samples": []}
    offsets = list(dict.fromkeys((0, count // 2, count - 1)))
    labels = ("newest", "middle", "oldest")
    samples = []
    for index, offset in enumerate(offsets):
        session = None
        record = {"position": labels[index] if count >= 3 else
                  ("newest" if offset == 0 else "oldest"),
                  "retr": "not_attempted", "top": "not_attempted",
                  "size": "unknown"}
        try:
            session = _pop(endpoint)
            current = _uidl(session)
            if offset >= len(current):
                record["retr"] = "missing"
            else:
                number, _ = current[offset]
                sizes = {}
                for line in session.list()[1]:
                    values = line.split()
                    if len(values) >= 2:
                        sizes[int(values[0])] = int(values[1])
                size = sizes.get(number)
                if size is None or size < 0:
                    record["size"] = "missing"
                elif size > MAX_MESSAGE_BYTES:
                    record["size"] = "too_large"
                else:
                    record["size"] = "valid"
                    try:
                        # POP3 RETR is read-only. Discard all returned bytes.
                        session.retr(number)
                        record["retr"] = "success"
                    except poplib.error_proto:
                        record["retr"] = "server_rejected"
                    except (socket.timeout, TimeoutError):
                        record["retr"] = "timeout"
                    except (OSError, EOFError, ssl.SSLError):
                        record["retr"] = "connection_error"
                    except Exception:
                        record["retr"] = "failed"
                    # TOP is optional, and its rejection does not imply RETR
                    # rejection. Request only headers and discard the result.
                    try:
                        session.top(number, 0)
                        record["top"] = "success"
                    except poplib.error_proto:
                        record["top"] = "server_rejected_or_unsupported"
                    except (socket.timeout, TimeoutError):
                        record["top"] = "timeout"
                    except (OSError, EOFError, ssl.SSLError):
                        record["top"] = "connection_error"
                    except Exception:
                        record["top"] = "failed"
        except MailConnectionError:
            record["retr"] = "connection_error"
        except Exception:
            record["retr"] = "diagnostic_failed"
        finally:
            if session is not None:
                _finish(session)
        samples.append(record)
    return {"message_count": count, "samples": samples}


def probe_smtp(endpoint: Endpoint) -> None:
    """Verify SMTP over TLS without sending mail or exposing server responses."""
    client = None
    stage = "connect"
    try:
        context = ssl.create_default_context()
        if endpoint.security == "ssl":
            client = smtplib.SMTP_SSL(endpoint.host, endpoint.port, timeout=12, context=context)
            stage = "login"
        else:
            client = smtplib.SMTP(endpoint.host, endpoint.port, timeout=12)
            stage = "ehlo"
            client.ehlo()
            stage = "starttls"
            client.starttls(context=context)
            stage = "ehlo_tls"
            client.ehlo()
            stage = "login"
        client.login(endpoint.username, endpoint.password)
    except smtplib.SMTPAuthenticationError as exc:
        # SMTP code is numeric; never print exc.smtp_error (may include private data).
        code = getattr(exc, "smtp_code", None)
        suffix = f" (SMTP {code})" if isinstance(code, int) else ""
        raise MailConnectionError("SMTP 계정 인증 거부" + suffix +
                                  ": 아이디·비밀번호·SMTP 사용 권한을 확인하세요.") from None
    except socket.gaierror:
        raise MailConnectionError("SMTP DNS 조회 실패: 서버 호스트명을 확인하세요.") from None
    except (TimeoutError, socket.timeout):
        raise MailConnectionError("SMTP 접속 시간 초과 (" + stage +
                                  " 단계): 클라우드에서 587 포트 접근이 차단됐거나 서버 응답이 지연될 수 있습니다.") from None
    except ConnectionRefusedError:
        raise MailConnectionError("SMTP TCP 연결 거부: 서버의 587 포트 허용 여부를 확인하세요.") from None
    except ssl.SSLCertVerificationError:
        raise MailConnectionError("SMTP TLS 인증서 검증 실패: 서버 인증서를 확인하세요.") from None
    except smtplib.SMTPNotSupportedError:
        raise MailConnectionError(
            "SMTP 서버가 STARTTLS 기능을 광고하지 않았습니다 (EHLO). "
            "서버 설정 또는 클라우드 네트워크 중간장비의 SMTP 응답 변경 여부를 확인하세요."
        ) from None
    except ssl.SSLError as exc:
        reason = getattr(exc, "reason", "")
        known_reasons = {
            "WRONG_VERSION_NUMBER": "TLS 프로토콜 버전 불일치",
            "TLSV1_ALERT_PROTOCOL_VERSION": "서버 TLS 버전 거부",
            "CERTIFICATE_VERIFY_FAILED": "서버 인증서 검증 오류",
            "UNEXPECTED_EOF_WHILE_READING": "TLS 연결이 협상 중 종료됨",
            "SSLV3_ALERT_HANDSHAKE_FAILURE": "TLS 핸드셰이크 거부",
        }
        kind = known_reasons.get(reason, "TLS 핸드셰이크 오류")
        raise MailConnectionError(
            "SMTP STARTTLS 명령 이후 " + kind +
            ": 서버 TLS 정책 또는 네트워크 중간장비를 확인하세요."
        ) from None
    except smtplib.SMTPResponseException as exc:
        code = getattr(exc, "smtp_code", None)
        suffix = f" (SMTP {code})" if isinstance(code, int) else ""
        raise MailConnectionError("SMTP 서버 응답 거부 (" + stage + " 단계)" + suffix +
                                  ": 서버 정책·접속 IP 제한을 확인하세요.") from None
    except (OSError, smtplib.SMTPException):
        raise MailConnectionError("SMTP 통신 실패 (" + stage +
                                  " 단계): 네트워크 또는 SMTP 서버 설정을 확인하세요.") from None
    finally:
        if client is not None:
            _finish(client)

class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}: self.hidden+=1
        if tag in {'p','br','div','li','tr'}: self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style'}: self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)


def parse_message(uid: str, raw: bytes) -> MailMessage:
    if len(raw)>MAX_MESSAGE_BYTES: return MailMessage(uid,notice='크기 제한으로 본문을 가져오지 않았습니다.')
    msg=BytesParser(policy=policy.default).parsebytes(raw)
    bodypart=msg.get_body(preferencelist=('plain','html'))
    body=''
    if bodypart is not None:
        try: body=bodypart.get_content()
        except (LookupError,UnicodeError,ValueError):
            body=(bodypart.get_payload(decode=True) or b'').decode('utf-8',errors='replace')
        if not isinstance(body,str):body=''
        if bodypart.get_content_type()=='text/html':
            parser=_PlainHTML();parser.feed(body);body=''.join(parser.parts)
    attachments=[]; notices=[]; total=0
    for part in msg.iter_attachments():
        if not part.get_filename(): continue
        payload=part.get_payload(decode=True) or b''
        total+=len(payload)
        if len(payload)>MAX_ATTACHMENT_BYTES or total>MAX_MESSAGE_BYTES or len(attachments)>=10:
            notices.append('제한을 초과한 첨부는 제외했습니다.');continue
        name=PurePosixPath(part.get_filename().replace('\\','/')).name
        name=re.sub(r'[\x00-\x1f\x7f]','_',name)[:180] or 'attachment.bin'
        if name in {'.','..'}: name='attachment.bin'
        attachments.append(Attachment(name,payload,part.get_content_type()))
    return MailMessage(uid,str(msg.get('From',''))[:500],str(msg.get('Subject','(제목 없음)'))[:500],
                       body[:20000],str(msg.get('Date',''))[:100],tuple(attachments),' '.join(set(notices)))


@traced('mail.collect')
def fetch_messages(endpoint: Endpoint, limit: int=30) -> tuple[MailMessage,...]:
    """Read recent messages, retry failed RETR once with a fresh UIDL snapshot.

    A failed RETR is NOT an empty email: never render an anonymous placeholder
    or replace a previously successful cached message with an error record.
    Reconnecting is bounded to one additional session per batch. No DELE.
    """
    if not 1 <= limit <= 30:
        raise ValueError('한 번에 1~30건을 가져올 수 있습니다.')
    client = _pop(endpoint)
    result = []
    failed_uids = []
    total = 0
    try:
        try:
            all_entries = _uidl(client)
            entries = all_entries[:limit]
        except Exception:
            raise MailConnectionError('메일 UIDL 목록 조회에 실패했습니다.') from None
        try:
            sizes = {}
            for line in client.list()[1]:
                parts = line.split()
                if len(parts) >= 2:
                    sizes[int(parts[0])] = int(parts[1])
        except Exception:
            raise MailConnectionError('메일 크기 목록(LIST) 조회에 실패했습니다.') from None
        for number, uid in entries:
            size = sizes.get(number)
            if size is None or size < 0 or size > MAX_MESSAGE_BYTES or total + size > MAX_BATCH_BYTES:
                result.append(MailMessage(uid, notice='크기 제한 또는 목록 누락으로 본문을 가져오지 않았습니다.'))
                continue
            try:
                lines = client.retr(number)[1]
                raw = b'\r\n'.join(lines)
            except Exception:
                failed_uids.append(uid)
                continue
            total += len(raw)
            if total > MAX_BATCH_BYTES:
                break
            try:
                result.append(parse_message(uid, raw))
            except Exception:
                # A MIME parsing error is not an empty message either.
                failed_uids.append(uid)
    finally:
        _finish(client)

    if failed_uids:
        # Some POP3 servers drop long-lived RETR sessions. Re-authenticate only
        # once and resolve message numbers by UIDL again, since POP3 sequence
        # numbers can change between sessions. Do not retry deleted/missing UIDs.
        retry_client = None
        try:
            retry_client = _pop(endpoint)
            current = {uid: number for number, uid in _uidl(retry_client)}
            retry_sizes = {}
            for line in retry_client.list()[1]:
                parts = line.split()
                if len(parts) >= 2:
                    retry_sizes[int(parts[0])] = int(parts[1])
            # Start with the oldest failed UID so a problematic newest message
            # cannot prevent other messages in the same retry session.
            for uid in reversed(failed_uids):
                number = current.get(uid)
                size = retry_sizes.get(number)
                if number is None or size is None or size < 0 or size > MAX_MESSAGE_BYTES:
                    continue
                if total + size > MAX_BATCH_BYTES:
                    continue
                try:
                    raw = b'\r\n'.join(retry_client.retr(number)[1])
                    total += len(raw)
                    if total > MAX_BATCH_BYTES:
                        break
                    result.append(parse_message(uid, raw))
                except Exception:
                    continue
        except (MailConnectionError, OSError, ValueError, poplib.error_proto):
            pass
        finally:
            if retry_client is not None:
                _finish(retry_client)

    # If a faulty recent item poisons both batch connections, do not hide
    # every older mail. Probe a bounded set of older UIDs, each in its own
    # connection, only when the normal batch yielded no readable message.
    # There are at most THREE extra reads; no DELE or message mutation.
    if failed_uids and not any(m.body or m.subject or m.sender for m in result):
        candidates = tuple(dict.fromkeys((
            limit, len(all_entries) // 2, len(all_entries) - 1,
        )))
        recovered = 0
        for position in candidates:
            if position < limit or position >= len(all_entries):
                continue
            uid = all_entries[position][1]
            backup = None
            try:
                backup = _pop(endpoint)
                # Message sequence numbers may change after a reconnect.
                fresh = {item_uid: number for number, item_uid in _uidl(backup)}
                number = fresh.get(uid)
                if number is None:
                    continue
                size = None
                for line in backup.list()[1]:
                    parts = line.split()
                    if len(parts) >= 2 and int(parts[0]) == number:
                        size = int(parts[1])
                        break
                if size is None or not 0 <= size <= MAX_MESSAGE_BYTES:
                    continue
                if total + size > MAX_BATCH_BYTES:
                    continue
                raw = b'\r\n'.join(backup.retr(number)[1])
                if len(raw) > MAX_MESSAGE_BYTES or total + len(raw) > MAX_BATCH_BYTES:
                    continue
                total += len(raw)
                parsed = parse_message(uid, raw)
                if not (parsed.sender or parsed.subject or parsed.body):
                    continue
                result.append(parsed)
                recovered += 1
            except Exception:
                # Do not leak the POP3 exception; it can contain private data.
                continue
            finally:
                if backup is not None:
                    _finish(backup)
            if recovered >= 2:
                break

    if failed_uids and not any(message.body or message.subject or message.sender
                                for message in result):
        # Preserve previous in-session successful cache through the UI caller.
        # Never expose the POP3 server exception, which can contain account data.
        raise MailConnectionError(
            'POP3 본문(RETR) 조회 실패: 메일 서버가 본문 요청을 처리하지 못했습니다. '
            '기존 정상 메일은 유지합니다. 잠시 후 다시 동기화하거나 후이즈 POP3 서버 상태를 확인하세요.'
        )
    # Newer UIDL first; never include failed anonymous placeholders. An
    # earlier cache entry with the same UID remains authoritative in the UI.
    order = {uid: pos for pos, (_, uid) in enumerate(entries)}
    return tuple(sorted(result, key=lambda message: order.get(message.uid, len(order))))
