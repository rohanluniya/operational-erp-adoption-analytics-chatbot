# CORE Pulse

**CORE Pulse** is an end-to-end governed analytics prototype for the global **CORE** operational platform, built on a 5-stage Medallion warehouse (`source_sim` → `bronze` → `silver` → `gold` → `goldview.v_core_adoption`) and a read-only Model Context Protocol (MCP) semantic layer. Across **34 automated `pytest` checks** (passing `34/34` on both DuckDB and SQL Server 2022), **9 headless browser UI checks**, and a **15-question Golden Evaluation**, deterministic `rules` mode achieves **15/15** tool and fact accuracy (`0.01 s` median latency) while tool-grounded `ollama/qwen2.5-coder:14b` achieves **15/15** tool match and **13/15** strict substring fact match (`10.37 s` median latency on CPU, vs. `0.01 s` in deterministic `rules` mode) with **15/15** numeric/non-additivity guardrail pass across all modes.

> **Synthetic data – prototype for demonstration only.** Fictional company, people and figures.

---

## Architecture, Models & Runtime Stack

- **Data Engineering & Dual Database Backend:** Python (`SQLAlchemy 2 Core`, `pandas`, `pydantic`) executing identical parameterized SQL across **SQL Server 2022** (`core_pulse` database, least-privilege `pulse_reader` login, native `SESSION_CONTEXT` Row-Level Security) and **DuckDB** (`data/core_pulse.duckdb`).
- **Semantic & MCP Layer:** Machine-readable metric catalog (`app/semantic/metrics.yaml`) shared between the Streamlit conversational router (`app/agent/graph.py`) and a standalone JSON-RPC 2.0 read-only MCP server (`mcp_server/server.py`, 10 allowlisted tools + 6 `core://metadata/*` resources).
- **Application UI:** Streamlit (`app/ui/streamlit_app.py`) + Plotly interactive charts, featuring per-user sign-in, persistent last-10 conversation history, cascading RLS scope filters, multi-turn context memory, `"How I got this & Medallion Lineage"` SQL audit drawers, and CSV/Excel exports.
- **Evaluated Models & Hardware:** Served via LiteLLM against an in-cluster CPU Ollama instance (`x86_64` Kubernetes pod, quantized GGUF weights, warm cache):

| Mode / Model | Architecture & Size | Weight Precision | License | Role |
|---|---|---|---|---|
| `rules (no LLM)` | Deterministic Python intent & template engine | N/A | Project code | Zero-LLM offline baseline & fallback |
| `ollama/qwen2.5-coder:14b` | Dense Transformer (`14.8B` parameters) | GGUF `Q4_K_M` | **Apache-2.0** | Tool routing & grounded executive prose |
| `ollama/gpt-oss:20b` | Mixture-of-Experts reasoning model (`20.9B` parameters, low reasoning effort) | GGUF `MXFP4` | **Apache-2.0** | Tool routing & grounded executive prose |

---

## Main Results

### 1. Certified Baseline KPIs (`goldview.v_core_adoption`, `AS_OF_DATE = 2026-11-17`)

| Certified KPI | Counting Formula & Event Timestamp | All-Time Cumulative | Oct 2026 (Complete) | Nov 2026 MTD (Days 1–17) | Supported Grains |
|---|---|---:|---:|---:|---|
| **Contracts Created** | `COUNT(DISTINCT ProjectId)` by `Project.CreatedDate` | **2,303** | 249 | 124 | `OVERALL`, `WAVE`, `ENTITY`, `BUSINESS_UNIT` |
| **Employees Logging In** | `COUNT(DISTINCT APPUserId)` (`Application Login`, `IsServiceAccount = 0`) | **419** | 380 | **278** | `OVERALL`, `WAVE`, `ENTITY` *(Strictly non-additive)* |
| **Timesheets Submitted** | `COUNT(DISTINCT TimecardId)` where `SubmittedDate IS NOT NULL` | **5,373** | 496 | 299 | `OVERALL`, `WAVE`, `ENTITY` |
| **Expense Reports** | `COUNT(DISTINCT ExpenseReportId)` where `SubmittedDate IS NOT NULL` | **1,859** | 196 | 93 | `OVERALL`, `WAVE`, `ENTITY`, `BUSINESS_UNIT` |

### 2. Golden Evaluation & Verification Suite (`results/eval/eval_report.md`)

All runs execute against the live SQL Server 2022 `core_pulse` backend (`1,216` certified rows, `37,116` Gold events). Latencies compare CPU-hosted Ollama inference against deterministic in-process `rules` mode (`0.01 s` median):

| Mode / Model | Questions | Status Match | MCP Tool Match | Grounded Fact Match | Guardrail Pass | Median Latency (s) | P95 Latency (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rules` (baseline) | 15 | **15/15** | **15/15** | **15/15** | **15/15** | **0.01** | 0.27 |
| `ollama/qwen2.5-coder:14b` | 15 | **15/15** | **15/15** | **13/15** | **15/15** | 10.37 | 21.05 |
| `ollama/gpt-oss:20b` | 15 | 14/15 | 13/15 | 10/15 | **15/15** | 8.52 | 11.23 |

- **Automated Test Suite (`pytest`):** **34/34 passed** on DuckDB (`8.25 s`) and **34/34 passed** on SQL Server 2022 (`15.29 s`), including all 12 adversarial edge cases from `prototype.md` and native `SESSION_CONTEXT` Row-Level Security (`1,216` Global rows vs. `532` AMER rows vs. `342` EMEA rows).

---

## How to Reproduce

```bash
# 1. Configure environment (defaults to zero-dependency local DuckDB + offline rules mode)
cp .env.example .env

# 2. Seed all 16 synthetic CORE tables and run the Bronze -> Silver -> Gold -> Certified View pipeline
uv run python scripts/reset_demo_data.py

# 3. Run the 34-case automated verification suite (Medallion parity, 12 edge cases, MCP, RLS, UI smoke)
DB_BACKEND=duckdb uv run pytest -v

# 4. Launch CORE Pulse on http://localhost:8502
APP_ACCESS_CODE=my-access-code DB_BACKEND=duckdb uv run streamlit run app/ui/streamlit_app.py --server.port 8502

# 5. Optional: Run the read-only MCP server over stdio or execute the 15-question Golden Evaluation
DB_BACKEND=duckdb uv run python -m mcp_server.server
DB_BACKEND=duckdb uv run python scripts/run_evaluation.py --models "rules"
```

---

## Further Documentation & Presentation Assets

- **[`APPENDIX.md`](APPENDIX.md):** Medallion schema details, proofs for all 12 adversarial edge cases, dual-database engineering notes, model license records, and enterprise production lift requirements.
- **[`docs/`](docs/):** Contract review ([`source_contract_review.md`](docs/source_contract_review.md)), [`assumptions.md`](docs/assumptions.md), [`kpi_dictionary.md`](docs/kpi_dictionary.md), [`architecture.md`](docs/architecture.md), [`demo_script.md`](docs/demo_script.md), [`user_guide.md`](docs/user_guide.md), and [`implementation_roadmap.md`](docs/implementation_roadmap.md).
- **[`results/`](results/):** Raw Golden Evaluation outputs ([`eval_report.md`](results/eval/eval_report.md), [`evaluation_summary.json`](results/eval/evaluation_summary.json)), SQL Server provisioning & RLS audit ([`mssql_provision.json`](results/mssql_provision.json)), and Playwright UI walkthrough logs ([`walkthrough.jsonl`](results/ui_walkthrough/walkthrough.jsonl)).
- **[`presentation_kit/`](presentation_kit/):** 12-slide executive PowerPoint ([`CORE_Pulse_Executive_Presentation.pptx`](presentation_kit/CORE_Pulse_Executive_Presentation.pptx)), interactive HTML5 deck ([`CORE_Pulse_Executive_Deck.html`](presentation_kit/CORE_Pulse_Executive_Deck.html)), 5 modular 1080p MP4 demo chapters, master walkthrough video, and 17 high-resolution screenshots.
