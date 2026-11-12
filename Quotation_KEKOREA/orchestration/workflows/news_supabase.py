"""Server-only Supabase REST storage for the KE KOREA market news feed.

Required secrets: NEWS_SUPABASE_URL and NEWS_SUPABASE_SECRET_KEY.
Never send either value to Streamlit widgets, browsers, or logs.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from Quotation_KEKOREA.orchestration.workflows.market_news import (
    CATEGORIES,
    KST,
    retain_last_24_hours,
)


@dataclass(frozen=True)
class NewsSupabase:
    url: str
    key: str

    @classmethod
    def from_config(cls, config: Mapping[str, str] | None = None) -> "NewsSupabase | None":
        config = os.environ if config is None else config
        url = str(config.get("NEWS_SUPABASE_URL") or "").strip().rstrip("/")
        key = str(config.get("NEWS_SUPABASE_SECRET_KEY") or "").strip()
        if not url or not key:
            return None
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co"):
            raise ValueError("NEWS_SUPABASE_URL must be an HTTPS *.supabase.co project URL")
        return cls(url, key)

    def _request(self, method: str, query: Mapping[str, str], payload: object | None = None) -> object:
        target = self.url + "/rest/v1/news_articles?" + urlencode(query)
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "apikey": self.key,
            "Authorization": "Bearer " + self.key,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        req = Request(target, headers=headers, data=body, method=method)
        with urlopen(req, timeout=15) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Supabase news payload too large")
        return json.loads(raw) if raw else None

    def upsert_categories(self, categories: Mapping[str, list[dict[str, str]]],
                          now: datetime | None = None) -> int:
        now = (now or datetime.now(KST)).astimezone(KST)
        records: list[dict[str, str]] = []
        for category, articles in categories.items():
            if category not in CATEGORIES:
                raise ValueError("Unknown news category")
            for item in retain_last_24_hours(articles, now):
                url = str(item.get("url") or "")
                if not url.startswith("https://"):
                    continue
                records.append({
                    "category": category,
                    "title": str(item.get("title") or "")[:240],
                    "url": url[:2048],
                    "publisher": str(item.get("publisher") or "Unknown")[:200],
                    "published_at": str(item["published_at"]),
                    "collected_at": now.isoformat(),
                })
        if records:
            self._request("POST", {"on_conflict": "category,url"}, records)
        return len(records)

    def fetch_category(self, category: str, now: datetime | None = None) -> list[dict[str, str]]:
        if category not in CATEGORIES:
            raise ValueError("Unknown news category")
        now = (now or datetime.now(KST)).astimezone(KST)
        since = (now - timedelta(hours=24)).astimezone(timezone.utc).isoformat()
        query = {
            "select": "category,title,url,publisher,published_at,collected_at",
            "category": "eq." + category,
            "published_at": "gte." + since,
            "order": "published_at.desc",
            "limit": "100" if category in {"태양광", "데이터센터"} else "25",
        }
        result = self._request("GET", query)
        if category == "데이터센터" and isinstance(result, list):
            core_query = {**query, "limit": "50", "or":
                "(title.ilike.*data center*,title.ilike.*data centre*,title.ilike.*datacenter*,"
                "title.ilike.*데이터센터*,title.ilike.*AI infrastructure*,title.ilike.*AI 인프라*)"}
            core = self._request("GET", core_query)
            if not isinstance(core, list):
                raise ValueError("Invalid Supabase infrastructure response")
            selected = retain_last_24_hours(core, now)[:50]
            seen = {row.get("url") for row in selected}
            selected += [row for row in result if row.get("url") not in seen][:100-len(selected)]
            result = selected
        if not isinstance(result, list):
            raise ValueError("Invalid Supabase response")
        output = []
        for record in result:
            try:
                published = datetime.fromisoformat(record["published_at"]).astimezone(KST)
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            output.append({
                "title": str(record.get("title") or ""),
                "url": str(record.get("url") or ""),
                "publisher": str(record.get("publisher") or ""),
                "published": published.strftime("%m-%d %H:%M"),
                "published_at": published.isoformat(),
                "collected_at": str(record.get("collected_at") or ""),
            })
        return sorted(retain_last_24_hours(output, now), key=lambda row: row["published_at"], reverse=True)
