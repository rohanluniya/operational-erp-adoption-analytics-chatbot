# CORE Pulse — 5-Minute Executive Demo Script

**Audience:** Executive Leadership, CORE Program Sponsors, Regional Operations VPs  
**Dataset:** Synthetic data – prototype for demonstration only (fictional company, people and figures)  
**Objective:** Show how Medallion Data Engineering (`Bronze -> Silver -> Gold -> goldview.v_core_adoption`) + a Read-Only MCP Semantic Layer eliminate metric drift, non-additive employee double-counting, and partial-month false alarms.

---

## Minute 0:00–1:00 — Sign-In, Executive KPI Strip & Partial-Month Discipline

1. Sign in as **Alex Morgan** (`Global CORE Program Lead`).
2. Point to the **Four Certified KPI Cards** at the top of **Chat**:
   - **Contracts Created:** `2,303` all-time cumulative (`Oct 2026` complete month vs `Nov 2026 MTD` days 1–17).
   - **Employees Logging In:** `Nov 2026 MTD` unique non-service employees (`IsServiceAccount = 0`), compared fairly against `Oct 1–17` equivalent MTD rather than flagging an artificial mid-month drop.
   - **Timesheets Submitted:** `5,373` formal submitted timecards (`SubmittedDate IS NOT NULL`, including timecards later approved or exported).
   - **Expense Reports:** `1,859` submitted expense reports by initial `SubmittedDate`.

## Minute 1:00–2:30 — Multi-Turn Adoption & Non-Additivity Proof

Ask the 3-turn executive adoption sequence:

1. **Prompt 1:** `How many employees logged into CORE this month?`
   - *Highlight:* CORE Pulse names the exact window (`Nov 2026 MTD, days 1–17, partial month`), compares against `Oct 1–17` equivalent MTD, and displays `Oct 2026 (complete month)`.
2. **Prompt 2:** `Show the six-month trend.`
   - *Highlight:* Context memory retains `Employees Logging In`. Complete months (`Jun–Oct 2026`) plot on a solid teal line while `Nov 2026 MTD` plots as an amber dotted diamond so executives never mistake an incomplete month for a drop.
3. **Prompt 3:** `Which rollout wave is most active?`
   - *Highlight:* Breaks unique employees down across Waves 1–4 **and** proves non-additivity: the true deduplicated `OVERALL` count is lower than the naive sum across Waves 1–4 because cross-wave employees (`U9001` and peers) are counted once per wave and deduplicated globally.

## Minute 2:30–3:45 — Rollout Go-Live vs. Actual Instrumented Activity

4. **Prompt 4:** `Which modules are live for the Western region?`
   - *Highlight:* Resolves *"Western region"* to `AMER` (`Americas`), queries `reference.rollout_registry` (`SIMULATED EXTENSION`), and distinguishes `INSTRUMENTED` modules (`CORE_LOGIN`, `PROJECTS`, `TIMECARDS`, `EXPENSES`) from `NOT_INSTRUMENTED` status-only modules (`INSPECTOR_SCHED`, `QUALIFICATIONS`, `LAB_TESTING`, `INVOICING`).
5. **Prompt 5:** `Are those modules actually seeing activity?`
   - *Highlight:* Retains `AMER` context and surfaces the actionable rollout gap: **`ROL-LATAM-EXP`** (`Latin America Operations · Expense Reports`, Wave 4) has been marked `LIVE` since `2026-10-15` yet has **zero observed expense submissions**.

## Minute 3:45–5:00 — Governed Refusals, RLS & Medallion Lineage Without SQL Overload

6. **Prompt 6:** `Show me how this metric was calculated and where the data came from.`
   - *Highlight:* Displays the exact counting rule, exclusions, and 5-stage Medallion path (`source_sim -> bronze -> silver -> gold -> goldview.v_core_adoption`) without forcing executives to parse raw SQL—while keeping the exact parameterized SQL available inside **How I got this & Medallion Lineage**.
7. **Bonus Governance Check:** Ask `Can you show Employees Logging In by Business Unit?` or switch Persona in **Settings** to **`EMEA Rollout Director`** and ask about `AMER` to show polite, deterministic Row-Level Security and attribution boundary enforcement.
