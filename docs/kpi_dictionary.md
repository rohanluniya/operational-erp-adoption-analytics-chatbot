# CORE Pulse — Governed KPI Dictionary

Owner: **Rohan Luniya** · Certified Consumer Interface: `goldview.v_core_adoption`

## 1. Authoritative Baseline Adoption KPIs

| KPI Name | Metric ID | Authoritative Source & Filter | Event Timestamp | Counting Grain & Formula | Additivity | Supported Reporting Levels | Unsupported Breakdowns & Reason |
|---|---|---|---|---|---|---|---|
| **Contracts Created** | `contracts_created` | `source_sim.project` -> `silver.project` -> `gold.coreadoption_event` (`EventType = 'PROJECT_CREATED'`) | `Project.CreatedDate` *(never `ProjectStartDate` or `ProposedStartDate`)* | `COUNT(DISTINCT ProjectId)` | **Additive** across disjoint projects, BUs, entities, waves, and months | `OVERALL`, `WAVE`, `ENTITY`, `BUSINESS_UNIT` | Module breakdown (single domain: Projects/Contracts) |
| **Employees Logging In** | `employees_logging_in` | `source_sim.application_log` joined to `application_log_type` (`Name = 'Application Login'`) and `app_user` (`IsServiceAccount = 0`) | `ApplicationLog.CreatedDate` | `COUNT(DISTINCT APPUserId)` recomputed at exact requested `(period, scope)` | **Strictly Non-Additive** across days, months, apps, entities, and waves | `OVERALL`, `WAVE`, `ENTITY` *(plus `APPLICATION` via `get_core_user_engagement`)* | **`BUSINESS_UNIT` unavailable** — login events and `APPUser` lack authoritative employee home BU |
| **Timesheets Submitted** | `timesheets_submitted` | `source_sim.timecard` (`SubmittedDate IS NOT NULL`), independent of current workflow status (`Submitted`, `Approved`, `Rejected`, `Exported`) | `Timecard.SubmittedDate` *(never `ProjectTask.ActualHours` or timeline events)* | `COUNT(DISTINCT TimecardId)` | **Additive** across distinct timecards and months | `OVERALL`, `WAVE`, `ENTITY` | **`BUSINESS_UNIT` unavailable** — a single timecard can book rows across multiple project tasks/BUs without an allocation rule |
| **Expense Reports** | `expense_reports` | `source_sim.expense_report` (`SubmittedDate IS NOT NULL`), independent of post-submission edits or status changes | `ExpenseReport.SubmittedDate` | `COUNT(DISTINCT ExpenseReportId)` | **Additive** across distinct submitted reports, BUs, entities, waves, and months | `OVERALL`, `WAVE`, `ENTITY`, `BUSINESS_UNIT` | None within adoption scope (line-item spend amounts are out-of-scope for Adoption MVP) |

---

## 2. Governed Derivative & Simulated Extension Read Models

| Read Model / Tool | Source Object | Classification | Purpose & Guardrail Rules |
|---|---|---|---|
| **Daily / Rolling User Engagement** (`get_core_user_engagement`) | `gold.coreadoption_user_activity` (`ActivityDate x APPUserId x ApplicationId`) | Governed Derivative | Computes exact distinct active non-service users and login event counts over custom windows (`MTD`, `Last 7d`, `Last 30d`, `Same-day-count prior MTD`) without summing monthly distinct rows. |
| **Rollout & Module Status** (`get_core_rollout_status`) | `reference.rollout_registry` + `reference.module_catalog` joined to observed Gold events | **`SIMULATED EXTENSION`** | Reports `PLANNED`, `ONBOARDING`, `LIVE`, `PAUSED`, `RETIRED` status, planned vs. actual go-live dates, optional `EligiblePopulation`, and whether instrumented events exist. Never equates app logins with specific module visits and marks uninstrumented modules `NOT INSTRUMENTED`. |
| **DataOps & Lineage Telemetry** (`get_core_pipeline_status`, `get_core_metric_lineage`) | `dataops.*` + `app/semantic/metrics.yaml` | Baseline Governance | Surfaces latest pipeline run status, step timings, `ApplicationLogId` bigint watermark, data quality / orphan / mapping-exception counts, and end-to-end lineage (`source_sim -> bronze -> silver -> gold -> goldview.v_core_adoption`). |
