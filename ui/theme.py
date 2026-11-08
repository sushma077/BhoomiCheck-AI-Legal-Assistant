"""Visual system: white surfaces, navy text, teal accent, and clear severity colours."""
from __future__ import annotations

import html

import streamlit as st

import config

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;600&display=swap');
:root {
  --navy: #14213d; --navy-soft: #33415c; --teal: #0f766e; --teal-soft: #e6f4f2; --line: #e2e8f0; --muted: #5b6b82; --bg: #f7f9fb;
  --high: #b91c1c; --high-bg: #fef2f2; --warn: #a15c07; --warn-bg: #fffaeb; --info: #1d4ed8; --info-bg: #eff6ff; --ok: #15803d; --ok-bg: #f0fdf4;
}
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', 'Noto Sans Devanagari', system-ui, sans-serif; }
.stApp { background: var(--bg); color: var(--navy); }
.block-container { max-width: 1120px; padding-top: 3.4rem; padding-bottom: 3rem; }
section[data-testid="stSidebar"] { background: #fff; border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] label p { font-size: 0.92rem; color: var(--navy-soft); }
h1, h2, h3 { color: var(--navy); letter-spacing: -0.015em; }
h1 { font-size: 1.75rem !important; font-weight: 700 !important; }
h3 { font-size: 1.05rem !important; font-weight: 600 !important; }
.stButton > button[kind="primary"], .stDownloadButton > button { background: var(--teal); border: 1px solid var(--teal); color: #fff; border-radius: 8px; font-weight: 600; }
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover { background: #0b5f59; border-color: #0b5f59; color: #fff; }
.stButton > button { border-radius: 8px; }
.brand { display:flex; gap:10px; align-items:center; margin: 0 0 14px 0; }
.brand-mark { width:34px; height:34px; border-radius:8px; background: var(--navy); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:15px; }
.brand-name { font-weight:700; color:var(--navy); font-size:1.08rem; line-height:1.1; }
.brand-sub { font-size:0.72rem; color:var(--muted); }
.side-status { margin-top:16px; padding:11px 12px; border:1px solid var(--line); border-radius:10px; font-size:0.8rem; color:var(--navy-soft); background:var(--bg); line-height:1.5; }
.page-intro { color: var(--muted); margin: -0.3rem 0 1.2rem 0; max-width: 760px; }
.hero { background: var(--navy); color:#fff; border-radius:14px; padding: 30px 32px; margin-bottom: 18px; }
.hero h1 { color:#fff !important; font-size:2rem !important; margin:0 0 6px 0; padding:0; }
.hero p { color:#cfd8e6; margin:0; font-size:1.02rem; max-width: 680px; }
.card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:12px; }
.card h4 { margin:0 0 5px 0; font-size:0.98rem; color:var(--navy); font-weight:600; }
.card p { margin:0; color:var(--navy-soft); font-size:0.9rem; line-height:1.5; }
.metric { background:#fff; border:1px solid var(--line); border-radius:12px; padding:13px 16px; }
.metric .n { font-size:1.65rem; font-weight:700; line-height:1.15; }
.metric .l { font-size:0.8rem; color:var(--muted); }
.finding { background:#fff; border:1px solid var(--line); border-left-width:5px; border-radius:10px; padding:14px 16px; margin-bottom:11px; }
.finding.high { border-left-color:var(--high); } .finding.warning { border-left-color:var(--warn); } .finding.information { border-left-color:var(--info); }
.finding h4 { margin:6px 0 4px 0; font-size:0.98rem; color:var(--navy); font-weight:600; }
.finding p { margin:4px 0; font-size:0.88rem; color:var(--navy-soft); line-height:1.5; }
.finding .label { font-weight:600; color:var(--navy); }
.finding .evidence { background:var(--bg); border-radius:6px; padding:6px 9px; font-size:0.81rem; color:var(--muted); margin:6px 0; }
.pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:0.73rem; font-weight:600; }
.pill.high { background:var(--high-bg); color:var(--high); } .pill.warning { background:var(--warn-bg); color:var(--warn); } .pill.information { background:var(--info-bg); color:var(--info); }
.pill.ok { background:var(--ok-bg); color:var(--ok); } .pill.neutral { background:#f1f5f9; color:var(--navy-soft); } .pill.teal { background:var(--teal-soft); color:var(--teal); }
.fact { display:flex; gap:12px; padding:7px 0; border-bottom:1px solid #eef2f6; font-size:0.89rem; }
.fact .k { flex:0 0 190px; color:var(--muted); } .fact .v { color:var(--navy); overflow-wrap:anywhere; }
.notice { background:var(--warn-bg); border:1px solid #f5e0b5; color:#713f12; border-radius:10px; padding:10px 14px; font-size:0.86rem; margin-bottom:12px; }
.empty { background:#fff; border:1px dashed #c7d2de; border-radius:12px; padding:26px; text-align:center; color:var(--muted); }
.footnote { margin-top:30px; padding-top:12px; border-top:1px solid var(--line); font-size:0.76rem; color:var(--muted); }
@media (max-width: 700px) { .fact { flex-direction:column; gap:1px; } .fact .k { flex:none; } .hero { padding:22px; } .hero h1 { font-size:1.55rem !important; } }
</style>
"""

SEVERITY_CLASS = {"High Priority": "high", "Warning": "warning", "Information": "information"}


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def e(value) -> str:
    return html.escape(str(value))


def brand() -> str:
    return f'<div class="brand"><div class="brand-mark">BC</div><div><div class="brand-name">{config.APP_NAME}</div><div class="brand-sub">Property document assistant</div></div></div>'


def sidebar_status(documents: list, result: dict | None) -> str:
    if not documents:
        return '<div class="side-status">No documents analysed yet. Start on <b>Upload Documents</b>.</div>'
    high = sum(f.severity == "High Priority" for f in result["findings"]) if result else 0
    return f'<div class="side-status"><b>{len(documents)}</b> document(s) analysed<br><b>{high}</b> High Priority finding(s)</div>'


def intro(title: str, text: str) -> None:
    st.markdown(f"# {title}")
    st.markdown(f'<p class="page-intro">{text}</p>', unsafe_allow_html=True)


def pill(text: str, cls: str = "neutral") -> str:
    return f'<span class="pill {cls}">{e(text)}</span>'


def metric(number, label: str, colour: str = "var(--navy)") -> str:
    return f'<div class="metric"><div class="n" style="color:{colour}">{e(number)}</div><div class="l">{e(label)}</div></div>'


def card(title: str, text: str) -> str:
    return f'<div class="card"><h4>{e(title)}</h4><p>{e(text)}</p></div>'


def facts(rows: list[tuple[str, str]]) -> str:
    return "".join(f'<div class="fact"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>' for k, v in rows)


def finding_card(finding) -> str:
    cls = SEVERITY_CLASS[finding.severity]
    sources = "<br>".join(
        f"{e(s.document)}" + (f", page {s.page}" if s.page else "") + (f": “{e(s.evidence)}”" if s.evidence else "") for s in finding.sources[:4])
    citations = "; ".join(
        f'<a href="{e(c.url)}" target="_blank">{e(c.title)}, {e(c.provision)}</a>' if c.url else f"{e(c.title)}, {e(c.provision)}" for c in finding.citations)
    parts = [f'<div class="finding {cls}">', pill(finding.severity, cls)]
    if finding.lawyer_referral:
        parts.append(" " + pill("Ask a lawyer", "neutral"))
    parts.append(f"<h4>{e(finding.title)}</h4><p><span class='label'>Why:</span> {e(finding.reason)}</p>")
    if sources:
        parts.append(f'<div class="evidence"><b>Where we saw this:</b><br>{sources}</div>')
    parts.append(f"<p><span class='label'>What to verify:</span> {e(finding.recommended_verification)}</p>")
    if citations:
        parts.append(f"<p style='font-size:.8rem'><span class='label'>Legal reference:</span> {citations}</p>")
    parts.append("</div>")
    return "".join(parts)


def empty(text: str) -> None:
    st.markdown(f'<div class="empty">{e(text)}</div>', unsafe_allow_html=True)
