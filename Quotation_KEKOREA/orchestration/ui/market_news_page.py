"""Read-only market headlines for the authenticated MASTER GRAPH home."""
from __future__ import annotations
import streamlit as st
import json
from pathlib import Path
from urllib.parse import urlsplit
from Quotation_KEKOREA.orchestration.workflows.market_news import CATEGORIES, KST, cutoff_kst, fetch_category, retain_last_24_hours
from datetime import datetime
from Quotation_KEKOREA.orchestration.workflows.market_news import parse_rss


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_news(category: str):
    snapshot = Path(__file__).resolve().parents[2] / "data" / "market_news_snapshot.json"
    if snapshot.exists():
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            updated = datetime.fromisoformat(payload["updated_at"])
            if (datetime.now(KST) - updated).total_seconds() < 5400:
                return retain_last_24_hours(payload["categories"].get(category, []), datetime.now(KST)), updated
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return retain_last_24_hours(fetch_category(category), datetime.now(KST)), None


@st.fragment(run_every="30m")
def render_market_news() -> None:
    now = datetime.now(KST)
    st.subheader("KE KOREA · 시장 뉴스 브리핑")
    st.caption("한국시간 " + cutoff_kst(now).strftime("%m/%d %H:%M") +
               " 이후 발행된 기사 · 로그인 시점 기준 · 30분 캐시")
    st.caption("제목과 원문 링크만 표시합니다. Bloomberg·PV Tech·PV Insights·Investing.com 등 개별 매체의 수록은 검색 인덱스 및 공개 RSS 제공 여부에 따라 달라집니다.")
    for category in CATEGORIES:
        st.markdown("#### " + category)
        try:
            stories, updated = _cached_news(category)
            if updated:
                st.caption("백그라운드 수집: " + updated.astimezone(KST).strftime("%m/%d %H:%M") + " KST")
            else:
                st.caption("실시간 RSS 조회 · 저장된 최신 수집본 없음")
        except Exception:
            st.warning("현재 " + category + " 뉴스 수집이 지연되고 있습니다. 잠시 후 다시 시도하세요.")
            continue
        if not stories:
            st.info("설정한 시간 이후 확인된 뉴스가 없습니다.")
            continue
        total_pages = min(5, (len(stories) + 4) // 5)
        page = st.selectbox(category + " 페이지", list(range(1, total_pages + 1)),
                            key="market_page_" + category,
                            format_func=lambda x: f"{x} / {total_pages} 페이지")
        for story in stories[(page - 1) * 5:page * 5]:
            st.write(story["title"])
            if urlsplit(story["url"]).scheme == "https":
                st.link_button("원문 보기", story["url"])
            st.caption(story["publisher"] + " · " + story["published"] + " KST")
