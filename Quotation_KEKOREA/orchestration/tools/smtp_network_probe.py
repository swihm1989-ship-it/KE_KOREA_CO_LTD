"""Non-authenticated SMTP STARTTLS probe. Prints only safe stages and TLS version."""
from __future__ import annotations
import socket
import ssl
import smtplib
import sys

HOST = "smtp.whoisworks.com"
PORT = 587


def probe():
    try:
        addresses = socket.getaddrinfo(HOST, PORT, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return "DNS_FAILURE"
    if not addresses:
        return "DNS_EMPTY"
    try:
        with smtplib.SMTP(HOST, PORT, timeout=8) as client:
            code, _ = client.ehlo()
            if code != 250:
                return "EHLO_UNEXPECTED_STATUS"
            if not client.has_extn("starttls"):
                return "STARTTLS_NOT_ADVERTISED"
            try:
                code, _ = client.starttls(context=ssl.create_default_context())
                if code != 220:
                    return "STARTTLS_REJECTED"
                return "TLS_OK version=" + str(client.sock.version())
            except ssl.SSLCertVerificationError:
                return "CERTIFICATE_VERIFICATION_FAILURE"
            except ssl.SSLError as exc:
                reason = getattr(exc, "reason", None)
                allowed = {"WRONG_VERSION_NUMBER", "TLSV1_ALERT_PROTOCOL_VERSION",
                           "UNEXPECTED_EOF_WHILE_READING", "SSLV3_ALERT_HANDSHAKE_FAILURE"}
                known_classes = {"SSLEOFError", "SSLCertVerificationError", "SSLZeroReturnError", "SSLError"}
                category = type(exc).__name__ if type(exc).__name__ in known_classes else "SSLError"
                return "TLS_HANDSHAKE_FAILURE " + category + " " + (
                    reason if reason in allowed else "OTHER"
                )
    except (TimeoutError, socket.timeout):
        return "NETWORK_TIMEOUT"
    except (ConnectionRefusedError, ConnectionResetError):
        return "NETWORK_CONNECTION_REFUSED_OR_RESET"
    except (smtplib.SMTPException, OSError):
        return "SMTP_TRANSPORT_FAILURE"


if __name__ == "__main__":
    result = probe()
    print("WHOIS_SMTP_STARTTLS_PROBE", result)
    # Observation-only: do not fail workflows due to external network limits.
    sys.exit(0)
