"""KE KOREA corporate email signature (email-client-compatible HTML).

Uses the exact company logo already shipped in the original KE KOREA app,
embedded via Content-ID in the outgoing email. No external image host needed.
Plain-text alternatives stay readable in clients that disable HTML or images.
"""
from __future__ import annotations

import base64
from html import escape
from io import BytesIO
from pathlib import Path
import re
from functools import lru_cache

LOGO_CID = "ke-korea-signature-logo"
SITE_URL = "https://www.ke-korea.co.kr"
SITE_TEXT = "www.ke-korea.co.kr"
LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "company_logo.png"


@lru_cache(maxsize=1)
def optimized_logo() -> bytes:
    """Return a compact PNG version of the existing logo. Never create a new logo."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if not LOGO_PATH.is_file() or LOGO_PATH.stat().st_size > 4_000_000:
        raise ValueError("KE KOREA 회사 로고 파일을 확인할 수 없습니다.")
    try:
        with Image.open(LOGO_PATH) as original:
            if original.format != "PNG" or original.width * original.height > 16_000_000:
                raise ValueError("KE KOREA 회사 로고 형식 또는 크기를 확인하세요.")
            image = ImageOps.exif_transpose(original).convert("RGBA")
            image.thumbnail((320, 200), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            data = output.getvalue()
    except (OSError, UnidentifiedImageError, ValueError):
        raise ValueError("KE KOREA 회사 로고를 읽거나 변환하지 못했습니다.") from None
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 300_000:
        raise ValueError("서명에 첨부할 회사 로고가 너무 큽니다.")
    return data


def signature_html(body_text: str, signature_text: str, *, logo_src: str) -> str:
    """Corporate style #2: navy name/title, divider, logo + company, URL.

    Every dynamic string is escaped. Only the exact company site is linked.
    HTML email uses inline CSS and table layout for Outlook compatibility.
    """
    content = str(body_text or "").strip()
    signature = str(signature_text or "").strip()
    if not content or not signature or len(signature)>1800:
        raise ValueError("메일 본문과 서명을 확인하세요.")
    lines = [line.strip() for line in signature.splitlines() if line.strip()]
    if len(lines) < 3:
        raise ValueError("이메일 서명에 이름, 직함, 회사명이 필요합니다.")
    name, title, company = lines[:3]
    rest = lines[3:]
    has_site = SITE_TEXT in rest
    address = [line for line in rest if line != SITE_TEXT]
    safe_src = str(logo_src)
    if not (safe_src == "cid:" + LOGO_CID or safe_src.startswith("data:image/png;base64,")):
        raise ValueError("서명 로고 경로가 유효하지 않습니다.")
    if safe_src.startswith("data:image/png;base64,"):
        # Preview-only data URL is built from our own packaged logo.
        base64.b64decode(safe_src.split(",", 1)[1], validate=True)
    html_body = escape(content).replace("\n", "<br>")
    address_html = "<br>".join(escape(x) for x in address)
    site_html = (
        '<div style="margin-top:10px;font-family:Arial,sans-serif;font-size:12px;">'
        '<a href="' + SITE_URL + '" style="color:#0877c9;text-decoration:none;">'
        + SITE_TEXT + "</a></div>" if has_site else ""
    )
    return (
        '<!doctype html><html><body style="margin:0;padding:0;'
        'font-family:Arial,Malgun Gothic,sans-serif;color:#243746;">'
        '<div style="white-space:normal;font-size:14px;line-height:1.75;">'
        + html_body + '</div>'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;margin-top:22px;max-width:500px;">'
        '<tr><td colspan="2" style="font-size:15px;font-weight:700;color:#092b4c;'
        'padding-bottom:3px;">' + escape(name) + '</td></tr>'
        '<tr><td colspan="2" style="font-size:12px;color:#526a7e;padding-bottom:13px;">'
        + escape(title) + '</td></tr>'
        '<tr><td colspan="2" style="border-top:1px solid #ccdae6;height:12px;">&nbsp;</td></tr>'
        '<tr><td valign="middle" style="width:125px;padding:3px 17px 3px 0;">'
        '<img src="' + escape(safe_src, quote=True) + '" width="118" alt="KE KOREA" '
        'style="width:118px;height:auto;display:block;border:0;max-width:118px;">'
        '</td><td valign="middle" style="font-family:Arial,Malgun Gothic,sans-serif;'
        'font-size:12px;line-height:1.65;color:#445e74;">'
        '<strong style="color:#092b4c;font-size:13px;">' + escape(company) + '</strong>'
        + ('<div style="margin-top:3px;">' + address_html + '</div>' if address_html else "")
        + '</td></tr><tr><td colspan="2">' + site_html + '</td></tr>'
        '</table></body></html>'
    )


def preview_signature_html(body_text: str, signature_text: str) -> str:
    """Self-contained HTML preview; data URIs never go in transmitted messages."""
    uri = "data:image/png;base64," + base64.b64encode(optimized_logo()).decode("ascii")
    return signature_html(body_text, signature_text, logo_src=uri)


def delivery_signature_html(body_text: str, signature_text: str) -> str:
    return signature_html(body_text, signature_text, logo_src="cid:" + LOGO_CID)
