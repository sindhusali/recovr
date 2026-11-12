"""Look and feel. Kept apart from main.py so the page code stays about behaviour.

Design idea: the khata (paper ledger). A ruled header band with a thin red margin
line, totals with a rule above them, and next-step advice marked by a coloured
edge. One distinctive element; everything else is quiet.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

STATIC = Path(__file__).resolve().parent / "static"
LOGO_PATH = STATIC / "logo.png"

# next-step kinds -> (material icon, label)
KIND_STYLE = {
    "wait": ("schedule", "Wait"),
    "message": ("chat", "Send a message"),
    "call": ("call", "Call"),
    "escalate": ("priority_high", "Escalate"),
}

_LOGO_SVG = (
    '<svg width="44" height="44" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<rect width="64" height="64" rx="14" fill="#16213A"/>'
    '<rect x="17" y="9" width="2" height="46" fill="#E5604F"/>'
    '<rect x="23" y="19" width="26" height="3" rx="1.5" fill="#DCE5F5"/>'
    '<rect x="23" y="28" width="22" height="3" rx="1.5" fill="#DCE5F5"/>'
    '<rect x="23" y="37" width="17" height="3" rx="1.5" fill="#DCE5F5"/>'
    '<rect x="23" y="46" width="26" height="2" fill="#7FD1A9"/>'
    '<rect x="23" y="50" width="26" height="2" fill="#7FD1A9"/>'
    "</svg>"
)

_CSS = """
<style>
@font-face { font-family: 'IBM Plex Sans'; font-weight: 400; font-display: swap;
  src: url(app/static/ibm-plex-sans-400.woff2) format('woff2'); }
@font-face { font-family: 'IBM Plex Sans'; font-weight: 500; font-display: swap;
  src: url(app/static/ibm-plex-sans-500.woff2) format('woff2'); }
@font-face { font-family: 'IBM Plex Sans'; font-weight: 600; font-display: swap;
  src: url(app/static/ibm-plex-sans-600.woff2) format('woff2'); }

:root {
  --rv-ink: #16213A; --rv-paper: #F7F9FC; --rv-rule: #D3DCEA; --rv-blue: #1F4E9E;
  --rv-red: #B42318; --rv-green: #1D7A55; --rv-amber: #B7791F; --rv-muted: #5B6783;
  --rv-font: 'IBM Plex Sans', 'Noto Sans Telugu', 'Noto Sans Devanagari', 'Nirmala UI', system-ui, sans-serif;
}

/* one typeface for text; icon spans are deliberately left alone */
.stApp, .stApp :is(p, h1, h2, h3, h4, h5, label, li, td, th, input, textarea, button, a, small,
                    [data-testid="stMetricValue"], [data-testid="stMetricLabel"]) {
  font-family: var(--rv-font);
}
.stApp :is(h1, h2, h3, h4) { font-weight: 600; letter-spacing: -0.01em; color: var(--rv-ink); }
.stApp h3 { margin-top: 1.1rem; }

/* quiet chrome */
[data-testid="stToolbar"], [data-testid="stDecoration"], footer { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; max-width: 1120px; }

/* ledger-page header */
.rv-head {
  display: flex; align-items: center; gap: 16px;
  padding: 18px 24px 18px 44px; margin: 0 0 1.4rem;
  border: 1px solid var(--rv-rule); border-radius: 6px; background-color: #fff;
  background-image:
    linear-gradient(to right, transparent 25px, rgba(180,35,24,.6) 25px, rgba(180,35,24,.6) 26px, transparent 26px),
    repeating-linear-gradient(to bottom, transparent 0, transparent 27px, #EEF2F9 27px, #EEF2F9 28px);
}
.rv-name { font-size: 1.85rem; font-weight: 600; line-height: 1.1; color: var(--rv-ink); letter-spacing: -0.02em; }
.rv-tag  { font-size: .98rem; color: var(--rv-muted); margin-top: 2px; }

/* totals, ledger style: a rule above the figure, figures line up */
[data-testid="stMetric"] { border-top: 2px solid var(--rv-ink); padding-top: .55rem; }
[data-testid="stMetricLabel"] { color: var(--rv-muted); }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; font-weight: 600; }

/* next-step card: coloured edge shows the kind of advice at a glance */
.rv-kind { display: none; }
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .rv-kind),
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .rv-kind) {
  background: #fff; border-left-width: 5px; border-left-style: solid;
}
[data-testid]:has(> [data-testid="stElementContainer"] .rv-wait)     { border-left-color: var(--rv-blue) !important; }
[data-testid]:has(> [data-testid="stElementContainer"] .rv-message)  { border-left-color: var(--rv-green) !important; }
[data-testid]:has(> [data-testid="stElementContainer"] .rv-call)     { border-left-color: var(--rv-amber) !important; }
[data-testid]:has(> [data-testid="stElementContainer"] .rv-escalate) { border-left-color: var(--rv-red) !important; }

/* sidebar: headings and expanders must stay readable on the dark ink */
[data-testid="stSidebar"] :is(h1, h2, h3, h4) { color: #E8EDF7; font-size: 1.05rem; }
[data-testid="stSidebar"] [data-testid="stExpander"] { background: #22304F; border-color: #33456B; }
[data-testid="stSidebar"] [data-testid="stExpander"] * { color: #E8EDF7; }

/* expanders and tables share one rule colour and one radius */
[data-testid="stExpander"] { background: #fff; border-color: var(--rv-rule); }
[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
textarea { font-size: 0.98rem; line-height: 1.55; }

@media (max-width: 640px) {
  .rv-head { padding-left: 38px; }
  .rv-name { font-size: 1.5rem; }
}
</style>
"""


def inject_style() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header() -> None:
    st.markdown(
        f'<div class="rv-head">{_LOGO_SVG}<div><div class="rv-name">recovr</div>'
        '<div class="rv-tag">Who owes you, and who to chase first.</div></div></div>',
        unsafe_allow_html=True,
    )


def kind_marker(kind: str) -> str:
    """Hidden marker the CSS uses to colour the advice card's edge."""
    return f'<span class="rv-kind rv-{kind if kind in KIND_STYLE else "message"}"></span>'
