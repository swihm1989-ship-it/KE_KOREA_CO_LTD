"""Mirror the existing KE KOREA Streamlit application theme.

Source of truth: Quotation_KEKOREA/app.py (its CSS / .ke-header rules).
This module is deliberately isolated: it does not import or execute app.py.
Only reusable visual presentation is shared, not authentication or business logic.
"""
from __future__ import annotations

from pathlib import Path
from html import escape


STYLE = """
<style>
  :root { --ke-navy:#092b4c; --ke-blue:#0877c9; --ke-sky:#eaf5fc; --ke-ink:#172b3d; }
  .stApp { background:#f5f8fb; color:var(--ke-ink); }
  [data-testid="stSidebar"] { background:#092b4c; border-right:1px solid #163e61; }
  [data-testid="stSidebar"] * { color:#f5f9fd; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label { padding:11px 13px; border-radius:9px; margin:3px 0; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:#16466f; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#0877c9; }
  .ke-header { background:linear-gradient(110deg,#fff 0%,#fff 55%,#edf7fd 100%); border:1px solid #dbe8f2; border-top:4px solid #0877c9; border-radius:14px; padding:18px 24px; margin:0 0 20px; box-shadow:0 5px 18px rgba(9,43,76,.05); }
  .ke-eyebrow { color:#0877c9; letter-spacing:.12em; text-transform:uppercase; font-size:.77rem; font-weight:700; }
  .ke-header h1 { color:#092b4c; margin:.25rem 0 .2rem; font-size:1.8rem; }
  .ke-header p { color:#5b6b78; margin:0; }
  .ke-section { color:#092b4c; font-weight:700; font-size:1.1rem; margin:.6rem 0 .2rem; }
  div.stButton > button[kind="primary"] { background:#0877c9; border-color:#0877c9; border-radius:9px; font-weight:700; }
  div.stButton > button[kind="primary"]:hover { background:#065f9f; border-color:#065f9f; }
  [data-testid="stMetric"] { background:#fff; border:1px solid #dbe8f2; border-radius:11px; padding:14px; }

  /* MASTER GRAPH page-width only; brand styles above match the original. */
  .block-container { max-width:1460px; padding-top:1.6rem; }
  h2,h3 { color:var(--ke-navy); }
  [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlockBorderWrapper"] {
    border-color:#dbe8f2;
  }
  .stTextInput input:focus, .stTextArea textarea:focus {
    border-color:var(--ke-blue);
  }
  @media (max-width: 640px) {
    .block-container { padding-top:1rem; }
    .ke-header { padding:14px 16px; border-radius:12px; }
    .ke-header h1 { font-size:1.45rem; line-height:1.25; }
  }
</style>
"""


def logo_path() -> Path:
    """The exact same logo as the existing app, without copying assets."""
    return Path(__file__).resolve().parents[2] / "assets" / "company_logo.png"


def header_html(title: str, description: str, *, eyebrow: str = "KE KOREA · AI WORKSPACE") -> str:
    """Only static/safely escaped header text may be embedded as HTML."""
    return (
        '<div class="ke-header">'
        f'<div class="ke-eyebrow">{escape(eyebrow)}</div>'
        f'<h1>{escape(title)}</h1>'
        f'<p>{escape(description)}</p>'
        '</div>'
    )
