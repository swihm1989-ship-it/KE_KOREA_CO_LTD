"""Public RSS market headlines, fetched only after authentication.

RSS items are metadata links, not full licensed article text.
"""
from __future__ import annotations
from datetime import datetime, timedelta, time, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
import html
import re

KST = ZoneInfo("Asia/Seoul")
CATEGORIES = {
    "태양광": '("solar power" OR "solar energy" OR "solar PV" OR photovoltaics OR polysilicon OR "solar wafer" OR "solar cell" OR "solar module" OR 태양광 OR BIPV OR Qcells OR 한화큐셀) when:2d',
    "데이터센터": '("data center" OR "data centre" OR datacenter OR 데이터센터 OR "AI infrastructure" OR "AI 인프라") when:2d',
    "원자재": '("crude oil" OR "natural gas" OR copper OR LNG) (price OR supply OR OPEC) when:2d',
    "증시·거시경제": '(stock market OR KOSPI OR Nasdaq OR Federal Reserve OR inflation) when:2d',
}
# Google News indexes third-party publishers; this is not a direct Bloomberg
# or Investing.com subscription/feed and their inclusion is not guaranteed.
def cutoff_kst(now: datetime) -> datetime:
    now = now.astimezone(KST)
    day = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    return datetime.combine(day, time(18), KST)


def parse_rss(xml_bytes: bytes, cutoff: datetime, now: datetime, *, default_publisher: str = "Google News") -> list[dict[str, str]]:
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
                     "publisher": publisher or default_publisher,
                     "published": published.strftime("%m-%d %H:%M"),
                     "published_at": published.isoformat()})
    return rows


def retain_last_24_hours(rows: list[dict[str, str]], now: datetime) -> list[dict[str, str]]:
    """Exclude unverified/undated entries rather than retaining them forever."""
    now = now.astimezone(KST)
    earliest = now - timedelta(hours=24)
    kept = []
    for row in rows:
        try:
            published = datetime.fromisoformat(row["published_at"]).astimezone(KST)
        except (KeyError, ValueError, TypeError):
            continue
        if earliest <= published <= now:
            kept.append(row)
    return kept


def fetch_category(category: str, now: datetime | None = None) -> list[dict[str, str]]:
    if category not in CATEGORIES:
        raise ValueError("Unknown category")
    now = (now or datetime.now(KST)).astimezone(KST)
    def google_feed(hl, gl, edition, topic=None):
        query = urlencode({"q": topic or CATEGORIES[category], "hl": hl, "gl": gl, "ceid": edition})
        return "https://news.google.com/rss/search?" + query, "Google News"

    sources = [google_feed("ko", "KR", "KR:ko")]
    if category in {"태양광", "데이터센터"}:
        sources.append(google_feed("en-US", "US", "US:en"))
    if category == "태양광":
        sources.append(("https://www.pv-tech.org/feed/", "PV Tech"))
    if category == "데이터센터":
        companies = '(NVIDIA OR 엔비디아 OR "Jensen Huang" OR "젠슨 황" OR 젠슨황) when:2d'
        sources += [google_feed("ko", "KR", "KR:ko", companies),
                    google_feed("en-US", "US", "US:en", companies)]

    def read_source(source):
        url, publisher = source
        request = Request(url, headers={"User-Agent": "KEKOREA-MarketDashboard/1.0"})
        try:
            with urlopen(request, timeout=7) as response:
                content = response.read(1_000_001)
            if len(content) > 1_000_000:
                raise ValueError("RSS feed too large")
            return parse_rss(content, now - timedelta(hours=24), now,
                             default_publisher=publisher), None
        except (OSError, ValueError, ET.ParseError) as exc:
            return [], type(exc).__name__

    # Bound total latency: source failures cannot serially block the UI.
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        results = list(pool.map(read_source, sources))
    if all(error for _, error in results):
        raise OSError("All news sources failed for " + category)
    rows = [row for batch, _ in results for row in batch]
    rows.sort(key=lambda row: row["published_at"], reverse=True)
    seen_titles, seen_urls, unique = set(), set(), []
    for row in rows:
        title = row["title"]
        suffix = " - " + row["publisher"]
        if title.endswith(suffix):
            title = title[:-len(suffix)]
        key = re.sub(r"\s+", " ", title).strip().casefold()
        url_key = row["url"].rstrip("/")
        if key not in seen_titles and url_key not in seen_urls:
            seen_titles.add(key)
            seen_urls.add(url_key)
            unique.append(row)
    limit = 100 if category in {"태양광", "데이터센터"} else 25
    if category == "데이터센터":
        # Reserve room for actual infrastructure news during a company news surge.
        primary_urls = {row["url"] for batch, _ in results[:2] for row in batch}
        primary = [row for row in unique if row["url"] in primary_urls]
        companies = [row for row in unique if row["url"] not in primary_urls]
        selected = primary[:50] + companies[:50]
        selected_urls = {row["url"] for row in selected}
        selected += [row for row in unique if row["url"] not in selected_urls][:limit-len(selected)]
        unique = sorted(selected, key=lambda row: row["published_at"], reverse=True)
    return retain_last_24_hours(unique, now)[:limit]
