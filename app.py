"""BhoomiCheck Streamlit app. Run with: streamlit run app.py"""
from __future__ import annotations

import warnings

import streamlit as st

warnings.filterwarnings("ignore", category=FutureWarning)

import config  # noqa: E402
from ui import pages, theme  # noqa: E402

st.set_page_config(page_title=f"{config.APP_NAME}: Property Document Check", page_icon="🏠", layout="wide", initial_sidebar_state="expanded")
theme.apply()

st.session_state.setdefault("documents", [])
st.session_state.setdefault("result", None)
st.session_state.setdefault("purpose", "purchase")
st.session_state.setdefault("chat", [])

PAGES = {
    "Home": pages.home,
    "Upload Documents": pages.upload,
    "Document Analysis": pages.document_analysis,
    "Ownership Details": pages.ownership,
    "Compare Documents": pages.compare,
    "Risk Analysis": pages.risks,
    "Due-Diligence Checklist": pages.checklist,
    "Legal Assistant": pages.assistant,
    "Property Report": pages.report,
    "About and Disclaimer": pages.about,
}

with st.sidebar:
    st.markdown(theme.brand(), unsafe_allow_html=True)
    if "nav" in st.session_state and st.session_state.nav not in PAGES:
        st.session_state.nav = "Home"
    choice = st.radio("Go to", list(PAGES), key="nav", label_visibility="collapsed")
    status_slot = st.empty()

PAGES[choice]()
status_slot.markdown(theme.sidebar_status(st.session_state.documents, st.session_state.result), unsafe_allow_html=True)
st.markdown(f'<div class="footnote">{config.LEGAL_NOTICE}</div>', unsafe_allow_html=True)
