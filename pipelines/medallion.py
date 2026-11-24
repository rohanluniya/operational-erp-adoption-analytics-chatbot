"""Governed Medallion + DataOps pipeline for CORE Pulse (DuckDB & SQL Server 2022 compatible).

Builds real, inspectable schemas and tables:
  1. source_sim.*   — 16 normalized synthetic CORE tables
  2. reference.*    — local_org_enrichment, application_mapping_seed, module_catalog, rollout_registry, rls grants
  3. dataops.*      — pipeline_registry, pipeline_run, pipeline_step_run, watermark, data_quality_metric
  4. bronze.core_*  — 16 source-aligned tables with SourceExtractDateTime, PipelineRunId & ApplicationLogId watermark
  5. silver.*       — 10 conformed tables (LEFT JOIN org enrichment, service-account exclusion, durable SubmittedDate)
  6. gold.*         — coreadoption_kpi_daily, coreadoption_user_activity, coreadoption_event + internal views
  7. goldview.*     — v_core_adoption & v_dim_date (certified consumer datasets)

All permanent-table SQL inserts specify explicit target column lists (never INSERT ... SELECT *).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from app.config import data_as_of_date, demo_seed
from pipelines.synthetic_data import generate_all

PIPELINE_NAME = "core_pulse_adoption_medallion"


def _is_mssql(engine: Engine) -> bool:
    return engine.dialect.name == "mssql"


def _ensure_schemas(conn, is_ms: bool) -> None:
    for sc in ("source_sim", "bronze", "silver", "gold", "goldview", "reference", "dataops", "rls", "app"):
        if is_ms:
            conn.execute(text(f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{sc}') EXEC('CREATE SCHEMA [{sc}]');"))
        else:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {sc};"))


def _drop_if_exists(conn, full_name: str, is_ms: bool, kind: str = "TABLE") -> None:
    schema, obj = full_name.split(".", 1)
    if is_ms:
        code = "'V'" if kind == "VIEW" else "'U'"
        conn.execute(text(f"IF OBJECT_ID('{schema}.{obj}', {code}) IS NOT NULL DROP {kind} {schema}.{obj};"))
    else:
        conn.execute(text(f"DROP {kind} IF EXISTS {schema}.{obj} CASCADE;"))


def _t(is_ms: bool, duck_type: str, ms_type: str) -> str:
    return ms_type if is_ms else duck_type


def create_medallion_ddl(engine: Engine, reset_all: bool = True) -> None:
    """Create DataOps, Bronze, Silver, Gold, Reference, RLS, and Certified Goldview objects."""
    is_ms = _is_mssql(engine)
    V = lambda n: _t(is_ms, f"VARCHAR({n})", f"NVARCHAR({n})")
    DT = _t(is_ms, "TIMESTAMP", "DATETIME2")
    BIG = "BIGINT"
    INT = "INTEGER"
    DEC = "DECIMAL(18,2)"

    ddl_tables = [
        # ---------------- DATAOPS ----------------
        ("dataops.pipeline_registry", f"""
            CREATE TABLE dataops.pipeline_registry (
                PipelineName {V(100)} PRIMARY KEY,
                DomainName {V(60)} NOT NULL,
                Description {V(300)} NOT NULL,
                OwnerTeam {V(100)} NOT NULL,
                TargetView {V(100)} NOT NULL,
                IsActive {INT} NOT NULL,
                CreatedDateTime {DT} NOT NULL
            )"""),
        ("dataops.pipeline_run", f"""
            CREATE TABLE dataops.pipeline_run (
                PipelineRunId {BIG} PRIMARY KEY,
                PipelineName {V(100)} NOT NULL,
                AsOfDate DATE NOT NULL,
                RunStatus {V(20)} NOT NULL,
                StartedDateTime {DT} NOT NULL,
                CompletedDateTime {DT} NULL,
                ErrorMessage {V(500)} NULL
            )"""),
        ("dataops.pipeline_step_run", f"""
            CREATE TABLE dataops.pipeline_step_run (
                StepRunId {BIG} PRIMARY KEY,
                PipelineRunId {BIG} NOT NULL,
                StepNumber {INT} NOT NULL,
                StepName {V(120)} NOT NULL,
                RunStatus {V(20)} NOT NULL,
                RowsAffected {BIG} NOT NULL,
                StartedDateTime {DT} NOT NULL,
                CompletedDateTime {DT} NULL,
                ErrorMessage {V(500)} NULL
            )"""),
        ("dataops.watermark", f"""
            CREATE TABLE dataops.watermark (
                PipelineName {V(100)} NOT NULL,
                SourceObject {V(120)} NOT NULL,
                WatermarkType {V(30)} NOT NULL,
                BigIntWatermark {BIG} NULL,
                DateTimeWatermark {DT} NULL,
                LastSuccessfulRunId {BIG} NULL,
                ModifiedDateTime {DT} NOT NULL,
                PRIMARY KEY (PipelineName, SourceObject)
            )"""),
        ("dataops.data_quality_metric", f"""
            CREATE TABLE dataops.data_quality_metric (
                QualityMetricId {BIG} PRIMARY KEY,
                PipelineRunId {BIG} NOT NULL,
                CheckName {V(120)} NOT NULL,
                CheckCategory {V(40)} NOT NULL,
                CheckStatus {V(20)} NOT NULL,
                MetricValue {BIG} NOT NULL,
                ExpectedValue {BIG} NULL,
                Details {V(300)} NOT NULL,
                LoggedDateTime {DT} NOT NULL
            )"""),

        # ---------------- RLS ACCESS ----------------
        ("rls.app_persona", f"""
            CREATE TABLE rls.app_persona (
                user_id {V(50)} PRIMARY KEY,
                display_name {V(100)} NOT NULL,
                role_title {V(100)} NOT NULL,
                scope_label {V(120)} NOT NULL
            )"""),
        ("rls.user_region_access", f"""
            CREATE TABLE rls.user_region_access (
                user_id {V(50)} NOT NULL,
                region_code {V(20)} NOT NULL,
                PRIMARY KEY (user_id, region_code)
            )"""),

        # ---------------- BRONZE (16 core_* tables) ----------------
        ("bronze.core_business_unit", f"""
            CREATE TABLE bronze.core_business_unit (
                BusinessUnitId {INT} PRIMARY KEY,
                BusinessUnit {V(30)} NOT NULL,
                BusinessUnitName {V(120)} NOT NULL,
                CompanyCode {V(30)} NOT NULL,
                CompanyName {V(120)} NOT NULL,
                CountryCode {V(10)} NOT NULL,
                Status {V(20)} NOT NULL,
                Type {V(30)} NOT NULL,
                Active {INT} NOT NULL,
                RegionCode {V(20)} NOT NULL,
                RegionDesc {V(80)} NOT NULL,
                CreatedDate {DT} NOT NULL,
                ModifiedDate {DT} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_project", f"""
            CREATE TABLE bronze.core_project (
                ProjectId {BIG} PRIMARY KEY,
                CreatedDate {DT} NOT NULL,
                BusinessUnit {V(30)} NOT NULL,
                ProjectName {V(160)} NOT NULL,
                ParentContractCode {V(50)} NULL,
                FlexContractNumber {V(50)} NULL,
                ProjectStatusId {INT} NOT NULL,
                ProjectStartDate DATE NULL,
                ActualEndDate DATE NULL,
                Billable {INT} NOT NULL,
                IsClosed {INT} NOT NULL,
                CurrencyCode {V(10)} NOT NULL,
                ModifiedDate {DT} NOT NULL,
                ProposedStartDate DATE NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_project_service", f"""
            CREATE TABLE bronze.core_project_service (
                ProjectServiceId {BIG} PRIMARY KEY,
                ProjectId {BIG} NOT NULL,
                ServiceCode {V(30)} NOT NULL,
                ServiceName {V(100)} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_project_phase", f"""
            CREATE TABLE bronze.core_project_phase (
                ProjectPhaseId {BIG} PRIMARY KEY,
                ProjectServiceId {BIG} NOT NULL,
                PhaseName {V(100)} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_project_task", f"""
            CREATE TABLE bronze.core_project_task (
                ProjectTaskId {BIG} PRIMARY KEY,
                ProjectPhaseId {BIG} NOT NULL,
                TaskName {V(100)} NOT NULL,
                ActualHours {DEC} NOT NULL,
                AssignedUserId {BIG} NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_project_task_timeline_event", f"""
            CREATE TABLE bronze.core_project_task_timeline_event (
                TimelineEventId {BIG} PRIMARY KEY,
                ProjectTaskId {BIG} NOT NULL,
                EventType {V(40)} NOT NULL,
                EventDateTime {DT} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_application", f"""
            CREATE TABLE bronze.core_application (
                ApplicationId {INT} PRIMARY KEY,
                ApplicationCode {V(40)} NOT NULL,
                ApplicationName {V(120)} NOT NULL,
                IsActive {INT} NOT NULL,
                CreatedDate {DT} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_application_log_type", f"""
            CREATE TABLE bronze.core_application_log_type (
                ApplicationLogTypeId {INT} PRIMARY KEY,
                Name {V(60)} NOT NULL,
                Description {V(160)} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_app_user", f"""
            CREATE TABLE bronze.core_app_user (
                APPUserId {BIG} PRIMARY KEY,
                EmployeeId {V(30)} NULL,
                ContactId {BIG} NULL,
                LDAPId {V(120)} NULL,
                IsServiceAccount {INT} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_application_log", f"""
            CREATE TABLE bronze.core_application_log (
                ApplicationLogId {BIG} PRIMARY KEY,
                ApplicationLogTypeId {INT} NOT NULL,
                ApplicationId {INT} NOT NULL,
                APPUserId {BIG} NOT NULL,
                CreatedDate {DT} NOT NULL,
                ClientHost {V(60)} NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_timecard_status", f"""
            CREATE TABLE bronze.core_timecard_status (
                TimecardStatusId {INT} PRIMARY KEY,
                StatusName {V(40)} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_timecard", f"""
            CREATE TABLE bronze.core_timecard (
                TimecardId {BIG} PRIMARY KEY,
                APPUserId {BIG} NOT NULL,
                PeriodStartDate DATE NOT NULL,
                TimecardStatusId {INT} NOT NULL,
                CreatedDate {DT} NOT NULL,
                SubmittedDate {DT} NULL,
                ApprovedDate {DT} NULL,
                ExportedDate {DT} NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_timecard_row", f"""
            CREATE TABLE bronze.core_timecard_row (
                TimecardRowId {BIG} PRIMARY KEY,
                TimecardId {BIG} NOT NULL,
                ProjectTaskId {BIG} NULL,
                ContractCode {V(50)} NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_timecard_entry", f"""
            CREATE TABLE bronze.core_timecard_entry (
                TimecardEntryId {BIG} PRIMARY KEY,
                TimecardRowId {BIG} NOT NULL,
                EntryDate DATE NOT NULL,
                HoursWorked {DEC} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_expense_report", f"""
            CREATE TABLE bronze.core_expense_report (
                ExpenseReportId {BIG} PRIMARY KEY,
                APPUserId {BIG} NOT NULL,
                BusinessUnit {V(30)} NOT NULL,
                ReportStatus {V(30)} NOT NULL,
                CreatedDate {DT} NOT NULL,
                SubmittedDate {DT} NULL,
                ModifiedDate {DT} NOT NULL,
                CurrencyCode {V(10)} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("bronze.core_expense_entry", f"""
            CREATE TABLE bronze.core_expense_entry (
                ExpenseEntryId {BIG} PRIMARY KEY,
                ExpenseReportId {BIG} NOT NULL,
                ProjectTaskId {BIG} NULL,
                BusinessUnit {V(30)} NOT NULL,
                AmountUSD {DEC} NOT NULL,
                ExpenseCategory {V(50)} NOT NULL,
                SourceExtractDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),

        # ---------------- SILVER (10 conformed objects) ----------------
        ("silver.organization", f"""
            CREATE TABLE silver.organization (
                BusinessUnit {V(30)} PRIMARY KEY,
                BusinessUnitId {INT} NOT NULL,
                BusinessUnitName {V(120)} NOT NULL,
                CompanyCode {V(30)} NOT NULL,
                CompanyName {V(120)} NOT NULL,
                CountryCode {V(10)} NOT NULL,
                RegionCode {V(20)} NOT NULL,
                RegionDesc {V(80)} NOT NULL,
                AdoptionEntity {V(100)} NOT NULL,
                AdoptionWaveNumber {INT} NOT NULL,
                AdoptionWaveLabel {V(30)} NOT NULL,
                HasLocalEnrichment {INT} NOT NULL,
                Active {INT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.application_mapping", f"""
            CREATE TABLE silver.application_mapping (
                ApplicationCode {V(40)} PRIMARY KEY,
                ApplicationId {INT} NOT NULL,
                ApplicationName {V(120)} NOT NULL,
                AdoptionEntity {V(100)} NOT NULL,
                AdoptionWaveNumber {INT} NOT NULL,
                AdoptionWaveLabel {V(30)} NOT NULL,
                BusinessUnit {V(30)} NULL,
                RegionCode {V(20)} NOT NULL,
                MappingStatus {V(20)} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.project", f"""
            CREATE TABLE silver.project (
                ProjectId {BIG} PRIMARY KEY,
                CreatedDate {DT} NOT NULL,
                CreatedMonth DATE NOT NULL,
                ProjectStartDate DATE NULL,
                BusinessUnit {V(30)} NOT NULL,
                BusinessUnitName {V(120)} NOT NULL,
                CompanyCode {V(30)} NOT NULL,
                CompanyName {V(120)} NOT NULL,
                CountryCode {V(10)} NOT NULL,
                RegionCode {V(20)} NOT NULL,
                RegionDesc {V(80)} NOT NULL,
                AdoptionEntity {V(100)} NOT NULL,
                AdoptionWaveNumber {INT} NOT NULL,
                ProjectName {V(160)} NOT NULL,
                IsClosed {INT} NOT NULL,
                ProjectCountIndicator {INT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.task_activity", f"""
            CREATE TABLE silver.task_activity (
                ProjectTaskId {BIG} PRIMARY KEY,
                ProjectPhaseId {BIG} NOT NULL,
                ProjectServiceId {BIG} NOT NULL,
                ProjectId {BIG} NOT NULL,
                BusinessUnit {V(30)} NOT NULL,
                ActualHours {DEC} NOT NULL,
                HasTaskHoursIndicator {INT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.login_activity", f"""
            CREATE TABLE silver.login_activity (
                ActivityDate DATE NOT NULL,
                APPUserId {BIG} NOT NULL,
                ApplicationId {INT} NOT NULL,
                EmployeeId {V(30)} NULL,
                ApplicationCode {V(40)} NOT NULL,
                AdoptionEntity {V(100)} NOT NULL,
                AdoptionWaveNumber {INT} NOT NULL,
                RegionCode {V(20)} NOT NULL,
                MappingStatus {V(20)} NOT NULL,
                LoginEventCount {INT} NOT NULL,
                FirstLoginDateTime {DT} NOT NULL,
                LastLoginDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL,
                PRIMARY KEY (ActivityDate, APPUserId, ApplicationId)
            )"""),
        ("silver.timecard", f"""
            CREATE TABLE silver.timecard (
                TimecardId {BIG} PRIMARY KEY,
                APPUserId {BIG} NOT NULL,
                PeriodStartDate DATE NOT NULL,
                TimecardStatusId {INT} NOT NULL,
                StatusName {V(40)} NOT NULL,
                SubmittedDate {DT} NULL,
                SubmittedMonth DATE NULL,
                IsSubmitted {INT} NOT NULL,
                AdoptionEntity {V(100)} NULL,
                AdoptionWaveNumber {INT} NULL,
                RegionCode {V(20)} NULL,
                HasSingleEntityAttribution {INT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.timecard_row", f"""
            CREATE TABLE silver.timecard_row (
                TimecardRowId {BIG} PRIMARY KEY,
                TimecardId {BIG} NOT NULL,
                ProjectTaskId {BIG} NULL,
                BusinessUnit {V(30)} NULL,
                IsOrphanTimecard {INT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.timecard_entry", f"""
            CREATE TABLE silver.timecard_entry (
                TimecardEntryId {BIG} PRIMARY KEY,
                TimecardRowId {BIG} NOT NULL,
                TimecardId {BIG} NULL,
                EntryDate DATE NOT NULL,
                HoursWorked {DEC} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.expense_report", f"""
            CREATE TABLE silver.expense_report (
                ExpenseReportId {BIG} PRIMARY KEY,
                APPUserId {BIG} NOT NULL,
                BusinessUnit {V(30)} NOT NULL,
                BusinessUnitName {V(120)} NOT NULL,
                CompanyCode {V(30)} NOT NULL,
                CompanyName {V(120)} NOT NULL,
                CountryCode {V(10)} NOT NULL,
                RegionCode {V(20)} NOT NULL,
                RegionDesc {V(80)} NOT NULL,
                AdoptionEntity {V(100)} NOT NULL,
                AdoptionWaveNumber {INT} NOT NULL,
                ReportStatus {V(30)} NOT NULL,
                SubmittedDate {DT} NOT NULL,
                SubmittedMonth DATE NOT NULL,
                ModifiedDate {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("silver.expense_entry", f"""
            CREATE TABLE silver.expense_entry (
                ExpenseEntryId {BIG} PRIMARY KEY,
                ExpenseReportId {BIG} NOT NULL,
                ProjectTaskId {BIG} NULL,
                BusinessUnit {V(30)} NOT NULL,
                AmountUSD {DEC} NOT NULL,
                ExpenseCategory {V(50)} NOT NULL,
                IsOrphanReport {INT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),

        # ---------------- GOLD (3 core tables + certified backing table) ----------------
        ("gold.coreadoption_kpi_daily", f"""
            CREATE TABLE gold.coreadoption_kpi_daily (
                ActivityDate DATE NOT NULL,
                BusinessUnit {V(30)} NOT NULL,
                KPIName {V(60)} NOT NULL,
                KPIValue {BIG} NOT NULL,
                MappingStatus {V(20)} NOT NULL,
                PipelineRunId {BIG} NOT NULL,
                LoadDateTime {DT} NOT NULL,
                PRIMARY KEY (ActivityDate, BusinessUnit, KPIName)
            )"""),
        ("gold.coreadoption_user_activity", f"""
            CREATE TABLE gold.coreadoption_user_activity (
                ActivityDate DATE NOT NULL,
                APPUserId {BIG} NOT NULL,
                ApplicationId {INT} NOT NULL,
                ApplicationCode {V(40)} NOT NULL,
                AdoptionEntity {V(100)} NOT NULL,
                AdoptionWaveNumber {INT} NOT NULL,
                RegionCode {V(20)} NOT NULL,
                LoginEventCount {INT} NOT NULL,
                PipelineRunId {BIG} NOT NULL,
                LoadDateTime {DT} NOT NULL,
                PRIMARY KEY (ActivityDate, APPUserId, ApplicationId)
            )"""),
        ("gold.coreadoption_event", f"""
            CREATE TABLE gold.coreadoption_event (
                EventKey {V(60)} PRIMARY KEY,
                EventType {V(30)} NOT NULL,
                SourceEventId {BIG} NOT NULL,
                EventDate DATE NOT NULL,
                EventMonth DATE NOT NULL,
                EventDateTime {DT} NOT NULL,
                KPIName {V(60)} NOT NULL,
                EventCount {INT} NOT NULL,
                DistinctEntityId {BIG} NOT NULL,
                APPUserId {BIG} NULL,
                EmployeeId {V(30)} NULL,
                ApplicationId {INT} NULL,
                ApplicationCode {V(40)} NULL,
                ProjectId {BIG} NULL,
                ExpenseReportId {BIG} NULL,
                BusinessUnit {V(30)} NULL,
                BusinessUnitName {V(120)} NULL,
                CompanyCode {V(30)} NULL,
                CompanyName {V(120)} NULL,
                CountryCode {V(10)} NULL,
                RegionCode {V(20)} NULL,
                RegionDesc {V(80)} NULL,
                AdoptionEntity {V(100)} NULL,
                AdoptionWaveNumber {INT} NULL,
                MappingStatus {V(20)} NOT NULL,
                LoadDateTime {DT} NOT NULL,
                PipelineRunId {BIG} NOT NULL
            )"""),
        ("gold.certified_adoption_store", f"""
            CREATE TABLE gold.certified_adoption_store (
                RowId {BIG} PRIMARY KEY,
                RecordType {V(20)} NOT NULL,
                ReportingLevel {V(20)} NOT NULL,
                PeriodDate DATE NOT NULL,
                PeriodDateKey {INT} NOT NULL,
                YearMonth {V(7)} NOT NULL,
                RelativeMonthNumber {INT} NOT NULL,
                IsCompleteMonth {INT} NOT NULL,
                AdoptionWaveNumber {INT} NULL,
                AdoptionWaveLabel {V(30)} NULL,
                AdoptionEntity {V(100)} NULL,
                BusinessUnit {V(30)} NULL,
                BusinessUnitName {V(120)} NULL,
                CompanyCode {V(30)} NULL,
                CompanyName {V(120)} NULL,
                CountryCode {V(10)} NULL,
                RegionCode {V(20)} NULL,
                RegionDesc {V(80)} NULL,
                KPIName {V(60)} NOT NULL,
                KPIValue {BIG} NOT NULL,
                SupportingRowCount {BIG} NOT NULL,
                MappingExceptionRows {BIG} NOT NULL,
                LoadDateTime {DT} NOT NULL
            )"""),
        ("gold.dim_date", f"""
            CREATE TABLE gold.dim_date (
                PeriodDate DATE PRIMARY KEY,
                PeriodDateKey {INT} NOT NULL,
                YearMonth {V(7)} NOT NULL,
                CalendarYear {INT} NOT NULL,
                CalendarMonth {INT} NOT NULL,
                MonthLabel {V(20)} NOT NULL,
                RelativeMonthNumber {INT} NOT NULL,
                IsCompleteMonth {INT} NOT NULL,
                DaysInMonth {INT} NOT NULL,
                ElapsedDays {INT} NOT NULL
            )"""),
    ]

    with engine.begin() as conn:
        _ensure_schemas(conn, is_ms)
        if reset_all:
            for vname in ("goldview.v_core_adoption", "goldview.v_dim_date",
                          "gold.v_core_adoption_current_internal", "gold.v_core_adoption_monthly_internal"):
                _drop_if_exists(conn, vname, is_ms, kind="VIEW")
            for tname, _ in reversed(ddl_tables):
                _drop_if_exists(conn, tname, is_ms, kind="TABLE")
        for _tname, sql in ddl_tables:
            conn.execute(text(sql))

        # Internal Gold views & Certified Goldview consumer views
        _drop_if_exists(conn, "gold.v_core_adoption_current_internal", is_ms, kind="VIEW")
        conn.execute(text("""
            CREATE VIEW gold.v_core_adoption_current_internal AS
            SELECT RecordType, ReportingLevel, PeriodDate, PeriodDateKey, YearMonth, RelativeMonthNumber,
                   IsCompleteMonth, AdoptionWaveNumber, AdoptionWaveLabel, AdoptionEntity, BusinessUnit,
                   BusinessUnitName, CompanyCode, CompanyName, CountryCode, RegionCode, RegionDesc,
                   KPIName, KPIValue, SupportingRowCount, MappingExceptionRows, LoadDateTime
            FROM gold.certified_adoption_store
            WHERE RecordType = 'CURRENT'
        """))

        _drop_if_exists(conn, "gold.v_core_adoption_monthly_internal", is_ms, kind="VIEW")
        conn.execute(text("""
            CREATE VIEW gold.v_core_adoption_monthly_internal AS
            SELECT RecordType, ReportingLevel, PeriodDate, PeriodDateKey, YearMonth, RelativeMonthNumber,
                   IsCompleteMonth, AdoptionWaveNumber, AdoptionWaveLabel, AdoptionEntity, BusinessUnit,
                   BusinessUnitName, CompanyCode, CompanyName, CountryCode, RegionCode, RegionDesc,
                   KPIName, KPIValue, SupportingRowCount, MappingExceptionRows, LoadDateTime
            FROM gold.certified_adoption_store
            WHERE RecordType = 'MONTHLY'
        """))

        _drop_if_exists(conn, "goldview.v_core_adoption", is_ms, kind="VIEW")
        conn.execute(text("""
            CREATE VIEW goldview.v_core_adoption AS
            SELECT RecordType, ReportingLevel, PeriodDate, PeriodDateKey, YearMonth, RelativeMonthNumber,
                   IsCompleteMonth, AdoptionWaveNumber, AdoptionWaveLabel, AdoptionEntity, BusinessUnit,
                   BusinessUnitName, CompanyCode, CompanyName, CountryCode, RegionCode, RegionDesc,
                   KPIName, KPIValue, SupportingRowCount, MappingExceptionRows, LoadDateTime
            FROM gold.certified_adoption_store
        """))

        _drop_if_exists(conn, "goldview.v_dim_date", is_ms, kind="VIEW")
        conn.execute(text("""
            CREATE VIEW goldview.v_dim_date AS
            SELECT PeriodDate, PeriodDateKey, YearMonth, CalendarYear, CalendarMonth, MonthLabel,
                   RelativeMonthNumber, IsCompleteMonth, DaysInMonth, ElapsedDays
            FROM gold.dim_date
        """))


def _write_df_explicit(conn, schema: str, table: str, df: pd.DataFrame, is_ms: bool, truncate_first: bool = True) -> int:
    """Insert DataFrame rows using an explicit target-column INSERT statement (never SELECT *)."""
    if truncate_first:
        conn.execute(text(f"DELETE FROM {schema}.{table};"))
    if df.empty:
        return 0
    cols = list(df.columns)
    col_list = ", ".join(cols)
    if not is_ms and len(df) > 100:
        cur = conn.connection.dbapi_connection.cursor()
        cur.register("_stg_df", df)
        try:
            cur.execute(f"INSERT INTO {schema}.{table} ({col_list}) SELECT {col_list} FROM _stg_df")
        finally:
            try:
                cur.unregister("_stg_df")
            except Exception:  # noqa: BLE001
                pass
            cur.close()
        return len(df)
    bind_list = ", ".join(f":{c}" for c in cols)
    stmt = text(f"INSERT INTO {schema}.{table} ({col_list}) VALUES ({bind_list})")
    recs = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for k, v in row.items():
            if pd.isna(v):
                clean[k] = None
            elif hasattr(v, "to_pydatetime"):
                clean[k] = v.to_pydatetime()
            elif hasattr(v, "item") and not isinstance(v, (str, bytes, date, datetime)):
                clean[k] = v.item()
            else:
                clean[k] = v
        recs.append(clean)
    chunk_sz = 1000
    for i in range(0, len(recs), chunk_sz):
        conn.execute(stmt, recs[i:i + chunk_sz])
    return len(recs)


def seed_source_and_reference(engine: Engine, seed: int | None = None, as_of: date | None = None) -> dict[str, int]:
    """Generate deterministic source_sim.* and reference.* tables."""
    is_ms = _is_mssql(engine)
    frames = generate_all(seed=seed, as_of=as_of)
    source_names = [
        "business_unit", "project", "project_service", "project_phase", "project_task",
        "project_task_timeline_event", "application", "application_log_type", "app_user",
        "application_log", "timecard_status", "timecard", "timecard_row", "timecard_entry",
        "expense_report", "expense_entry",
    ]
    ref_names = ["local_org_enrichment", "bu_wave_governance", "application_mapping_seed", "module_catalog", "rollout_registry"]
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        _ensure_schemas(conn, is_ms)
        for sname in source_names:
            _drop_if_exists(conn, f"source_sim.{sname}", is_ms, kind="TABLE")
            frames[sname].head(0).to_sql(sname, conn, schema="source_sim", if_exists="replace", index=False)
            counts[f"source_sim.{sname}"] = _write_df_explicit(conn, "source_sim", sname, frames[sname], is_ms, truncate_first=True)
        for rname in ref_names:
            _drop_if_exists(conn, f"reference.{rname}", is_ms, kind="TABLE")
            frames[rname].head(0).to_sql(rname, conn, schema="reference", if_exists="replace", index=False)
            counts[f"reference.{rname}"] = _write_df_explicit(conn, "reference", rname, frames[rname], is_ms, truncate_first=True)

        # Populate RLS personas & region grants
        personas = pd.DataFrame([
            {"user_id": "global_program_lead", "display_name": "Global CORE Program Lead",
             "role_title": "VP Global Operations & BI", "scope_label": "All Regions & Waves"},
            {"user_id": "amer_ops_vp", "display_name": "Americas Operations VP",
             "role_title": "Regional Operations VP — Americas", "scope_label": "Americas (AMER · Waves 1 & 4)"},
            {"user_id": "emea_rollout_director", "display_name": "EMEA Rollout Director",
             "role_title": "Regional Rollout Director — EMEA", "scope_label": "Europe, Middle East & Africa (EMEA · Wave 2)"},
        ])
        grants = pd.DataFrame([
            {"user_id": "global_program_lead", "region_code": "AMER"},
            {"user_id": "global_program_lead", "region_code": "EMEA"},
            {"user_id": "global_program_lead", "region_code": "APAC"},
            {"user_id": "amer_ops_vp", "region_code": "AMER"},
            {"user_id": "emea_rollout_director", "region_code": "EMEA"},
        ])
        _write_df_explicit(conn, "rls", "app_persona", personas, is_ms, truncate_first=True)
        _write_df_explicit(conn, "rls", "user_region_access", grants, is_ms, truncate_first=True)
    return counts


def run_medallion_pipeline(engine: Engine, as_of: date | None = None) -> dict:
    """Execute the governed 11-step Bronze -> Silver -> Gold -> Certified View + DataOps pipeline.
    Safe to rerun idempotently: ApplicationLog uses a BigInt watermark in dataops.watermark.
    """
    is_ms = _is_mssql(engine)
    as_of = data_as_of_date() if as_of is None else as_of
    now_ts = datetime(as_of.year, as_of.month, as_of.day, 6, 15, 0)

    with engine.begin() as conn:
        # Ensure pipeline_registry & watermark row exist
        reg_cnt = conn.execute(text("SELECT COUNT(*) FROM dataops.pipeline_registry WHERE PipelineName = :p"),
                               {"p": PIPELINE_NAME}).scalar() or 0
        if reg_cnt == 0:
            conn.execute(text("""
                INSERT INTO dataops.pipeline_registry
                    (PipelineName, DomainName, Description, OwnerTeam, TargetView, IsActive, CreatedDateTime)
                VALUES
                    (:p, 'CORE Adoption', 'Bronze->Silver->Gold->goldview.v_core_adoption governed pipeline',
                     'Rohan Luniya', 'goldview.v_core_adoption', 1, :ts)
            """), {"p": PIPELINE_NAME, "ts": now_ts})

        wm_row = conn.execute(text("""
            SELECT BigIntWatermark FROM dataops.watermark
            WHERE PipelineName = :p AND SourceObject = 'source_sim.application_log'
        """), {"p": PIPELINE_NAME}).fetchone()
        last_wm = int(wm_row[0]) if wm_row and wm_row[0] is not None else 0

        max_run = conn.execute(text("SELECT COALESCE(MAX(PipelineRunId), 1000) FROM dataops.pipeline_run")).scalar()
        run_id = int(max_run) + 1
        max_step = conn.execute(text("SELECT COALESCE(MAX(StepRunId), 5000) FROM dataops.pipeline_step_run")).scalar()
        step_seq = int(max_step)

        conn.execute(text("""
            INSERT INTO dataops.pipeline_run
                (PipelineRunId, PipelineName, AsOfDate, RunStatus, StartedDateTime, CompletedDateTime, ErrorMessage)
            VALUES (:rid, :p, :asof, 'RUNNING', :ts, NULL, NULL)
        """), {"rid": run_id, "p": PIPELINE_NAME, "asof": as_of, "ts": now_ts})

    def log_step(conn, num: int, name: str, rows: int) -> None:
        nonlocal step_seq
        step_seq += 1
        conn.execute(text("""
            INSERT INTO dataops.pipeline_step_run
                (StepRunId, PipelineRunId, StepNumber, StepName, RunStatus, RowsAffected, StartedDateTime, CompletedDateTime, ErrorMessage)
            VALUES (:sid, :rid, :n, :nm, 'SUCCESS', :rw, :ts, :ts2, NULL)
        """), {"sid": step_seq, "rid": run_id, "n": num, "nm": name, "rw": int(rows), "ts": now_ts, "ts2": now_ts})

    try:
        with engine.begin() as conn:
            # -------- STEP 1: Refresh CORE reference & operational Bronze snapshots --------
            snapshot_specs = [
                ("business_unit", "core_business_unit",
                 ["BusinessUnitId", "BusinessUnit", "BusinessUnitName", "CompanyCode", "CompanyName", "CountryCode",
                  "Status", "Type", "Active", "RegionCode", "RegionDesc", "CreatedDate", "ModifiedDate"]),
                ("project", "core_project",
                 ["ProjectId", "CreatedDate", "BusinessUnit", "ProjectName", "ParentContractCode", "FlexContractNumber",
                  "ProjectStatusId", "ProjectStartDate", "ActualEndDate", "Billable", "IsClosed", "CurrencyCode",
                  "ModifiedDate", "ProposedStartDate"]),
                ("project_service", "core_project_service", ["ProjectServiceId", "ProjectId", "ServiceCode", "ServiceName"]),
                ("project_phase", "core_project_phase", ["ProjectPhaseId", "ProjectServiceId", "PhaseName"]),
                ("project_task", "core_project_task", ["ProjectTaskId", "ProjectPhaseId", "TaskName", "ActualHours", "AssignedUserId"]),
                ("project_task_timeline_event", "core_project_task_timeline_event",
                 ["TimelineEventId", "ProjectTaskId", "EventType", "EventDateTime"]),
                ("application", "core_application", ["ApplicationId", "ApplicationCode", "ApplicationName", "IsActive", "CreatedDate"]),
                ("application_log_type", "core_application_log_type", ["ApplicationLogTypeId", "Name", "Description"]),
                ("app_user", "core_app_user", ["APPUserId", "EmployeeId", "ContactId", "LDAPId", "IsServiceAccount"]),
            ]
            step1_rows = 0
            for src_tbl, brz_tbl, cols in snapshot_specs:
                conn.execute(text(f"DELETE FROM bronze.{brz_tbl};"))
                c_str = ", ".join(cols)
                res = conn.execute(text(f"""
                    INSERT INTO bronze.{brz_tbl} ({c_str}, SourceExtractDateTime, PipelineRunId)
                    SELECT {c_str}, :ts, :rid FROM source_sim.{src_tbl}
                """), {"ts": now_ts, "rid": run_id})
                step1_rows += max(0, res.rowcount or 0)
            log_step(conn, 1, "Refresh CORE reference & project bronze snapshots", step1_rows)

            # -------- STEP 2: Incremental ApplicationLog via BigIntWatermark --------
            new_logs = conn.execute(text("""
                INSERT INTO bronze.core_application_log
                    (ApplicationLogId, ApplicationLogTypeId, ApplicationId, APPUserId, CreatedDate, ClientHost, SourceExtractDateTime, PipelineRunId)
                SELECT s.ApplicationLogId, s.ApplicationLogTypeId, s.ApplicationId, s.APPUserId, s.CreatedDate, s.ClientHost, :ts, :rid
                FROM source_sim.application_log s
                WHERE s.ApplicationLogId > :wm
                  AND NOT EXISTS (SELECT 1 FROM bronze.core_application_log b WHERE b.ApplicationLogId = s.ApplicationLogId)
            """), {"ts": now_ts, "rid": run_id, "wm": last_wm})
            inc_rows = max(0, new_logs.rowcount or 0)
            new_max_wm = conn.execute(text("SELECT COALESCE(MAX(ApplicationLogId), 0) FROM bronze.core_application_log")).scalar() or 0
            log_step(conn, 2, "Increment bronze.core_application_log via watermark", inc_rows)

            # -------- STEP 3: Refresh timecard & expense Bronze tables --------
            step3_specs = [
                ("timecard_status", "core_timecard_status", ["TimecardStatusId", "StatusName"]),
                ("timecard", "core_timecard",
                 ["TimecardId", "APPUserId", "PeriodStartDate", "TimecardStatusId", "CreatedDate", "SubmittedDate", "ApprovedDate", "ExportedDate"]),
                ("timecard_row", "core_timecard_row", ["TimecardRowId", "TimecardId", "ProjectTaskId", "ContractCode"]),
                ("timecard_entry", "core_timecard_entry", ["TimecardEntryId", "TimecardRowId", "EntryDate", "HoursWorked"]),
                ("expense_report", "core_expense_report",
                 ["ExpenseReportId", "APPUserId", "BusinessUnit", "ReportStatus", "CreatedDate", "SubmittedDate", "ModifiedDate", "CurrencyCode"]),
                ("expense_entry", "core_expense_entry",
                 ["ExpenseEntryId", "ExpenseReportId", "ProjectTaskId", "BusinessUnit", "AmountUSD", "ExpenseCategory"]),
            ]
            step3_rows = 0
            for src_tbl, brz_tbl, cols in step3_specs:
                conn.execute(text(f"DELETE FROM bronze.{brz_tbl};"))
                c_str = ", ".join(cols)
                res = conn.execute(text(f"""
                    INSERT INTO bronze.{brz_tbl} ({c_str}, SourceExtractDateTime, PipelineRunId)
                    SELECT {c_str}, :ts, :rid FROM source_sim.{src_tbl}
                """), {"ts": now_ts, "rid": run_id})
                step3_rows += max(0, res.rowcount or 0)
            log_step(conn, 3, "Refresh timecard & expense bronze sources", step3_rows)

            # -------- STEP 4: Build conformed silver.organization & silver.application_mapping --------
            # LEFT JOIN optional local_org_enrichment so BU-AU-REN-10 is NEVER lost (Edge Case #7)!
            conn.execute(text("DELETE FROM silver.organization;"))
            wave_lbl = ("'Wave ' + CAST(COALESCE(e.AdoptionWaveNumber, g.AdoptionWaveNumber, 0) AS NVARCHAR(10))"
                        if is_ms else "'Wave ' || CAST(COALESCE(e.AdoptionWaveNumber, g.AdoptionWaveNumber, 0) AS VARCHAR)")
            r4a = conn.execute(text(f"""
                INSERT INTO silver.organization
                    (BusinessUnit, BusinessUnitId, BusinessUnitName, CompanyCode, CompanyName, CountryCode,
                     RegionCode, RegionDesc, AdoptionEntity, AdoptionWaveNumber, AdoptionWaveLabel,
                     HasLocalEnrichment, Active, PipelineRunId)
                SELECT
                    TRIM(b.BusinessUnit),
                    b.BusinessUnitId,
                    b.BusinessUnitName,
                    b.CompanyCode,
                    b.CompanyName,
                    b.CountryCode,
                    b.RegionCode,
                    b.RegionDesc,
                    COALESCE(e.AdoptionEntity, g.AdoptionEntity, 'Unassigned Entity'),
                    COALESCE(e.AdoptionWaveNumber, g.AdoptionWaveNumber, 0),
                    {wave_lbl},
                    CASE WHEN e.OrganizationCode IS NOT NULL THEN 1 ELSE 0 END,
                    b.Active,
                    :rid
                FROM bronze.core_business_unit b
                LEFT JOIN reference.local_org_enrichment e
                    ON TRIM(b.BusinessUnit) = TRIM(e.OrganizationCode)
                LEFT JOIN reference.bu_wave_governance g
                    ON TRIM(b.BusinessUnit) = TRIM(g.BusinessUnit)
            """), {"rid": run_id})

            conn.execute(text("DELETE FROM silver.application_mapping;"))
            wave_app_lbl = ("CASE WHEN m.AdoptionWaveNumber > 0 THEN 'Wave ' + CAST(m.AdoptionWaveNumber AS NVARCHAR(10)) ELSE 'Excluded' END"
                            if is_ms else "CASE WHEN m.AdoptionWaveNumber > 0 THEN 'Wave ' || CAST(m.AdoptionWaveNumber AS VARCHAR) ELSE 'Excluded' END")
            r4b = conn.execute(text(f"""
                INSERT INTO silver.application_mapping
                    (ApplicationCode, ApplicationId, ApplicationName, AdoptionEntity, AdoptionWaveNumber,
                     AdoptionWaveLabel, BusinessUnit, RegionCode, MappingStatus, PipelineRunId)
                SELECT
                    a.ApplicationCode,
                    a.ApplicationId,
                    a.ApplicationName,
                    m.AdoptionEntity,
                    m.AdoptionWaveNumber,
                    {wave_app_lbl},
                    m.BusinessUnit,
                    m.RegionCode,
                    m.MappingStatus,
                    :rid
                FROM bronze.core_application a
                INNER JOIN reference.application_mapping_seed m
                    ON a.ApplicationCode = m.ApplicationCode
            """), {"rid": run_id})
            log_step(conn, 4, "Build silver.organization & silver.application_mapping", (r4a.rowcount or 0) + (r4b.rowcount or 0))

            # -------- STEP 5 & 6: Build Silver atomic & enriched facts (in pandas -> explicit SQL inserts for 100% dialect parity) --------
            df_org = pd.read_sql(text("SELECT * FROM silver.organization"), conn)
            df_amap = pd.read_sql(text("SELECT * FROM silver.application_mapping"), conn)
            df_proj = pd.read_sql(text("SELECT * FROM bronze.core_project"), conn)
            df_psvc = pd.read_sql(text("SELECT * FROM bronze.core_project_service"), conn)
            df_pphs = pd.read_sql(text("SELECT * FROM bronze.core_project_phase"), conn)
            df_ptsk = pd.read_sql(text("SELECT * FROM bronze.core_project_task"), conn)
            df_logs = pd.read_sql(text("SELECT * FROM bronze.core_application_log"), conn)
            df_ltyp = pd.read_sql(text("SELECT * FROM bronze.core_application_log_type"), conn)
            df_usr = pd.read_sql(text("SELECT * FROM bronze.core_app_user"), conn)
            df_tc = pd.read_sql(text("SELECT * FROM bronze.core_timecard"), conn)
            df_tcs = pd.read_sql(text("SELECT * FROM bronze.core_timecard_status"), conn)
            df_tcr = pd.read_sql(text("SELECT * FROM bronze.core_timecard_row"), conn)
            df_tce = pd.read_sql(text("SELECT * FROM bronze.core_timecard_entry"), conn)
            df_exp = pd.read_sql(text("SELECT * FROM bronze.core_expense_report"), conn)
            df_expe = pd.read_sql(text("SELECT * FROM bronze.core_expense_entry"), conn)

            # 5a. silver.project (filter CreatedDate <= as_of)
            df_proj["CreatedDate"] = pd.to_datetime(df_proj["CreatedDate"])
            df_proj = df_proj[df_proj["CreatedDate"].dt.date <= as_of].drop_duplicates(subset=["ProjectId"], keep="last")
            sp = df_proj.merge(df_org, on="BusinessUnit", how="left")
            sp["CreatedMonth"] = sp["CreatedDate"].dt.to_period("M").dt.to_timestamp().dt.date
            sp["ProjectCountIndicator"] = 1
            sp["PipelineRunId"] = run_id
            sp_cols = ["ProjectId", "CreatedDate", "CreatedMonth", "ProjectStartDate", "BusinessUnit",
                       "BusinessUnitName", "CompanyCode", "CompanyName", "CountryCode", "RegionCode",
                       "RegionDesc", "AdoptionEntity", "AdoptionWaveNumber", "ProjectName", "IsClosed",
                       "ProjectCountIndicator", "PipelineRunId"]
            n_sp = _write_df_explicit(conn, "silver", "project", sp[sp_cols], is_ms)

            # 5b. silver.task_activity (Task -> Phase -> Service -> Project)
            ta = (df_ptsk.merge(df_pphs[["ProjectPhaseId", "ProjectServiceId"]], on="ProjectPhaseId", how="inner")
                         .merge(df_psvc[["ProjectServiceId", "ProjectId"]], on="ProjectServiceId", how="inner")
                         .merge(sp[["ProjectId", "BusinessUnit"]], on="ProjectId", how="inner"))
            ta["HasTaskHoursIndicator"] = (ta["ActualHours"] > 0).astype(int)
            ta["PipelineRunId"] = run_id
            ta_cols = ["ProjectTaskId", "ProjectPhaseId", "ProjectServiceId", "ProjectId",
                       "BusinessUnit", "ActualHours", "HasTaskHoursIndicator", "PipelineRunId"]
            n_ta = _write_df_explicit(conn, "silver", "task_activity", ta[ta_cols], is_ms)

            # 5c. silver.login_activity (ActivityDate x APPUserId x ApplicationId; Application Login only; IsServiceAccount = 0)
            login_type_ids = set(df_ltyp.loc[df_ltyp["Name"] == "Application Login", "ApplicationLogTypeId"])
            non_svc_users = df_usr.loc[df_usr["IsServiceAccount"] == 0, ["APPUserId", "EmployeeId"]].drop_duplicates("APPUserId")
            df_logs["CreatedDate"] = pd.to_datetime(df_logs["CreatedDate"])
            lg = df_logs[(df_logs["ApplicationLogTypeId"].isin(login_type_ids)) & (df_logs["CreatedDate"].dt.date <= as_of)].copy()
            lg = lg.merge(non_svc_users, on="APPUserId", how="inner")
            lg = lg.merge(df_amap[["ApplicationId", "ApplicationCode", "AdoptionEntity", "AdoptionWaveNumber", "RegionCode", "MappingStatus"]],
                          on="ApplicationId", how="inner")
            lg["ActivityDate"] = lg["CreatedDate"].dt.date
            sla = (lg.groupby(["ActivityDate", "APPUserId", "ApplicationId", "EmployeeId", "ApplicationCode",
                               "AdoptionEntity", "AdoptionWaveNumber", "RegionCode", "MappingStatus"], dropna=False)
                     .agg(LoginEventCount=("ApplicationLogId", "count"),
                          FirstLoginDateTime=("CreatedDate", "min"),
                          LastLoginDateTime=("CreatedDate", "max"))
                     .reset_index())
            sla["PipelineRunId"] = run_id
            sla_cols = ["ActivityDate", "APPUserId", "ApplicationId", "EmployeeId", "ApplicationCode",
                        "AdoptionEntity", "AdoptionWaveNumber", "RegionCode", "MappingStatus",
                        "LoginEventCount", "FirstLoginDateTime", "LastLoginDateTime", "PipelineRunId"]
            n_sla = _write_df_explicit(conn, "silver", "login_activity", sla[sla_cols], is_ms)
            log_step(conn, 5, "Build base silver project, task & login facts", n_sp + n_ta + n_sla)

            # 6a. silver.timecard_row & silver.timecard_entry (detecting orphan rows!)
            valid_tc_ids = set(df_tc["TimecardId"])
            tcr = df_tcr.merge(ta[["ProjectTaskId", "BusinessUnit"]], on="ProjectTaskId", how="left")
            tcr["IsOrphanTimecard"] = (~tcr["TimecardId"].isin(valid_tc_ids)).astype(int)
            tcr["PipelineRunId"] = run_id
            n_tcr = _write_df_explicit(conn, "silver", "timecard_row",
                                       tcr[["TimecardRowId", "TimecardId", "ProjectTaskId", "BusinessUnit", "IsOrphanTimecard", "PipelineRunId"]], is_ms)

            tce = df_tce.merge(df_tcr[["TimecardRowId", "TimecardId"]], on="TimecardRowId", how="left")
            tce["PipelineRunId"] = run_id
            n_tce = _write_df_explicit(conn, "silver", "timecard_entry",
                                       tce[["TimecardEntryId", "TimecardRowId", "TimecardId", "EntryDate", "HoursWorked", "PipelineRunId"]], is_ms)

            # 6b. silver.timecard: derive conservative Entity/Wave ONLY when all linked tasks belong to a single AdoptionEntity!
            # Multi-BU / multi-entity timecards (Edge Case #9: TC 99103) stay unattributed at Entity/Wave and NEVER duplicate!
            tcr_org = tcr[tcr["IsOrphanTimecard"] == 0].merge(
                df_org[["BusinessUnit", "AdoptionEntity", "AdoptionWaveNumber", "RegionCode"]], on="BusinessUnit", how="left"
            )
            tc_ent_agg = (tcr_org.dropna(subset=["AdoptionEntity"])
                          .groupby("TimecardId")
                          .agg(n_ent=("AdoptionEntity", "nunique"),
                               AdoptionEntity=("AdoptionEntity", "first"),
                               AdoptionWaveNumber=("AdoptionWaveNumber", "first"),
                               RegionCode=("RegionCode", "first"))
                          .reset_index())
            single_ent = tc_ent_agg[tc_ent_agg["n_ent"] == 1].drop(columns=["n_ent"])

            stc = df_tc.drop_duplicates("TimecardId", keep="last").merge(df_tcs, on="TimecardStatusId", how="left")
            stc["SubmittedDate"] = pd.to_datetime(stc["SubmittedDate"])
            # Respect as_of cutoff
            stc.loc[stc["SubmittedDate"].notna() & (stc["SubmittedDate"].dt.date > as_of), "SubmittedDate"] = pd.NaT
            stc["IsSubmitted"] = stc["SubmittedDate"].notna().astype(int)
            stc["SubmittedMonth"] = stc["SubmittedDate"].dt.to_period("M").dt.to_timestamp().dt.date
            stc = stc.merge(single_ent, on="TimecardId", how="left")
            stc["HasSingleEntityAttribution"] = stc["AdoptionEntity"].notna().astype(int)
            stc["PipelineRunId"] = run_id
            stc_cols = ["TimecardId", "APPUserId", "PeriodStartDate", "TimecardStatusId", "StatusName",
                        "SubmittedDate", "SubmittedMonth", "IsSubmitted", "AdoptionEntity", "AdoptionWaveNumber",
                        "RegionCode", "HasSingleEntityAttribution", "PipelineRunId"]
            n_stc = _write_df_explicit(conn, "silver", "timecard", stc[stc_cols], is_ms)

            # 6c. silver.expense_report (submitted reports only for adoption fact) & silver.expense_entry
            valid_exp_ids = set(df_exp["ExpenseReportId"])
            expe = df_expe.copy()
            expe["IsOrphanReport"] = (~expe["ExpenseReportId"].isin(valid_exp_ids)).astype(int)
            expe["PipelineRunId"] = run_id
            n_expe = _write_df_explicit(conn, "silver", "expense_entry",
                                        expe[["ExpenseEntryId", "ExpenseReportId", "ProjectTaskId", "BusinessUnit",
                                              "AmountUSD", "ExpenseCategory", "IsOrphanReport", "PipelineRunId"]], is_ms)

            sexp = df_exp.drop_duplicates("ExpenseReportId", keep="last").copy()
            sexp["SubmittedDate"] = pd.to_datetime(sexp["SubmittedDate"])
            sexp["ModifiedDate"] = pd.to_datetime(sexp["ModifiedDate"])
            sexp = sexp[sexp["SubmittedDate"].notna() & (sexp["SubmittedDate"].dt.date <= as_of)].copy()
            sexp["SubmittedMonth"] = sexp["SubmittedDate"].dt.to_period("M").dt.to_timestamp().dt.date
            sexp = sexp.merge(df_org[["BusinessUnit", "BusinessUnitName", "CompanyCode", "CompanyName",
                                      "CountryCode", "RegionCode", "RegionDesc", "AdoptionEntity", "AdoptionWaveNumber"]],
                              on="BusinessUnit", how="left")
            sexp["PipelineRunId"] = run_id
            sexp_cols = ["ExpenseReportId", "APPUserId", "BusinessUnit", "BusinessUnitName", "CompanyCode",
                         "CompanyName", "CountryCode", "RegionCode", "RegionDesc", "AdoptionEntity",
                         "AdoptionWaveNumber", "ReportStatus", "SubmittedDate", "SubmittedMonth",
                         "ModifiedDate", "PipelineRunId"]
            n_sexp = _write_df_explicit(conn, "silver", "expense_report", sexp[sexp_cols], is_ms)
            log_step(conn, 6, "Build enriched silver timecard & expense facts", n_tcr + n_tce + n_stc + n_expe + n_sexp)

            # -------- STEP 7: Publish gold.coreadoption_kpi_daily & gold.coreadoption_user_activity --------
            kpi_daily_rows = []
            for bu_code, grp in sp.groupby("BusinessUnit"):
                kpi_daily_rows.append({
                    "ActivityDate": as_of, "BusinessUnit": bu_code, "KPIName": "Contracts Created",
                    "KPIValue": int(grp["ProjectId"].nunique()), "MappingStatus": "CONFIRMED",
                    "PipelineRunId": run_id, "LoadDateTime": now_ts,
                })
            for bu_code, grp in sexp.groupby("BusinessUnit"):
                kpi_daily_rows.append({
                    "ActivityDate": as_of, "BusinessUnit": bu_code, "KPIName": "Expense Reports",
                    "KPIValue": int(grp["ExpenseReportId"].nunique()), "MappingStatus": "CONFIRMED",
                    "PipelineRunId": run_id, "LoadDateTime": now_ts,
                })
            # Timecards lack governed BU attribution -> publish overall total under 'UNATTRIBUTED' per prototype.md §7.3
            sub_tc = stc[stc["IsSubmitted"] == 1].copy()
            kpi_daily_rows.append({
                "ActivityDate": as_of, "BusinessUnit": "UNATTRIBUTED", "KPIName": "Timesheets Submitted",
                "KPIValue": int(sub_tc["TimecardId"].nunique()), "MappingStatus": "UNATTRIBUTED_BU",
                "PipelineRunId": run_id, "LoadDateTime": now_ts,
            })
            n_kd = _write_df_explicit(conn, "gold", "coreadoption_kpi_daily", pd.DataFrame(kpi_daily_rows), is_ms)

            # gold.coreadoption_user_activity (CONFIRMED mapped applications only; REVIEW/EXCLUDED tracked as exceptions)
            sla_conf = sla[sla["MappingStatus"] == "CONFIRMED"].copy()
            gua = sla_conf[["ActivityDate", "APPUserId", "ApplicationId", "ApplicationCode",
                            "AdoptionEntity", "AdoptionWaveNumber", "RegionCode", "LoginEventCount"]].copy()
            gua["PipelineRunId"] = run_id
            gua["LoadDateTime"] = now_ts
            n_gua = _write_df_explicit(conn, "gold", "coreadoption_user_activity", gua, is_ms)
            log_step(conn, 7, "Publish gold.coreadoption_kpi_daily & user_activity", n_kd + n_gua)

            # -------- STEP 8: Publish authoritative gold.coreadoption_event --------
            ev_frames = []
            # 8a. PROJECT_CREATED
            ev_p = pd.DataFrame({
                "EventKey": "PROJECT_CREATED:" + sp["ProjectId"].astype(str),
                "EventType": "PROJECT_CREATED",
                "SourceEventId": sp["ProjectId"],
                "EventDate": sp["CreatedDate"].dt.date,
                "EventMonth": sp["CreatedMonth"],
                "EventDateTime": sp["CreatedDate"],
                "KPIName": "Contracts Created",
                "EventCount": 1,
                "DistinctEntityId": sp["ProjectId"],
                "APPUserId": None,
                "EmployeeId": None,
                "ApplicationId": None,
                "ApplicationCode": None,
                "ProjectId": sp["ProjectId"],
                "ExpenseReportId": None,
                "BusinessUnit": sp["BusinessUnit"],
                "BusinessUnitName": sp["BusinessUnitName"],
                "CompanyCode": sp["CompanyCode"],
                "CompanyName": sp["CompanyName"],
                "CountryCode": sp["CountryCode"],
                "RegionCode": sp["RegionCode"],
                "RegionDesc": sp["RegionDesc"],
                "AdoptionEntity": sp["AdoptionEntity"],
                "AdoptionWaveNumber": sp["AdoptionWaveNumber"],
                "MappingStatus": "CONFIRMED",
                "LoadDateTime": now_ts,
                "PipelineRunId": run_id,
            })
            ev_frames.append(ev_p)

            # 8b. LOGIN (one row per ActivityDate x APPUserId x ApplicationId in silver.login_activity where MappingStatus='CONFIRMED')
            sla_conf_reset = sla_conf.reset_index(drop=True)
            ev_l = pd.DataFrame({
                "EventKey": ("LOGIN:" + sla_conf_reset["ActivityDate"].astype(str) + ":"
                             + sla_conf_reset["APPUserId"].astype(str) + ":" + sla_conf_reset["ApplicationId"].astype(str)),
                "EventType": "LOGIN",
                "SourceEventId": sla_conf_reset.index + 1,
                "EventDate": sla_conf_reset["ActivityDate"],
                "EventMonth": pd.to_datetime(sla_conf_reset["ActivityDate"]).dt.to_period("M").dt.to_timestamp().dt.date,
                "EventDateTime": sla_conf_reset["FirstLoginDateTime"],
                "KPIName": "Employees Logging In",
                "EventCount": sla_conf_reset["LoginEventCount"],
                "DistinctEntityId": sla_conf_reset["APPUserId"],
                "APPUserId": sla_conf_reset["APPUserId"],
                "EmployeeId": sla_conf_reset["EmployeeId"],
                "ApplicationId": sla_conf_reset["ApplicationId"],
                "ApplicationCode": sla_conf_reset["ApplicationCode"],
                "ProjectId": None,
                "ExpenseReportId": None,
                "BusinessUnit": None,          # Never fabricate login BU!
                "BusinessUnitName": None,
                "CompanyCode": None,
                "CompanyName": None,
                "CountryCode": None,
                "RegionCode": sla_conf_reset["RegionCode"],
                "RegionDesc": None,
                "AdoptionEntity": sla_conf_reset["AdoptionEntity"],
                "AdoptionWaveNumber": sla_conf_reset["AdoptionWaveNumber"],
                "MappingStatus": "CONFIRMED",
                "LoadDateTime": now_ts,
                "PipelineRunId": run_id,
            })
            ev_frames.append(ev_l)

            # 8c. TIMECARD_SUBMITTED
            ev_t = pd.DataFrame({
                "EventKey": "TIMECARD_SUBMITTED:" + sub_tc["TimecardId"].astype(str),
                "EventType": "TIMECARD_SUBMITTED",
                "SourceEventId": sub_tc["TimecardId"],
                "EventDate": sub_tc["SubmittedDate"].dt.date,
                "EventMonth": sub_tc["SubmittedMonth"],
                "EventDateTime": sub_tc["SubmittedDate"],
                "KPIName": "Timesheets Submitted",
                "EventCount": 1,
                "DistinctEntityId": sub_tc["TimecardId"],
                "APPUserId": sub_tc["APPUserId"],
                "EmployeeId": None,
                "ApplicationId": None,
                "ApplicationCode": None,
                "ProjectId": None,
                "ExpenseReportId": None,
                "BusinessUnit": None,          # Never fabricate multi-task BU!
                "BusinessUnitName": None,
                "CompanyCode": None,
                "CompanyName": None,
                "CountryCode": None,
                "RegionCode": sub_tc["RegionCode"],
                "RegionDesc": None,
                "AdoptionEntity": sub_tc["AdoptionEntity"],
                "AdoptionWaveNumber": sub_tc["AdoptionWaveNumber"],
                "MappingStatus": np.where(sub_tc["HasSingleEntityAttribution"] == 1, "CONFIRMED", "UNATTRIBUTED_ENTITY"),
                "LoadDateTime": now_ts,
                "PipelineRunId": run_id,
            })
            ev_frames.append(ev_t)

            # 8d. EXPENSE_SUBMISSION
            ev_e = pd.DataFrame({
                "EventKey": "EXPENSE_SUBMISSION:" + sexp["ExpenseReportId"].astype(str),
                "EventType": "EXPENSE_SUBMISSION",
                "SourceEventId": sexp["ExpenseReportId"],
                "EventDate": sexp["SubmittedDate"].dt.date,
                "EventMonth": sexp["SubmittedMonth"],
                "EventDateTime": sexp["SubmittedDate"],
                "KPIName": "Expense Reports",
                "EventCount": 1,
                "DistinctEntityId": sexp["ExpenseReportId"],
                "APPUserId": sexp["APPUserId"],
                "EmployeeId": None,
                "ApplicationId": None,
                "ApplicationCode": None,
                "ProjectId": None,
                "ExpenseReportId": sexp["ExpenseReportId"],
                "BusinessUnit": sexp["BusinessUnit"],
                "BusinessUnitName": sexp["BusinessUnitName"],
                "CompanyCode": sexp["CompanyCode"],
                "CompanyName": sexp["CompanyName"],
                "CountryCode": sexp["CountryCode"],
                "RegionCode": sexp["RegionCode"],
                "RegionDesc": sexp["RegionDesc"],
                "AdoptionEntity": sexp["AdoptionEntity"],
                "AdoptionWaveNumber": sexp["AdoptionWaveNumber"],
                "MappingStatus": "CONFIRMED",
                "LoadDateTime": now_ts,
                "PipelineRunId": run_id,
            })
            ev_frames.append(ev_e)

            df_events = pd.concat(ev_frames, ignore_index=True)
            n_ev = _write_df_explicit(conn, "gold", "coreadoption_event", df_events, is_ms)
            log_step(conn, 8, "Publish authoritative gold.coreadoption_event", n_ev)

            # -------- STEP 9: Build gold.dim_date & Certified Adoption Aggregates (CURRENT + MONTHLY) --------
            # Calendar months from 2025-06-01 through as_of month
            cur_m_start = date(as_of.year, as_of.month, 1)
            all_months = []
            ym_y, ym_m = 2025, 6
            while (ym_y, ym_m) <= (as_of.year, as_of.month):
                ms = date(ym_y, ym_m, 1)
                dim_days = calendar.monthrange(ym_y, ym_m)[1]
                is_comp = 1 if (ms < cur_m_start or as_of.day == dim_days) else 0
                elap = dim_days if is_comp else as_of.day
                rel = (ym_y - as_of.year) * 12 + (ym_m - as_of.month)
                all_months.append({
                    "PeriodDate": ms,
                    "PeriodDateKey": ym_y * 10000 + ym_m * 100 + 1,
                    "YearMonth": f"{ym_y:04d}-{ym_m:02d}",
                    "CalendarYear": ym_y,
                    "CalendarMonth": ym_m,
                    "MonthLabel": ms.strftime("%b %Y"),
                    "RelativeMonthNumber": rel,
                    "IsCompleteMonth": is_comp,
                    "DaysInMonth": dim_days,
                    "ElapsedDays": elap,
                })
                ym_m += 1
                if ym_m > 12:
                    ym_y, ym_m = ym_y + 1, 1
            df_dim_date = pd.DataFrame(all_months)
            _write_df_explicit(conn, "gold", "dim_date", df_dim_date, is_ms)
            month_meta = {r["PeriodDate"]: r for r in all_months}
            cur_meta = month_meta[cur_m_start]

            # Count mapping exception rows (REVIEW login rows + multi-entity unattributed timecards)
            login_exc_total = int((sla["MappingStatus"] == "REVIEW").sum())
            tc_exc_total = int((sub_tc["HasSingleEntityAttribution"] == 0).sum())

            entity_region = df_org.groupby("AdoptionEntity").agg(
                AdoptionWaveNumber=("AdoptionWaveNumber", "first"),
                RegionCode=("RegionCode", "first"),
                RegionDesc=("RegionDesc", "first"),
            ).to_dict(orient="index")
            bu_lookup = df_org.set_index("BusinessUnit").to_dict(orient="index")

            cert_rows = []
            rid_seq = 1

            def push_cert(rec_type: str, level: str, pmeta: dict, kpi: str, val: int, sup_rows: int, exc_rows: int = 0,
                          wave_num=None, entity=None, bu=None):
                nonlocal rid_seq
                binfo = bu_lookup.get(bu, {}) if bu else {}
                einfo = entity_region.get(entity, {}) if entity else {}
                wv = wave_num if wave_num is not None else (binfo.get("AdoptionWaveNumber") or einfo.get("AdoptionWaveNumber"))
                rc = binfo.get("RegionCode") or einfo.get("RegionCode")
                rd = binfo.get("RegionDesc") or einfo.get("RegionDesc")
                cert_rows.append({
                    "RowId": rid_seq,
                    "RecordType": rec_type,
                    "ReportingLevel": level,
                    "PeriodDate": pmeta["PeriodDate"],
                    "PeriodDateKey": pmeta["PeriodDateKey"],
                    "YearMonth": pmeta["YearMonth"],
                    "RelativeMonthNumber": pmeta["RelativeMonthNumber"],
                    "IsCompleteMonth": pmeta["IsCompleteMonth"],
                    "AdoptionWaveNumber": int(wv) if wv is not None and not pd.isna(wv) else None,
                    "AdoptionWaveLabel": f"Wave {int(wv)}" if wv is not None and not pd.isna(wv) else None,
                    "AdoptionEntity": entity or binfo.get("AdoptionEntity"),
                    "BusinessUnit": bu,
                    "BusinessUnitName": binfo.get("BusinessUnitName"),
                    "CompanyCode": binfo.get("CompanyCode"),
                    "CompanyName": binfo.get("CompanyName"),
                    "CountryCode": binfo.get("CountryCode"),
                    "RegionCode": rc,
                    "RegionDesc": rd,
                    "KPIName": kpi,
                    "KPIValue": int(val),
                    "SupportingRowCount": int(sup_rows),
                    "MappingExceptionRows": int(exc_rows),
                    "LoadDateTime": now_ts,
                })
                rid_seq += 1

            all_kpis = ["Contracts Created", "Employees Logging In", "Timesheets Submitted", "Expense Reports"]
            bu_supported_kpis = ["Contracts Created", "Expense Reports"]
            waves_sorted = sorted(df_org["AdoptionWaveNumber"].unique().tolist())
            entities_sorted = sorted(df_org["AdoptionEntity"].unique().tolist())
            bus_sorted = sorted(df_org["BusinessUnit"].unique().tolist())

            def calc_kpi(sub_df: pd.DataFrame, kpi: str) -> tuple[int, int]:
                kdf = sub_df[sub_df["KPIName"] == kpi]
                if kdf.empty:
                    return 0, 0
                if kpi == "Employees Logging In":
                    return int(kdf["APPUserId"].nunique()), int(kdf["EventCount"].sum())
                return int(kdf["DistinctEntityId"].nunique()), int(len(kdf))

            # 9a. CURRENT rows (cumulative dataset population as of as_of; Employees = cumulative distinct non-service users)
            for kpi in all_kpis:
                v, sr = calc_kpi(df_events, kpi)
                exc = login_exc_total if kpi == "Employees Logging In" else (tc_exc_total if kpi == "Timesheets Submitted" else 0)
                push_cert("CURRENT", "OVERALL", cur_meta, kpi, v, sr, exc)
                for wv in waves_sorted:
                    vw, srw = calc_kpi(df_events[df_events["AdoptionWaveNumber"] == wv], kpi)
                    push_cert("CURRENT", "WAVE", cur_meta, kpi, vw, srw, 0, wave_num=wv)
                for ent in entities_sorted:
                    ve, sre = calc_kpi(df_events[df_events["AdoptionEntity"] == ent], kpi)
                    push_cert("CURRENT", "ENTITY", cur_meta, kpi, ve, sre, 0, entity=ent)
                if kpi in bu_supported_kpis:
                    for bu in bus_sorted:
                        vb, srb = calc_kpi(df_events[df_events["BusinessUnit"] == bu], kpi)
                        push_cert("CURRENT", "BUSINESS_UNIT", cur_meta, kpi, vb, srb, 0, bu=bu)

            # 9b. MONTHLY rows (recomputed distinctly per month & reporting level!)
            for pm in all_months:
                pdate = pm["PeriodDate"]
                mdf = df_events[df_events["EventMonth"] == pdate]
                for kpi in all_kpis:
                    v, sr = calc_kpi(mdf, kpi)
                    push_cert("MONTHLY", "OVERALL", pm, kpi, v, sr, 0)
                    for wv in waves_sorted:
                        vw, srw = calc_kpi(mdf[mdf["AdoptionWaveNumber"] == wv], kpi)
                        push_cert("MONTHLY", "WAVE", pm, kpi, vw, srw, 0, wave_num=wv)
                    for ent in entities_sorted:
                        ve, sre = calc_kpi(mdf[mdf["AdoptionEntity"] == ent], kpi)
                        push_cert("MONTHLY", "ENTITY", pm, kpi, ve, sre, 0, entity=ent)
                    if kpi in bu_supported_kpis:
                        for bu in bus_sorted:
                            vb, srb = calc_kpi(mdf[mdf["BusinessUnit"] == bu], kpi)
                            push_cert("MONTHLY", "BUSINESS_UNIT", pm, kpi, vb, srb, 0, bu=bu)

            df_cert = pd.DataFrame(cert_rows)
            n_cert = _write_df_explicit(conn, "gold", "certified_adoption_store", df_cert, is_ms)
            log_step(conn, 9, "Rebuild goldview.v_core_adoption CURRENT & MONTHLY aggregates", n_cert)

            # -------- STEP 10: Run DataOps Validation & Parity Suite --------
            q_max = conn.execute(text("SELECT COALESCE(MAX(QualityMetricId), 0) FROM dataops.data_quality_metric")).scalar() or 0
            qm_rows = []

            def add_qm(name: str, cat: str, val: int, exp: int | None, ok: bool, details: str):
                nonlocal q_max
                q_max += 1
                qm_rows.append({
                    "QualityMetricId": int(q_max),
                    "PipelineRunId": run_id,
                    "CheckName": name,
                    "CheckCategory": cat,
                    "CheckStatus": "PASS" if ok else "WARNING",
                    "MetricValue": int(val),
                    "ExpectedValue": int(exp) if exp is not None else None,
                    "Details": details,
                    "LoggedDateTime": now_ts,
                })

            # Parity 1: Projects
            p_sil = int(sp["ProjectId"].nunique())
            p_ev = int(df_events.loc[df_events["EventType"] == "PROJECT_CREATED", "DistinctEntityId"].nunique())
            add_qm("parity_projects_created", "PARITY", p_ev, p_sil, p_ev == p_sil,
                   "silver.project distinct ProjectId == gold PROJECT_CREATED EventId")

            # Parity 2: Timecards
            tc_sil = int(sub_tc["TimecardId"].nunique())
            tc_ev = int(df_events.loc[df_events["EventType"] == "TIMECARD_SUBMITTED", "DistinctEntityId"].nunique())
            add_qm("parity_timecards_submitted", "PARITY", tc_ev, tc_sil, tc_ev == tc_sil,
                   "silver.timecard submitted TimecardId == gold TIMECARD_SUBMITTED EventId")

            # Parity 3: Expenses
            ex_sil = int(sexp["ExpenseReportId"].nunique())
            ex_ev = int(df_events.loc[df_events["EventType"] == "EXPENSE_SUBMISSION", "DistinctEntityId"].nunique())
            add_qm("parity_expense_reports", "PARITY", ex_ev, ex_sil, ex_ev == ex_sil,
                   "silver.expense_report submitted ExpenseReportId == gold EXPENSE_SUBMISSION EventId")

            # Parity 4: Distinct Login Users (Oct 2026 closed month)
            oct_sil = int(sla_conf.loc[(pd.to_datetime(sla_conf["ActivityDate"]).dt.year == 2026) &
                                       (pd.to_datetime(sla_conf["ActivityDate"]).dt.month == 10), "APPUserId"].nunique())
            oct_cert = int(df_cert.loc[(df_cert["RecordType"] == "MONTHLY") &
                                       (df_cert["ReportingLevel"] == "OVERALL") &
                                       (df_cert["YearMonth"] == "2026-10") &
                                       (df_cert["KPIName"] == "Employees Logging In"), "KPIValue"].iloc[0])
            add_qm("parity_oct2026_distinct_logins", "PARITY", oct_cert, oct_sil, oct_cert == oct_sil,
                   "Oct 2026 OVERALL Employees Logging In == distinct non-service confirmed APPUserId")

            # Non-additivity check: sum of entity employee logins > OVERALL distinct employees
            sum_ent_cur = int(df_cert.loc[(df_cert["RecordType"] == "CURRENT") &
                                          (df_cert["ReportingLevel"] == "ENTITY") &
                                          (df_cert["KPIName"] == "Employees Logging In"), "KPIValue"].sum())
            ov_cur = int(df_cert.loc[(df_cert["RecordType"] == "CURRENT") &
                                     (df_cert["ReportingLevel"] == "OVERALL") &
                                     (df_cert["KPIName"] == "Employees Logging In"), "KPIValue"].iloc[0])
            add_qm("non_additive_employee_dedup", "SEMANTICS", ov_cur, None, sum_ent_cur > ov_cur,
                   f"OVERALL distinct users ({ov_cur}) < naive sum across entities ({sum_ent_cur}); cross-entity users deduplicated")

            # Referential orphan checks & mapping exception checks (logged as WARNING visibility, zero silent inflation!)
            orphan_tcr = int(tcr["IsOrphanTimecard"].sum())
            orphan_expe = int(expe["IsOrphanReport"].sum())
            unmapped_bu = int((df_org["HasLocalEnrichment"] == 0).sum())
            add_qm("orphan_timecard_rows", "REFERENTIAL", orphan_tcr, 0, orphan_tcr == 0,
                   f"{orphan_tcr} orphan TimecardRow record(s) quarantined without inflating KPIs")
            add_qm("orphan_expense_entries", "REFERENTIAL", orphan_expe, 0, orphan_expe == 0,
                   f"{orphan_expe} orphan ExpenseEntry record(s) quarantined without inflating KPIs")
            add_qm("application_mapping_exceptions", "MAPPING", login_exc_total, 0, login_exc_total == 0,
                   f"{login_exc_total} login activity row(s) on REVIEW apps excluded from certified totals")
            add_qm("core_bu_without_local_enrichment_kept", "COMPLETENESS", unmapped_bu, 1, True,
                   f"{unmapped_bu} CORE BU(s) absent from local enrichment preserved via LEFT JOIN")

            if p_ev != p_sil or tc_ev != tc_sil or ex_ev != ex_sil or oct_cert != oct_sil:
                raise RuntimeError("Critical source-to-gold parity check failed!")

            n_qm = _write_df_explicit(conn, "dataops", "data_quality_metric", pd.DataFrame(qm_rows), is_ms, truncate_first=False)
            log_step(conn, 10, "Validate certified view parity, orphans & non-additivity", n_qm)

            # -------- STEP 11: Advance Watermark & Complete DataOps Run Status --------
            conn.execute(text("DELETE FROM dataops.watermark WHERE PipelineName = :p AND SourceObject = 'source_sim.application_log'"),
                         {"p": PIPELINE_NAME})
            conn.execute(text("""
                INSERT INTO dataops.watermark
                    (PipelineName, SourceObject, WatermarkType, BigIntWatermark, DateTimeWatermark, LastSuccessfulRunId, ModifiedDateTime)
                VALUES (:p, 'source_sim.application_log', 'BIGINT_ID', :wm, :ts, :rid, :ts)
            """), {"p": PIPELINE_NAME, "wm": int(new_max_wm), "ts": now_ts, "rid": run_id})

            log_step(conn, 11, "Advance watermark & complete DataOps status", 1)
            conn.execute(text("""
                UPDATE dataops.pipeline_run
                SET RunStatus = 'SUCCESS', CompletedDateTime = :ts
                WHERE PipelineRunId = :rid
            """), {"ts": now_ts, "rid": run_id})

        return {
            "pipeline_run_id": run_id,
            "status": "SUCCESS",
            "incremental_app_logs": inc_rows,
            "watermark_id": int(new_max_wm),
            "certified_rows": n_cert,
            "events": n_ev,
        }
    except Exception as exc:
        with engine.begin() as err_conn:
            err_conn.execute(text("""
                UPDATE dataops.pipeline_run
                SET RunStatus = 'FAILED', CompletedDateTime = :ts, ErrorMessage = :msg
                WHERE PipelineRunId = :rid
            """), {"ts": now_ts, "msg": str(exc)[:480], "rid": run_id})
        raise
