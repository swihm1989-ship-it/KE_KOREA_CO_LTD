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
    if not 1 <= limit <= 30:
        raise ValueError('한 번에 1~30건을 가져올 수 있습니다.')
    client = _pop(endpoint)
    try:
        try:
            entries = _uidl(client)[:limit]
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
        result = []
        total = 0
        for number, uid in entries:
            size = sizes.get(number)
            if size is None or size < 0 or size > MAX_MESSAGE_BYTES or total + size > MAX_BATCH_BYTES:
                result.append(MailMessage(uid, notice='크기 제한 또는 목록 누락으로 본문을 가져오지 않았습니다.'))
                continue
            try:
                lines = client.retr(number)[1]
                raw = b'\r\n'.join(lines)
            except Exception:
                result.append(MailMessage(uid, notice='이 메일의 POP3 본문(RETR) 조회에 실패했습니다.'))
                continue
            total += len(raw)
            if total > MAX_BATCH_BYTES:
                result.append(MailMessage(uid, notice='이번 조회의 용량 제한을 초과했습니다.'))
                break
            try:
                result.append(parse_message(uid, raw))
            except Exception:
                result.append(MailMessage(uid, notice='이 메일의 MIME 형식 해석에 실패했습니다.'))
        return tuple(result)
    finally:
        _finish(client)
