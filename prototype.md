# CORE Pulse: AI and BI Data Product Context

> **Document type:** Machine-readable project context, implementation specification, and agent prompt  
> **Audience:** AI agents, MCP servers, data engineers, analytics engineers, BI developers, semantic-model builders, and conversational analytics systems  
> **Data classification:** Metadata and business context only. No production records, credentials, personal information, or actual KPI values are included.  
> **Example data:** Any example values in this document are explicitly synthetic and must never be treated as production data.

---

## 1. Agent role and mission

You are an enterprise data-engineering and analytics agent responsible for maintaining and extending **CORE Pulse**, a governed data product that measures adoption of the CORE operational application.

The primary objective is to extract selected operational data from CORE, transform it through a medallion architecture, calculate four authoritative adoption KPIs, and publish a simple certified dataset that can be consumed by Tableau, Power BI, Excel, SQL, Tableau Pulse, conversational assistants, or other AI-enabled analytics products.

The implementation must optimize for:

1. Correct business-event definitions.
2. Reproducible and auditable transformations.
3. Minimal consumer-facing complexity.
4. Clear grains and non-additive-measure handling.
5. Source-system lineage.
6. Safe reruns and idempotent deployment.
7. Explicit column lists in all permanent-table inserts.
8. Separation between engineering objects and business-facing objects.
9. No exposure of source credentials or sensitive authentication attributes.
10. Future extension into operational-integrity checks without redesigning the adoption layer.

The adoption product must remain understandable to a data analyst or BI developer who did not build the pipeline.

---

## 2. Product identity

### Product name

**CORE Pulse**

### Product purpose

CORE Pulse gives stakeholders a concise view of:

- Projects or contracts created in CORE.
- Employees actively logging into CORE.
- Timecards submitted through CORE.
- Expense reports submitted through CORE.
- Monthly movement and adoption trends.
- Adoption by rollout wave and governed entity where attribution is available.
- CORE-native geography such as business unit, company, country, and region where attribution is supported by the source transaction.

### Recommended BI experiences

- **Adoption Pulse:** current KPI cards and monthly trends.
- **Integrity Pulse:** a future quality and workflow product, intentionally outside the adoption MVP specification.

### Current certified consumer datasets

```text
goldview.v_core_adoption
goldview.v_dim_date
```

For the CORE Pulse adoption dashboard, the preferred source is only:

```text
goldview.v_core_adoption
```

No join or relationship is required in Tableau or Power BI for the adoption MVP.

---

## 3. Scope and non-scope

### In scope

- CORE source extraction for the four adoption KPIs.
- Bronze, silver, gold, and certified-view transformations.
- Current cumulative KPI totals.
- True-event monthly trends.
- Rollout-wave and adoption-entity attribution.
- CORE-native geography when present and defensible.
- DataOps logging, watermarks, run status, and safe reruns.
- A simple final consumer view suitable for BI and AI systems.

### Out of scope for this document

- Detailed data-quality rules.
- Record-level remediation workflows.
- Rule exclusions and exception approvals.
- Contract-format quality scoring.
- Excessive-time-entry thresholds.
- Expense-line validation.
- Operational-integrity dashboards.

Quality and integrity are a planned adjacent product, but this document focuses only on adoption KPIs and the enabling data model.

---

## 4. Source platform context

### Source system

```text
Linked server: BncDb
Source database: BvCoreProd
Application: CORE
```

The source is accessed through SQL Server linked-server queries. Source extraction should be performed remotely where practical so only required columns and rows cross the linked-server boundary.

### Security constraints

Never extract or persist sensitive authentication attributes from `OP.APPUser`, including:

```text
Password
ConfirmationCode
SecurityCode
TwoFactorAuthenticationKey
```

Only the minimum identity attributes needed for analytics may be extracted:

```text
APPUserId
EmployeeId
ContactId
LDAPId
IsServiceAccount
```

---

## 5. Authoritative KPI definitions

These definitions are final unless formally changed through business governance.

| KPI | Source event | Event date | Counting rule | Additivity |
|---|---|---|---|---|
| Contracts Created | A row is created in `Project.Project` | `Project.CreatedDate` | Count distinct `ProjectId` | Additive across disjoint projects and periods |
| Employees Logging In | A non-service user generates an `Application Login` event | `ApplicationLog.CreatedDate` | Count distinct `APPUserId` per requested period/scope | Non-additive across applications, entities, waves, and months |
| Timesheets Submitted | A timecard has a populated submission timestamp | `Timecard.SubmittedDate` | Count distinct `TimecardId` where `SubmittedDate IS NOT NULL` | Additive across distinct timecards and periods |
| Expense Reports | An expense report has a populated submission timestamp | `ExpenseReport.SubmittedDate` | Count distinct `ExpenseReportId` where `SubmittedDate IS NOT NULL` | Additive across distinct reports and periods |

### Important semantic decisions

#### Contracts Created

Use `Project.CreatedDate` as the creation event. Do not use `ProjectStartDate`, `ProposedStartDate`, or another effective date as the creation timestamp.

#### Employees Logging In

Only include events where:

```text
ApplicationLogType.Name = Application Login
APPUser.IsServiceAccount = 0
```

The same employee may log into several applications or entities. Distinct users must be recalculated at the requested reporting level. Do not sum entity-level employee counts to derive a wave or global total.

#### Timesheets Submitted

Use the dedicated timesheet transaction:

```text
Timesheet.Timecard
```

A timecard is considered submitted if:

```sql
SubmittedDate IS NOT NULL
```

Do not filter only to the current status `Submitted`, because a previously submitted timecard can later move to Rejected, Approved, or Exported.

Do not use `ProjectTask.ActualHours > 0` as the authoritative timesheet-submission definition. That field may support task-activity analysis, but it is not the formal timecard transaction.

Do not use `ProjectTaskTimelineEvent` for the timesheet KPI. Timeline events represent task lifecycle events such as assignment, activation, readiness, and completion.

#### Expense Reports

Use `ExpenseReport.SubmittedDate`. Current status may change after submission, so the durable submission timestamp is the authoritative event evidence.

---

## 6. Source tables and required context

## 6.1 CORE business unit reference

### Source

```text
BvCoreProd.Admin.BusinessUnit
```

### Required columns

```text
BusinessUnitId
BusinessUnit
BusinessUnitName
CompanyCode
CompanyName
CountryCode
Status
Type
Active
RegionCode
RegionDesc
CreatedDate
ModifiedDate
```

### Purpose

- CORE-native business hierarchy.
- Company, country, and region attribution.
- Business-unit validity and descriptive names.
- Primary geography for operational transactions.

CORE-native geography is authoritative for inclusion. A record must not be discarded because a separate local BI organization hierarchy does not contain the business unit.

---

## 6.2 Projects and contracts

### Source

```text
BvCoreProd.Project.Project
```

### Adoption-critical columns

```text
ProjectId
CreatedDate
BusinessUnit
ProjectName
ParentContractCode
FlexContractNumber
ProjectStatusId
ProjectStartDate
ActualEndDate
Billable
IsClosed
```

### Future analytical columns already useful in the medallion layer

```text
ProjectTypeId
ObjectTypeCode
BvServiceCode
BillingMethodId
BillingFrequencyId
BillingDayTypeId
BillingTasksBilledMethodId
RevenueRecognitionId
InvoiceStructureId
CurrencyCode
PurchaseOrder
PaymentTermsCode
InternalProject
CompanyId
DivisionId
ProgramId
ModifiedDate
ProposedStartDate
ProposedEndDate
```

### Purpose

- Current project population.
- True project-created monthly trend.
- Adoption by CORE business unit and geography.

---

## 6.3 Project hierarchy and task activity

### Sources

```text
BvCoreProd.Project.ProjectService
BvCoreProd.Project.ProjectPhase
BvCoreProd.Project.ProjectTask
BvCoreProd.Project.ProjectTaskTimelineEvent
```

### Join path

```text
ProjectTask.ProjectPhaseId
    -> ProjectPhase.ProjectPhaseId

ProjectPhase.ProjectServiceId
    -> ProjectService.ProjectServiceId

ProjectService.ProjectId
    -> Project.ProjectId
```

### Purpose

- Task-to-project attribution.
- Historical compatibility for the original task-hours proxy.
- Future workflow and integrity analysis.
- Not the authoritative source for the timecard-submission KPI.

---

## 6.4 Application login activity

### Sources

```text
BvCoreProd.OP.ApplicationLog
BvCoreProd.Admin.ApplicationLogType
BvCoreProd.OP.Application
BvCoreProd.OP.APPUser
```

### Join path

```text
ApplicationLog.ApplicationLogTypeId
    -> ApplicationLogType.ApplicationLogTypeId

ApplicationLog.ApplicationId
    -> Application.ApplicationId

ApplicationLog.APPUserId
    -> APPUser.APPUserId

Application.ApplicationCode
    -> silver.application_mapping.ApplicationCode
```

### Required logic

```text
ApplicationLogType.Name = Application Login
APPUser.IsServiceAccount = 0
```

### Purpose

- Daily user/application activity.
- Distinct active employees.
- Application adoption.
- Rollout entity and wave attribution using governed application mapping.

### Attribution limitation

Login events do not currently have reliable business-unit attribution for most applications. Use adoption entity, rollout wave, application, and date. Do not fabricate a business unit.

---

## 6.5 Timecards

### Sources

```text
BvCoreProd.Timesheet.Timecard
BvCoreProd.Timesheet.TimecardStatus
BvCoreProd.Timesheet.TimecardRow
BvCoreProd.Timesheet.TimecardEntry
```

### Relationship path

```text
Timecard.TimecardId
    -> TimecardRow.TimecardId

TimecardRow.TimecardRowId
    -> TimecardEntry.TimecardRowId

TimecardRow.ProjectTaskId
    -> ProjectTask.ProjectTaskId
```

### Timecard workflow statuses

```text
1 = Time Entry
2 = Rejected
3 = Submitted
4 = Approved
5 = Exported
```

### Required KPI logic

```sql
COUNT(DISTINCT TimecardId)
WHERE SubmittedDate IS NOT NULL
```

### Purpose

- Authoritative timesheet-submission KPI.
- Monthly true-event trend.
- Optional future employee, pay-period, contract, project-task, and hours analysis.

---

## 6.6 Expense reports

### Sources

```text
BvCoreProd.Expense.ExpenseReport
BvCoreProd.Expense.ExpenseEntry
```

### Relationship path

```text
ExpenseEntry.ExpenseReportId
    -> ExpenseReport.ExpenseReportId

ExpenseEntry.ProjectTaskId
    -> ProjectTask.ProjectTaskId
```

### Required KPI logic

```sql
COUNT(DISTINCT ExpenseReportId)
WHERE SubmittedDate IS NOT NULL
```

### Purpose

- Current submitted-report population.
- Monthly true-event trend.
- Default business-unit attribution.
- Future expense-level analysis.

---

## 7. Medallion architecture

## 7.1 Bronze layer

### Purpose

Bronze is a source-aligned local landing layer. Bronze should preserve source keys and selected source attributes with minimal business transformation.

### Key bronze tables

```text
bronze.core_business_unit
bronze.core_project
bronze.core_project_service
bronze.core_project_phase
bronze.core_project_task
bronze.core_project_task_timeline_event
bronze.core_application
bronze.core_application_log_type
bronze.core_app_user
bronze.core_application_log
bronze.core_timecard
bronze.core_timecard_status
bronze.core_timecard_row
bronze.core_timecard_entry
bronze.core_expense_report
bronze.core_expense_entry
```

### Bronze audit columns

Every bronze table should include:

```text
SourceExtractDateTime
PipelineRunId
```

### Bronze load patterns

- Use full current snapshots for moderate reference and operational tables during MVP stabilization.
- Use incremental loading for `ApplicationLog` based on `ApplicationLogId` and `dataops.watermark`.
- Stage remote results before replacing permanent bronze snapshots.
- Use explicit target-column lists for all permanent-table inserts.
- Do not use `INSERT table SELECT *` against a permanent table.
- Preserve source data types where practical, while safely widening text or numeric fields when needed.

### Watermark pattern

```text
PipelineName
SourceObject
WatermarkType
BigIntWatermark
DateTimeWatermark
LastSuccessfulRunId
ModifiedDateTime
```

The application log uses a bigint ID watermark.

---

## 7.2 Silver layer

### Purpose

Silver provides conformed atomic facts, normalized keys, governed mappings, deduplication, and reusable business meaning.

### Important silver objects

```text
silver.organization
silver.application_mapping
silver.project
silver.task_activity
silver.login_activity
silver.timecard
silver.timecard_row
silver.timecard_entry
silver.expense_report
silver.expense_entry
```

### `silver.organization`

**Grain:** one row per normalized CORE business unit.

Primary source:

```text
bronze.core_business_unit
```

Optional enrichment:

```text
dbo.vDimOrganization
```

Optional enrichment join:

```sql
LTRIM(RTRIM(bronze.core_business_unit.BusinessUnit))
    = LTRIM(RTRIM(dbo.vDimOrganization.OrganizationCode))
```

The join must be a left join. CORE records remain available when no local organization match exists.

### `silver.application_mapping`

**Grain:** one governed row per application code.

Maps:

```text
ApplicationCode
-> AdoptionEntity
-> AdoptionWaveNumber
-> optional BusinessUnit
-> MappingStatus
```

Recommended statuses:

```text
CONFIRMED
REVIEW
EXCLUDED
```

### `silver.project`

**Grain:** one row per ProjectId.

Transformations:

- Normalize business unit.
- Preserve Project.CreatedDate.
- Map CORE geography.
- Retain current project state.
- Set one project-count indicator.

### `silver.task_activity`

**Grain:** one row per ProjectTaskId.

Transformations:

- Join task to phase, service, and project.
- Attach ProjectId and project business unit.
- Preserve actual hours and assignment.
- Maintain the historical task-activity indicator separately from the formal timecard KPI.

### `silver.login_activity`

**Grain:** ActivityDate x APPUserId x ApplicationId.

Transformations:

- Keep only application-login events.
- Exclude service accounts.
- Collapse multiple login events by user, application, and day.
- Calculate LoginEventCount, FirstLoginDateTime, and LastLoginDateTime.
- Map application to adoption entity and wave.

### `silver.timecard`

**Grain:** one row per TimecardId.

Transformations:

- Join status description.
- Preserve submitted, approved, rejected, and export timestamps.
- Derive IsSubmitted from SubmittedDate.
- Keep submission evidence even after status changes.

### `silver.timecard_row`

**Grain:** one row per TimecardRowId.

Transformations:

- Connect timecard to contract references and optional project task.

### `silver.timecard_entry`

**Grain:** one row per TimecardEntryId.

Transformations:

- Attach TimecardId via TimecardRow.
- Preserve entry date and hours.
- Attach pay-period context.

### `silver.expense_report`

**Grain:** one row per submitted ExpenseReportId.

Transformations:

- Keep reports where SubmittedDate is populated for the adoption fact.
- Normalize default business unit.
- Map CORE-native geography.
- Preserve workflow dates.

### `silver.expense_entry`

**Grain:** one row per ExpenseEntryId.

Transformations:

- Preserve transaction, amount, currency, contract, BU, and project-task context.
- Used for future analysis, not required for the four adoption KPI totals.

---

## 7.3 Gold layer

### Purpose

Gold stores reusable adoption facts and event facts. Business consumers should normally use certified views rather than physical gold tables.

### Key gold objects

```text
gold.coreadoption_kpi_daily
gold.coreadoption_user_activity
gold.coreadoption_event
gold.v_core_adoption_current_internal
gold.v_core_adoption_monthly_internal
```

### `gold.coreadoption_kpi_daily`

**Purpose:** current cumulative adoption snapshot.

Typical fields:

```text
ActivityDate
BusinessUnit
KPIName
KPIValue
MappingStatus
PipelineRunId
LoadDateTime
```

Current KPI definitions:

- Contracts Created = current distinct project population.
- Timesheets Submitted = current distinct submitted timecard population.
- Expense Reports = current distinct submitted expense-report population.

Timecards currently lack governed BU attribution. Publish the overall timecard total without inventing a BU.

### `gold.coreadoption_user_activity`

**Grain:** date x user x application.

Purpose:

- Preserve distinct-user analysis.
- Support employee adoption without summing raw login events.

### `gold.coreadoption_event`

**Purpose:** authoritative true-event fact for monthly trends.

Event types:

```text
PROJECT_CREATED
LOGIN
TIMECARD_SUBMITTED
EXPENSE_SUBMISSION
```

Recommended event fields:

```text
EventType
EventId
EventDate
EventDateTime
KPIName
EventCount
DistinctEntityId
APPUserId
EmployeeId
ApplicationId
ApplicationCode
ProjectId
ExpenseReportId
BusinessUnit
CORE geography attributes
AdoptionEntity
AdoptionWaveNumber
Mapping statuses
LoadDateTime
PipelineRunId
```

Counting behavior:

- Contracts, timecards, and expense reports: distinct EventId.
- Employees: distinct APPUserId for the requested period and scope.

### Internal aggregate views

```text
gold.v_core_adoption_current_internal
gold.v_core_adoption_monthly_internal
```

These are implementation objects and should not be presented as consumer datasets.

The monthly internal view publishes explicit reporting levels:

```text
OVERALL
WAVE
ENTITY
BUSINESS_UNIT
```

Employee counts must be recalculated distinctly at each level. Do not produce employee BU rows unless a governed BU mapping exists.

---

## 8. Certified consumer view

## `goldview.v_core_adoption`

This is the single adoption dataset for Tableau, Power BI, and AI systems.

### Core fields

```text
RecordType
ReportingLevel
PeriodDate
PeriodDateKey
YearMonth
RelativeMonthNumber
IsCompleteMonth
AdoptionWaveNumber
AdoptionWaveLabel
AdoptionEntity
BusinessUnit
BusinessUnitName
CompanyCode
CompanyName
CountryCode
RegionCode
RegionDesc
KPIName
KPIValue
SupportingRowCount
MappingExceptionRows
LoadDateTime
```

### Record types

```text
CURRENT
MONTHLY
```

### Reporting levels

```text
OVERALL
WAVE
ENTITY
BUSINESS_UNIT
```

### Consumer rules

- Filter to exactly one RecordType and one ReportingLevel per worksheet or query.
- Use OVERALL for top-level KPI cards.
- Use WAVE for rollout-wave comparison.
- Use ENTITY for adoption-entity comparison.
- Use BUSINESS_UNIT only for KPIs with defensible BU attribution.
- Do not sum employee counts across entities or waves.
- Use the precomputed OVERALL or WAVE employee row instead.

---

## 9. Star-schema and snowflake interpretation

The consumer view is intentionally denormalized, but the underlying model follows a fact-and-dimension pattern.

### Logical facts

```text
Current KPI snapshot fact
True event fact
Daily user/application activity fact
```

### Logical dimensions

```text
Date
CORE Business Unit
Application
Adoption Entity
Adoption Wave
KPI
```

### Why the certified view is denormalized

The adoption dashboard is small and requires one simple BI source. Denormalization prevents:

- Cross-fact duplication.
- Ambiguous relationship behavior in Tableau.
- Incorrect distinct-user totals.
- Duplicated field names.
- Complex filter propagation.

For enterprise semantic models, the same underlying facts may be represented as a star schema, but employee distinct counts still require measure logic at query time or pre-aggregated reporting levels.

---

## 10. DataOps and orchestration

### Control objects

```text
dataops.pipeline_registry
dataops.pipeline_run
dataops.pipeline_step_run
dataops.watermark
dataops.data_quality_metric
```

### Required run statuses

```text
RUNNING
SUCCESS
WARNING
FAILED
CANCELLED
```

### Production sequence

The preferred single governed pipeline sequence is:

```text
1. Refresh CORE reference and operational bronze snapshots
2. Increment ApplicationLog using watermark
3. Refresh timecard and expense detail bronze sources
4. Build conformed organization
5. Build base silver adoption facts
6. Build enriched silver facts
7. Publish current gold KPI snapshot
8. Publish authoritative event fact
9. Rebuild current and monthly internal aggregates
10. Validate certified view
11. Complete DataOps status
```

### Error-handling requirements

- Use `SET XACT_ABORT ON`.
- In every CATCH block, capture ERROR_NUMBER, ERROR_PROCEDURE, ERROR_LINE, and ERROR_MESSAGE.
- If `XACT_STATE() <> 0`, roll back before writing failure logs.
- After rollback, update pipeline step and run status.
- Rethrow the original error.
- Never allow failure logging to mask the source error with SQL Server error 3930.

### Insert standards

All permanent-table inserts must specify target columns:

```sql
INSERT schema.table
(
    ColumnA,
    ColumnB,
    ColumnC
)
SELECT
    SourceA,
    SourceB,
    SourceC;
```

Do not use:

```sql
INSERT schema.table
SELECT *;
```

This requirement is critical because the medallion tables may gain nullable fields over time.

---

## 11. Validation requirements

An AI agent or pipeline must not declare success until these validations pass.

### Current KPI validation

The certified view must contain one OVERALL CURRENT row for each KPI:

```text
Contracts Created
Employees Logging In
Timesheets Submitted
Expense Reports
```

### Event parity

```text
Distinct silver ProjectId with CreatedDate
    = distinct PROJECT_CREATED EventId

Distinct silver TimecardId with SubmittedDate
    = distinct TIMECARD_SUBMITTED EventId

Distinct silver ExpenseReportId with SubmittedDate
    = distinct EXPENSE_SUBMISSION EventId
```

Login validation:

```text
Distinct users in event fact for a given period
    = distinct non-service APPUserId in silver login activity for the same period and scope
```

### Monthly trend coverage

The MONTHLY OVERALL reporting level must contain all four KPI names after the event refresh.

### Referential checks

- Timecard rows should resolve to timecards.
- Timecard entries should resolve to timecard rows.
- Expense entries should resolve to expense reports.
- Task records should resolve through phase and service to project.
- Orphans must be reported, not silently discarded.

### Freshness checks

- LoadDateTime must update after a successful run.
- Latest event dates should be plausible relative to the source extraction time.
- Current KPI and monthly event refreshes must not use stale older load timestamps.

---

## 12. Tableau and Power BI consumption

### Tableau

Use one data source:

```text
goldview.v_core_adoption
```

Base measure:

```tableau
SUM([KPI Value])
```

#### KPI cards

```text
Record Type = CURRENT
Reporting Level = OVERALL
KPI Name = one KPI
```

#### Monthly trend

```text
Record Type = MONTHLY
Reporting Level = OVERALL
Period Date on Columns
SUM(KPI Value) on Rows
```

#### Wave matrix

```text
Record Type = CURRENT
Reporting Level = WAVE
Adoption Wave Label on Rows
KPI Name on Columns
SUM(KPI Value) on Text
```

#### Entity matrix

```text
Record Type = CURRENT
Reporting Level = ENTITY
Adoption Entity on Rows
KPI Name on Columns
SUM(KPI Value) on Text
```

Do not enable grand totals for employee entity or wave matrices.

### Power BI

A single import table may be created from `goldview.v_core_adoption`.

Recommended measures:

```DAX
KPI Value = SUM('CORE Adoption'[KPIValue])
```

Use visual-level filters for RecordType and ReportingLevel.

Do not sum pre-aggregated employee entity rows to calculate a total. Filter to the OVERALL employee row.

---

## 13. AI and conversational analytics instructions

An AI system answering questions from this product must honor the semantic rules below.

### Safe question examples

- What is the current number of contracts created?
- How many distinct employees logged in last month?
- What is the monthly trend in submitted timecards?
- Compare expense-report submissions this month with the prior month.
- Which rollout wave has the highest submitted-expense count?
- Show adoption by entity for contracts and timecards.

### Query-routing rules

- For current totals, filter `RecordType = CURRENT`.
- For trends, filter `RecordType = MONTHLY`.
- For global totals, filter `ReportingLevel = OVERALL`.
- For rollout wave, filter `ReportingLevel = WAVE`.
- For adoption entity, filter `ReportingLevel = ENTITY`.
- For BU breakdown, filter `ReportingLevel = BUSINESS_UNIT`.
- Do not combine different reporting levels in one aggregation.
- Do not infer business-unit attribution for employee logins when BusinessUnit is null.
- Always mention when the current month is incomplete using `IsCompleteMonth`.
- Treat employee counts as non-additive.

### Ambiguous-question behavior

If a user asks “How many users?” interpret as distinct employees logging in, not login-event count. If both are useful, state the distinction.

If a user asks “How many timesheets?” interpret as distinct submitted TimecardId values, not project tasks with hours.

If a user asks “contracts created,” use project creation events, not project start dates.

If a user asks for a geography unsupported by a KPI, state that attribution is unavailable rather than assigning records artificially.

---

## 14. Synthetic examples

> All examples below are fabricated solely to illustrate grain and structure.

### Example current records

| RecordType | ReportingLevel | KPIName | KPIValue | AdoptionWaveLabel | AdoptionEntity | BusinessUnit |
|---|---|---|---:|---|---|---|
| CURRENT | OVERALL | Contracts Created | 1,234 | null | null | null |
| CURRENT | OVERALL | Employees Logging In | 567 | null | null | null |
| CURRENT | WAVE | Expense Reports | 89 | Wave 1 | null | null |
| CURRENT | ENTITY | Timesheets Submitted | 456 | Wave 2 | Example Entity | null |
| CURRENT | BUSINESS_UNIT | Contracts Created | 78 | Wave 1 | Example Entity | BU-001 |

### Example monthly records

| RecordType | ReportingLevel | PeriodDate | KPIName | KPIValue | IsCompleteMonth |
|---|---|---|---|---:|---:|
| MONTHLY | OVERALL | 2026-09-01 | Contracts Created | 120 | 1 |
| MONTHLY | OVERALL | 2026-09-01 | Employees Logging In | 340 | 1 |
| MONTHLY | OVERALL | 2026-09-01 | Timesheets Submitted | 2,100 | 1 |
| MONTHLY | OVERALL | 2026-09-01 | Expense Reports | 980 | 1 |
| MONTHLY | OVERALL | 2026-10-01 | Contracts Created | 132 | 0 |

### Example non-additivity

Synthetic entity employee counts:

```text
Entity A = 100
Entity B = 80
```

If 20 employees used applications mapped to both entities, the distinct total is 160, not 180. The AI or BI solution must use the precomputed OVERALL or WAVE row.

---

## 15. MCP server resource design

A future MCP server may expose the following resources and tools.

### Resources

```text
core://metadata/project
core://metadata/kpis
core://metadata/sources
core://metadata/lineage
core://metadata/semantic-rules
core://metadata/freshness
```

### Read-only tools

```text
get_core_adoption_current
get_core_adoption_monthly
get_core_adoption_by_wave
get_core_adoption_by_entity
get_core_adoption_by_business_unit
get_core_pipeline_status
```

### Tool constraints

- Every tool must apply a single ReportingLevel.
- Employee tools must use published distinct counts.
- The monthly tool must include `IsCompleteMonth`.
- Responses must communicate data freshness.
- The MCP server must not expose source credentials or linked-server details to untrusted consumers.
- Query templates should use parameterized SQL.
- The server should enforce row limits and timeout controls.

### Example tool contract

```json
{
  "name": "get_core_adoption_monthly",
  "description": "Returns monthly CORE adoption values using authoritative source-event dates.",
  "inputs": {
    "kpi_name": "Contracts Created | Employees Logging In | Timesheets Submitted | Expense Reports",
    "reporting_level": "OVERALL | WAVE | ENTITY | BUSINESS_UNIT",
    "start_month": "YYYY-MM-01",
    "end_month": "YYYY-MM-01",
    "adoption_wave_number": "optional integer",
    "adoption_entity": "optional string",
    "business_unit": "optional string"
  },
  "required_filters": {
    "RecordType": "MONTHLY"
  },
  "result_fields": [
    "PeriodDate",
    "KPIName",
    "KPIValue",
    "ReportingLevel",
    "IsCompleteMonth",
    "LoadDateTime"
  ]
}
```

---

## 16. Future enhancements

### Near term

- Merge the nested adoption and integrity orchestrators into one pipeline.
- Add SQL Server Agent scheduling.
- Refresh Tableau extract after the SQL pipeline completes.
- Add a certified semantic description to Tableau and Power BI.
- Add run-level validation for all four source-to-event parity checks.
- Add a rollout-scope reporting level if a distinct all-rollout total is required.

### Medium term

- Add employee-home-BU attribution from an authoritative HR source.
- Add application-owner-BU attribution as a separate dimension if required.
- Preserve both user organization and application organization rather than conflating the two.
- Add formal data contracts and schema-change detection.
- Convert suitable snapshot loads to incremental loads after measuring volume and update behavior.
- Add data observability alerts for freshness, volume, null growth, and schema drift.

### AI readiness

- Publish metric definitions through a semantic catalog.
- Provide lineage from certified KPI to source event.
- Add a glossary for CORE, project, timecard, expense report, adoption entity, and rollout wave.
- Store approved synonyms such as “active users” -> Employees Logging In, with a note that the metric is period-specific distinct users.
- Add natural-language query tests with expected SQL and expected grain.
- Add explicit instructions against summing distinct-user subtotals.

---

## 17. Definition of done

The adoption product is production-ready when:

1. All four current KPI rows are present at OVERALL reporting level.
2. All four monthly KPI trends are present using authoritative event dates.
3. Source-to-event parity passes for projects, timecards, and expense reports.
4. Login distinct-user validation passes for sampled periods.
5. No permanent insert relies on positional `SELECT *` behavior.
6. Pipeline failures retain the original SQL error.
7. No stale RUNNING records remain after failed sessions.
8. Tableau uses only `goldview.v_core_adoption` for the adoption dashboard.
9. Tableau KPI cards reconcile exactly to SQL.
10. The current partial month is labeled as incomplete.
11. Employee totals are not calculated by summing lower-level distinct counts.
12. The dataset has a documented owner, refresh schedule, and support process.

---

## 18. Compact implementation prompt for an AI agent

Use the following block when a shorter executable prompt is required.

```text
Build and maintain an enterprise SQL Server medallion data product named CORE Pulse.

Source is BvCoreProd through linked server BncDb. Implement bronze source-aligned tables, silver conformed atomic facts, gold current/event facts, DataOps controls, and one certified adoption view: goldview.v_core_adoption.

Authoritative KPI rules:
1. Contracts Created = distinct Project.ProjectId using Project.CreatedDate.
2. Employees Logging In = distinct non-service APPUserId per period using ApplicationLog.CreatedDate where ApplicationLogType.Name = 'Application Login'.
3. Timesheets Submitted = distinct Timesheet.TimecardId where SubmittedDate is not null, using SubmittedDate as event date. Do not use ProjectTask.ActualHours or task timeline events as the timesheet-submission source.
4. Expense Reports = distinct ExpenseReportId where SubmittedDate is not null, using SubmittedDate as event date.

Required source domains: Admin.BusinessUnit; Project.Project, ProjectService, ProjectPhase, ProjectTask, ProjectTaskTimelineEvent; OP.ApplicationLog, Application, APPUser; Admin.ApplicationLogType; Timesheet.Timecard, TimecardStatus, TimecardRow, TimecardEntry; Expense.ExpenseReport and ExpenseEntry.

Bronze must preserve selected source fields and add SourceExtractDateTime and PipelineRunId. ApplicationLog is incremental using ApplicationLogId watermark. Never extract APPUser passwords, confirmation codes, security codes, or MFA keys. Stage remote snapshots before replacing bronze data. Use explicit permanent-table column lists and never INSERT SELECT * into permanent tables.

Silver grains:
- organization: one CORE BU
- project: one ProjectId
- task_activity: one ProjectTaskId joined Task -> Phase -> Service -> Project
- login_activity: ActivityDate x APPUserId x ApplicationId, excluding service accounts
- timecard: one TimecardId
- timecard_row: one TimecardRowId
- timecard_entry: one TimecardEntryId
- expense_report: one submitted ExpenseReportId
- expense_entry: one ExpenseEntryId

Use CORE-native BU/company/country/region as primary geography. Local dbo.vDimOrganization enrichment is optional through a left join and must never exclude CORE records. ApplicationCode maps to governed AdoptionEntity and AdoptionWaveNumber through silver.application_mapping. Do not fabricate login BU attribution.

Gold facts:
- coreadoption_kpi_daily for current cumulative KPI snapshots
- coreadoption_user_activity at Date x User x Application
- coreadoption_event for authoritative events PROJECT_CREATED, LOGIN, TIMECARD_SUBMITTED, and EXPENSE_SUBMISSION

Certified view goldview.v_core_adoption must combine RecordType CURRENT and MONTHLY with explicit ReportingLevel OVERALL, WAVE, ENTITY, and BUSINESS_UNIT. Publish KPIName, KPIValue, period, completeness flag, wave/entity, CORE geography, supporting row count, mapping exceptions, and load timestamp.

Employees are non-additive. Recalculate COUNT(DISTINCT APPUserId) at every reporting level. Consumers must use the precomputed row for the requested level and must never sum entity or wave employee counts. Omit employee BUSINESS_UNIT rows until a governed mapping exists.

Implement DataOps pipeline registry, run log, step log, watermark, and validation. Use XACT_ABORT. Roll back before logging in every CATCH block. Preserve the original source error. Ensure idempotent deployment and safe reruns.

Validate four current KPIs, four monthly trends, source-to-event parity, referential integrity, freshness, and distinct-user behavior. Publish no actual data, secrets, passwords, or personal information in documentation or prompts.
```

---

## 19. Documentation governance

This document contains architecture and semantics only. Before distributing externally:

- Confirm it contains no screenshots with production values.
- Confirm it contains no employee names, IDs, emails, LDAP values, or record identifiers.
- Confirm all example values remain clearly synthetic.
- Confirm linked-server and database names are acceptable for the intended audience.
- Redact internal object names if the document leaves the engineering organization.
- Version the document when KPI logic changes.

### Suggested document metadata

```text
Document owner: BI Data Engineering
Business owner: CORE Product / Operations
Version: 1.0
Status: Implementation baseline
Review cadence: Quarterly and upon KPI-definition change
```

---

## 20. Final consumer contract

The downstream system should need to understand only this interface:

```text
Dataset: goldview.v_core_adoption
Measure: KPIValue
Dimensions: RecordType, ReportingLevel, PeriodDate, KPIName, Wave, Entity, CORE Geography
Freshness: LoadDateTime
Period completeness: IsCompleteMonth
```

The engineering complexity remains behind the certified view. Tableau, Power BI, an MCP server, Tableau Pulse, or a conversational AI system should not need to reconstruct project, login, timecard, or expense business logic independently.
