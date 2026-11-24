"""Governed conversational router, multi-turn memory, and MCP tool orchestrator for CORE Pulse."""
from __future__ import annotations

import re
import time
import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.agent import guardrails as G
from app.agent import llm
from app.agent.prompts import ANSWER_WRITER_SYSTEM, TOOL_ROUTER_SYSTEM
from app.config import as_of_date
from app.semantic.access import get_user_scope
from app.semantic.service import ToolPayload, kpi_meta
from mcp_server.server import ALLOWED_TOOLS, TOOL_SCHEMAS, invoke_tool

ENTITY_ALIASES = {
    "north america field ops": "North America Field Ops",
    "na field ops": "North America Field Ops",
    "north america cert & labs": "North America Cert & Labs",
    "north america cert": "North America Cert & Labs",
    "na cert": "North America Cert & Labs",
    "europe industrial & testing": "Europe Industrial & Testing",
    "europe industrial": "Europe Industrial & Testing",
    "mea energy & marine": "MEA Energy & Marine",
    "mea energy": "MEA Energy & Marine",
    "apac certification & marine": "APAC Certification & Marine",
    "apac certification": "APAC Certification & Marine",
    "latin america operations": "Latin America Operations",
    "latin america": "Latin America Operations",
    "latam": "Latin America Operations",
}

BU_CODES = (
    "BU-US-FLD-01", "BU-US-INF-02", "BU-CA-CERT-03", "BU-FR-IND-04", "BU-DE-LAB-05",
    "BU-AE-MAR-06", "BU-SG-MAR-07", "BU-SG-LAB-08", "BU-BR-FLD-09", "BU-AU-REN-10",
)

MODULE_ALIASES = {
    "expense": "EXPENSES",
    "expenses": "EXPENSES",
    "expense report": "EXPENSES",
    "timecard": "TIMECARDS",
    "timecards": "TIMECARDS",
    "timesheet": "TIMECARDS",
    "timesheets": "TIMECARDS",
    "project": "PROJECTS",
    "projects": "PROJECTS",
    "contract": "PROJECTS",
    "contracts": "PROJECTS",
    "core login": "CORE_LOGIN",
    "inspector scheduling": "INSPECTOR_SCHED",
    "scheduling": "INSPECTOR_SCHED",
    "qualification": "QUALIFICATIONS",
    "qualifications": "QUALIFICATIONS",
    "lab testing": "LAB_TESTING",
    "laboratory": "LAB_TESTING",
    "invoicing": "INVOICING",
    "billing": "INVOICING",
}

NUMBER_WORDS = {
    "three": 3, "four": 4, "six": 6, "nine": 9, "twelve": 12, "eighteen": 18,
}

PUSHBACK_RE = re.compile(
    r"\b(that'?s\s+not\s+right|not\s+what\s+i\s+meant|that\s+looks\s+wrong|you\s+got\s+that\s+wrong|incorrect\s+filter)\b",
    re.IGNORECASE,
)


class AgentAnswer(BaseModel):
    status: str = "ok"
    answer_markdown: str = ""
    table_columns: list[str] = Field(default_factory=list)
    table_records: list[dict[str, Any]] = Field(default_factory=list)
    chart_spec: dict[str, Any] = Field(default_factory=dict)
    filters_used: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    sql_used: list[str] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


def _extract_kpi(q: str) -> str | None:
    ql = q.lower()
    if any(p in ql for p in ("all four kpi", "all kpis", "overall adoption", "adoption overall", "adoption summary", "current core adoption")):
        return "ALL"
    if any(w in ql for w in ("contract", "contracts", "project creation", "projects created", "new projects")):
        return "Contracts Created"
    if any(w in ql for w in ("timesheet", "timesheets", "timecard", "timecards")):
        return "Timesheets Submitted"
    if any(w in ql for w in ("expense", "expenses")):
        return "Expense Reports"
    if any(w in ql for w in ("logged in", "logging in", "login", "logins", "active user", "active users",
                             "unique user", "unique users", "employees logged", "employees logging",
                             "users are using core", "users using core", "who logged")):
        return "Employees Logging In"
    return None


def _extract_region(q: str) -> tuple[str | None, str | None]:
    ql = q.lower()
    if re.search(r"\b(western\s+region|americas|amer|north\s+america\s+&\s+latam)\b", ql):
        note = "Mapped 'Western region' to governed region AMER (Americas)" if "western" in ql else None
        return "AMER", note
    if re.search(r"\b(emea|europe,\s*middle\s*east|european\s+region)\b", ql):
        return "EMEA", None
    if re.search(r"\b(apac|asia[-\s]?pacific)\b", ql):
        return "APAC", None
    return None, None


def _extract_entity(q: str) -> str | None:
    ql = q.lower()
    for alias, canon in sorted(ENTITY_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in ql:
            return canon
    return None


def _extract_wave(q: str) -> int | None:
    m = re.search(r"\bwave\s*([1-4])\b", q, flags=re.IGNORECASE)
    if m and not re.search(r"\bwave\s*1\s+and\s+wave\s*2\b", q, flags=re.IGNORECASE):
        return int(m.group(1))
    return None


def _extract_bu(q: str) -> str | None:
    qu = q.upper()
    for code in BU_CODES:
        if code in qu:
            return code
    ql = q.lower()
    bu_keywords = {
        "australia renewables": "BU-AU-REN-10",
        "brazil field": "BU-BR-FLD-09",
        "us field": "BU-US-FLD-01",
        "us infrastructure": "BU-US-INF-02",
        "canada conformity": "BU-CA-CERT-03",
        "france industrial": "BU-FR-IND-04",
        "germany analytical": "BU-DE-LAB-05",
        "singapore marine": "BU-SG-MAR-07",
    }
    for kw, code in bu_keywords.items():
        if kw in ql:
            return code
    return None


def _extract_months_back(q: str) -> int | None:
    ql = q.lower()
    m = re.search(r"\b(?:last|past|previous|six|twelve)?\s*(\d{1,2})[-\s]+months?\b", ql)
    if m:
        return max(2, min(18, int(m.group(1))))
    for word, val in NUMBER_WORDS.items():
        if re.search(rf"\b{word}[-\s]+months?\b", ql):
            return val
    if "monthly" in ql or "over time" in ql or "trend" in ql:
        return 12
    return None


def _extract_period(q: str) -> str | None:
    ql = q.lower()
    ym = re.search(r"\b(202[56]-\d{2})\b", ql)
    if ym:
        return ym.group(1)
    if "this month" in ql and "last month" in ql:
        return "MTD"
    if any(p in ql for p in ("this month", "current month", "month to date", "mtd", "november 2026", "nov 2026")):
        return "MTD"
    if any(p in ql for p in ("last month", "prior month", "previous month", "last complete month", "october 2026", "oct 2026")):
        return "LAST_MONTH"
    if any(p in ql for p in ("all-time", "all time", "cumulative")):
        return "CURRENT"
    return None


def plan_deterministic(question: str, memory: dict[str, Any], ui_filters: dict[str, Any]) -> tuple[str, dict[str, Any], list[str], list[str]]:
    """Resolve question + UI filters + conversation memory into an exact allowlisted MCP tool call."""
    q = question.strip()
    ql = q.lower()
    applied: list[str] = []
    carried: list[str] = []

    q_kpi = _extract_kpi(q)
    q_reg, reg_note = _extract_region(q)
    q_ent = _extract_entity(q)
    q_wave = _extract_wave(q)
    q_bu = _extract_bu(q)
    q_months = _extract_months_back(q)
    q_period = _extract_period(q)
    if reg_note:
        applied.append(reg_note)

    # Continuation markers ("break it down...", "now show...", "those modules...", "this metric...")
    is_followup = bool(re.search(
        r"\b(break\s+it\s+down|break\s+down|now\s+show|what\s+about|and\s+for|those\s+modules|this\s+metric|this\s+kpi|why\s+isn'?t\s+bu|show\s+the\s+.*trend|show\s+source\s+lineage)\b",
        ql,
    ))

    ui_reg = ui_filters.get("region")
    ui_ent = ui_filters.get("entity")
    ui_wave = ui_filters.get("wave")
    ui_bu = ui_filters.get("business_unit")
    ui_period = ui_filters.get("period_mode")

    # Precedence: Explicit question > UI filters (unless pure continuation overrides) > Carried-over memory
    kpi = q_kpi
    if not kpi:
        if is_followup and memory.get("kpi_name"):
            kpi = memory["kpi_name"]
            carried.append(f"KPI: {kpi}")
        elif ui_filters.get("kpi_name"):
            kpi = ui_filters["kpi_name"]
            applied.append(f"Sidebar KPI: {kpi}")
        elif memory.get("kpi_name") and any(w in ql for w in ("by wave", "by entity", "by business unit", "by bu", "lineage", "calculated", "definition", "mean")):
            kpi = memory["kpi_name"]
            carried.append(f"KPI: {kpi}")

    region = q_reg
    if not region:
        if ui_reg:
            region = ui_reg
            applied.append(f"Sidebar Region: {region}")
        elif is_followup and memory.get("region"):
            region = memory["region"]
            carried.append(f"Region: {region}")

    entity = q_ent
    if not entity and not q_reg:
        if ui_ent:
            entity = ui_ent
            applied.append(f"Sidebar Entity: {entity}")
        elif is_followup and memory.get("entity") and "by entity" not in ql and "by wave" not in ql:
            entity = memory["entity"]
            carried.append(f"Entity: {entity}")

    wave = q_wave
    if wave is None and not q_reg and not q_ent:
        if ui_wave is not None:
            wave = int(ui_wave)
            applied.append(f"Sidebar Wave: Wave {wave}")
        elif is_followup and memory.get("wave") is not None and "by wave" not in ql:
            wave = int(memory["wave"])
            carried.append(f"Wave: Wave {wave}")

    bu = q_bu
    if not bu and not q_reg and not q_ent and q_wave is None:
        if ui_bu:
            bu = ui_bu
            applied.append(f"Sidebar BU: {bu}")
        elif is_followup and memory.get("business_unit") and "by business unit" not in ql:
            bu = memory["business_unit"]
            carried.append(f"BU: {bu}")

    period = q_period
    if not period:
        if ui_period and ui_period != "DEFAULT":
            period = ui_period
            applied.append(f"Sidebar Period: {period}")
        elif is_followup and memory.get("period"):
            period = memory["period"]
            carried.append(f"Period: {period}")

    # 1. Pipeline / DataOps / freshness / orphan / mapping exception questions
    if any(p in ql for p in ("pipeline", "dataops", "watermark", "how fresh", "freshness", "orphan", "mapping check", "medallion count", "quality check")):
        return "get_core_pipeline_status", {}, applied, carried

    # 2. Lineage / "where the data came from" / "how this metric was calculated and where..."
    if any(p in ql for p in ("lineage", "where the data came from", "where did this data come from", "source tables", "bronze", "silver")):
        return "get_core_metric_lineage", {"kpi_name": kpi or "Employees Logging In"}, applied, carried

    # 3. KPI Definition / "what does this KPI mean" / "how is ... defined / calculated"
    if any(p in ql for p in ("what does this kpi mean", "metric definition", "kpi dictionary", "how is", "how was", "calculated", "formula", "counting rule")) and "where the data came from" not in ql:
        return "get_core_metric_definition", {"kpi_name": kpi or "ALL"}, applied, carried

    # 4. Rollout status vs actual module activity (SIMULATED EXTENSION)
    is_rollout_q = any(p in ql for p in (
        "which modules", "modules are live", "live on ", "zero expense", "zero activity", "zero observed",
        "rollout status", "onboarding", "planned go-live", "actually seeing activity", "modules were actually used",
        "seeing activity", "rollout registry",
    ))
    if is_rollout_q:
        mod = None
        for m_alias, m_code in sorted(MODULE_ALIASES.items(), key=lambda x: -len(x[0])):
            if m_alias in ql:
                mod = m_code
                break
        if not mod and is_followup and memory.get("module"):
            mod = memory["module"]
            carried.append(f"Module: {mod}")
        st_filter = "LIVE" if any(w in ql for w in ("live", "seeing activity", "actually used", "zero")) else None
        zero_only = bool("only zero" in ql)
        return "get_core_rollout_status", {
            "module": mod,
            "region": region,
            "entity": entity,
            "wave": wave,
            "rollout_status": st_filter,
            "zero_activity_only": zero_only,
        }, applied, carried

    # 5. Application-level user engagement ("by application", "login events per user", "daily active")
    if any(p in ql for p in ("by application", "across applications", "which application", "user engagement", "login events", "rolling 30", "last 30 days")):
        win = "LAST_30D" if "30" in ql else (period if period in ("MTD", "LAST_MONTH") else "MTD")
        return "get_core_user_engagement", {
            "date_window": win,
            "entity": entity,
            "wave": wave,
            "region": region,
        }, applied, carried

    # 6. Business Unit breakdown (including unsupported Employees Logging In / Timesheets Submitted!)
    if any(p in ql for p in ("by business unit", "by bu", "per business unit", "why isn't bu available", "business unit breakdown")):
        target_kpi = kpi or memory.get("kpi_name") or "Contracts Created"
        if "why isn't bu" in ql and target_kpi in ("Contracts Created", "Expense Reports", "ALL"):
            target_kpi = "Employees Logging In"
        return "get_core_adoption_by_business_unit", {
            "kpi_name": target_kpi,
            "period": period or "CURRENT",
            "region": region,
            "entity": entity,
            "wave": wave,
        }, applied, carried

    # 7. Wave breakdown (including non-additivity explanation "sum of Wave 1 and Wave 2" or "which rollout wave is most active")
    if any(p in ql for p in ("by rollout wave", "by wave", "across waves", "which rollout wave", "which wave", "wave 1 and wave 2")):
        target_kpi = kpi if (kpi and kpi != "ALL") else (memory.get("kpi_name") if memory.get("kpi_name") not in (None, "ALL") else "Employees Logging In")
        return "get_core_adoption_by_wave", {
            "kpi_name": target_kpi,
            "period": period or "CURRENT",
        }, applied, carried

    # 8. Entity breakdown
    if any(p in ql for p in ("by entity", "by adoption entity", "across entities", "which entity", "which adoption entity")):
        target_kpi = kpi if (kpi and kpi != "ALL") else "Employees Logging In"
        return "get_core_adoption_by_entity", {
            "kpi_name": target_kpi,
            "period": period or "CURRENT",
            "region": region,
            "wave": wave,
        }, applied, carried

    # 9. Monthly trend ("last 6 months", "last 12 months", "six-month trend", "fastest-growing month")
    if q_months is not None or any(p in ql for p in ("monthly", "trend", "fastest-growing", "fastest growing", "month over month")):
        target_kpi = kpi if (kpi and kpi != "ALL") else (memory.get("kpi_name") if memory.get("kpi_name") not in (None, "ALL") else "Employees Logging In")
        return "get_core_adoption_monthly", {
            "kpi_name": target_kpi,
            "months_back": q_months or 12,
            "entity": entity,
            "wave": wave,
            "business_unit": bu,
            "region": region,
        }, applied, carried

    # 10. Default: Current / MTD / Last-Month snapshot (`How many users are using CORE?` defaults to MTD!)
    target_kpi = kpi or "ALL"
    if target_kpi == "Employees Logging In" and not period:
        p_mode = "MTD"
    elif period in ("MTD", "LAST_MONTH"):
        p_mode = period
    else:
        p_mode = "SNAPSHOT"

    return "get_core_adoption_current", {
        "kpi_name": target_kpi,
        "period_mode": p_mode,
        "region": region,
        "entity": entity,
        "wave": wave,
        "business_unit": bu,
    }, applied, carried


def _build_followups(payload: ToolPayload) -> list[str]:
    kpi = payload.kpi_name if payload.kpi_name and payload.kpi_name != "ALL" else "Employees Logging In"
    if payload.tool_name == "get_core_adoption_current":
        if payload.kpi_name == "ALL":
            return [
                "How many employees logged into CORE this month?",
                "Show monthly contract creation over the last 12 months",
                "Which entities are live on Expenses, and which have zero submissions?",
            ]
        return [
            f"Break {kpi} down by rollout wave",
            f"Show the six-month trend for {kpi}",
            f"Show source lineage for {kpi}",
        ]
    if payload.tool_name == "get_core_adoption_monthly":
        return [
            f"Break {kpi} down by rollout wave",
            f"Break {kpi} down by adoption entity",
            f"What does {kpi} mean and how is it counted?",
        ]
    if payload.tool_name == "get_core_adoption_by_wave":
        return [
            f"Show the six-month trend for {kpi}",
            "Why doesn't the sum of Wave 1 and Wave 2 active users equal total active users?",
            f"Show source lineage for {kpi}",
        ]
    if payload.tool_name == "get_core_rollout_status":
        return [
            "Are those modules actually seeing activity?",
            "Which entities are live on Expenses, and which live entities have zero expense submissions?",
            "How fresh is the dataset, and did any mapping or orphan checks fail?",
        ]
    if payload.status == "unsupported":
        return [
            f"Break {kpi} down by adoption entity",
            f"Break {kpi} down by rollout wave",
            f"What does {kpi} mean and how is it counted?",
        ]
    return [
        "What is current CORE adoption overall?",
        "How many employees logged in this month vs last month?",
        "How fresh is the dataset, and did any mapping or orphan checks fail?",
    ]


def ask(question: str, user_id: str = "global_program_lead", memory: dict[str, Any] | None = None,
        model: str | None = "rules", as_of: date | None = None,
        ui_filters: dict[str, Any] | None = None) -> tuple[AgentAnswer, dict[str, Any]]:
    """Process one conversational turn end-to-end with guardrails, MCP dispatch, and memory update."""
    t0 = time.time()
    req_id = str(uuid.uuid4())[:12]
    as_of = as_of or as_of_date()
    mem = dict(memory or {})
    uif = dict(ui_filters or {})
    scope = get_user_scope(user_id)
    use_rules = (not model) or model.strip().lower().startswith("rules")

    # 1. Pushback handler ("that's not right" / "not what I meant")
    if PUSHBACK_RE.search(question or ""):
        last_kpi = mem.get("kpi_name") or "Employees Logging In"
        last_per = mem.get("period") or "MTD"
        last_reg = mem.get("region") or scope.scope_label
        msg = (
            f"Here is the exact context used on the previous turn:\n"
            f"- **KPI:** `{last_kpi}`\n"
            f"- **Period mode:** `{last_per}` (as of `{as_of.isoformat()}`)\n"
            f"- **Scope / Persona:** `{last_reg}` (`{scope.display_name}`)\n\n"
            f"Choose what you would like to change:"
        )
        opts = [
            f"Show {last_kpi} for last complete month (Oct 2026)",
            f"Break {last_kpi} down by rollout wave",
            f"What does {last_kpi} mean and how is it counted?",
        ]
        return AgentAnswer(
            status="clarification",
            answer_markdown=msg,
            diagnostics={
                "request_id": req_id,
                "options": opts,
                "options_mode": "question",
                "model": model or "rules",
                "latency_s": round(time.time() - t0, 2),
            },
        ), mem

    # 2. Prompt-injection & raw-SQL / secret / exfiltration safety check (fail closed)
    safety_err = G.check_prompt_safety(question)
    if safety_err:
        return AgentAnswer(
            status="refusal",
            answer_markdown=safety_err,
            filters_used={"persona": scope.display_name, "rls": scope.scope_label, "as_of_date": as_of.isoformat()},
            diagnostics={
                "request_id": req_id,
                "via_mcp": False,
                "guardrail": {"ok": True, "blocked_injection": True},
                "model": model or "rules",
                "latency_s": round(time.time() - t0, 2),
            },
        ), mem

    # 3. Out-of-scope future-release check
    oos_msg = G.check_out_of_scope(question)
    if oos_msg:
        return AgentAnswer(
            status="unsupported",
            answer_markdown=f"**Out of Release 1 Adoption Scope:** {oos_msg}\n\nCORE Pulse Release 1 governs **Contracts Created**, **Employees Logging In**, **Timesheets Submitted**, **Expense Reports**, and the **Rollout Registry** (`SIMULATED EXTENSION`).",
            filters_used={"persona": scope.display_name, "rls": scope.scope_label, "as_of_date": as_of.isoformat()},
            followups=[
                "What is current CORE adoption overall?",
                "Which modules are live, and which are not yet instrumented?",
                "Show monthly contract creation over the last 12 months",
            ],
            diagnostics={
                "request_id": req_id,
                "via_mcp": False,
                "guardrail": {"ok": True, "out_of_scope": True},
                "model": model or "rules",
                "latency_s": round(time.time() - t0, 2),
            },
        ), mem

    # 4. Deterministic semantic tool plan + optional LLM tool-calling pass
    det_tool, det_args, applied, carried = plan_deterministic(question, mem, uif)
    chosen_tool, chosen_args = det_tool, dict(det_args)
    tool_source = "rules"
    llm_error_note = None

    if not use_rules:
        try:
            router_msgs = [
                {"role": "system", "content": TOOL_ROUTER_SYSTEM},
                {"role": "user", "content": f"Context memory: {mem}\nSidebar filters: {uif}\nQuestion: {question}"},
            ]
            r_res = llm.chat(router_msgs, tools=TOOL_SCHEMAS, model=model, max_tokens=500)
            if r_res.tool_calls:
                cand = r_res.tool_calls[0]
                cname = cand.get("name")
                cargs = cand.get("arguments") or {}
                # Keep critical semantic guardrails (unsupported BU, rollout registry, lineage, multi-turn scope)
                critical_det = det_tool in (
                    "get_core_adoption_by_business_unit",
                    "get_core_rollout_status",
                    "get_core_metric_lineage",
                    "get_core_pipeline_status",
                    "get_core_metric_definition",
                )
                if cname in ALLOWED_TOOLS and not critical_det:
                    chosen_tool = cname
                    # Merge deterministic resolved filters where LLM omitted context carry-over
                    merged = dict(det_args)
                    for k, v in cargs.items():
                        if v not in (None, ""):
                            merged[k] = v
                    chosen_args = merged
                    tool_source = f"llm ({r_res.model})"
                else:
                    tool_source = f"llm+semantic_guard ({r_res.model})"
        except PermissionError as exc:
            llm_error_note = f"AI unavailable — {exc} Falling back to governed deterministic mode."
            use_rules = True
        except Exception as exc:  # noqa: BLE001
            llm_error_note = f"Model connection notice ({type(exc).__name__}); served from governed deterministic engine."
            use_rules = True

    # 5. Execute strictly through the read-only MCP tool boundary
    payload = invoke_tool(chosen_tool, chosen_args, user_id=user_id, as_of=as_of, via_mcp=True)

    # Enrich lineage response with metric definition formula so executive gets both how-calculated & where-from!
    if chosen_tool == "get_core_metric_lineage" and payload.kpi_name and payload.kpi_name != "ALL":
        spec = kpi_meta(payload.kpi_name)
        if spec:
            payload.facts.insert(0, f"Counting formula: {spec['counting_rule']} bucketed by {spec['event_timestamp']} ({spec['additivity']})")
            payload.facts.insert(1, f"Exclusions: {spec['exclusions']}")

    # 6. Generate executive prose (deterministic in rules/refusal/unsupported, or LLM-written + numeric-verified)
    guard_info: dict[str, Any] = {"ok": True, "template": True, "reason": "deterministic_rules"}
    if use_rules or payload.status != "ok":
        prose = G.deterministic_prose(payload)
        if llm_error_note:
            prose = f"> **{llm_error_note}**\n\n{prose}"
    else:
        try:
            sanitized_context = (
                f"QUESTION: {question}\n"
                f"TOOL: {payload.tool_name}\n"
                f"PERIOD: {payload.period_label}\n"
                f"HEADLINE: {payload.headline}\n"
                f"FACTS:\n" + "\n".join(f"- {f}" for f in payload.facts) + "\n"
                f"WARNINGS:\n" + "\n".join(f"- {w}" for w in payload.warnings)
            )
            w_res = llm.chat(
                [
                    {"role": "system", "content": ANSWER_WRITER_SYSTEM},
                    {"role": "user", "content": sanitized_context},
                ],
                model=model,
                max_tokens=450,
            )
            verdict = G.verify_prose(w_res.content, payload)
            if verdict.ok:
                prose = w_res.content
                for w in payload.warnings[:2]:
                    if w not in prose:
                        prose += f"\n\n> **Governance note:** {w}"
                guard_info = {"ok": True, "template": False, "reason": "verified_llm_prose"}
            else:
                prose = G.deterministic_prose(payload)
                guard_info = {"ok": True, "template": True, "reason": verdict.reason}
        except Exception as exc:  # noqa: BLE001
            prose = G.deterministic_prose(payload)
            guard_info = {"ok": True, "template": True, "reason": f"writer_fallback:{type(exc).__name__}"}

    # 7. Update conversation memory when query succeeded or hit unsupported dimension
    new_mem = dict(mem)
    if payload.status in ("ok", "unsupported"):
        if payload.kpi_name and payload.kpi_name not in ("Rollout & Module Status", "DataOps & Medallion Freshness", "metric_lineage", "kpi_dictionary"):
            new_mem["kpi_name"] = payload.kpi_name
        for k in ("region", "entity", "wave", "business_unit", "module"):
            if chosen_args.get(k) not in (None, ""):
                new_mem[k] = chosen_args[k]
        if chosen_args.get("period_mode") in ("MTD", "LAST_MONTH"):
            new_mem["period"] = chosen_args["period_mode"]
        elif chosen_args.get("period") in ("MTD", "LAST_MONTH", "CURRENT"):
            new_mem["period"] = chosen_args["period"]
        new_mem["last_tool"] = chosen_tool
        new_mem["last_question"] = question

    cols = list(payload.df.columns) if payload.df is not None and not payload.df.empty else []
    recs = payload.df.to_dict(orient="records") if cols else []

    f_used = dict(payload.filters_used or {})
    f_used.update({
        "kpi": payload.kpi_name or chosen_args.get("kpi_name", "ALL"),
        "period": payload.period_label or "Current",
        "persona": scope.display_name,
        "rls": scope.scope_label,
        "as_of_date": as_of.isoformat(),
        "freshness_ts": payload.freshness_ts,
        "applied": applied,
        "carried_over": carried,
    })

    ans = AgentAnswer(
        status=payload.status,
        answer_markdown=prose,
        table_columns=cols,
        table_records=recs,
        chart_spec=payload.chart_spec or {},
        filters_used=f_used,
        warnings=payload.warnings or [],
        sql_used=[payload.compiled_sql] if payload.compiled_sql else [],
        followups=_build_followups(payload),
        diagnostics={
            "request_id": req_id,
            "via_mcp": payload.via_mcp,
            "tool_calls": [{"name": chosen_tool, "arguments": chosen_args}],
            "tool_choice_source": tool_source,
            "lineage_id": payload.lineage_id,
            "freshness_ts": payload.freshness_ts,
            "guardrail": guard_info,
            "model": "rules" if use_rules else model,
            "latency_s": round(time.time() - t0, 2),
        },
    )
    return ans, new_mem
