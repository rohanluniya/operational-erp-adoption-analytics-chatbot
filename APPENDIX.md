# CORE Pulse — Engineering Appendix, Edge-Case Proofs & Governance Details

This appendix documents the Medallion pipeline design, the 12 adversarial edge-case verifications, dual-database execution trade-offs, model license records, and what remains simulated versus an enterprise production integration.

---

## 1. Medallion & DataOps Architecture Details

All layers are physical database tables and views built by `pipelines/medallion.py` and verified on both **DuckDB** (`data/core_pulse.duckdb`) and **SQL Server 2022** (`core_pulse`):

1. **`source_sim.*` (16 normalized CORE tables):** `business_unit`, `project`, `project_service`, `project_phase`, `project_task`, `project_task_timeline_event`, `application_log`, `application_log_type`, `application`, `app_user`, `timecard`, `timecard_status`, `timecard_row`, `timecard_entry`, `expense_report`, and `expense_entry`.
2. **`bronze.core_*` (16 raw landing tables):** Explicit target-column `INSERT` statements (never `SELECT *`), preserving source keys plus `SourceExtractDateTime` and `PipelineRunId`. `bronze.core_application_log` uses an incremental high-water mark (`BigIntWatermark = 127,985` on `ApplicationLogId`) persisted in `dataops.watermark` only after downstream steps commit.
3. **`silver.*` (10 conformed operational tables):**
   - `silver.organization` uses a `LEFT JOIN` against `reference.local_org_enrichment` so CORE Business Units missing optional local enrichment (`BU-AU-REN-10`) remain in certified reporting (`HasLocalEnrichment = 0`).
   - `silver.login_activity` enforces `ApplicationLogType.Name = 'Application Login'` and `APPUser.IsServiceAccount = 0` at `ActivityDate x APPUserId x ApplicationId` grain.
   - `silver.timecard_row` and `silver.expense_entry` flag orphan child rows (`IsOrphanTimecard`, `IsOrphanReport`) and quarantine them from Gold facts while logging exact counts to `dataops.data_quality_metric`.
4. **`gold.*` & `goldview.*`:**
   - `gold.coreadoption_event` (`37,116` events) uses compound `EventKey` (`EventType + ':' + SourceEventId`) to prevent cross-domain key collisions.
   - `gold.coreadoption_user_activity` preserves atomic user-day-application grain so rolling and cross-application engagement (`get_core_user_engagement`) is deduplicated at query time.
   - `goldview.v_core_adoption` (`1,216` certified rows) serves `RecordType` (`CURRENT`, `MONTHLY`) across `OVERALL`, `WAVE`, `ENTITY`, and `BUSINESS_UNIT` (where supported), recomputing `COUNT(DISTINCT APPUserId)` independently at every grain.

---

## 2. Verification of the 12 Adversarial Edge Cases (`tests/test_medallion_and_edge_cases.py`)

| # | Adversarial Scenario | Seeded Fixture | Verified Outcome |
|---:|---|---|---|
| 1 | Same user logs into two apps across Waves 1 & 2 on the same day | `APPUserId = 9001` (`2026-10-14`, `2026-11-10`) | Counted once in `Wave 1`, once in `Wave 2`, and **once** in `OVERALL` (`419` global unique users vs higher naive wave sum). |
| 2 | Same user logs into the same app 5 times on one day | `APPUserId = 9002` (`2026-11-05`) | Collapsed to 1 row in `silver.login_activity` (`LoginEventCount = 5`) and 1 unique employee. |
| 3 | Service accounts generating automated logins | `APPUserId IN (9501..9512)` (`IsServiceAccount = 1`) | Zero rows in `silver.login_activity` and `goldview.v_core_adoption`. |
| 4 | Submitted timecard whose workflow status later became `Exported` | `TimecardId = 99101` (`Status = 'Exported'`, `SubmittedDate` populated) | Included in `Timesheets Submitted` (`SubmittedDate IS NOT NULL` governs inclusion, not current workflow status). |
| 5 | Draft timecard with hours entered but never submitted | `TimecardId = 99102` (`SubmittedDate IS NULL`) | Excluded from `Timesheets Submitted`; task hours are never used as a proxy. |
| 6 | Project created in Oct 2026 with `ProjectStartDate` in Dec 2026 | `ProjectId = 99001` | Bucketed in `2026-10` by `Project.CreatedDate`. |
| 7 | Valid CORE Business Unit missing from optional local enrichment | `BU-AU-REN-10` | Preserved via `LEFT JOIN` in `silver.organization` (`HasLocalEnrichment = 0`) and included in `Contracts Created` & `Expense Reports`. |
| 8 | Expense report submitted in Oct 2026 and edited in Nov 2026 | `ExpenseReportId = 99501` | Bucketed once in `2026-10` by initial `SubmittedDate`. |
| 9 | Module marked `LIVE` in rollout registry with zero observed events | `ROL-LATAM-EXP` (`BU-BR-FLD-09`, `EXPENSES`, live `2026-10-15`) | Reported as `LIVE — ZERO observed events` by `get_core_rollout_status`. |
| 10 | Partial current month (`Nov 2026` as of `2026-11-17`) | `YearMonth = '2026-11'` | Marked `IsCompleteMonth = 0`; benchmarked against `Oct 1–17` equivalent MTD and excluded from complete-month peak rankings. |
| 11 | Multi-BU timecard + BU breakdown request | `TimecardId = 99103` | Counted once in `OVERALL`, flagged in `MappingExceptionRows`, and BU breakdown requests for `Timesheets Submitted` return `unsupported`. |
| 12 | Orphan child records & unconfirmed/sandbox applications | 3 orphan `TimecardRow`, 2 orphan `ExpenseEntry`, `CORE-LEGACY-SYNC` (`REVIEW`), `CORE-SANDBOX-UAT` (`EXCLUDED`) | Quarantined from certified totals and logged in `dataops.data_quality_metric`. |

---

## 3. Dual-Database & Guardrail Engineering Notes

- **DuckDB Single-Process Connection Isolation:** DuckDB rejects simultaneous `read_only=False` and `read_only=True` connections to the same file within a single Python process. `app/db.py` solves this by running all application, RLS lookup, and DataOps status reads over `read_only=True` connections and explicitly disposing pooled engines in `clear_engine_cache()` before and after ETL write operations.
- **SQL Server `SESSION_CONTEXT` RLS on `WAVE` Grain:** Because `WAVE`-level rows in `gold.certified_adoption_store` aggregate across multiple Business Units within a wave (`RegionCode IS NULL`), `sql/rls_mssql.sql` defines `rls.fn_store_access(@RegionCode, @AdoptionWaveNumber)` joining `rls.user_region_access` to `silver.organization` so regional personas (`amer_ops_vp`, `emea_rollout_director`) see exact parity between SQL Server native RLS (`532` AMER rows, `342` EMEA rows) and DuckDB.
- **MCP Parameter Signature Filtering:** Smaller or reasoning LLMs occasionally emit extra contextual arguments (for example passing `kpi_name` into `get_core_user_engagement`). `mcp_server/server.py` inspects `inspect.signature(fn)` on every allowlisted tool call, stripping extraneous or untrusted keys (`sql`, `query`, `path`, `user_id`) while preserving strict schema safety.
- **Numeric & Non-Additivity Prose Guardrail:** `app/agent/guardrails.py` verifies every standalone number in LLM-generated prose against the structured `ToolPayload` (`headline`, `facts`, `warnings`, and `df`). Any ungrounded number or naive wave-sum claim triggers an automatic fallback to deterministic templated narration.

---

## 4. Model Licenses & Governance Record

| Model Identifier | Role in CORE Pulse | License | Usage Restrictions / Notes |
|---|---|---|---|
| `rules (no LLM)` | Deterministic router & templated executive narration | Project code | Zero external model dependency; 100% offline deterministic execution. |
| `ollama/qwen2.5-coder:14b` | Tool selection & grounded executive summary narration | **Apache-2.0** ([Qwen/Qwen2.5-Coder-14B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct)) | Permissive commercial & research license; zero territorial or company-size restrictions. |
| `ollama/gpt-oss:20b` | Reasoning tool selection & grounded executive summary narration | **Apache-2.0** ([openai/gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b)) | Permissive Apache 2.0 open-weight license; zero territorial or company-size restrictions. |

---

## 5. What Remains Simulated vs. Enterprise Production Requirements

- **Simulated in Pilot:**
  - All 16 `source_sim.*` operational tables are deterministically generated (`seed=42`, `AS_OF_DATE=2026-11-17`).
  - `reference.rollout_registry` and `reference.module_catalog` are explicitly marked `SIMULATED EXTENSION` (`prototype.md` does not define a live rollout tracker table).
  - Four future-release modules (`INSPECTOR_SCHED`, `QUALIFICATIONS`, `LAB_TESTING`, `INVOICING`) are status-only (`NOT_INSTRUMENTED`).
  - Demo authentication uses a shared access code (`APP_ACCESS_CODE`) rather than enterprise SSO.
- **Required for Enterprise Production Integration:**
  1. Replace `source_sim.*` seeding with read-only CDC / incremental extraction from production CORE SQL Server replicas, retaining the `ApplicationLogId` watermark + 7-day late-arrival lookback window.
  2. Bind Microsoft Entra ID / Active Directory group claims directly to SQL Server `sp_set_session_context @key=N'user_id', @read_only=1`.
  3. Integrate authoritative HRIS worker home-BU master data (`EmployeeId <-> APPUserId`) before enabling Business Unit attribution for `Employees Logging In`, and establish a finance-approved multi-BU timecard allocation rule before enabling Business Unit attribution for `Timesheets Submitted`.
