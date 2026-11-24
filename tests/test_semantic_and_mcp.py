"""Semantic layer, non-additivity invariants, Row-Level Security, and JSON-RPC MCP server tests."""
from __future__ import annotations

import pytest

from app.semantic import service as Svc
from mcp_server.server import ALLOWED_TOOLS, handle_jsonrpc, invoke_tool


def test_non_additive_employees_logging_in_across_waves_and_entities():
    ov = Svc.get_core_adoption_current(kpi_name="ALL")
    ov_users = int(ov.df.loc[ov.df["KPI Name"] == "Employees Logging In", "All-Time Cumulative"].iloc[0])

    by_w = Svc.get_core_adoption_by_wave("Employees Logging In", period="CURRENT")
    wave_sum = int(by_w.df["Employees Logging In"].sum())
    assert wave_sum > ov_users, "Cross-wave users must cause naive wave sum to exceed deduplicated OVERALL"
    assert f"{ov_users:,}" in by_w.headline

    by_e = Svc.get_core_adoption_by_entity("Employees Logging In", period="CURRENT")
    ent_sum = int(by_e.df["Employees Logging In"].sum())
    assert ent_sum > ov_users, "Cross-entity users must cause naive entity sum to exceed deduplicated OVERALL"


def test_unsupported_bu_attribution_for_logins_and_timecards():
    r_login = Svc.get_core_adoption_by_business_unit("Employees Logging In")
    assert r_login.status == "unsupported"
    assert "unavailable" in r_login.headline.lower()

    r_tc = Svc.get_core_adoption_by_business_unit("Timesheets Submitted")
    assert r_tc.status == "unsupported"
    assert "multiple project tasks" in " ".join(r_tc.facts).lower()

    # Supported BU breakdowns work cleanly
    r_proj = Svc.get_core_adoption_by_business_unit("Contracts Created")
    assert r_proj.status == "ok"
    assert len(r_proj.df) == 10

    r_exp = Svc.get_core_adoption_by_business_unit("Expense Reports")
    assert r_exp.status == "ok"
    assert len(r_exp.df) == 10


def test_rollout_status_distinguishes_live_uninstrumented_and_zero_activity():
    res = Svc.get_core_rollout_status()
    assert res.status == "ok"
    assert "SIMULATED EXTENSION" in res.headline
    evidences = set(res.df["Activity Evidence"].unique())
    assert "Observed activity" in evidences
    assert "LIVE — ZERO observed events" in evidences
    assert "Not instrumented in pilot" in evidences

    zero_only = Svc.get_core_rollout_status(module="EXPENSES", rollout_status="LIVE", zero_activity_only=True)
    assert len(zero_only.df) == 1
    assert zero_only.df["RolloutId"].iloc[0] == "ROL-LATAM-EXP"


def test_persona_row_level_security_enforced():
    # Americas Operations VP can query AMER & Wave 1, blocked on EMEA & Wave 2
    ok_amer = Svc.get_core_adoption_current("Contracts Created", region="AMER", user_id="amer_ops_vp")
    assert ok_amer.status == "ok"

    deny_emea = Svc.get_core_adoption_current("Contracts Created", region="EMEA", user_id="amer_ops_vp")
    assert deny_emea.status == "refusal"
    assert "don't have access" in deny_emea.headline

    deny_wave2 = Svc.get_core_adoption_by_entity("Contracts Created", wave=2, user_id="amer_ops_vp")
    assert deny_wave2.status == "refusal"

    # EMEA Rollout Director scoped strictly to EMEA / Wave 2
    emea_waves = Svc.get_core_adoption_by_wave("Contracts Created", user_id="emea_rollout_director")
    assert emea_waves.status == "ok"
    assert list(emea_waves.df["Rollout Wave"]) == ["Wave 2"]


def test_mcp_jsonrpc_protocol_and_security_allowlist():
    init = handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "core-pulse-mcp"

    tlist = handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tlist["result"]["tools"]}
    assert names == ALLOWED_TOOLS
    assert len(names) == 10

    rlist = handle_jsonrpc({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert len(rlist["result"]["resources"]) == 6

    rread = handle_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "core://metadata/semantic-rules"}})
    assert "Employees Logging In" in rread["result"]["contents"][0]["text"]

    tcall = handle_jsonrpc({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "get_core_adoption_current", "arguments": {"kpi_name": "ALL", "sql": "DROP TABLE gold.coreadoption_event"}},
    })
    assert tcall["result"]["status"] == "ok"
    assert tcall["result"]["via_mcp"] is True

    # Arbitrary SQL tool rejected
    bad = handle_jsonrpc({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "execute_raw_sql", "arguments": {"query": "SELECT * FROM source_sim.app_user"}},
    })
    assert "error" in bad

    with pytest.raises(ValueError):
        invoke_tool("run_shell", {"cmd": "whoami"})
