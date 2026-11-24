"""Top navigation page registry (Chat, Rollout Explorer, Data Catalog, User Guide, About)."""
from __future__ import annotations

import streamlit as st

PAGES: dict[str, "st.Page"] = {}


def build() -> list:
    from app.ui.views import about, catalog, chat, rollout, user_guide

    PAGES.clear()
    PAGES["chat"] = st.Page(chat.render, title="Chat", icon="💬", url_path="chat", default=True)
    PAGES["rollout"] = st.Page(rollout.render, title="Rollout Explorer", icon="🧭", url_path="rollout")
    PAGES["catalog"] = st.Page(catalog.render, title="Data Catalog", icon="🗂️", url_path="catalog")
    PAGES["guide"] = st.Page(user_guide.render, title="User Guide", icon="📘", url_path="guide")
    PAGES["about"] = st.Page(about.render, title="About", icon="ℹ️", url_path="about")
    return list(PAGES.values())


def go(name: str) -> None:
    st.switch_page(PAGES[name])
