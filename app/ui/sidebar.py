"""Sidebar for CORE Pulse: Quick Guide, Persona & Model Settings, Cascading Scope Filters, and Conversations."""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache

import pandas as pd
import streamlit as st
from sqlalchemy import text

from app.agent.llm import SESSION_USAGE
from app.config import backend, data_as_of_date
from app.db import get_engine
from app.semantic.access import get_user_scope
from app.ui import branding as B
from app.ui import common as C

QUICK_TIPS = """
1. **Ask about the four certified CORE KPIs** (`Contracts Created`, `Employees Logging In`, `Timesheets Submitted`, `Expense Reports`) in plain English.
2. **Non-additivity is enforced automatically:** `Employees Logging In` (`COUNT(DISTINCT APPUserId)`) is never summed across waves, entities, applications, or months.
3. **Partial-month safety:** November 2026 (`2026-11-17`) is an incomplete month in progress (`MTD`) and is always compared fairly against equivalent elapsed days (`Oct 1–17`) as well as last complete month (`Oct 2026`).
4. **Rollout vs. Observed Activity:** Use **Rollout Explorer** or ask *"Which modules are live vs actually seeing activity?"* (`SIMULATED EXTENSION` registry vs observed `gold.coreadoption_event` rows).
5. **Inspect every answer:** Expand **How I got this & Medallion Lineage** under any response for the MCP tool call, `Source -> Bronze -> Silver -> Gold -> goldview.v_core_adoption` lineage, and parameterized SQL.
"""

KPI_OPTIONS = [
    "Default (Auto / All KPIs)",
    "Contracts Created",
    "Employees Logging In",
    "Timesheets Submitted",
    "Expense Reports",
]

PERIOD_OPTIONS = [
    "Default",
    "This Month (MTD)",
    "Last Complete Month (Oct 2026)",
    "All-Time Cumulative",
]

PERIOD_CODE = {
    "This Month (MTD)": "MTD",
    "Last Complete Month (Oct 2026)": "LAST_MONTH",
    "All-Time Cumulative": "CURRENT",
}

FILTER_KEYS = ["flt_region", "flt_entity", "flt_wave", "flt_bu", "flt_kpi", "flt_period"]


@lru_cache(maxsize=2)
def _org_df() -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        return pd.read_sql(text("""
            SELECT RegionCode, CountryCode, AdoptionEntity, AdoptionWaveNumber, BusinessUnit, BusinessUnitName
            FROM silver.organization
            ORDER BY AdoptionWaveNumber, RegionCode, BusinessUnit
        """), conn)


@st.dialog("CORE Pulse — Quick Guide")
def quick_guide() -> None:
    st.markdown(QUICK_TIPS)
    st.button("Open Full User Guide", type="primary", key="qg_open_guide", on_click=C.queue_page, args=("guide",))


def clear_filters() -> None:
    for k in FILTER_KEYS:
        st.session_state.pop(k, None)


def _persona_changed() -> None:
    st.session_state.persona = st.session_state.persona_select
    C.new_conversation()
    clear_filters()


def _settings() -> dict:
    with st.expander("Settings", expanded=False):
        if "persona_select" not in st.session_state:
            st.session_state.persona_select = st.session_state.persona
        persona = st.selectbox("Persona (RLS)", list(C.PERSONAS), key="persona_select", on_change=_persona_changed)
        user_id = C.PERSONAS[persona]
        scope = get_user_scope(user_id)
        st.markdown(f"<div class='cp-scope'>Data access: <b>{C.esc(scope.scope_label)}</b></div>", unsafe_allow_html=True)

        max_d = data_as_of_date()
        as_of = st.date_input(
            "As-of date",
            value=max_d,
            min_value=date(2025, 7, 1),
            max_value=max_d,
            help="Moves the deterministic point-in-time clock for MTD and cumulative views.",
        )
        choices = C.model_choices()
        if st.session_state.get("model_select") not in choices:
            wanted = st.session_state.get("model_param") or str(st.query_params.get("model", "")).strip().lower()
            st.session_state.model_select = next(
                (c for c in choices if wanted and c.lower().startswith(wanted)),
                choices[0],
            )
        model = st.selectbox(
            "Model (LiteLLM)",
            choices,
            key="model_select",
            help="'rules (no LLM)' runs 100% deterministic local routing & templated executive prose.",
        )
    return {
        "user_id": user_id,
        "as_of": as_of,
        "model": None if model.startswith("rules") else model,
        "model_label": model,
    }


def _prune_single(key: str, valid_options: list[str]) -> None:
    cur = st.session_state.get(key)
    if cur not in (None, *valid_options):
        st.session_state.pop(key, None)


def _filters(user_id: str) -> dict:
    scope = get_user_scope(user_id)
    org = _org_df()
    org = org[org["RegionCode"].isin(scope.regions)]

    with st.expander("Scope filters", expanded=True):
        reg_opts = ["All in scope"] + sorted(org["RegionCode"].unique().tolist())
        _prune_single("flt_region", reg_opts)
        sel_reg = st.selectbox("Region", reg_opts, key="flt_region")
        if sel_reg != "All in scope":
            org = org[org["RegionCode"] == sel_reg]

        ent_opts = ["All in scope"] + sorted(org["AdoptionEntity"].unique().tolist())
        _prune_single("flt_entity", ent_opts)
        sel_ent = st.selectbox("Adoption Entity", ent_opts, key="flt_entity")
        if sel_ent != "All in scope":
            org = org[org["AdoptionEntity"] == sel_ent]

        wave_opts = ["All in scope"] + [f"Wave {int(w)}" for w in sorted(org["AdoptionWaveNumber"].unique().tolist())]
        _prune_single("flt_wave", wave_opts)
        sel_wave = st.selectbox("Rollout Wave", wave_opts, key="flt_wave")
        if sel_wave != "All in scope":
            wnum = int(sel_wave.split()[-1])
            org = org[org["AdoptionWaveNumber"] == wnum]

        bu_opts = ["All in scope"] + sorted(org["BusinessUnit"].unique().tolist())
        _prune_single("flt_bu", bu_opts)
        sel_bu = st.selectbox("Business Unit", bu_opts, key="flt_bu")

        _prune_single("flt_kpi", KPI_OPTIONS)
        sel_kpi = st.selectbox("KPI Focus", KPI_OPTIONS, key="flt_kpi")

        _prune_single("flt_period", PERIOD_OPTIONS)
        sel_per = st.selectbox("Period Window", PERIOD_OPTIONS, key="flt_period")

        st.button("Clear filters", width="stretch", on_click=clear_filters, key="clear_filters")

    ui: dict = {}
    if sel_reg != "All in scope":
        ui["region"] = sel_reg
    if sel_ent != "All in scope":
        ui["entity"] = sel_ent
    if sel_wave != "All in scope":
        ui["wave"] = int(sel_wave.split()[-1])
    if sel_bu != "All in scope":
        ui["business_unit"] = sel_bu
    if sel_kpi != KPI_OPTIONS[0]:
        ui["kpi_name"] = sel_kpi
    if sel_per != PERIOD_OPTIONS[0]:
        ui["period_mode"] = PERIOD_CODE[sel_per]
    return ui


def filter_chips(ui: dict) -> list[str]:
    out = []
    if ui.get("region"):
        out.append(f"Region: {ui['region']}")
    if ui.get("entity"):
        out.append(f"Entity: {ui['entity']}")
    if ui.get("wave") is not None:
        out.append(f"Wave: Wave {ui['wave']}")
    if ui.get("business_unit"):
        out.append(f"BU: {ui['business_unit']}")
    if ui.get("kpi_name"):
        out.append(f"KPI: {ui['kpi_name']}")
    if ui.get("period_mode"):
        out.append(f"Period: {ui['period_mode']}")
    return out


def _relative_time(ts: datetime | None) -> str:
    if ts is None:
        return ""
    secs = (datetime.now() - ts).total_seconds()
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    days = int(secs // 86400)
    return "yesterday" if days == 1 else f"{days}d ago"


def _conversations(user_key: str) -> None:
    st.markdown("**Conversations**")
    if st.button("➕ New conversation", width="stretch", key="new_conv"):
        C.new_conversation()
        st.rerun()
    store = C.history_store()
    if store is None:
        st.caption("Conversation history unavailable.")
        return
    try:
        convs = store.list(user_key)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"History unavailable ({type(exc).__name__}).")
        return
    if not convs:
        st.caption("Your last 10 conversations will appear here.")
    active = st.session_state.get("active_cid")
    for c in convs:
        cols = st.columns([5, 1])
        mark = "📌 " if c.is_pinned else ""
        cur = "▸ " if c.conversation_id == active else ""
        label = f"{cur}{mark}{C.md_escape(c.title)} · {_relative_time(c.updated_at)}"
        if cols[0].button(
            label,
            key=f"conv_{c.conversation_id}",
            width="stretch",
            type="primary" if c.conversation_id == active else "secondary",
        ):
            C.open_conversation(c.conversation_id)
            st.rerun()
        with cols[1].popover("⋯", help="Rename, pin or delete"):
            new_t = st.text_input("Rename", value=c.title, key=f"ren_{c.conversation_id}", max_chars=120)
            if st.button("Save name", key=f"ren_btn_{c.conversation_id}"):
                store.rename(user_key, c.conversation_id, new_t)
                st.rerun()
            if st.button("Unpin" if c.is_pinned else "Pin to top", key=f"pin_{c.conversation_id}"):
                store.pin(user_key, c.conversation_id, not c.is_pinned)
                st.rerun()
            confirm = st.checkbox("Confirm delete", key=f"delc_{c.conversation_id}")
            if st.button("Delete", key=f"del_{c.conversation_id}", disabled=not confirm):
                store.delete(user_key, c.conversation_id)
                if active == c.conversation_id:
                    C.new_conversation()
                st.rerun()
    st.caption("Keeps your last 10 threads; pinned conversations stay on top.")


def render() -> dict:
    with st.sidebar:
        if st.button("❓ Quick guide", width="stretch"):
            quick_guide()
        who = st.session_state.get("auth_name")
        if who:
            c1, c2 = st.columns([3, 2], vertical_alignment="center")
            c1.caption(f"Signed in as **{C.md_escape(who)}**")
            c2.button("Sign out", key="sign_out", on_click=C.sign_out, width="stretch")
        cfg = _settings()
        cfg["ui_filters"] = _filters(cfg["user_id"])
        st.divider()
        _conversations(st.session_state.get("auth_user") or "")
        st.divider()
        st.caption(f"Backend: {backend()} · last closed month: Oct 2026")
        st.caption(B.footer_line())
    st.session_state["cfg"] = cfg
    return cfg
