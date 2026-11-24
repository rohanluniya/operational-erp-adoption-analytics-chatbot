"""Rollout Explorer view: Wave/Entity/Module deployment status vs observed instrumented activity."""
from __future__ import annotations

import streamlit as st

from app.semantic import service as Svc
from app.ui import common as C
from app.viz.charts import figure
from app.viz.tables import TABLE_CSS, render_html, to_csv_bytes


def render() -> None:
    cfg = st.session_state["cfg"]
    st.markdown("### 🧭 Rollout Explorer")
    st.info(
        "**Governance distinction:** Module deployment states (`LIVE`, `ONBOARDING`, `PLANNED`, `PAUSED`, `RETIRED`) "
        "come from `reference.rollout_registry`. Application logins (`CORE_LOGIN`) are **never** "
        "used to claim usage of uninstrumented modules (`INSPECTOR_SCHED`, `QUALIFICATIONS`, `LAB_TESTING`, `INVOICING`)."
    )

    f1, f2, f3 = st.columns([1, 1, 1.35], vertical_alignment="bottom")
    st_pick = f1.selectbox("Filter by Rollout Status", ["All statuses", "LIVE", "ONBOARDING", "PLANNED", "PAUSED", "RETIRED"])
    mod_pick = f2.selectbox(
        "Filter by Module",
        ["All modules", "CORE_LOGIN", "PROJECTS", "TIMECARDS", "EXPENSES",
         "INSPECTOR_SCHED", "QUALIFICATIONS", "LAB_TESTING", "INVOICING"],
    )
    zero_only = f3.checkbox("Only LIVE rollouts with zero activity", value=False)

    res = Svc.get_core_rollout_status(
        module=None if mod_pick == "All modules" else mod_pick,
        rollout_status=None if st_pick == "All statuses" else st_pick,
        zero_activity_only=zero_only,
        user_id=cfg["user_id"],
        as_of=cfg["as_of"],
    )

    if res.status == "refusal":
        st.error(res.headline)
        return

    st.markdown(res.headline)

    # Render clean, non-truncating summary cards
    df = res.df
    total_dep = len(df)
    status_vc = df["Status"].value_counts().to_dict() if not df.empty else {}
    st_parts = [f"{cnt} {st_name.title()}" for st_name, cnt in status_vc.items()]
    st_sub = " · ".join(st_parts) if st_parts else "No deployments in current filter"

    active_live = int((df["Activity Evidence"] == "Observed activity").sum()) if not df.empty else 0
    zero_live = int((df["Activity Evidence"] == "LIVE — ZERO observed events").sum()) if not df.empty else 0
    uninst_live = int(((df["Status"] == "LIVE") & (df["Instrumentation"] != "INSTRUMENTED")).sum()) if not df.empty else 0

    cards = [
        ("Module Deployments", f"{total_dep:,}", "In selected scope", st_sub),
        ("Live with Activity", f"{active_live:,}", "Verified in Gold events", "Instrumented modules recording activity"),
        ("Live with Zero Activity", f"{zero_live:,}", "Actionable rollout gap", "Marked LIVE with 0 observed events"),
        ("Status-Only Live Modules", f"{uninst_live:,}", "Not yet instrumented", "Tracked in registry; telemetry planned"),
    ]
    c_cols = st.columns(4)
    for idx, (ctitle, cval, cperiod, csub) in enumerate(cards):
        c_cols[idx].markdown(
            f"<div class='cp-kpi-card'>"
            f"<div class='k-title'>{C.esc(ctitle)}</div>"
            f"<div class='k-val'>{C.esc(cval)}</div>"
            f"<div class='k-period'>{C.esc(cperiod)}</div>"
            f"<div class='k-sub'>{C.esc(csub)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.write("")

    fig = figure(res.chart_spec)
    if fig is not None:
        st.plotly_chart(fig, width="stretch", key="rollout_chart")

    if not res.df.empty:
        st.markdown(TABLE_CSS + render_html(res.df), unsafe_allow_html=True)
        st.download_button(
            "⬇️ Download Rollout Matrix (CSV)",
            to_csv_bytes(res.df),
            file_name="core_pulse_rollout_registry.csv",
            mime="text/csv",
        )

    st.markdown("#### Investigate in Chat")
    b1, b2, b3 = st.columns(3)
    with b1:
        C.ask_button(
            "Ask: Live Expenses with Zero Activity",
            "Which entities are live on Expenses, and which live entities have zero expense submissions?",
            key="ro_ask_1",
        )
    with b2:
        C.ask_button(
            "Ask: Western Region Live Modules",
            "Which modules are live for the Western region?",
            key="ro_ask_2",
        )
    with b3:
        C.ask_button(
            "Ask: Are Live Modules Seeing Activity?",
            "Are those modules actually seeing activity?",
            key="ro_ask_3",
        )
