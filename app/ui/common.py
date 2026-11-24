"""Shared UI helpers for CORE Pulse: theme CSS, header, sign-in, conversation history, and answer rendering."""
from __future__ import annotations

import base64
import html
import json
import re

import pandas as pd
import streamlit as st

from app.config import env, settings
from app.ui import branding as B
from app.viz.charts import figure
from app.viz.tables import TABLE_CSS, render_html, to_csv_bytes, to_excel_bytes

PERSONAS = {
    k: v["user_id"] for k, v in settings().get("personas", {}).items()
}

WELCOME_EXAMPLES = [
    "How many employees logged into CORE this month?",
    "Show monthly contract creation over the last 12 months and highlight the fastest-growing month.",
    "Which entities are live on Expenses, and which live entities have zero expense submissions?",
]

DEMO_JOURNEY_EXAMPLES = [
    "How many employees logged into CORE this month?",
    "Show the six-month trend.",
    "Which rollout wave is most active?",
    "Which modules are live for the Western region?",
    "Are those modules actually seeing activity?",
    "Show me how this metric was calculated and where the data came from.",
]

GOVERNANCE_EXAMPLES = [
    "What is current CORE adoption overall?",
    "Why doesn't the sum of Wave 1 and Wave 2 active users equal total active users?",
    "Can you show Employees Logging In by Business Unit?",
    "Can you show Timesheets Submitted by Business Unit?",
    "Which rollout wave has the highest timecard submission volume?",
    "How fresh is the dataset, and did any mapping or orphan checks fail in the latest run?",
]

CSS = """
<style>
/* Streamlit's top bar (logo, top navigation) is 3.75rem high and overlays the page: start cleanly below it */
[data-testid="stMainBlockContainer"], .block-container {padding-top: 3.5rem; max-width: 1360px;}
[data-testid="stSidebar"] {min-width: 345px;}
.cp-head {display:flex; align-items:center; gap:14px; padding: 10px 16px;
          border-radius: 12px; background: linear-gradient(90deg, #0F766E 0%, #3730A3 100%);
          color:#fff; margin-bottom: 8px;}
.cp-head-left {display:flex; align-items:center; gap:14px;}
.cp-head img {width: 52px; height: 52px; background:#fff; border-radius: 50%; padding: 3px;}
.cp-head .name {font-size: 1.55rem; font-weight: 800; letter-spacing: 0.05em; margin: 0; line-height: 1.15;}
.cp-head .author {font-size: 0.84rem; opacity: 0.90; margin-top: 3px;}
.rl-banner {background: #FFF4E5; border: 1px solid #F5B041; color: #7E5109; padding: 6px 12px; border-radius: 8px;
            font-size: 0.85rem; margin-bottom: 10px;}
.cp-scope {font-size: 0.8rem; color: #475569; margin-bottom: 4px;}
.cp-chip {display:inline-block; background:#E6F4F1; color:#0F766E; border-radius:12px; padding:2px 10px;
          margin:2px 4px 2px 0; font-size:0.78rem; font-weight:600;}
.cp-chip.filter {background:#EEF0FB; color:#3730A3;}
.cp-chip.mcp {background:#ECFDF5; color:#047857; border:1px solid #A7F3D0;}
div[data-testid="stChatMessage"] {background: #FFFFFF;}
.stButton>button {border-radius: 8px; border: 1px solid #CBD5E1; text-align: left; white-space: normal;
                  height: auto; padding: 0.45rem 0.72rem; font-size: 0.85rem;}
.stButton>button p {white-space: normal !important; overflow: visible !important; text-overflow: clip !important;}
.stButton>button:hover {border-color: #0F766E; color: #0F766E;}
.cp-kpi-card {border:1px solid #E2E8F0; border-top: 3px solid #0F766E; border-radius:10px; padding:12px 14px;
              background:#FFFFFF; box-shadow: 0 1px 2px rgba(15,23,42,0.04); min-height: 136px;
              display: flex; flex-direction: column; justify-content: space-between; white-space: normal;}
.cp-kpi-card .k-title {font-size:0.79rem; font-weight:700; color:#334155; text-transform:uppercase; letter-spacing:0.03em;}
.cp-kpi-card .k-val {font-size:1.50rem; font-weight:800; color:#0B1F3A; margin:3px 0;}
.cp-kpi-card .k-period {font-size:0.76rem; color:#0F766E; font-weight:600;}
.cp-kpi-card .k-sub {font-size:0.76rem; color:#64748B; margin-top:4px; line-height:1.38; white-space: normal;}
.ug-fig {margin: 14px 0 22px; padding: 0;}
.ug-fig img {display: block; height: auto; border-radius: 10px; border: 1px solid #CBD5E1;
             box-shadow: 0 4px 16px rgba(11, 31, 58, 0.08);}
.ug-fig figcaption {font-size: 0.82rem; color: #475569; margin-top: 6px; font-style: italic;}
</style>
"""

MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~<])")


def esc(text) -> str:
    return html.escape("" if text is None else str(text))


def md_escape(text) -> str:
    return MD_SPECIAL.sub(r"\\\1", "" if text is None else str(text))


def logo_data_uri() -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(B.LOGO_PATH.read_bytes()).decode()


def apply_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    default_persona = next(iter(PERSONAS.keys()), "Global CORE Program Lead")
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("memory", {})
    st.session_state.setdefault("pending", None)
    st.session_state.setdefault("persona", default_persona)
    st.session_state.setdefault("active_cid", None)
    st.session_state.setdefault("welcome_dismissed", False)
    st.session_state.setdefault("model_param", str(st.query_params.get("model", "")).strip().lower())


def model_choices() -> list[str]:
    current = env("LLM_MODEL", "ollama/qwen2.5-coder:14b") or "ollama/qwen2.5-coder:14b"
    raw = env("LLM_MODEL_CHOICES", "ollama/qwen2.5-coder:14b,ollama/gpt-oss:20b") or ""
    choices = [current] + [m.strip() for m in raw.split(",") if m.strip() and m.strip() != current]
    return choices + ["rules (no LLM)"]


def header() -> None:
    """Clean header + synthetic data notice matching IRIS."""
    st.markdown(
        f"<div class='cp-head'>"
        f"<div class='cp-head-left'><img src='{logo_data_uri()}' alt='{esc(B.APP_NAME)} logo'/>"
        f"<div><div class='name'>{esc(B.APP_NAME)}</div>"
        f"<div class='author'>{esc(B.AUTHOR_LINE)}</div></div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='rl-banner'>⚠️ <b>Synthetic data – prototype for demonstration only.</b> "
        "Fictional company, people and figures.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sign-in gate
# ---------------------------------------------------------------------------
def signed_in() -> bool:
    return bool(st.session_state.get("auth_user"))


def sign_in(display_name: str, code: str) -> str | None:
    import hmac
    from app.history.store import normalize_user

    uid = normalize_user(display_name)
    if not uid:
        return "Please enter your display name."
    expected = env("APP_ACCESS_CODE", "my-access-code")
    if not expected:
        return "Sign-in is not configured: set APP_ACCESS_CODE in .env."
    if not hmac.compare_digest(str(code or "").encode(), str(expected).encode()):
        return "The access code is not correct."
    st.session_state["auth_user"] = uid
    st.session_state["auth_name"] = display_name.strip()[:80]
    return None


def sign_out() -> None:
    for k in ("auth_user", "auth_name", "active_cid", "welcome_dismissed"):
        st.session_state.pop(k, None)
    st.session_state.messages, st.session_state.memory = [], {}


def login_page() -> None:
    header()
    st.markdown(f"### Sign in to {B.APP_NAME}")
    with st.form("login", clear_on_submit=False):
        name = st.text_input("Your name", max_chars=80, placeholder="e.g. Alex Morgan")
        code = st.text_input("Access code", type="password")
        ok = st.form_submit_button("Sign in", type="primary")
    if ok:
        err = sign_in(name, code)
        if err:
            st.error(err)
        else:
            st.rerun()
    st.caption(
        "Demo sign-in only: your name keeps your conversation history separate from other users. "
        "A production deployment would use single sign-on (Microsoft Entra ID / Active Directory)."
    )
    st.caption(B.footer_line())


# ---------------------------------------------------------------------------
# Conversation history helpers
# ---------------------------------------------------------------------------
def history_store():
    try:
        from app.history.store import ConversationStore
        return ConversationStore()
    except Exception:  # noqa: BLE001
        return None


def new_conversation() -> None:
    st.session_state.messages, st.session_state.memory = [], {}
    st.session_state.active_cid = None


def open_conversation(cid: str) -> None:
    store = history_store()
    user = st.session_state.get("auth_user")
    if store is None or not user:
        return
    conv, msgs, state = store.load(user, cid)
    if conv is None:
        return
    for m in msgs:
        if m.get("role") == "assistant":
            m.setdefault("answer", {}).setdefault("diagnostics", {})["resumed"] = True
    st.session_state.messages = msgs
    st.session_state.memory = state.get("memory") or {}
    st.session_state.active_cid = conv.conversation_id
    if conv.persona in PERSONAS:
        st.session_state["restore_persona"] = conv.persona
    if state.get("ui_widgets"):
        st.session_state["restore_filters"] = state["ui_widgets"]


def apply_restored_filters() -> None:
    persona = st.session_state.pop("restore_persona", None)
    if persona in PERSONAS:
        st.session_state.persona = persona
        st.session_state["persona_select"] = persona
    pending = st.session_state.pop("restore_filters", None)
    if pending is None:
        return
    from app.ui.sidebar import FILTER_KEYS, clear_filters
    clear_filters()
    for k in FILTER_KEYS:
        if pending.get(k) not in (None, [], "", "Default", "Default (Auto / All KPIs)"):
            st.session_state[k] = pending[k]


def save_turn(question: str, payload: dict, memory: dict, cfg: dict) -> str | None:
    from app.history.store import ConversationLimit
    from app.ui.sidebar import FILTER_KEYS

    store = history_store()
    user = st.session_state.get("auth_user")
    if store is None or not user:
        return None
    try:
        state_blob = {
            "memory": memory,
            "persona": st.session_state.persona,
            "ui_filters": cfg.get("ui_filters") or {},
            "ui_widgets": {k: st.session_state.get(k) for k in FILTER_KEYS},
        }
        cid = store.save_turn(
            user_id=user,
            cid=st.session_state.get("active_cid"),
            persona=st.session_state.persona,
            question=question,
            payload=payload,
            memory=state_blob,
        )
        st.session_state.active_cid = cid
    except ConversationLimit as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        return f"History note: conversation could not be saved ({type(exc).__name__})."
    return None


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def chips(values: list[str], kind: str = "") -> None:
    vals = [v for v in values if v]
    if vals:
        cls = f"cp-chip {kind}".strip()
        st.markdown("".join(f"<span class='{cls}'>{esc(v)}</span>" for v in vals), unsafe_allow_html=True)


def queue_page(name: str, question: str | None = None) -> None:
    if question:
        st.session_state.pending = question
    st.session_state.nav_goto = name


def ask_button(label: str, question: str, key: str) -> None:
    st.button(label, key=key, help=question, on_click=queue_page, args=("chat", question))


def example_buttons(questions: list[str], prefix: str, ncols: int = 2) -> None:
    cols = st.columns(ncols)
    for i, q in enumerate(questions):
        if cols[i % ncols].button(q, key=f"{prefix}_{i}", width="stretch"):
            st.session_state.pending = q
            st.rerun()


def render_answer(ans: dict, idx: int, cfg: dict) -> None:
    """Render insight text, scope chips, HTML table, Plotly chart, downloads, lineage drawer, and follow-ups."""
    status = ans.get("status", "ok")
    d = ans.get("diagnostics") or {}
    f = ans.get("filters_used") or {}

    if status == "refusal":
        st.error("🔒 " + (ans.get("answer_markdown") or ""))
    elif status == "unsupported":
        st.warning("ℹ️ " + (ans.get("answer_markdown") or ""))
    elif status == "clarification":
        st.info(ans.get("answer_markdown") or "")
        for j, opt in enumerate(d.get("options", [])[:4]):
            if st.button(opt, key=f"opt_{idx}_{j}"):
                st.session_state.pending = opt
                st.rerun()
    else:
        st.markdown(ans.get("answer_markdown") or "")

    if status in ("ok", "unsupported"):
        chip_vals = [
            f.get("kpi"),
            f.get("period"),
            f.get("persona"),
        ]
        chips(chip_vals)
        if d.get("via_mcp"):
            chips([f"MCP Tool: {(d.get('tool_calls') or [{}])[0].get('name', 'governed')}"], "mcp")
        if f.get("applied"):
            st.caption("Filters applied: " + " · ".join(f["applied"]))
        if f.get("carried_over"):
            st.caption("↪ Context carried over: " + " · ".join(f["carried_over"]))

    cols = ans.get("table_columns") or []
    recs = ans.get("table_records") or []
    df = pd.DataFrame(recs, columns=cols) if cols and recs else pd.DataFrame()
    if not df.empty:
        st.markdown(TABLE_CSS + render_html(df), unsafe_allow_html=True)

    fig = figure(ans.get("chart_spec") or {})
    if fig is not None:
        st.plotly_chart(fig, width="stretch", key=f"chart_{idx}")

    if not df.empty:
        c1, c2, _ = st.columns([1, 1, 5])
        c1.download_button(
            "⬇️ CSV",
            to_csv_bytes(df),
            file_name=f"core_pulse_{idx}.csv",
            mime="text/csv",
            key=f"csv_{idx}",
        )
        c2.download_button(
            "⬇️ Excel",
            to_excel_bytes(df),
            file_name=f"core_pulse_{idx}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"xls_{idx}",
        )

    if status in ("ok", "unsupported", "refusal"):
        with st.expander("🔍 How I got this & Medallion Lineage"):
            st.markdown(
                f"**KPI / Contract:** `{f.get('kpi', '-')}`  \n"
                f"**Period Window:** `{f.get('period', '-')}` (As-of `{f.get('as_of_date', '-')}`)  \n"
                f"**Persona & RLS Scope:** `{f.get('persona', '-')}` — {f.get('rls', '-')}  \n"
                f"**Lineage Pointer:** `{d.get('lineage_id', 'goldview.v_core_adoption')}` · "
                f"**Freshness:** `{d.get('freshness_ts') or f.get('freshness_ts') or 'latest'}`"
            )
            calls = d.get("tool_calls") or []
            if calls:
                st.markdown(f"**MCP Tool Call** (router: `{d.get('tool_choice_source', 'rules')}`, `via_mcp={d.get('via_mcp')}`)")
                st.json(calls, expanded=False)
            g = d.get("guardrail") or {}
            if g:
                g_lbl = "verified LLM narration" if (g.get("ok") and not g.get("template")) else f"deterministic template ({g.get('reason', 'rules')})"
                st.caption(f"Guardrail: {g_lbl} · model: {d.get('model', 'rules')} · latency: {d.get('latency_s', '-')} s")
            for sql in ans.get("sql_used") or []:
                st.code(sql, language="sql")

    fu = ans.get("followups") or []
    if fu and status in ("ok", "unsupported"):
        st.markdown("**Suggested follow-ups**")
        fcols = st.columns(min(3, len(fu)))
        for j, q in enumerate(fu[:3]):
            if fcols[j].button(q, key=f"fu_{idx}_{j}", width="stretch"):
                st.session_state.pending = q
                st.rerun()


def to_json(obj) -> str:
    return json.dumps(obj, default=str)
