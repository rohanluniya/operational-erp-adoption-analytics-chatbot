"""About view: Architecture, Semantic Governance Contract, Production Lift, and Modular Release Roadmap."""
from __future__ import annotations

import streamlit as st

from app.config import backend
from app.ui import branding as B

HOW_IT_WORKS_DOT = """
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#E6F4F1", color="#0F766E", fontname="Helvetica", fontsize=11];
  edge [color="#3730A3"];
  q [label="Your question\\n(plain English)", fillcolor="#EEF0FB", color="#3730A3"];
  a [label="AI assistant\\nselects governed tool,\\nnever guesses numbers"];
  m [label="Medallion & Semantic\\nKPI definitions"];
  s [label="Secure data access\\n(row-level security,\\nread-only)"];
  o [label="Answer:\\ninsight + table + chart", fillcolor="#EEF0FB", color="#3730A3"];
  q -> a -> m -> s -> o;
}
"""


def render() -> None:
    st.markdown(f"## About {B.APP_NAME}")
    st.markdown(
        f"**{B.APP_NAME}** is a conversational rollout and adoption analytics "
        f"assistant for the global **{B.OPERATIONAL_PLATFORM}** platform. Ask a question in plain English and get "
        "a concise insight, a governed table, an interactive chart, and full source-to-answer lineage."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            "#### Authoritative Baseline (`prototype.md`)\n"
            "- **Four Certified KPIs:** `Contracts Created`, `Employees Logging In`, `Timesheets Submitted`, and `Expense Reports`.\n"
            "- **True Event Timestamps:** `Project.CreatedDate`, `ApplicationLog.CreatedDate`, `Timecard.SubmittedDate`, and `ExpenseReport.SubmittedDate`.\n"
            "- **Non-Additive Distinct Users:** `COUNT(DISTINCT APPUserId)` (`IsServiceAccount = 0`) recomputed at each grain (`OVERALL`, `WAVE`, `ENTITY`), never summed from child rows.\n"
            "- **Explicit Attribution Limits:** Business Unit breakdowns are blocked for `Employees Logging In` (no employee home-BU table) and `Timesheets Submitted` (multi-BU task rows).\n"
            "- **DataOps Governance:** `ApplicationLogId` incremental watermark, explicit `INSERT` column lists, orphan row quarantine, and parity checks."
        )
    with c2:
        st.markdown(
            "#### Prototype Scope vs. Production Lift\n"
            "- **Synthetic Data:** Fictional company, people, and figures across 3 regions (`AMER`, `EMEA`, `APAC`), 4 waves, and 10 Business Units with zero corporate connectivity.\n"
            "- **Rollout Registry (`SIMULATED EXTENSION`):** `reference.rollout_registry` and `reference.module_catalog` model `LIVE` / `ONBOARDING` / `PLANNED` states and distinguish `INSTRUMENTED` vs `NOT_INSTRUMENTED` modules.\n"
            "- **Dual Database Runtime:** Runs identically on **SQL Server 2022** (`core_pulse`, read-only login `pulse_reader`, native `SESSION_CONTEXT` Row-Level Security) and local **DuckDB**. Active backend: **`"
            + backend().upper() + "`**.\n"
            "- **Enterprise Lift:** Point Bronze extractors to read-only replicas of production CORE SQL Server, bind Microsoft Entra ID SSO to `SESSION_CONTEXT`, and connect HRIS worker home-BU master data."
        )

    st.markdown("#### How it works")
    st.graphviz_chart(HOW_IT_WORKS_DOT)

    st.markdown("#### Modular Platform Roadmap")
    st.markdown(
        "| Release | Analytics Domain | Planned Capabilities |\n"
        "|---|---|---|\n"
        "| **Release 1 (Current)** | **CORE Rollout & Adoption** | 4 baseline adoption KPIs, Medallion + DataOps watermarks, Rollout Registry (`SIMULATED EXTENSION`), conversational BI |\n"
        "| **Release 2** | **Contracts & Project Delivery** | Project/Service/Phase/Task lifecycle, turnaround cycle time, backlog velocity |\n"
        "| **Release 3** | **Field Scheduling & Qualifications** | Inspector dispatch utilization, NDT/safety certification expiry & compliance |\n"
        "| **Release 4** | **Laboratory LIMS & Billing** | Specimen throughput, certificate turnaround, milestone & T&M invoicing |"
    )

    st.markdown("#### This version")
    st.markdown(f"- {B.AUTHOR_LINE}\n- Version {B.VERSION}\n- Owner: {B.AUTHOR}")
