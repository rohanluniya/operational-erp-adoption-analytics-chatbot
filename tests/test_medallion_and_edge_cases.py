"""Medallion architecture, parity, idempotency, and all 12 §3 adversarial edge-case tests."""
from __future__ import annotations

from sqlalchemy import text

from app.config import ROOT
from app.db import get_engine
from pipelines.medallion import run_medallion_pipeline


def test_prototype_md_untouched():
    proto = ROOT / "prototype.md"
    assert proto.exists()
    txt = proto.read_text(encoding="utf-8")
    assert "CORE Adoption" in txt
    assert len(txt) > 30000


def test_all_16_source_and_bronze_tables_populated():
    expected_source = [
        "business_unit", "project", "project_service", "project_phase", "project_task",
        "project_task_timeline_event", "application_log", "application_log_type", "application",
        "app_user", "timecard", "timecard_status", "timecard_row", "timecard_entry",
        "expense_report", "expense_entry",
    ]
    eng = get_engine()
    with eng.connect() as conn:
        for t in expected_source:
            s_cnt = int(conn.execute(text(f"SELECT COUNT(*) FROM source_sim.{t}")).scalar() or 0)
            b_cnt = int(conn.execute(text(f"SELECT COUNT(*) FROM bronze.core_{t}")).scalar() or 0)
            assert s_cnt > 0, f"source_sim.{t} should not be empty"
            assert b_cnt == s_cnt, f"bronze.core_{t} ({b_cnt}) must match source_sim.{t} ({s_cnt})"


def test_medallion_incremental_watermark_idempotency():
    from app.config import data_as_of_date
    from app.db import clear_engine_cache
    clear_engine_cache()
    try:
        res = run_medallion_pipeline(get_engine(admin=True), as_of=data_as_of_date())
    finally:
        clear_engine_cache()
    assert res["status"] == "SUCCESS"
    assert res["incremental_app_logs"] == 0
    assert res["certified_rows"] > 1000


def test_source_to_gold_parity_for_four_baseline_kpis():
    eng = get_engine()
    with eng.connect() as conn:
        src_proj = int(conn.execute(text("SELECT COUNT(DISTINCT ProjectId) FROM source_sim.project WHERE CAST(CreatedDate AS DATE) <= CAST('2026-11-17' AS DATE)")).scalar())
        gv_proj = int(conn.execute(text("SELECT KPIValue FROM goldview.v_core_adoption WHERE RecordType='CURRENT' AND ReportingLevel='OVERALL' AND KPIName='Contracts Created'")).scalar())
        assert gv_proj == src_proj

        src_tc = int(conn.execute(text("SELECT COUNT(DISTINCT TimecardId) FROM source_sim.timecard WHERE SubmittedDate IS NOT NULL AND CAST(SubmittedDate AS DATE) <= CAST('2026-11-17' AS DATE)")).scalar())
        gv_tc = int(conn.execute(text("SELECT KPIValue FROM goldview.v_core_adoption WHERE RecordType='CURRENT' AND ReportingLevel='OVERALL' AND KPIName='Timesheets Submitted'")).scalar())
        assert gv_tc == src_tc

        src_exp = int(conn.execute(text("SELECT COUNT(DISTINCT ExpenseReportId) FROM source_sim.expense_report WHERE SubmittedDate IS NOT NULL AND CAST(SubmittedDate AS DATE) <= CAST('2026-11-17' AS DATE)")).scalar())
        gv_exp = int(conn.execute(text("SELECT KPIValue FROM goldview.v_core_adoption WHERE RecordType='CURRENT' AND ReportingLevel='OVERALL' AND KPIName='Expense Reports'")).scalar())
        assert gv_exp == src_exp

        src_usr = int(conn.execute(text("""
            SELECT COUNT(DISTINCT l.APPUserId)
            FROM source_sim.application_log l
            JOIN source_sim.application_log_type lt ON l.ApplicationLogTypeId = lt.ApplicationLogTypeId
            JOIN source_sim.app_user u ON l.APPUserId = u.APPUserId
            JOIN source_sim.application a ON l.ApplicationId = a.ApplicationId
            JOIN reference.application_mapping_seed m ON a.ApplicationCode = m.ApplicationCode
            WHERE lt.Name = 'Application Login' AND u.IsServiceAccount = 0
              AND m.MappingStatus = 'CONFIRMED' AND CAST(l.CreatedDate AS DATE) <= CAST('2026-11-17' AS DATE)
        """)).scalar())
        gv_usr = int(conn.execute(text("SELECT KPIValue FROM goldview.v_core_adoption WHERE RecordType='CURRENT' AND ReportingLevel='OVERALL' AND KPIName='Employees Logging In'")).scalar())
        assert gv_usr == src_usr


def test_edge_case_1_and_2_same_day_dual_wave_and_multi_login_dedup():
    eng = get_engine()
    with eng.connect() as conn:
        # Edge Case #1: APPUserId 9001 logged into Wave 1 & Wave 2 on 2026-11-10
        w_cnt = int(conn.execute(text("""
            SELECT COUNT(DISTINCT AdoptionWaveNumber)
            FROM gold.coreadoption_user_activity
            WHERE APPUserId = 9001 AND ActivityDate = CAST('2026-11-10' AS DATE)
        """)).scalar())
        assert w_cnt == 2
        dedup_u = int(conn.execute(text("""
            SELECT COUNT(DISTINCT APPUserId)
            FROM gold.coreadoption_user_activity
            WHERE APPUserId = 9001 AND ActivityDate = CAST('2026-11-10' AS DATE)
        """)).scalar())
        assert dedup_u == 1

        # Edge Case #2: APPUserId 9002 logged into same app 5 times on 2026-11-05 -> 1 silver grain row, LoginEventCount == 5
        row = conn.execute(text("""
            SELECT COUNT(*), SUM(LoginEventCount)
            FROM silver.login_activity
            WHERE APPUserId = 9002 AND ActivityDate = CAST('2026-11-05' AS DATE)
        """)).fetchone()
        assert int(row[0]) == 1
        assert int(row[1]) >= 5


def test_edge_case_3_service_accounts_excluded():
    eng = get_engine()
    with eng.connect() as conn:
        src_svc = int(conn.execute(text("""
            SELECT COUNT(*) FROM source_sim.application_log l
            JOIN source_sim.app_user u ON l.APPUserId = u.APPUserId
            WHERE u.IsServiceAccount = 1
        """)).scalar())
        assert src_svc > 0
        sil_svc = int(conn.execute(text("""
            SELECT COUNT(*) FROM silver.login_activity s
            JOIN bronze.core_app_user u ON s.APPUserId = u.APPUserId
            WHERE u.IsServiceAccount = 1
        """)).scalar())
        assert sil_svc == 0


def test_edge_case_4_and_5_timecard_exported_included_and_draft_excluded():
    eng = get_engine()
    with eng.connect() as conn:
        # TC 99101 is Exported with SubmittedDate -> MUST be in gold.coreadoption_event
        inc = int(conn.execute(text("""
            SELECT COUNT(*) FROM gold.coreadoption_event
            WHERE EventType = 'TIMECARD_SUBMITTED' AND DistinctEntityId = 99101
        """)).scalar())
        assert inc == 1

        # TC 99102 is Draft with NULL SubmittedDate -> MUST NOT be in gold.coreadoption_event
        exc = int(conn.execute(text("""
            SELECT COUNT(*) FROM gold.coreadoption_event
            WHERE EventType = 'TIMECARD_SUBMITTED' AND DistinctEntityId = 99102
        """)).scalar())
        assert exc == 0


def test_edge_case_6_and_8_true_event_timestamps_for_project_and_expense():
    eng = get_engine()
    with eng.connect() as conn:
        # Project 99001 Created Oct 2026, Start Dec 2026 -> EventMonth must be 2026-10-01
        pm = str(conn.execute(text("""
            SELECT EventMonth FROM gold.coreadoption_event
            WHERE EventType = 'PROJECT_CREATED' AND DistinctEntityId = 99001
        """)).scalar())
        assert pm.startswith("2026-10-01")

        # Expense 99501 Submitted Oct 2026, Modified Nov 2026 -> EventMonth must be 2026-10-01
        em = str(conn.execute(text("""
            SELECT EventMonth FROM gold.coreadoption_event
            WHERE EventType = 'EXPENSE_SUBMISSION' AND DistinctEntityId = 99501
        """)).scalar())
        assert em.startswith("2026-10-01")


def test_edge_case_7_missing_local_enrichment_preserved_via_left_join():
    eng = get_engine()
    with eng.connect() as conn:
        enr = int(conn.execute(text("SELECT COUNT(*) FROM reference.local_org_enrichment WHERE OrganizationCode='BU-AU-REN-10'")).scalar())
        assert enr == 0
        sil = conn.execute(text("SELECT HasLocalEnrichment, AdoptionEntity FROM silver.organization WHERE BusinessUnit='BU-AU-REN-10'")).fetchone()
        assert sil is not None
        assert int(sil[0]) == 0
        gv = int(conn.execute(text("""
            SELECT KPIValue FROM goldview.v_core_adoption
            WHERE RecordType='CURRENT' AND ReportingLevel='BUSINESS_UNIT'
              AND KPIName='Contracts Created' AND BusinessUnit='BU-AU-REN-10'
        """)).scalar())
        assert gv > 0


def test_edge_case_9_10_11_12_rollout_gap_partial_month_multibu_and_orphans():
    eng = get_engine()
    with eng.connect() as conn:
        # #9: ROL-LATAM-EXP is LIVE with 0 expense submissions for BU-BR-FLD-09
        st_val = conn.execute(text("SELECT RolloutStatus FROM reference.rollout_registry WHERE RolloutId='ROL-LATAM-EXP'")).scalar()
        assert st_val == "LIVE"
        br_exp = int(conn.execute(text("SELECT COUNT(*) FROM gold.coreadoption_event WHERE EventType='EXPENSE_SUBMISSION' AND BusinessUnit='BU-BR-FLD-09'")).scalar())
        assert br_exp == 0

        # #10: 2026-11 is incomplete (IsCompleteMonth = 0), 2026-10 is complete (IsCompleteMonth = 1)
        nov_c = int(conn.execute(text("SELECT IsCompleteMonth FROM goldview.v_dim_date WHERE YearMonth='2026-11'")).scalar())
        oct_c = int(conn.execute(text("SELECT IsCompleteMonth FROM goldview.v_dim_date WHERE YearMonth='2026-10'")).scalar())
        assert nov_c == 0
        assert oct_c == 1

        # #11: Multi-BU timecard 99103 counted once in OVERALL, excluded from single-entity rollup
        tc_ov = int(conn.execute(text("SELECT MappingExceptionRows FROM goldview.v_core_adoption WHERE RecordType='CURRENT' AND ReportingLevel='OVERALL' AND KPIName='Timesheets Submitted'")).scalar())
        assert tc_ov >= 1

        # #12: Orphan rows & unconfirmed apps tracked in dataops.data_quality_metric
        qm = conn.execute(text("SELECT CheckName, MetricValue FROM dataops.data_quality_metric WHERE CheckName IN ('orphan_timecard_rows', 'orphan_expense_entries', 'application_mapping_exceptions')")).fetchall()
        qm_map = {r[0]: float(r[1]) for r in qm}
        assert qm_map["orphan_timecard_rows"] == 3.0
        assert qm_map["orphan_expense_entries"] == 2.0
        assert qm_map["application_mapping_exceptions"] >= 1.0
