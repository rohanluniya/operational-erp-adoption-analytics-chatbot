"""CORE Pulse — Streamlit Entry Point.

Signs the user in, renders top navigation (Chat, Rollout Explorer, Data Catalog, User Guide, About),
shared executive header, and left sidebar (Persona RLS, cascading scope filters, As-of date, LiteLLM model,
and persistent last-10 conversation history).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.ui import branding as B  # noqa: E402

st.set_page_config(
    page_title=B.page_title(),
    page_icon=str(B.LOGO_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)

from app.ui import common as C  # noqa: E402
from app.ui import nav, sidebar  # noqa: E402


def main() -> None:
    C.init_state()
    C.apply_css()
    st.logo(str(B.LOGO_PATH), size="large")
    if not C.signed_in():
        st.navigation(
            [st.Page(C.login_page, title="Sign in", icon="🔐", url_path="signin")],
            position="hidden",
        ).run()
        return
    C.apply_restored_filters()
    page = st.navigation(nav.build(), position="top")
    goto = st.session_state.pop("nav_goto", None)
    if goto in nav.PAGES:
        nav.go(goto)
    sidebar.render()
    C.header()
    page.run()


main()
