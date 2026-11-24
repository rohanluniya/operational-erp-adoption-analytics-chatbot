"""Governed HTML table formatting and CSV / Excel export helpers for CORE Pulse."""
from __future__ import annotations

import html
import io
import pandas as pd

TABLE_CSS = """
<style>
table.cp-tbl { width: 100%; border-collapse: collapse; font-size: 0.86rem; margin: 8px 0 12px; }
table.cp-tbl th { background: #0B1F3A; color: #FFFFFF; text-align: left; padding: 8px 10px; font-weight: 700; }
table.cp-tbl td { padding: 7px 10px; border-bottom: 1px solid #E2E8F0; color: #1E293B; }
table.cp-tbl tr:nth-child(even) td { background: #F8FAFC; }
table.cp-tbl td.num, table.cp-tbl th.num { text-align: right; font-variant-numeric: tabular-nums; }
.cp-badge-warn { background: #FEF3C7; color: #92400E; padding: 2px 7px; border-radius: 6px; font-weight: 600; font-size: 0.78rem; }
.cp-badge-ok { background: #DCFCE7; color: #166534; padding: 2px 7px; border-radius: 6px; font-weight: 600; font-size: 0.78rem; }
</style>
"""


def _fmt_cell(val) -> tuple[str, bool]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—", False
    if isinstance(val, bool):
        return ("Yes" if val else "No"), False
    if isinstance(val, int):
        return f"{val:,}", True
    if isinstance(val, float):
        if val.is_integer():
            return f"{int(val):,}", True
        return f"{val:,.1f}", True
    s = html.escape(str(val))
    if "ZERO observed" in s or "Partial" in s or "Not instrumented" in s or "WARNING" in s:
        return f"<span class='cp-badge-warn'>{s}</span>", False
    if s in ("LIVE", "Observed activity", "PASS", "Complete"):
        return f"<span class='cp-badge-ok'>{s}</span>", False
    return s, False


def render_html(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""
    cols = list(df.columns)
    num_cols = {c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and c not in ("Wave", "AdoptionWaveNumber")}
    ths = "".join(f"<th class='{'num' if c in num_cols else ''}'>{html.escape(str(c))}</th>" for c in cols)
    rows_html = []
    for _, row in df.iterrows():
        tds = []
        for c in cols:
            txt, is_n = _fmt_cell(row[c])
            cls = "num" if (c in num_cols or is_n) and c not in ("Wave",) else ""
            tds.append(f"<td class='{cls}'>{txt}</td>")
        rows_html.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table class='cp-tbl'><thead><tr>{ths}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="CORE_Pulse_Data")
    return buf.getvalue()
