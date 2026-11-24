"""Read-only Model Context Protocol (MCP) tool & resource server for CORE Pulse.

Exposes:
  * 6 metadata resources (`core://metadata/project`, `kpis`, `sources`, `lineage`, `semantic-rules`, `freshness`)
  * 10 typed read-only tools (`get_core_adoption_current`, `get_core_adoption_monthly`,
    `get_core_adoption_by_wave`, `get_core_adoption_by_entity`, `get_core_adoption_by_business_unit`,
    `get_core_rollout_status`, `get_core_user_engagement`, `get_core_metric_definition`,
    `get_core_pipeline_status`, `get_core_metric_lineage`)

Supports JSON-RPC 2.0 over stdio (`python -m mcp_server.server`) AND direct local MCP envelope dispatch
(`call_mcp_tool_local`), never permitting arbitrary SQL, filesystem access, or source mutations.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any

from app.config import as_of_date, settings
from app.semantic import service as S

MCP_RESOURCES = {
    "core://metadata/project": lambda: {
        "product": settings()["app_name"],
        "company": settings()["company_long"],
        "operational_platform": settings()["operational_platform"],
        "certified_view": "goldview.v_core_adoption",
        "synthetic_demo": True,
    },
    "core://metadata/kpis": lambda: S.semantic_catalog()["metrics"],
    "core://metadata/sources": lambda: {
        "schemas": ["source_sim", "bronze", "silver", "gold", "goldview", "reference", "dataops"],
        "certified_consumer_datasets": ["goldview.v_core_adoption", "goldview.v_dim_date"],
    },
    "core://metadata/lineage": lambda: {
        k: v["lineage"] for k, v in S.semantic_catalog()["metrics"].items()
    },
    "core://metadata/semantic-rules": lambda: {
        "non_additive_kpis": ["Employees Logging In"],
        "bu_supported_kpis": list(S.BU_SUPPORTED_KPIS),
        "bu_unavailable_kpis": ["Employees Logging In", "Timesheets Submitted"],
        "partial_month_rule": "Always inspect IsCompleteMonth; compare MTD against equivalent elapsed prior-month days.",
    },
    "core://metadata/freshness": lambda: {
        "as_of_date": as_of_date().isoformat(),
        "pipeline": S.get_core_pipeline_status().headline,
    },
}

ALLOWED_TOOLS = {
    "get_core_adoption_current",
    "get_core_adoption_monthly",
    "get_core_adoption_by_wave",
    "get_core_adoption_by_entity",
    "get_core_adoption_by_business_unit",
    "get_core_rollout_status",
    "get_core_user_engagement",
    "get_core_metric_definition",
    "get_core_pipeline_status",
    "get_core_metric_lineage",
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_core_adoption_current",
            "description": "Current, MTD, or last-complete-month CORE adoption snapshot for one KPI or ALL four KPIs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kpi_name": {"type": "string", "description": "Contracts Created | Employees Logging In | Timesheets Submitted | Expense Reports | ALL"},
                    "period_mode": {"type": "string", "enum": ["SNAPSHOT", "MTD", "LAST_MONTH"]},
                    "region": {"type": "string", "description": "Optional: AMER | EMEA | APAC"},
                    "entity": {"type": "string"},
                    "wave": {"type": "integer"},
                    "business_unit": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_adoption_monthly",
            "description": "Monthly true-event adoption trend for a KPI over the last N months, including fastest-growing complete month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kpi_name": {"type": "string"},
                    "months_back": {"type": "integer", "default": 12},
                    "reporting_level": {"type": "string", "enum": ["OVERALL", "WAVE", "ENTITY", "BUSINESS_UNIT"]},
                    "entity": {"type": "string"},
                    "wave": {"type": "integer"},
                    "business_unit": {"type": "string"},
                    "region": {"type": "string"},
                },
                "required": ["kpi_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_adoption_by_wave",
            "description": "Break down a CORE adoption KPI across Rollout Waves (Wave 1..4). Preserves non-additive OVERALL deduplication.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kpi_name": {"type": "string"},
                    "period": {"type": "string", "description": "CURRENT | MTD | LAST_MONTH | YYYY-MM"},
                },
                "required": ["kpi_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_adoption_by_entity",
            "description": "Break down a CORE adoption KPI across governed Adoption Entities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kpi_name": {"type": "string"},
                    "period": {"type": "string"},
                    "region": {"type": "string"},
                    "wave": {"type": "integer"},
                },
                "required": ["kpi_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_adoption_by_business_unit",
            "description": "Break down a KPI by CORE Business Unit (supported for Contracts Created and Expense Reports; returns governance limitation for Logins and Timecards).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kpi_name": {"type": "string"},
                    "period": {"type": "string"},
                    "region": {"type": "string"},
                    "entity": {"type": "string"},
                    "wave": {"type": "integer"},
                },
                "required": ["kpi_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_rollout_status",
            "description": "Query the SIMULATED EXTENSION rollout registry & module catalog (PLANNED, ONBOARDING, LIVE, PAUSED, RETIRED) and compare against observed instrumented events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {"type": "string"},
                    "region": {"type": "string"},
                    "entity": {"type": "string"},
                    "wave": {"type": "integer"},
                    "rollout_status": {"type": "string", "enum": ["PLANNED", "ONBOARDING", "LIVE", "PAUSED", "RETIRED"]},
                    "zero_activity_only": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_user_engagement",
            "description": "Governed unique non-service user engagement and login event counts by CORE application over MTD, LAST_MONTH, LAST_30D, or ALL_TIME.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_window": {"type": "string", "enum": ["MTD", "LAST_MONTH", "LAST_30D", "ALL_TIME"]},
                    "application": {"type": "string"},
                    "entity": {"type": "string"},
                    "wave": {"type": "integer"},
                    "region": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_metric_definition",
            "description": "Authoritative KPI formula, counting grain, event timestamp, exclusions, non-additivity rule, and supported dimensions.",
            "parameters": {
                "type": "object",
                "properties": {"kpi_name": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_pipeline_status",
            "description": "DataOps pipeline run status, ApplicationLogId watermark, Medallion table counts, and data quality / parity checks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_core_metric_lineage",
            "description": "Navigable end-to-end table lineage: Source Sim -> Bronze -> Silver -> Gold -> Certified View.",
            "parameters": {
                "type": "object",
                "properties": {"kpi_name": {"type": "string"}},
            },
        },
    },
]


def invoke_tool(tool_name: str, arguments: dict[str, Any] | None, user_id: str = "global_program_lead",
                as_of=None, via_mcp: bool = True) -> S.ToolPayload:
    """Validate allowlisted tool name & sanitized arguments, execute read-only query, and tag MCP telemetry."""
    import inspect

    if tool_name not in ALLOWED_TOOLS:
        raise ValueError(f"Unsupported or disallowed tool '{tool_name}'. Arbitrary SQL and unlisted tools are blocked.")
    args = dict(arguments or {})
    # Strip any untrusted SQL / system override keys if injected
    for bad in ("sql", "query", "raw_sql", "command", "path", "user_id", "as_of"):
        args.pop(bad, None)

    fn = getattr(S, tool_name)
    sig_params = set(inspect.signature(fn).parameters.keys()) - {"user_id", "as_of"}
    clean_args = {k: v for k, v in args.items() if k in sig_params and v is not None and v != ""}
    if "user_id" in inspect.signature(fn).parameters:
        if as_of is not None and "as_of" in inspect.signature(fn).parameters:
            clean_args["as_of"] = as_of
        res = fn(user_id=user_id, **clean_args)
    else:
        res = fn(**clean_args)
    res.via_mcp = via_mcp
    return res


def handle_jsonrpc(req: dict[str, Any]) -> dict[str, Any]:
    """Minimal JSON-RPC 2.0 MCP handler supporting tools/list, tools/call, resources/list, resources/read."""
    rid = req.get("id")
    method = req.get("method", "")
    params = req.get("params") or {}
    t0 = time.time()
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "core-pulse-mcp", "version": "1.0.0"},
                "capabilities": {"tools": {}, "resources": {}},
            }
        elif method == "tools/list":
            result = {"tools": [t["function"] for t in TOOL_SCHEMAS]}
        elif method == "tools/call":
            tname = params.get("name", "")
            targs = params.get("arguments") or {}
            uid = params.get("_persona_user_id", "global_program_lead")
            payload = invoke_tool(tname, targs, user_id=uid, via_mcp=True)
            result = {
                "request_id": str(uuid.uuid4())[:12],
                "via_mcp": True,
                "elapsed_ms": round((time.time() - t0) * 1000, 1),
                "status": payload.status,
                "headline": payload.headline,
                "facts": payload.facts,
                "warnings": payload.warnings,
                "period_label": payload.period_label,
                "freshness_ts": payload.freshness_ts,
                "lineage_id": payload.lineage_id,
                "rows": payload.df.to_dict(orient="records"),
            }
        elif method == "resources/list":
            result = {"resources": [{"uri": u, "name": u.split("/")[-1]} for u in MCP_RESOURCES]}
        elif method == "resources/read":
            uri = params.get("uri", "")
            if uri not in MCP_RESOURCES:
                raise ValueError(f"Unknown MCP resource URI: {uri}")
            result = {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(MCP_RESOURCES[uri](), default=str)}]}
        else:
            raise ValueError(f"Unsupported MCP method: {method}")
        return {"jsonrpc": "2.0", "id": rid, "result": result}
    except Exception as exc:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": str(exc)}}


def main() -> None:  # pragma: no cover - stdio entrypoint
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp = handle_jsonrpc(json.loads(line))
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
