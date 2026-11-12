"""Read-only market headlines for the authenticated MASTER GRAPH home."""
from __future__ import annotations
import streamlit as st
import json
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from Quotation_KEKOREA.orchestration.workflows.market_news import CATEGORIES, KST, fetch_category, retain_last_24_hours
from datetime import datetime
from Quotation_KEKOREA.orchestration.workflows.news_supabase import NewsSupabase


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_news(category: str):
    try:
        secrets = dict(st.secrets)
    except (FileNotFoundError, KeyError):
        secrets = {}
    fallback = ([], None)
    store = NewsSupabase.from_config(secrets)
    if store is not None:
        try:
            stories = store.fetch_category(category)
            if stories:
                fallback = (stories, None)
            updated_times = [item.get("collected_at") for item in stories if item.get("collected_at")]
            updated = datetime.fromisoformat(max(updated_times)) if updated_times else None
            if stories:
                fallback = (stories, updated)
            if stories and (updated is None or (datetime.now(KST) - updated).total_seconds() < 5400):
                return stories, updated
        except Exception as exc:
            if isinstance(exc, HTTPError):
                reason = f"HTTP {exc.code}"
            elif isinstance(exc, URLError):
                reason = "네트워크 연결 오류"
            else:
                reason = type(exc).__name__
            st.warning(f"Supabase 뉴스 조회 실패 ({reason}) · 기존 뉴스 소스로 전환합니다.")
    snapshot = Path(__file__).resolve().parents[2] / "data" / "market_news_snapshot.json"
    if snapshot.exists():
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            updated = datetime.fromisoformat(payload["updated_at"])
            stories = retain_last_24_hours(payload["categories"].get(category, []), datetime.now(KST))
            if stories:
                if (datetime.now(KST) - updated).total_seconds() < 5400:
                    return stories, updated
                if not fallback[0]:
                    fallback = (stories, updated)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        live = retain_last_24_hours(fetch_category(category), datetime.now(KST))
        if live:
            return live, None
    except (OSError, ValueError):
        if not fallback[0]:
            raise
    if fallback[0]:
        st.warning("최신 뉴스 조회가 지연되어 최근 24시간 내 기존 수집본을 표시합니다.")
    return fallback


NEWS_STYLE = """
<style>
.ke-news-list { list-style:none; margin:0; padding:0 24px; background:#fff;
  border:1px solid #dbe8f2; border-radius:4px; }
.ke-news-list li { margin:0; padding:0; }
.ke-news-row { display:flex; gap:16px; align-items:flex-start; padding:18px 0;
  border-bottom:1px solid #e8edf2; }
.ke-news-list li:last-child .ke-news-row { border-bottom:0; }
.ke-news-body { flex:1; min-width:0; }
.ke-news-row h3 { margin:0 0 6px; padding:0; font-size:16px; font-weight:700;
  line-height:1.5; letter-spacing:-.02em; overflow-wrap:anywhere; color:#172b3d; }
.ke-news-row a { color:#172b3d; text-decoration:none; }
.ke-news-row a:hover { color:#0877c9; text-decoration:underline; }
.ke-news-row a:focus-visible { outline:2px solid #0877c9; outline-offset:3px; }
.ke-news-meta { display:flex; flex-wrap:wrap; gap:6px 12px; color:#617386;
  font-size:12px; line-height:1.5; }
@media (max-width:640px) {
  .ke-news-list { padding:0 14px; }
  .ke-news-row { gap:12px; padding:14px 0; }
  .ke-news-row h3 { font-size:15px; }
}
</style>
"""


def _safe_https(value: object) -> str:
    value = str(value or "").strip()
    if any(ord(c) < 33 for c in value) or "\\" in value:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return ""


def news_list_html(stories: list[dict[str, str]]) -> str:
    """Escape feed metadata; never fabricate excerpts or fetch article pages."""
    rows = []
    for story in stories:
        title = str(story.get("title") or "제목 없음")
        publisher = str(story.get("publisher") or "")
        suffix = " - " + publisher
        if publisher and title.endswith(suffix):
            title = title[:-len(suffix)]
        title = escape(title)
        url = _safe_https(story.get("url"))
        headline = (f'<a href="{escape(url, quote=True)}" target="_blank" '
                    f'rel="noopener noreferrer">{title}</a>') if url else title
        published = str(story.get("published") or "")
        metadata = "".join(f'<span>{escape(part)}</span>' for part in
                           (publisher, published + " KST" if published else "") if part)
        rows.append(f'<li><article class="ke-news-row"><div class="ke-news-body">'
                    f'<h3>{headline}</h3><div class="ke-news-meta">{metadata}</div>'
                    '</div></article></li>')
    return '<ul class="ke-news-list" aria-label="시장 뉴스 기사">' + "".join(rows) + '</ul>'


@st.fragment(run_every="30m")
def render_market_news() -> None:
    st.markdown(NEWS_STYLE, unsafe_allow_html=True)
    st.subheader("시장 뉴스")
    st.caption("최근 24시간 · 제목을 누르면 원문이 새 탭으로 열립니다.")
    categories = list(CATEGORIES)
    tabs = st.tabs(categories)
    for category, tab in zip(categories, tabs):
        with tab:
            try:
                stories, updated = _cached_news(category)
            except Exception:
                st.warning("현재 " + category + " 뉴스 수집이 지연되고 있습니다. 잠시 후 다시 시도하세요.")
                continue
            if updated:
                st.caption("수집 " + updated.astimezone(KST).strftime("%m/%d %H:%M") + " KST · " + str(len(stories)) + "개 기사")
            else:
                st.caption("실시간 RSS · " + str(len(stories)) + "개 기사")
            if not stories:
                st.info("최근 24시간 이내 확인된 뉴스가 없습니다.")
                continue
            total_pages = max(1, (len(stories) + 4) // 5)
            key = "market_page_" + category
            if st.session_state.get(key, 1) not in range(1, total_pages + 1):
                st.session_state[key] = 1
            # Render navigation after the list, so headlines lead the page.
            selected = st.session_state.get(key, 1)
            st.markdown(news_list_html(stories[(selected - 1) * 5:selected * 5]), unsafe_allow_html=True)
            st.selectbox(category + " 페이지", list(range(1, total_pages + 1)), key=key,
                         format_func=lambda x: f"{x} / {total_pages} 페이지", label_visibility="collapsed")
    with st.expander("뉴스 제공 안내"):
        st.caption("공개 RSS와 검색 인덱스의 제목·출처·링크를 표시합니다. 개별 매체 수록은 보장되지 않습니다.")
