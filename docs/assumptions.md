# Assumptions & Design Decisions — CORE Pulse

1. **100% Synthetic Organization:**
   - All entities, business units, project codes, user IDs (`U1001`..), service accounts (`SVC_*`), timestamps, and rollout schedules are deterministically generated (`DEMO_SEED=42`) and contain zero real company or employee data.
2. **Deterministic Reference Clock (`AS_OF_DATE = 2026-11-17`):**
   - Dataset spans **18 calendar months** (`2025-06-01` through `2026-11-17`): **17 complete closed months** (`Jun 2025 – Oct 2026`, `IsCompleteMonth = 1`) plus **1 partial open month** (`Nov 2026`, 17 days elapsed, `IsCompleteMonth = 0`).
   - Month-to-Date (`MTD`) comparisons compare `2026-11-01 .. 2026-11-17` against the **equivalent 17-day prior-month window (`2026-10-01 .. 2026-10-17`)** (`coreadoption_event`), while complete-month trends compare `Oct 2026` vs `Sep 2026`.
3. **Default Interpretation of `"How many users are using CORE?"` (`SIMULATED EXTENSION` UX Default):**
   - Per specification, unqualified active-user questions report **unique non-service employees logging in during the current calendar month-to-date (`Nov 2026 MTD`, as of `2026-11-17`)**, clearly labeled as partial MTD alongside the last complete month (`Oct 2026`) and cumulative `CURRENT` distinct user count.
4. **Strict Attribution & Non-Additivity Governance:**
   - **Employees Logging In:** Available at `OVERALL`, `WAVE`, and `ENTITY` (via `silver.application_mapping` where `MappingStatus = 'CONFIRMED'`). **Not available at `BUSINESS_UNIT`** because `OP.ApplicationLog` / `OP.APPUser` carries no authoritative employee home BU. Distinct counts are recomputed at every level and never summed across waves, entities, applications, or months.
   - **Timesheets Submitted:** Available at `OVERALL`, `WAVE`, and `ENTITY` (derived conservatively when all `TimecardRow` entries belong to a single governed Adoption Entity; multi-entity or unmapped timecards stay in `OVERALL` without duplication). **Not available at `BUSINESS_UNIT`** because a single timecard frequently spans tasks across multiple BUs without a governed allocation rule.
   - **Contracts Created & Expense Reports:** Available across `OVERALL`, `WAVE`, `ENTITY`, and `BUSINESS_UNIT` via authoritative `Project.BusinessUnit` and `ExpenseReport.BusinessUnit`.
5. **Simulated Rollout Registry & Module Catalog (`SIMULATED EXTENSION`):**
   - `LIVE` in `reference.rollout_registry` means formal operational cutover has occurred (`ActualGoLiveDate <= AS_OF_DATE` and `RolloutStatus = 'LIVE'`). It does **not** guarantee observed transaction events (e.g. `ROL-LATAM-EXP` is `LIVE` with `0` observed expense submissions, surfacing an actionable adoption gap).
   - Modules marked `NOT INSTRUMENTED` (`Inspector Scheduling`, `Qualifications`, `Laboratory Testing`, `Invoicing`) show registry status only and never use application logins as a proxy for module usage.
6. **Platform & Runtime Stack Alignment:**
   - Per stakeholder direction, CORE Pulse reuses the exact IRIS enterprise prototype stack: Python, SQLAlchemy 2 Core, SQL Server 2022 (with native `SESSION_CONTEXT` Row-Level Security) + DuckDB offline mirror, LiteLLM (`ollama/gpt-oss:20b`, `ollama/qwen2.5-coder:14b`, plus `rules` mode), Streamlit multi-page UI, persistent 10-conversation history, and a read-only Python MCP tool server (`mcp_server/server.py`).
