"""Data Catalog & Medallion Foundation view: KPI Dictionary, End-to-End Lineage, and DataOps Inspector."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import text

from app.db import get_engine
from app.semantic import service as Svc
from app.ui import common as C
from app.viz.charts import figure
from app.viz.tables import TABLE_CSS, render_html


def render() -> None:
    st.markdown("### 🗂️ Data Catalog, Medallion Architecture & DataOps")
    t_kpi, t_lin, t_ops, t_prev = st.tabs([
        "📏 Governed KPI Dictionary",
        "🔗 Source-to-Answer Lineage",
        "⚙️ DataOps & Quality Checks",
        "🔬 Medallion Table Preview",
    ])

    with t_kpi:
        defs = Svc.get_core_metric_definition("ALL")
        st.markdown(defs.headline)
        st.markdown(TABLE_CSS + render_html(defs.df), unsafe_allow_html=True)
        st.info(
            "**Non-Additivity Rule:** `Employees Logging In` (`COUNT(DISTINCT APPUserId)`) is strictly non-additive "
            "across days, months, applications, adoption entities, and rollout waves. Every grain in `goldview.v_core_adoption` "
            "and `get_core_user_engagement` is deduplicated from atomic user-day activity—never summed from child rows."
        )
        c1, c2 = st.columns(2)
        with c1:
            C.ask_button(
                "Test Unsupported BU Breakdown (Logins)",
                "Can you show Employees Logging In by Business Unit?",
                key="cat_ask_bu1",
            )
        with c2:
            C.ask_button(
                "Test Wave Non-Additivity Explanation",
                "Why doesn't the sum of Wave 1 and Wave 2 active users equal total active users?",
                key="cat_ask_w12",
            )

    with t_lin:
        lin = Svc.get_core_metric_lineage("ALL")
        st.markdown(lin.headline)
        st.markdown(TABLE_CSS + render_html(lin.df), unsafe_allow_html=True)
        st.code(
            "source_sim.* (16 normalized CORE tables)\n"
            "   └──▶ bronze.core_* (explicit column lists, SourceExtractDateTime, PipelineRunId, ApplicationLogId watermark)\n"
            "          └──▶ silver.* (conformed org LEFT JOIN local enrichment, parent-child integrity, IsServiceAccount=0)\n"
            "                 └──▶ gold.coreadoption_event + gold.coreadoption_user_activity + gold.coreadoption_kpi_daily\n"
            "                        └──▶ goldview.v_core_adoption (certified CURRENT & MONTHLY contract)\n"
            "                               └──▶ Read-Only MCP Server (10 typed tools) ──▶ CORE Pulse Chat Answer",
            language="text",
        )

    with t_ops:
        ops = Svc.get_core_pipeline_status()
        st.markdown(ops.headline)
        fig = figure(ops.chart_spec)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="ops_layer_chart")
        st.markdown("#### Latest Run Data Quality & Source-to-Gold Parity Checks")
        st.markdown(TABLE_CSS + render_html(ops.df), unsafe_allow_html=True)

        eng = get_engine()
        with eng.connect() as conn:
            wm = pd.read_sql(text("SELECT * FROM dataops.watermark"), conn)
            steps = pd.read_sql(text("""
                SELECT StepNumber, StepName, RowsAffected, RunStatus
                FROM dataops.pipeline_step_run
                WHERE PipelineRunId = (SELECT MAX(PipelineRunId) FROM dataops.pipeline_run)
                ORDER BY StepNumber
            """), conn)
        st.markdown("#### Incremental Watermark (`dataops.watermark`)")
        st.markdown(TABLE_CSS + render_html(wm), unsafe_allow_html=True)
        with st.expander("View 11 Pipeline Step Execution Logs (`dataops.pipeline_step_run`)"):
            st.markdown(TABLE_CSS + render_html(steps), unsafe_allow_html=True)

    with t_prev:
        st.markdown("#### Inspect Live Medallion Objects (Top 15 Rows)")
        obj = st.selectbox(
            "Select schema.object",
            [
                "goldview.v_core_adoption",
                "goldview.v_dim_date",
                "gold.coreadoption_user_activity",
                "gold.coreadoption_event",
                "silver.organization",
                "silver.application_mapping",
                "bronze.core_application_log",
                "reference.rollout_registry",
                "reference.module_catalog",
            ],
        )
        eng = get_engine()
        with eng.connect() as conn:
            sample_df = pd.read_sql(text(f"SELECT * FROM {obj} LIMIT 15" if eng.dialect.name == "duckdb"
                                         else f"SELECT TOP 15 * FROM {obj}"), conn)
        st.markdown(TABLE_CSS + render_html(sample_df), unsafe_allow_html=True)
