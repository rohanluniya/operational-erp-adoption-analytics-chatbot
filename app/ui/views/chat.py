"""Chat page: Executive KPI overview strip + conversational analytics with CORE Pulse."""
from __future__ import annotations

import time

import streamlit as st

from app.agent.graph import ask
from app.semantic import service as Svc
from app.ui import branding as B
from app.ui import common as C
from app.ui import sidebar as Side


def _kpi_overview_strip(cfg: dict) -> None:
    """Render the four baseline KPI cards with unambiguous period labels + Rollout Registry summary."""
    uif = cfg.get("ui_filters") or {}
    snap = Svc.get_core_adoption_current(
        kpi_name="ALL",
        region=uif.get("region"),
        user_id=cfg["user_id"],
        as_of=cfg["as_of"],
    )
    if snap.df is None or snap.df.empty:
        return
    cols = st.columns(4)
    as_of_day = cfg["as_of"].day
    mtd_col = f"This Month MTD (Nov 1–{as_of_day})"
    eq_col = f"Prior Equiv. MTD (Oct 1–{as_of_day})"
    for idx, (_, row) in enumerate(snap.df.iterrows()):
        kname = str(row["KPI Name"])
        if kname == "Employees Logging In":
            primary_v = f"{int(row[mtd_col]):,}"
            p_lbl = f"Nov 2026 MTD (1–{as_of_day}, unique users)"
            sub_lbl = f"Oct 1–{as_of_day}: {int(row[eq_col]):,} · Oct full: {int(row['Last Complete Month (Oct 2026)']):,} · All-time: {int(row['All-Time Cumulative']):,}"
        else:
            primary_v = f"{int(row['All-Time Cumulative']):,}"
            p_lbl = "All-time cumulative (Jun 2025 – Nov 2026)"
            sub_lbl = f"Oct 2026 (complete): {int(row['Last Complete Month (Oct 2026)']):,} · Nov MTD: {int(row[mtd_col]):,}"
        cols[idx].markdown(
            f"<div class='cp-kpi-card'>"
            f"<div class='k-title'>{C.esc(kname)}</div>"
            f"<div class='k-val'>{C.esc(primary_v)}</div>"
            f"<div class='k-period'>{C.esc(p_lbl)}</div>"
            f"<div class='k-sub'>{C.esc(sub_lbl)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _has_history() -> bool:
    store, user = C.history_store(), st.session_state.get("auth_user")
    if store is None or not user:
        return False
    try:
        return bool(store.list(user))
    except Exception:  # noqa: BLE001
        return False


def welcome_card() -> None:
    if st.session_state.get("welcome_dismissed") or _has_history():
        return
    with st.container(border=True, key="welcome_card"):
        c1, c2 = st.columns([12, 1])
        c1.markdown(f"#### Welcome to {B.APP_NAME}")
        if c2.button("✕", key="welcome_close", help="Dismiss"):
            st.session_state.welcome_dismissed = True
            st.rerun()
        st.markdown(
            "Ask about CORE operational rollout and adoption in plain English. Every answer queries "
            "`goldview.v_core_adoption` (or governed Medallion tables) through read-only MCP tools, "
            "preserves non-additive distinct employee counts, and includes a table, chart, and full SQL/lineage audit."
        )
        C.example_buttons(C.WELCOME_EXAMPLES, "wel", 3)
        b1, b2, _ = st.columns([2, 2, 6])
        b1.button("📘 Open User Guide", key="welcome_guide", on_click=C.queue_page, args=("guide",))
        b2.button("🧭 Open Rollout Explorer", key="welcome_rollout", on_click=C.queue_page, args=("rollout",))


def prompt_gallery() -> None:
    st.markdown("#### 5-Minute Executive Demo Journey")
    C.example_buttons(C.DEMO_JOURNEY_EXAMPLES, "journey", 2)
    with st.expander("Governance, Non-Additivity & DataOps Verification Questions", expanded=False):
        C.example_buttons(C.GOVERNANCE_EXAMPLES, "gov", 2)


def process(question: str, cfg: dict) -> None:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(C.md_escape(question))
    warning = None
    with st.chat_message("assistant", avatar="📊"):
        with st.spinner("Querying governed CORE Medallion layer via MCP ..."):
            t0 = time.time()
            try:
                ans, mem = ask(
                    question,
                    user_id=cfg["user_id"],
                    memory=st.session_state.memory,
                    model=cfg["model"] or "rules",
                    as_of=cfg["as_of"],
                    ui_filters=cfg.get("ui_filters"),
                )
                payload = ans.model_dump()
                payload["diagnostics"]["question"] = question
                st.session_state.memory = mem
                warning = C.save_turn(question, payload, mem, cfg)
            except Exception as exc:  # noqa: BLE001
                payload = {
                    "answer_markdown": f"Unexpected error: `{type(exc).__name__}`: {exc}",
                    "status": "error",
                    "followups": [],
                    "diagnostics": {"latency_s": round(time.time() - t0, 2), "question": question},
                }
    st.session_state.messages.append({"role": "assistant", "answer": payload})
    if warning:
        st.session_state["history_warning"] = warning
    st.rerun()


def _bottom_chips(cfg: dict) -> None:
    chips = Side.filter_chips(cfg.get("ui_filters") or {})
    target = getattr(st, "bottom", None)
    holder = target.container() if target is not None else st.container()
    with holder:
        if chips:
            C.chips(["Active Filters: " + chips[0]] + chips[1:], "filter")
        else:
            st.caption("No sidebar filters selected: questions apply to your full Persona RLS scope unless narrowed in the prompt.")


def render() -> None:
    cfg = st.session_state["cfg"]
    if st.session_state.get("history_warning"):
        st.warning(st.session_state.pop("history_warning"))

    _kpi_overview_strip(cfg)
    st.write("")

    if not st.session_state.messages and not st.session_state.pending:
        welcome_card()
        prompt_gallery()

    for i, m in enumerate(st.session_state.messages):
        with st.chat_message(m["role"], avatar="🧑‍💼" if m["role"] == "user" else "📊"):
            if m["role"] == "user":
                st.markdown(C.md_escape(m["content"]))
            else:
                C.render_answer(m["answer"], i, cfg)

    _bottom_chips(cfg)
    typed = st.chat_input("Ask CORE Pulse, e.g. 'How many employees logged into CORE this month?'")
    q = typed or st.session_state.pending
    if q:
        st.session_state.pending = None
        process(q, cfg)
