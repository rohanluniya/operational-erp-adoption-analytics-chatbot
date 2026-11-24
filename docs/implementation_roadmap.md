# CORE Pulse — Modular Enterprise Roadmap

## Current Pilot Scope (Release 1 — Adoption Pulse)
- **Certified Baseline KPIs (`goldview.v_core_adoption`):** Contracts Created, Employees Logging In, Timesheets Submitted, Expense Reports (`CURRENT` & `MONTHLY`; `OVERALL`, `WAVE`, `ENTITY`, and supported `BUSINESS_UNIT` grains).
- **Simulated Extension (`reference.*`):** Rollout Registry & Module Catalog (`PLANNED`, `ONBOARDING`, `LIVE`, `PAUSED`, `RETIRED` vs. observed instrumented activity).
- **DataOps & Governance:** 16-table Bronze layer with `ApplicationLogId` incremental watermark, 10-table Silver conformed layer, Gold event/user/snapshot facts, DataOps run/step/quality logging, dual RLS, and read-only MCP tool interface.

## Future Releases (Design Only — Not Implemented in Release 1)

Each future domain plugs into the same Medallion + Semantic YAML + Read-Only MCP architecture **without altering the four Release 1 Adoption KPI definitions**:

1. **Release 2 — Contracts & Project Delivery Pulse:**
   - Cycle times across `Project -> ProjectService -> ProjectPhase -> ProjectTask`, milestone turnaround, active backlog, and field inspector task completion using dedicated delivery fact tables.
2. **Release 3 — Operational Integrity Pulse:**
   - Contract-setup completeness rules, unsubmitted draft timecard aging, rejected-timesheet rework rates, and cross-BU time-allocation governance rules.
3. **Release 4 — Field Resource Scheduling, Qualifications & Laboratory Throughput:**
   - Instrumenting `Inspector Scheduling`, `Qualifications`, `Laboratory Testing`, and `Invoicing` modules with dedicated source-to-Gold event contracts and HRIS home-BU employee attribution.
4. **Enterprise Production Lift:**
   - Replace synthetic `source_sim.*` with remote incremental extraction from production CORE replicas, bind Entra ID / SSO entitlements to `rls.user_scope_access`, schedule SQL Server Agent / Airflow orchestrators, and point `LiteLLM` at the enterprise-approved managed LLM endpoint.
