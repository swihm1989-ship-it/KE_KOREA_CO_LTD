"""Public RSS market headlines, fetched only after authentication.

RSS items are metadata links, not full licensed article text.
"""
from __future__ import annotations
from datetime import datetime, timedelta, time, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
import html
import re

KST = ZoneInfo("Asia/Seoul")
CATEGORIES = {
    "태양광": '("polysilicon" OR "solar wafer" OR "solar cell" OR "solar module") (PV Tech OR PV Insights OR solar) when:2d',
    "데이터센터": '("data center" OR "data centre") (AI power grid OR investment OR construction) when:2d',
    "원자재": '("crude oil" OR "natural gas" OR copper OR LNG) (price OR supply OR OPEC) when:2d',
    "증시·거시경제": '(stock market OR KOSPI OR Nasdaq OR Federal Reserve OR inflation) when:2d',
}
# Google News indexes third-party publishers; this is not a direct Bloomberg
# or Investing.com subscription/feed and their inclusion is not guaranteed.
def cutoff_kst(now: datetime) -> datetime:
    now = now.astimezone(KST)
    day = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    return datetime.combine(day, time(18), KST)


def parse_rss(xml_bytes: bytes, cutoff: datetime, now: datetime) -> list[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    rows = []
    for item in root.findall(".//item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        stamp = (item.findtext("pubDate") or "").strip()
        publisher = (item.findtext("source") or "").strip()
        if not title or not link.startswith("https://") or not stamp:
            continue
        try:
            published = parsedate_to_datetime(stamp)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(KST)
        except (TypeError, ValueError, IndexError):
            continue
        if not cutoff <= published <= now:
            continue
        rows.append({"title": title[:240], "url": link,
                     "publisher": publisher or "Google News",
                     "published": published.strftime("%m-%d %H:%M")})
    return rows


def fetch_category(category: str, now: datetime | None = None) -> list[dict[str, str]]:
    if category not in CATEGORIES:
        raise ValueError("Unknown category")
    now = (now or datetime.now(KST)).astimezone(KST)
    query = urlencode({"q": CATEGORIES[category], "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    url = "https://news.google.com/rss/search?" + query
    request = Request(url, headers={"User-Agent": "KEKOREA-MarketDashboard/1.0"})
    with urlopen(request, timeout=7) as response:
        content = response.read(1_000_001)
    if len(content) > 1_000_000:
        raise ValueError("RSS feed too large")
    rows = parse_rss(content, cutoff_kst(now), now)
    seen = set()
    unique = []
    for row in rows:
        key = re.sub(r"\\s+", " ", row["title"]).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique[:25]
