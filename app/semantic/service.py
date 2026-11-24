"""Governed analytics service for CORE Pulse.

Single read-only business service shared by BOTH:
  * the Streamlit conversational agent (`app/agent/`), and
  * the read-only Python MCP server (`mcp_server/server.py`).

Every query uses parameterized SQL against `goldview.v_core_adoption`, `gold.coreadoption_user_activity`,
`gold.coreadoption_event`, `reference.rollout_registry` (`SIMULATED EXTENSION`), or `dataops.*`,
enforces Persona Row-Level Security, and returns structured results + compiled SQL + lineage + warnings.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd
import yaml
from sqlalchemy import text

from app.config import ROOT, as_of_date, backend
from app.db import get_engine
from app.semantic.access import UserScope, check_scope_allowed, get_user_scope

KPI_CANONICAL = {
    "contracts_created": "Contracts Created",
    "contracts created": "Contracts Created",
    "contracts": "Contracts Created",
    "projects": "Contracts Created",
    "projects created": "Contracts Created",
    "employees_logging_in": "Employees Logging In",
    "employees logging in": "Employees Logging In",
    "employees": "Employees Logging In",
    "users": "Employees Logging In",
    "active users": "Employees Logging In",
    "logins": "Employees Logging In",
    "timesheets_submitted": "Timesheets Submitted",
    "timesheets submitted": "Timesheets Submitted",
    "timesheets": "Timesheets Submitted",
    "timecards": "Timesheets Submitted",
    "timecard submissions": "Timesheets Submitted",
    "expense_reports": "Expense Reports",
    "expense reports": "Expense Reports",
    "expenses": "Expense Reports",
    "expense submissions": "Expense Reports",
}

ALL_KPIS = ("Contracts Created", "Employees Logging In", "Timesheets Submitted", "Expense Reports")
BU_SUPPORTED_KPIS = ("Contracts Created", "Expense Reports")


@lru_cache(maxsize=1)
def semantic_catalog() -> dict:
    with open(ROOT / "app" / "semantic" / "metrics.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_kpi_name(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().lower()
    if s in ("all", "overview", "all kpis", "*"):
        return "ALL"
    if s in KPI_CANONICAL:
        return KPI_CANONICAL[s]
    cat = semantic_catalog()["metrics"]
    for _mid, spec in cat.items():
        if s == spec["kpi_name"].lower() or s in [syn.lower() for syn in spec.get("synonyms", [])]:
            return spec["kpi_name"]
    for k, v in KPI_CANONICAL.items():
        if k in s:
            return v
    return None


def kpi_meta(kpi_name: str) -> dict:
    cat = semantic_catalog()["metrics"]
    for mid, spec in cat.items():
        if spec["kpi_name"] == kpi_name:
            out = dict(spec)
            out["metric_id"] = mid
            return out
    return {}


@dataclass
class ToolPayload:
    status: str = "ok"                     # ok | unsupported | refusal | empty
    tool_name: str = ""
    metric_id: str = ""
    kpi_name: str = ""
    headline: str = ""
    facts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    df: pd.DataFrame = field(default_factory=pd.DataFrame)
    chart_spec: dict[str, Any] = field(default_factory=dict)
    filters_used: dict[str, Any] = field(default_factory=dict)
    period_label: str = ""
    is_complete_month: bool = True
    freshness_ts: str = ""
    lineage_id: str = ""
    compiled_sql: str = ""
    via_mcp: bool = False


def _freshness(conn) -> str:
    row = conn.execute(text("SELECT MAX(LoadDateTime) FROM goldview.v_core_adoption")).fetchone()
    if row and row[0]:
        return str(row[0])[:19]
    return "unknown"


def _fmt_int(val: Any) -> str:
    try:
        return f"{int(round(float(val))):,}"
    except (TypeError, ValueError):
        return str(val)


def _month_bounds(as_of: date) -> tuple[date, date]:
    cur_m = date(as_of.year, as_of.month, 1)
    if as_of.month == 1:
        prev_m = date(as_of.year - 1, 12, 1)
    else:
        prev_m = date(as_of.year, as_of.month - 1, 1)
    return cur_m, prev_m


def _same_days_mtd_counts(conn, kpi_name: str, as_of: date, scope: UserScope,
                          region: str | None = None, entity: str | None = None,
                          wave: int | None = None, bu: str | None = None) -> dict[str, Any]:
    """Compare current MTD (e.g. Nov 1..17) with equivalent elapsed days in prior month (Oct 1..17)."""
    cur_start = date(as_of.year, as_of.month, 1)
    elap = as_of.day
    prev_y, prev_m = (as_of.year - 1, 12) if as_of.month == 1 else (as_of.year, as_of.month - 1)
    prev_start = date(prev_y, prev_m, 1)
    prev_end_day = min(elap, calendar.monthrange(prev_y, prev_m)[1])
    prev_eq_end = date(prev_y, prev_m, prev_end_day)
    prev_full_end = date(prev_y, prev_m, calendar.monthrange(prev_y, prev_m)[1])

    where = ["KPIName = :kpi"]
    params: dict[str, Any] = {"kpi": kpi_name}
    if not scope.is_global:
        r_ph = ", ".join(f":sr{i}" for i in range(len(scope.regions)))
        where.append(f"RegionCode IN ({r_ph})")
        for i, rc in enumerate(scope.regions):
            params[f"sr{i}"] = rc
    if region:
        where.append("RegionCode = :reg")
        params["reg"] = region
    if entity:
        where.append("AdoptionEntity = :ent")
        params["ent"] = entity
    if wave is not None:
        where.append("AdoptionWaveNumber = :wv")
        params["wv"] = int(wave)
    if bu:
        where.append("BusinessUnit = :bu")
        params["bu"] = bu

    agg_expr = "COUNT(DISTINCT APPUserId)" if kpi_name == "Employees Logging In" else "COUNT(DISTINCT DistinctEntityId)"
    w_sql = " AND ".join(where)

    def q_range(d1: date, d2: date) -> int:
        p = dict(params, d1=d1, d2=d2)
        val = conn.execute(
            text(f"SELECT {agg_expr} FROM gold.coreadoption_event WHERE {w_sql} AND EventDate >= :d1 AND EventDate <= :d2"),
            p,
        ).scalar()
        return int(val or 0)

    mtd_val = q_range(cur_start, as_of)
    prev_mtd_val = q_range(prev_start, prev_eq_end)
    prev_full_val = q_range(prev_start, prev_full_end)
    sql_txt = (f"SELECT {agg_expr} AS KPIValue FROM gold.coreadoption_event "
               f"WHERE {w_sql} AND EventDate BETWEEN '{cur_start}' AND '{as_of}'")
    return {
        "mtd_val": mtd_val,
        "mtd_label": f"{cur_start.strftime('%b %Y')} MTD (days 1–{elap}, partial month)",
        "prev_mtd_val": prev_mtd_val,
        "prev_mtd_label": f"{prev_start.strftime('%b %Y')} days 1–{prev_end_day} (equivalent MTD)",
        "prev_full_val": prev_full_val,
        "prev_full_label": f"{prev_start.strftime('%b %Y')} (complete month)",
        "sql": sql_txt,
    }


# ---------------------------------------------------------------------------
# 1. get_core_adoption_current
# ---------------------------------------------------------------------------
def get_core_adoption_current(kpi_name: str = "ALL", period_mode: str = "SNAPSHOT",
                              region: str | None = None, entity: str | None = None,
                              wave: int | None = None, business_unit: str | None = None,
                              user_id: str = "global_program_lead",
                              as_of: date | None = None) -> ToolPayload:
    as_of = as_of or as_of_date()
    scope = get_user_scope(user_id)
    refusal = check_scope_allowed(scope, region=region, entity=entity, wave=wave, business_unit=business_unit)
    if refusal:
        return ToolPayload(status="refusal", tool_name="get_core_adoption_current", headline=refusal)

    resolved = resolve_kpi_name(kpi_name) or "ALL"
    if business_unit and resolved in ("Employees Logging In", "Timesheets Submitted"):
        meta = kpi_meta(resolved)
        reason = meta["unsupported_levels"]["BUSINESS_UNIT"]
        return ToolPayload(
            status="unsupported",
            tool_name="get_core_adoption_current",
            metric_id=meta["metric_id"],
            kpi_name=resolved,
            headline=f"**{resolved}** is not available by Business Unit (`{business_unit}`).",
            facts=[reason, "Try breaking down by **Adoption Entity** or **Rollout Wave** instead."],
            warnings=[reason],
            filters_used={"kpi": resolved, "business_unit": business_unit, "persona": scope.display_name},
        )

    eng = get_engine(user_id=user_id)
    with eng.connect() as conn:
        fresh = _freshness(conn)
        eff_reg = region or (scope.regions[0] if not scope.is_global and len(scope.regions) == 1 else None)

        # Single-KPI MTD or Last-Month request
        if resolved != "ALL" and (period_mode in ("MTD", "LAST_MONTH") or eff_reg or entity or wave is not None or business_unit):
            meta = kpi_meta(resolved)
            comp = _same_days_mtd_counts(conn, resolved, as_of, scope, region=eff_reg, entity=entity, wave=wave, bu=business_unit)
            # Also get all-time cumulative in this scope
            w_clauses = ["KPIName = :kpi", "EventDate <= :asof"]
            p_all: dict[str, Any] = {"kpi": resolved, "asof": as_of}
            if eff_reg:
                w_clauses.append("RegionCode = :reg")
                p_all["reg"] = eff_reg
            if entity:
                w_clauses.append("AdoptionEntity = :ent")
                p_all["ent"] = entity
            if wave is not None:
                w_clauses.append("AdoptionWaveNumber = :wv")
                p_all["wv"] = int(wave)
            if business_unit:
                w_clauses.append("BusinessUnit = :bu")
                p_all["bu"] = business_unit
            agg_expr = "COUNT(DISTINCT APPUserId)" if resolved == "Employees Logging In" else "COUNT(DISTINCT DistinctEntityId)"
            cum_val = int(conn.execute(text(f"SELECT {agg_expr} FROM gold.coreadoption_event WHERE {' AND '.join(w_clauses)}"), p_all).scalar() or 0)

            scope_txt = business_unit or entity or (f"Wave {wave}" if wave is not None else None) or eff_reg or "All CORE (Global)"
            if period_mode == "LAST_MONTH":
                primary_val = comp["prev_full_val"]
                primary_lbl = comp["prev_full_label"]
                is_comp = True
            else:
                primary_val = comp["mtd_val"]
                primary_lbl = comp["mtd_label"]
                is_comp = False

            diff_eq = comp["mtd_val"] - comp["prev_mtd_val"]
            pct_eq = (diff_eq / comp["prev_mtd_val"] * 100.0) if comp["prev_mtd_val"] else 0.0
            sign_eq = "+" if diff_eq >= 0 else ""

            df = pd.DataFrame([
                {"Window": comp["mtd_label"], "KPI": resolved, "Value": comp["mtd_val"], "Period Complete": "Partial (MTD)"},
                {"Window": comp["prev_mtd_label"], "KPI": resolved, "Value": comp["prev_mtd_val"], "Period Complete": "Equivalent Prior MTD"},
                {"Window": comp["prev_full_label"], "KPI": resolved, "Value": comp["prev_full_val"], "Period Complete": "Complete Month"},
                {"Window": f"Cumulative through {as_of.isoformat()}", "KPI": resolved, "Value": cum_val, "Period Complete": "All-time in dataset"},
            ])
            warns = []
            if not is_comp:
                warns.append(f"{comp['mtd_label']} is an incomplete month in progress (as of {as_of.isoformat()}); compared fairly against {comp['prev_mtd_label']}.")
            if resolved == "Employees Logging In":
                warns.append("Distinct employee counts are non-additive across waves, entities, applications, and months.")
            return ToolPayload(
                status="ok",
                tool_name="get_core_adoption_current",
                metric_id=meta["metric_id"],
                kpi_name=resolved,
                headline=(f"**{resolved}** for **{scope_txt}** ({primary_lbl}): **{_fmt_int(primary_val)}** "
                          f"({comp['mtd_label']}: **{_fmt_int(comp['mtd_val'])}**, {sign_eq}{_fmt_int(diff_eq)} / {sign_eq}{pct_eq:.1f}% vs {comp['prev_mtd_label']} **{_fmt_int(comp['prev_mtd_val'])}**; "
                          f"{comp['prev_full_label']}: **{_fmt_int(comp['prev_full_val'])}**; All-time cumulative: **{_fmt_int(cum_val)}**)."),
                facts=[
                    f"Current MTD ({comp['mtd_label']}): {_fmt_int(comp['mtd_val'])}",
                    f"Equivalent Prior MTD ({comp['prev_mtd_label']}): {_fmt_int(comp['prev_mtd_val'])} ({sign_eq}{pct_eq:.1f}%)",
                    f"Last Complete Month ({comp['prev_full_label']}): {_fmt_int(comp['prev_full_val'])}",
                    f"Cumulative All-Time (Jun 2025 – {as_of.isoformat()}): {_fmt_int(cum_val)}",
                ],
                warnings=warns,
                df=df,
                chart_spec={
                    "kind": "bar",
                    "title": f"{resolved} — Period Comparison ({scope_txt})",
                    "x": df["Window"].iloc[:3].tolist(),
                    "y": df["Value"].iloc[:3].tolist(),
                    "y_label": meta.get("unit", "count"),
                },
                filters_used={"kpi": resolved, "scope": scope_txt, "period_mode": period_mode, "as_of": as_of.isoformat(), "persona": scope.display_name},
                period_label=primary_lbl,
                is_complete_month=is_comp,
                freshness_ts=fresh,
                lineage_id=f"goldview.v_core_adoption::{meta['metric_id']}",
                compiled_sql=comp["sql"],
            )

        # Multi-KPI executive overview (all 4 KPIs with unambiguous period labels!)
        rows_out = []
        for kpi in (ALL_KPIS if resolved == "ALL" else [resolved]):
            comp = _same_days_mtd_counts(conn, kpi, as_of, scope, region=eff_reg)
            if scope.is_global and not eff_reg:
                cur_row = conn.execute(text("""
                    SELECT KPIValue, SupportingRowCount, MappingExceptionRows
                    FROM goldview.v_core_adoption
                    WHERE RecordType = 'CURRENT' AND ReportingLevel = 'OVERALL' AND KPIName = :k
                """), {"k": kpi}).fetchone()
                cum_val = int(cur_row[0]) if cur_row else 0
                exc_val = int(cur_row[2]) if cur_row else 0
            else:
                agg_expr = "COUNT(DISTINCT APPUserId)" if kpi == "Employees Logging In" else "COUNT(DISTINCT DistinctEntityId)"
                cum_val = int(conn.execute(text(f"""
                    SELECT {agg_expr} FROM gold.coreadoption_event
                    WHERE KPIName = :k AND RegionCode = :r AND EventDate <= :asof
                """), {"k": kpi, "r": eff_reg, "asof": as_of}).scalar() or 0)
                exc_val = 0
            rows_out.append({
                "KPI Name": kpi,
                "All-Time Cumulative": cum_val,
                f"Last Complete Month (Oct 2026)": comp["prev_full_val"],
                f"This Month MTD (Nov 1–{as_of.day})": comp["mtd_val"],
                f"Prior Equiv. MTD (Oct 1–{as_of.day})": comp["prev_mtd_val"],
                "Mapping Exceptions": exc_val,
            })
        df = pd.DataFrame(rows_out)
        scope_txt = eff_reg or "All CORE (Global)"
        sql_compiled = ("SELECT RecordType, ReportingLevel, KPIName, KPIValue, SupportingRowCount, MappingExceptionRows, LoadDateTime "
                        "FROM goldview.v_core_adoption WHERE RecordType = 'CURRENT' AND ReportingLevel = 'OVERALL'")
        facts = [
            f"{r['KPI Name']}: All-time {_fmt_int(r['All-Time Cumulative'])} | Oct 2026 (complete) {_fmt_int(r['Last Complete Month (Oct 2026)'])} | Nov 2026 MTD {_fmt_int(r[f'This Month MTD (Nov 1–{as_of.day})'])}"
            for r in rows_out
        ]
        return ToolPayload(
            status="ok",
            tool_name="get_core_adoption_current",
            metric_id="all_adoption_kpis" if resolved == "ALL" else kpi_meta(resolved)["metric_id"],
            kpi_name=resolved,
            headline=f"**CORE Pulse Adoption Summary** for **{scope_txt}** as of **{as_of.isoformat()}** (all-time cumulative, last complete month Oct 2026, and partial Nov 2026 MTD):",
            facts=facts,
            warnings=[
                f"Nov 2026 is a partial month in progress ({as_of.day} days elapsed); MTD figures are compared fairly against Oct 1–{as_of.day}.",
                "Employees Logging In is strictly non-additive across months, waves, and entities.",
            ],
            df=df,
            chart_spec={
                "kind": "grouped_bar",
                "title": f"CORE Adoption — Oct 2026 (Complete) vs Nov 2026 MTD ({scope_txt})",
                "x": df["KPI Name"].tolist(),
                "series": [
                    {"name": "Oct 2026 (Complete)", "values": df["Last Complete Month (Oct 2026)"].tolist()},
                    {"name": f"Nov 2026 MTD (1–{as_of.day})", "values": df[f"This Month MTD (Nov 1–{as_of.day})"].tolist()},
                ],
                "y_label": "Count",
            },
            filters_used={"kpi": resolved, "scope": scope_txt, "as_of": as_of.isoformat(), "persona": scope.display_name},
            period_label=f"As of {as_of.isoformat()}",
            is_complete_month=False,
            freshness_ts=fresh,
            lineage_id="goldview.v_core_adoption::CURRENT_OVERALL",
            compiled_sql=sql_compiled,
        )


# ---------------------------------------------------------------------------
# 2. get_core_adoption_monthly
# ---------------------------------------------------------------------------
def get_core_adoption_monthly(kpi_name: str, months_back: int = 12,
                              start_month: str | None = None, end_month: str | None = None,
                              reporting_level: str = "OVERALL",
                              entity: str | None = None, wave: int | None = None,
                              business_unit: str | None = None, region: str | None = None,
                              user_id: str = "global_program_lead",
                              as_of: date | None = None) -> ToolPayload:
    as_of = as_of or as_of_date()
    scope = get_user_scope(user_id)
    refusal = check_scope_allowed(scope, region=region, entity=entity, wave=wave, business_unit=business_unit)
    if refusal:
        return ToolPayload(status="refusal", tool_name="get_core_adoption_monthly", headline=refusal)

    resolved = resolve_kpi_name(kpi_name) or "Employees Logging In"
    meta = kpi_meta(resolved)
    eff_reg = region or (scope.regions[0] if not scope.is_global and len(scope.regions) == 1 else None)

    if business_unit:
        reporting_level = "BUSINESS_UNIT"
    elif entity:
        reporting_level = "ENTITY"
    elif wave is not None:
        reporting_level = "WAVE"

    if reporting_level == "BUSINESS_UNIT" and resolved not in BU_SUPPORTED_KPIS:
        reason = meta["unsupported_levels"]["BUSINESS_UNIT"]
        return ToolPayload(
            status="unsupported",
            tool_name="get_core_adoption_monthly",
            metric_id=meta["metric_id"],
            kpi_name=resolved,
            headline=f"**{resolved}** monthly trend is unavailable at the Business Unit level.",
            facts=[reason],
            warnings=[reason],
            filters_used={"kpi": resolved, "reporting_level": "BUSINESS_UNIT", "persona": scope.display_name},
        )

    end_dt = date.fromisoformat(end_month) if end_month else date(as_of.year, as_of.month, 1)
    if start_month:
        start_dt = date.fromisoformat(start_month)
    else:
        total_m = end_dt.year * 12 + (end_dt.month - 1) - max(1, months_back - 1)
        sy, sm = divmod(total_m, 12)
        start_dt = max(date(2025, 6, 1), date(sy, sm + 1, 1))

    eng = get_engine(user_id=user_id)
    with eng.connect() as conn:
        fresh = _freshness(conn)
        # If filtered by Region (without single entity/wave/BU), compute directly from gold.coreadoption_event by month
        if eff_reg and reporting_level == "OVERALL":
            agg_expr = "COUNT(DISTINCT APPUserId)" if resolved == "Employees Logging In" else "COUNT(DISTINCT DistinctEntityId)"
            sql_q = f"""
                SELECT d.PeriodDate, d.YearMonth, d.IsCompleteMonth,
                       COALESCE(e.val, 0) AS KPIValue
                FROM goldview.v_dim_date d
                LEFT JOIN (
                    SELECT EventMonth, {agg_expr} AS val
                    FROM gold.coreadoption_event
                    WHERE KPIName = :k AND RegionCode = :reg AND EventDate <= :asof
                    GROUP BY EventMonth
                ) e ON d.PeriodDate = e.EventMonth
                WHERE d.PeriodDate >= :s AND d.PeriodDate <= :e
                ORDER BY d.PeriodDate
            """
            df_raw = pd.read_sql(text(sql_q), conn, params={"k": resolved, "reg": eff_reg, "asof": as_of, "s": start_dt, "e": end_dt})
            scope_txt = f"Region {eff_reg}"
        else:
            clauses = ["RecordType = 'MONTHLY'", "ReportingLevel = :lvl", "KPIName = :k",
                       "PeriodDate >= :s", "PeriodDate <= :e"]
            params: dict[str, Any] = {"lvl": reporting_level, "k": resolved, "s": start_dt, "e": end_dt}
            if wave is not None:
                clauses.append("AdoptionWaveNumber = :wv")
                params["wv"] = int(wave)
            if entity:
                clauses.append("AdoptionEntity = :ent")
                params["ent"] = entity
            if business_unit:
                clauses.append("BusinessUnit = :bu")
                params["bu"] = business_unit
            sql_q = f"""
                SELECT PeriodDate, YearMonth, IsCompleteMonth, AdoptionWaveLabel, AdoptionEntity, BusinessUnit, KPIValue
                FROM goldview.v_core_adoption
                WHERE {' AND '.join(clauses)}
                ORDER BY PeriodDate
            """
            df_raw = pd.read_sql(text(sql_q), conn, params=params)
            scope_txt = business_unit or entity or (f"Wave {wave}" if wave is not None else "All CORE (Global)")

    if df_raw.empty:
        return ToolPayload(status="empty", tool_name="get_core_adoption_monthly", kpi_name=resolved,
                           headline=f"No monthly records found for **{resolved}** in **{scope_txt}**.")

    df = df_raw[["YearMonth", "KPIValue", "IsCompleteMonth"]].copy()
    df["Status"] = df["IsCompleteMonth"].map(lambda c: "Complete" if int(c) == 1 else "Partial MTD")
    df["MoM Change"] = df["KPIValue"].diff().fillna(0).astype(int)
    df["MoM %"] = (df["KPIValue"].pct_change() * 100.0).round(1)

    # Identify fastest-growing complete month
    comp_df = df[df["IsCompleteMonth"] == 1].copy()
    fastest_note = ""
    if len(comp_df) >= 2:
        comp_df["delta"] = comp_df["KPIValue"].diff()
        best_idx = comp_df["delta"].idxmax()
        if pd.notna(best_idx) and pd.notna(comp_df.loc[best_idx, "delta"]):
            bm = comp_df.loc[best_idx, "YearMonth"]
            bd = int(comp_df.loc[best_idx, "delta"])
            bv = int(comp_df.loc[best_idx, "KPIValue"])
            fastest_note = f"Fastest complete-month growth: **{bm}** (+{_fmt_int(bd)} MoM to {_fmt_int(bv)})."

    latest_comp = comp_df.iloc[-1] if not comp_df.empty else df.iloc[-1]
    prev_comp = comp_df.iloc[-2] if len(comp_df) >= 2 else None
    mom_txt = ""
    if prev_comp is not None:
        d_c = int(latest_comp["KPIValue"]) - int(prev_comp["KPIValue"])
        s_c = "+" if d_c >= 0 else ""
        mom_txt = f" ({s_c}{_fmt_int(d_c)} vs {prev_comp['YearMonth']} {_fmt_int(prev_comp['KPIValue'])})"

    partial_row = df[df["IsCompleteMonth"] == 0]
    partial_txt = ""
    warns = []
    if not partial_row.empty:
        pr = partial_row.iloc[-1]
        partial_txt = f"; partial **{pr['YearMonth']} MTD**: **{_fmt_int(pr['KPIValue'])}**"
        warns.append(f"{pr['YearMonth']} is an incomplete partial month (as of {as_of.isoformat()}) and is excluded from complete-month peak/MoM rankings.")
    if resolved == "Employees Logging In":
        warns.append("Monthly Employees Logging In counts are distinct per month—do not sum monthly bars to compute a multi-month unique user total.")

    disp_df = df[["YearMonth", "KPIValue", "MoM Change", "Status"]].rename(columns={"YearMonth": "Month", "KPIValue": resolved})
    facts = [
        f"Range: {df['YearMonth'].iloc[0]} to {df['YearMonth'].iloc[-1]} ({len(df)} months)",
        f"Latest complete month ({latest_comp['YearMonth']}): {_fmt_int(latest_comp['KPIValue'])}{mom_txt}",
    ]
    if fastest_note:
        facts.append(fastest_note.replace("**", ""))
    if not partial_row.empty:
        facts.append(f"Current partial month ({partial_row.iloc[-1]['YearMonth']} MTD): {_fmt_int(partial_row.iloc[-1]['KPIValue'])}")

    return ToolPayload(
        status="ok",
        tool_name="get_core_adoption_monthly",
        metric_id=meta["metric_id"],
        kpi_name=resolved,
        headline=(f"**{resolved}** monthly trend for **{scope_txt}** ({df['YearMonth'].iloc[0]} – {df['YearMonth'].iloc[-1]}): "
                  f"latest complete month **{latest_comp['YearMonth']}** = **{_fmt_int(latest_comp['KPIValue'])}**{mom_txt}{partial_txt}. "
                  f"{fastest_note}").strip(),
        facts=facts,
        warnings=warns,
        df=disp_df,
        chart_spec={
            "kind": "line",
            "title": f"{resolved} — Monthly Trend ({scope_txt})",
            "x": df["YearMonth"].tolist(),
            "y": df["KPIValue"].tolist(),
            "partial_flags": (df["IsCompleteMonth"] == 0).tolist(),
            "y_label": meta.get("unit", "count"),
        },
        filters_used={"kpi": resolved, "scope": scope_txt, "start_month": str(start_dt), "end_month": str(end_dt), "persona": scope.display_name},
        period_label=f"{df['YearMonth'].iloc[0]} – {df['YearMonth'].iloc[-1]}",
        is_complete_month=partial_row.empty,
        freshness_ts=fresh,
        lineage_id=f"goldview.v_core_adoption::{meta['metric_id']}::MONTHLY",
        compiled_sql=" ".join(sql_q.split()),
    )


# ---------------------------------------------------------------------------
# 3 & 4 & 5. Breakdown by Wave / Entity / Business Unit
# ---------------------------------------------------------------------------
def _breakdown(level: str, tool_name: str, kpi_name: str, period: str = "CURRENT",
               region: str | None = None, wave: int | None = None, entity: str | None = None,
               user_id: str = "global_program_lead", as_of: date | None = None) -> ToolPayload:
    as_of = as_of or as_of_date()
    scope = get_user_scope(user_id)
    refusal = check_scope_allowed(scope, region=region, entity=entity, wave=wave)
    if refusal:
        return ToolPayload(status="refusal", tool_name=tool_name, headline=refusal)

    resolved = resolve_kpi_name(kpi_name) or "Employees Logging In"
    meta = kpi_meta(resolved)
    if level == "BUSINESS_UNIT" and resolved not in BU_SUPPORTED_KPIS:
        reason = meta["unsupported_levels"]["BUSINESS_UNIT"]
        return ToolPayload(
            status="unsupported",
            tool_name=tool_name,
            metric_id=meta["metric_id"],
            kpi_name=resolved,
            headline=f"**{resolved}** is unavailable by **Business Unit**.",
            facts=[reason, "Governed breakdowns available for this KPI: **Rollout Wave** (`WAVE`) and **Adoption Entity** (`ENTITY`)."],
            warnings=[reason],
            filters_used={"kpi": resolved, "reporting_level": "BUSINESS_UNIT", "persona": scope.display_name},
        )

    cur_m, prev_m = _month_bounds(as_of)
    p_upper = (period or "CURRENT").upper()
    if p_upper in ("MTD", "THIS_MONTH", "CURRENT_MONTH"):
        rec_type, p_date, p_lbl, is_comp = "MONTHLY", cur_m, f"{cur_m.strftime('%b %Y')} MTD (partial)", False
    elif p_upper in ("LAST_MONTH", "PRIOR_MONTH", "OCT_2026"):
        rec_type, p_date, p_lbl, is_comp = "MONTHLY", prev_m, f"{prev_m.strftime('%b %Y')} (complete month)", True
    elif len(period or "") == 7 and "-" in (period or ""):
        p_date = date.fromisoformat(f"{period}-01")
        rec_type = "MONTHLY"
        is_comp = p_date < cur_m
        p_lbl = f"{p_date.strftime('%b %Y')}" + ("" if is_comp else " MTD (partial)")
    else:
        rec_type, p_date, p_lbl, is_comp = "CURRENT", cur_m, f"Cumulative through {as_of.isoformat()}", True

    eng = get_engine(user_id=user_id)
    with eng.connect() as conn:
        fresh = _freshness(conn)
        clauses = ["RecordType = :rt", "ReportingLevel = :lvl", "KPIName = :k"]
        params: dict[str, Any] = {"rt": rec_type, "lvl": level, "k": resolved}
        if rec_type == "MONTHLY":
            clauses.append("PeriodDate = :pd")
            params["pd"] = p_date
        if not scope.is_global:
            if level == "WAVE":
                w_ph = ", ".join(f":sw{i}" for i in range(len(scope.waves)))
                clauses.append(f"AdoptionWaveNumber IN ({w_ph})")
                for i, wv in enumerate(scope.waves):
                    params[f"sw{i}"] = wv
            else:
                r_ph = ", ".join(f":sr{i}" for i in range(len(scope.regions)))
                clauses.append(f"RegionCode IN ({r_ph})")
                for i, rc in enumerate(scope.regions):
                    params[f"sr{i}"] = rc
        if region and level != "WAVE":
            clauses.append("RegionCode = :reg")
            params["reg"] = region
        if wave is not None:
            clauses.append("AdoptionWaveNumber = :wv")
            params["wv"] = int(wave)
        if entity and level == "BUSINESS_UNIT":
            clauses.append("AdoptionEntity = :ent")
            params["ent"] = entity

        sql_q = f"""
            SELECT AdoptionWaveNumber, AdoptionWaveLabel, AdoptionEntity, BusinessUnit, BusinessUnitName,
                   RegionCode, CountryCode, KPIValue, SupportingRowCount
            FROM goldview.v_core_adoption
            WHERE {' AND '.join(clauses)}
            ORDER BY KPIValue DESC
        """
        df_raw = pd.read_sql(text(sql_q), conn, params=params)

        # Fetch true deduplicated OVERALL total when global & unfiltered so we explicitly show non-additivity!
        dedup_total = None
        if resolved == "Employees Logging In" and scope.is_global and not region and wave is None:
            ov_clauses = ["RecordType = :rt", "ReportingLevel = 'OVERALL'", "KPIName = :k"]
            ov_p: dict[str, Any] = {"rt": rec_type, "k": resolved}
            if rec_type == "MONTHLY":
                ov_clauses.append("PeriodDate = :pd")
                ov_p["pd"] = p_date
            dedup_total = conn.execute(
                text(f"SELECT KPIValue FROM goldview.v_core_adoption WHERE {' AND '.join(ov_clauses)}"), ov_p
            ).scalar()

    if df_raw.empty:
        return ToolPayload(status="empty", tool_name=tool_name, kpi_name=resolved,
                           headline=f"No {level.lower()} rows available for **{resolved}** ({p_lbl}).")

    if level == "WAVE":
        label_col = "AdoptionWaveLabel"
        disp = df_raw[["AdoptionWaveLabel", "KPIValue", "SupportingRowCount"]].rename(
            columns={"AdoptionWaveLabel": "Rollout Wave", "KPIValue": resolved, "SupportingRowCount": "Supporting Events"}
        )
        dim_title = "Rollout Wave"
    elif level == "ENTITY":
        label_col = "AdoptionEntity"
        disp = df_raw[["AdoptionEntity", "AdoptionWaveLabel", "RegionCode", "KPIValue"]].rename(
            columns={"AdoptionEntity": "Adoption Entity", "AdoptionWaveLabel": "Wave", "RegionCode": "Region", "KPIValue": resolved}
        )
        dim_title = "Adoption Entity"
    else:
        label_col = "BusinessUnit"
        disp = df_raw[["BusinessUnit", "BusinessUnitName", "AdoptionEntity", "RegionCode", "CountryCode", "KPIValue"]].rename(
            columns={"BusinessUnit": "BU Code", "BusinessUnitName": "Business Unit", "AdoptionEntity": "Entity",
                     "RegionCode": "Region", "CountryCode": "Country", "KPIValue": resolved}
        )
        dim_title = "Business Unit"

    top_row = df_raw.iloc[0]
    top_name = str(top_row[label_col])
    top_val = int(top_row["KPIValue"])
    naive_sum = int(df_raw["KPIValue"].sum())

    warns = []
    non_add_note = ""
    if resolved == "Employees Logging In":
        if dedup_total is not None and int(dedup_total) != naive_sum:
            overlap = naive_sum - int(dedup_total)
            non_add_note = (f" True deduplicated overall total is **{_fmt_int(dedup_total)}** "
                            f"(not the naive sum {_fmt_int(naive_sum)}, because **{_fmt_int(overlap)}** employees logged into applications across multiple {dim_title.lower()}s).")
        warns.append(f"Non-additive metric: do not add {dim_title} employee rows together; employees active across multiple {dim_title.lower()}s are counted once in each {dim_title.lower()} and deduplicated at OVERALL.")
    if not is_comp:
        warns.append(f"{p_lbl} is an incomplete month in progress as of {as_of.isoformat()}.")

    facts = [f"{r[label_col]}: {_fmt_int(r['KPIValue'])}" for _, r in df_raw.iterrows()]
    if dedup_total is not None:
        facts.append(f"True deduplicated OVERALL {resolved}: {_fmt_int(dedup_total)} (naive sum across {dim_title.lower()}s = {_fmt_int(naive_sum)})")

    return ToolPayload(
        status="ok",
        tool_name=tool_name,
        metric_id=meta["metric_id"],
        kpi_name=resolved,
        headline=(f"**{resolved}** by **{dim_title}** ({p_lbl}): highest is **{top_name}** at **{_fmt_int(top_val)}** "
                  f"across {len(df_raw)} {dim_title.lower()}s.{non_add_note}"),
        facts=facts,
        warnings=warns,
        df=disp,
        chart_spec={
            "kind": "hbar",
            "title": f"{resolved} by {dim_title} ({p_lbl})",
            "x": df_raw["KPIValue"].tolist(),
            "y": df_raw[label_col].astype(str).tolist(),
            "x_label": meta.get("unit", "count"),
        },
        filters_used={"kpi": resolved, "reporting_level": level, "period": p_lbl, "region": region, "wave": wave, "persona": scope.display_name},
        period_label=p_lbl,
        is_complete_month=is_comp,
        freshness_ts=fresh,
        lineage_id=f"goldview.v_core_adoption::{meta['metric_id']}::{level}",
        compiled_sql=" ".join(sql_q.split()),
    )


def get_core_adoption_by_wave(kpi_name: str, period: str = "CURRENT", user_id: str = "global_program_lead",
                              as_of: date | None = None) -> ToolPayload:
    return _breakdown("WAVE", "get_core_adoption_by_wave", kpi_name, period=period, user_id=user_id, as_of=as_of)


def get_core_adoption_by_entity(kpi_name: str, period: str = "CURRENT", region: str | None = None,
                                wave: int | None = None, user_id: str = "global_program_lead",
                                as_of: date | None = None) -> ToolPayload:
    return _breakdown("ENTITY", "get_core_adoption_by_entity", kpi_name, period=period, region=region,
                      wave=wave, user_id=user_id, as_of=as_of)


def get_core_adoption_by_business_unit(kpi_name: str, period: str = "CURRENT", region: str | None = None,
                                       entity: str | None = None, wave: int | None = None,
                                       user_id: str = "global_program_lead",
                                       as_of: date | None = None) -> ToolPayload:
    return _breakdown("BUSINESS_UNIT", "get_core_adoption_by_business_unit", kpi_name, period=period,
                      region=region, entity=entity, wave=wave, user_id=user_id, as_of=as_of)


# ---------------------------------------------------------------------------
# 6. get_core_rollout_status (SIMULATED EXTENSION)
# ---------------------------------------------------------------------------
def get_core_rollout_status(module: str | None = None, region: str | None = None,
                            entity: str | None = None, wave: int | None = None,
                            rollout_status: str | None = None, zero_activity_only: bool = False,
                            user_id: str = "global_program_lead",
                            as_of: date | None = None) -> ToolPayload:
    as_of = as_of or as_of_date()
    scope = get_user_scope(user_id)
    refusal = check_scope_allowed(scope, region=region, entity=entity, wave=wave)
    if refusal:
        return ToolPayload(status="refusal", tool_name="get_core_rollout_status", headline=refusal)

    eng = get_engine(user_id=user_id)
    with eng.connect() as conn:
        fresh = _freshness(conn)
        clauses = ["1=1"]
        params: dict[str, Any] = {}
        if not scope.is_global:
            r_ph = ", ".join(f":sr{i}" for i in range(len(scope.regions)))
            clauses.append(f"r.RegionCode IN ({r_ph})")
            for i, rc in enumerate(scope.regions):
                params[f"sr{i}"] = rc
        if region:
            clauses.append("r.RegionCode = :reg")
            params["reg"] = region
        if entity:
            clauses.append("r.AdoptionEntity = :ent")
            params["ent"] = entity
        if wave is not None:
            clauses.append("r.AdoptionWaveNumber = :wv")
            params["wv"] = int(wave)
        if rollout_status:
            clauses.append("r.RolloutStatus = :st")
            params["st"] = rollout_status.upper()
        if module:
            clauses.append("(r.ModuleCode = :mod OR LOWER(m.ModuleName) LIKE :mod_like)")
            params["mod"] = module.upper()
            params["mod_like"] = f"%{module.lower()}%"

        sql_q = f"""
            SELECT r.RolloutId, r.AdoptionWaveNumber, r.RegionCode, r.CountryCode, r.AdoptionEntity,
                   r.BusinessUnit, r.ModuleCode, m.ModuleName, m.ActivityInstrumentation,
                   r.RolloutStatus, r.PlannedGoLiveDate, r.ActualGoLiveDate, r.EligiblePopulation
            FROM reference.rollout_registry r
            INNER JOIN reference.module_catalog m ON r.ModuleCode = m.ModuleCode
            WHERE {' AND '.join(clauses)}
            ORDER BY r.AdoptionWaveNumber, r.AdoptionEntity, r.ModuleCode
        """
        df_reg = pd.read_sql(text(sql_q), conn, params=params)
        df_ev = pd.read_sql(text("""
            SELECT EventType, AdoptionEntity, BusinessUnit,
                   COUNT(DISTINCT DistinctEntityId) AS distinct_cnt,
                   COUNT(DISTINCT APPUserId) AS user_cnt
            FROM gold.coreadoption_event
            WHERE EventDate <= :asof
            GROUP BY EventType, AdoptionEntity, BusinessUnit
        """), conn, params={"asof": as_of})

    if df_reg.empty:
        return ToolPayload(status="empty", tool_name="get_core_rollout_status",
                           headline="No rollout registry entries matched those filters.")

    mod_to_ev = {
        "CORE_LOGIN": "LOGIN",
        "PROJECTS": "PROJECT_CREATED",
        "TIMECARDS": "TIMECARD_SUBMITTED",
        "EXPENSES": "EXPENSE_SUBMISSION",
    }
    obs_list, state_list, rate_list = [], [], []
    for _, r in df_reg.iterrows():
        inst = r["ActivityInstrumentation"]
        mcode = r["ModuleCode"]
        if inst != "INSTRUMENTED":
            obs_list.append(None)
            state_list.append("Not instrumented in pilot")
            rate_list.append("Rate unavailable — module not instrumented")
            continue
        ev_type = mod_to_ev[mcode]
        sub = df_ev[(df_ev["EventType"] == ev_type) & (df_ev["AdoptionEntity"] == r["AdoptionEntity"])]
        if pd.notna(r["BusinessUnit"]) and r["BusinessUnit"] and mcode in ("PROJECTS", "EXPENSES"):
            sub = sub[sub["BusinessUnit"] == r["BusinessUnit"]]
        cnt = int(sub["user_cnt"].sum() if mcode == "CORE_LOGIN" else sub["distinct_cnt"].sum())
        obs_list.append(cnt)
        if cnt > 0:
            state_list.append("Observed activity")
        elif r["RolloutStatus"] == "LIVE":
            state_list.append("LIVE — ZERO observed events")
        else:
            state_list.append("No activity yet (pre-live)")
        # Rate rule (§2): only CORE_LOGIN has a compatible user numerator vs EligiblePopulation denominator!
        if mcode == "CORE_LOGIN" and pd.notna(r["EligiblePopulation"]) and int(r["EligiblePopulation"]) > 0:
            pct = min(100.0, cnt / int(r["EligiblePopulation"]) * 100.0)
            rate_list.append(f"{pct:.1f}% ({cnt}/{int(r['EligiblePopulation'])} eligible)")
        else:
            rate_list.append("Rate unavailable — eligible population or user linkage not supported")

    df_reg["Observed Count"] = obs_list
    df_reg["Activity Evidence"] = state_list
    df_reg["Adoption Rate"] = rate_list

    if zero_activity_only:
        df_reg = df_reg[(df_reg["RolloutStatus"] == "LIVE") & (df_reg["ActivityEvidence" if "ActivityEvidence" in df_reg else "Activity Evidence"] == "LIVE — ZERO observed events")]

    status_counts = df_reg["RolloutStatus"].value_counts().to_dict()
    zero_live = df_reg[df_reg["Activity Evidence"] == "LIVE — ZERO observed events"]
    uninst_live = df_reg[(df_reg["RolloutStatus"] == "LIVE") & (df_reg["ActivityInstrumentation"] != "INSTRUMENTED")]

    disp = df_reg[["RolloutId", "AdoptionWaveNumber", "RegionCode", "AdoptionEntity", "BusinessUnit",
                   "ModuleName", "RolloutStatus", "ActualGoLiveDate", "ActivityInstrumentation",
                   "Observed Count", "Activity Evidence"]].rename(columns={
                       "AdoptionWaveNumber": "Wave", "RegionCode": "Region", "AdoptionEntity": "Entity",
                       "BusinessUnit": "BU", "ModuleName": "Module", "RolloutStatus": "Status",
                       "ActualGoLiveDate": "Actual Go-Live", "ActivityInstrumentation": "Instrumentation",
                   })

    st_summary = ", ".join(f"**{k}**: {v}" for k, v in status_counts.items())
    zero_note = ""
    if not zero_live.empty:
        z_items = ", ".join(f"`{row['RolloutId']}` ({row['AdoptionEntity']} · {row['ModuleName']}, live {row['ActualGoLiveDate']})"
                            for _, row in zero_live.iterrows())
        zero_note = f" Actionable gap: **{len(zero_live)}** instrumented `LIVE` rollout(s) show **zero observed events**: {z_items}."

    chart_counts = df_reg.groupby("RolloutStatus").size().reindex(["LIVE", "ONBOARDING", "PLANNED", "PAUSED", "RETIRED"]).dropna()
    return ToolPayload(
        status="ok",
        tool_name="get_core_rollout_status",
        metric_id="rollout_registry_extension",
        kpi_name="Rollout & Module Status",
        headline=f"**CORE Rollout & Module Registry** (`SIMULATED EXTENSION`, {len(df_reg)} module deployments in scope — {st_summary}).{zero_note}",
        facts=[
            f"Rollout status breakdown: {st_summary.replace('**', '')}",
            f"LIVE with observed instrumented events: {int((df_reg['Activity Evidence'] == 'Observed activity').sum())}",
            f"LIVE instrumented with ZERO observed events: {len(zero_live)}",
            f"LIVE modules without event instrumentation (status-only): {len(uninst_live)}",
        ],
        warnings=[
            "SIMULATED EXTENSION: `reference.rollout_registry` and `reference.module_catalog` are pilot extensions; application logins are never equated to specific module visits.",
            "Transaction counts (Contracts, Timecards, Expenses) are never relabeled as % user adoption.",
        ],
        df=disp,
        chart_spec={
            "kind": "bar",
            "title": "Rollout Deployments by Status",
            "x": [str(x) for x in chart_counts.index.tolist()],
            "y": [int(y) for y in chart_counts.values.tolist()],
            "y_label": "Module deployments",
        },
        filters_used={"module": module, "region": region, "entity": entity, "wave": wave, "status": rollout_status, "persona": scope.display_name},
        period_label=f"Registry as of {as_of.isoformat()}",
        is_complete_month=True,
        freshness_ts=fresh,
        lineage_id="reference.rollout_registry+gold.coreadoption_event",
        compiled_sql=" ".join(sql_q.split()),
    )


# ---------------------------------------------------------------------------
# 7. get_core_user_engagement (distinct-at-query-level governed derivative)
# ---------------------------------------------------------------------------
def get_core_user_engagement(date_window: str = "MTD", application: str | None = None,
                             entity: str | None = None, wave: int | None = None,
                             region: str | None = None, user_id: str = "global_program_lead",
                             as_of: date | None = None) -> ToolPayload:
    as_of = as_of or as_of_date()
    scope = get_user_scope(user_id)
    refusal = check_scope_allowed(scope, region=region, entity=entity, wave=wave)
    if refusal:
        return ToolPayload(status="refusal", tool_name="get_core_user_engagement", headline=refusal)

    cur_m, prev_m = _month_bounds(as_of)
    win = (date_window or "MTD").upper()
    if win in ("LAST_MONTH", "PRIOR_MONTH"):
        d1 = prev_m
        d2 = date(prev_m.year, prev_m.month, calendar.monthrange(prev_m.year, prev_m.month)[1])
        w_lbl = f"{prev_m.strftime('%b %Y')} (complete month)"
    elif win in ("LAST_30D", "30D"):
        d1 = pd.Timestamp(as_of) - pd.Timedelta(days=29)
        d1 = d1.date()
        d2 = as_of
        w_lbl = f"Rolling 30 days ({d1.isoformat()} – {d2.isoformat()})"
    elif win in ("ALL_TIME", "CUMULATIVE"):
        d1, d2 = date(2025, 6, 1), as_of
        w_lbl = f"All-time ({d1.isoformat()} – {d2.isoformat()})"
    else:
        d1, d2 = cur_m, as_of
        w_lbl = f"{cur_m.strftime('%b %Y')} MTD ({d1.isoformat()} – {d2.isoformat()}, partial)"

    eng = get_engine(user_id=user_id)
    with eng.connect() as conn:
        fresh = _freshness(conn)
        clauses = ["ActivityDate >= :d1", "ActivityDate <= :d2"]
        params: dict[str, Any] = {"d1": d1, "d2": d2}
        if not scope.is_global:
            r_ph = ", ".join(f":sr{i}" for i in range(len(scope.regions)))
            clauses.append(f"RegionCode IN ({r_ph})")
            for i, rc in enumerate(scope.regions):
                params[f"sr{i}"] = rc
        if region:
            clauses.append("RegionCode = :reg")
            params["reg"] = region
        if entity:
            clauses.append("AdoptionEntity = :ent")
            params["ent"] = entity
        if wave is not None:
            clauses.append("AdoptionWaveNumber = :wv")
            params["wv"] = int(wave)
        if application:
            clauses.append("ApplicationCode = :app")
            params["app"] = application.upper()

        w_sql = " AND ".join(clauses)
        total_distinct = int(conn.execute(
            text(f"SELECT COUNT(DISTINCT APPUserId) FROM gold.coreadoption_user_activity WHERE {w_sql}"), params
        ).scalar() or 0)
        total_events = int(conn.execute(
            text(f"SELECT COALESCE(SUM(LoginEventCount), 0) FROM gold.coreadoption_user_activity WHERE {w_sql}"), params
        ).scalar() or 0)
        df_apps = pd.read_sql(text(f"""
            SELECT ApplicationCode, AdoptionEntity, AdoptionWaveNumber, RegionCode,
                   COUNT(DISTINCT APPUserId) AS UniqueEmployees,
                   SUM(LoginEventCount) AS LoginEvents,
                   COUNT(DISTINCT ActivityDate) AS ActiveDays
            FROM gold.coreadoption_user_activity
            WHERE {w_sql}
            GROUP BY ApplicationCode, AdoptionEntity, AdoptionWaveNumber, RegionCode
            ORDER BY UniqueEmployees DESC
        """), conn, params=params)

    naive_app_sum = int(df_apps["UniqueEmployees"].sum()) if not df_apps.empty else 0
    return ToolPayload(
        status="ok",
        tool_name="get_core_user_engagement",
        metric_id="employees_logging_in",
        kpi_name="Employees Logging In",
        headline=(f"**CORE User Engagement** ({w_lbl}): **{_fmt_int(total_distinct)}** unique non-service employees "
                  f"generated **{_fmt_int(total_events)}** login events across **{len(df_apps)}** governed application(s)."),
        facts=[
            f"Deduplicated unique employees ({w_lbl}): {_fmt_int(total_distinct)}",
            f"Total login events ({w_lbl}): {_fmt_int(total_events)} (avg {total_events / max(1, total_distinct):.1f} logins per active user)",
            f"Sum across application rows: {_fmt_int(naive_app_sum)} (cross-app users deduplicated in headline total)",
        ],
        warnings=[
            "Computed directly from `gold.coreadoption_user_activity` (`IsServiceAccount = 0`, `CONFIRMED` apps only); never sum application rows to derive unique users."
        ],
        df=df_apps.rename(columns={"ApplicationCode": "Application", "AdoptionEntity": "Entity",
                                   "AdoptionWaveNumber": "Wave", "RegionCode": "Region",
                                   "UniqueEmployees": "Unique Employees", "LoginEvents": "Login Events",
                                   "ActiveDays": "Active Days"}),
        chart_spec={
            "kind": "hbar",
            "title": f"Unique Active Employees by CORE Application ({w_lbl})",
            "x": df_apps["UniqueEmployees"].tolist(),
            "y": df_apps["ApplicationCode"].tolist(),
            "x_label": "Unique employees",
        } if not df_apps.empty else {},
        filters_used={"window": w_lbl, "application": application, "entity": entity, "wave": wave, "region": region, "persona": scope.display_name},
        period_label=w_lbl,
        is_complete_month="partial" not in w_lbl,
        freshness_ts=fresh,
        lineage_id="gold.coreadoption_user_activity::ENGAGEMENT",
        compiled_sql=f"SELECT COUNT(DISTINCT APPUserId) FROM gold.coreadoption_user_activity WHERE {w_sql}",
    )


# ---------------------------------------------------------------------------
# 8, 9, 10. Metric Definition, Pipeline Status & Metric Lineage
# ---------------------------------------------------------------------------
def get_core_metric_definition(kpi_name: str = "ALL") -> ToolPayload:
    resolved = resolve_kpi_name(kpi_name) or "ALL"
    cat = semantic_catalog()["metrics"]
    rows = []
    for mid, spec in cat.items():
        if resolved != "ALL" and spec["kpi_name"] != resolved:
            continue
        rows.append({
            "KPI Name": spec["kpi_name"],
            "Counting Rule": spec["counting_rule"],
            "Event Timestamp": spec["event_timestamp"],
            "Additivity": spec["additivity"],
            "Supported Levels": ", ".join(spec["supported_levels"]),
            "Unsupported / Limitations": "; ".join(f"{k}: {v}" for k, v in spec.get("unsupported_levels", {}).items()) or "All standard levels supported",
        })
    df = pd.DataFrame(rows)
    if resolved != "ALL" and rows:
        spec = kpi_meta(resolved)
        headline = (f"**{resolved}** — `{spec['counting_rule']}` bucketed by `{spec['event_timestamp']}` "
                    f"({spec['distinct_count_behavior']})")
        facts = [
            f"Definition: {spec['plain_definition']}",
            f"Exclusions: {spec['exclusions']}",
            f"Additivity: {spec['distinct_count_behavior']}",
            f"Supported grains: {', '.join(spec['supported_levels'])}",
        ]
        for uk, uv in spec.get("unsupported_levels", {}).items():
            facts.append(f"Limitation ({uk}): {uv}")
    else:
        headline = "**CORE Pulse Governed KPI Dictionary** — 4 authoritative adoption metrics published in `goldview.v_core_adoption`:"
        facts = [f"{r['KPI Name']}: {r['Counting Rule']} by {r['Event Timestamp']} ({r['Additivity']})" for r in rows]

    return ToolPayload(
        status="ok",
        tool_name="get_core_metric_definition",
        metric_id="kpi_dictionary",
        kpi_name=resolved,
        headline=headline,
        facts=facts,
        warnings=["Employees Logging In is non-additive: adding counts across two entities or waves double-counts employees who log into both."],
        df=df,
        filters_used={"kpi": resolved},
        period_label="Semantic Catalog v1.0",
        lineage_id="app/semantic/metrics.yaml",
        compiled_sql="-- Metadata read from governed semantic catalog (app/semantic/metrics.yaml)",
    )


def get_core_pipeline_status() -> ToolPayload:
    eng = get_engine()
    with eng.connect() as conn:
        run_df = pd.read_sql(text("""
            SELECT PipelineRunId, PipelineName, AsOfDate, RunStatus, StartedDateTime, CompletedDateTime
            FROM dataops.pipeline_run ORDER BY PipelineRunId DESC
        """), conn)
        wm_df = pd.read_sql(text("SELECT * FROM dataops.watermark"), conn)
        latest_run = int(run_df["PipelineRunId"].iloc[0]) if not run_df.empty else 0
        qm_df = pd.read_sql(text("""
            SELECT CheckName, CheckCategory, CheckStatus, MetricValue, ExpectedValue, Details
            FROM dataops.data_quality_metric
            WHERE PipelineRunId = :r ORDER BY QualityMetricId
        """), conn, params={"r": latest_run})

        layer_counts = []
        for layer, tbl in [
            ("1. Source Sim", "source_sim.project"),
            ("1. Source Sim", "source_sim.application_log"),
            ("1. Source Sim", "source_sim.timecard"),
            ("1. Source Sim", "source_sim.expense_report"),
            ("2. Bronze", "bronze.core_application_log"),
            ("3. Silver", "silver.organization"),
            ("3. Silver", "silver.login_activity"),
            ("4. Gold", "gold.coreadoption_event"),
            ("5. Certified View", "goldview.v_core_adoption"),
            ("6. Extension", "reference.rollout_registry"),
        ]:
            cnt = int(conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0)
            layer_counts.append({"Layer": layer, "Object": tbl, "Rows": cnt})

    wm_val = int(wm_df["BigIntWatermark"].iloc[0]) if not wm_df.empty else 0
    r_stat = str(run_df["RunStatus"].iloc[0]) if not run_df.empty else "UNKNOWN"
    r_ts = str(run_df["CompletedDateTime"].iloc[0])[:19] if not run_df.empty else "unknown"
    df_layers = pd.DataFrame(layer_counts)
    return ToolPayload(
        status="ok",
        tool_name="get_core_pipeline_status",
        metric_id="dataops_status",
        kpi_name="DataOps & Medallion Freshness",
        headline=(f"**DataOps Pipeline Status:** `{r_stat}` (Run `#{latest_run}`, refreshed `{r_ts}`, "
                  f"backend `{backend()}`, `ApplicationLogId` watermark = `{_fmt_int(wm_val)}`)."),
        facts=[f"{r['CheckName']} [{r['CheckStatus']}]: {r['Details']}" for _, r in qm_df.iterrows()],
        warnings=["Orphan child records and REVIEW/EXCLUDED app mappings are quarantined and logged in DataOps without inflating certified KPIs."],
        df=qm_df.rename(columns={"CheckName": "Check", "CheckCategory": "Category", "CheckStatus": "Status",
                                 "MetricValue": "Observed", "ExpectedValue": "Expected"}),
        chart_spec={
            "kind": "hbar",
            "title": "Medallion Layer Row Counts (Source -> Certified View)",
            "x": df_layers["Rows"].tolist(),
            "y": df_layers["Object"].tolist(),
            "x_label": "Rows",
        },
        filters_used={"pipeline_run_id": latest_run, "backend": backend()},
        period_label=f"Refreshed {r_ts}",
        freshness_ts=r_ts,
        lineage_id=f"dataops.pipeline_run::{latest_run}",
        compiled_sql="SELECT * FROM dataops.pipeline_run; SELECT * FROM dataops.data_quality_metric;",
    )


def get_core_metric_lineage(kpi_name: str = "ALL") -> ToolPayload:
    resolved = resolve_kpi_name(kpi_name) or "ALL"
    cat = semantic_catalog()["metrics"]
    rows = []
    for _mid, spec in cat.items():
        if resolved != "ALL" and spec["kpi_name"] != resolved:
            continue
        lin = spec["lineage"]
        rows.append({
            "KPI Name": spec["kpi_name"],
            "1. Source Sim": ", ".join(lin["source_tables"]),
            "2. Bronze Layer": ", ".join(lin["bronze_tables"]),
            "3. Silver Layer": ", ".join(lin["silver_tables"]),
            "4. Gold Fact": ", ".join(lin["gold_objects"]),
            "5. Certified View": lin["certified_object"],
        })
    df = pd.DataFrame(rows)
    return ToolPayload(
        status="ok",
        tool_name="get_core_metric_lineage",
        metric_id="metric_lineage",
        kpi_name=resolved,
        headline=f"**End-to-End Medallion Lineage** (`Synthetic Source -> Bronze -> Silver -> Gold -> Certified View -> Answer`) for **{resolved}**:",
        facts=[
            f"{r['KPI Name']}: {r['1. Source Sim']} -> {r['2. Bronze Layer']} -> {r['3. Silver Layer']} -> {r['4. Gold Fact']} -> {r['5. Certified View']}"
            for r in rows
        ],
        df=df,
        filters_used={"kpi": resolved},
        period_label="Lineage Map",
        lineage_id="core://metadata/lineage",
        compiled_sql="-- End-to-end table lineage resolved from governed semantic catalog",
    )
