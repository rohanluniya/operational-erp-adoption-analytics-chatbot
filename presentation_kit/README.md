# CORE Pulse — Executive Presentation & Video Kit

This folder contains the executive presentation decks, modular 1080p H.264 (`yuv420p`) demo snippets, master walkthrough video, and high-resolution screenshots captured live from **CORE Pulse** (`:8502`, backed by SQL Server 2022 `core_pulse` with native `SESSION_CONTEXT` Row-Level Security).

## Slide Decks

| Artifact | Format | Purpose |
|---|---|---|
| `CORE_Pulse_Executive_Presentation.pptx` | Native 16:9 PowerPoint | 12-slide executive presentation with vector Medallion architecture diagrams, embedded 1080p MP4 demo chapters, poster frames, and speaker notes. |
| `CORE_Pulse_Executive_Deck.html` | Standalone HTML5 Deck | Interactive browser presentation (`ArrowLeft` / `ArrowRight`) embedding the 5 live 1080p MP4 videos directly in Slides 5–9. |

## Video Chapters (`videos/`)

| File | Scope Demonstrated |
|---|---|
| `00_core_pulse_master_walkthrough.mp4` | Complete end-to-end executive walkthrough concatenating Chapters 1–5 in 1080p H.264. |
| `01_signin_and_executive_kpi_strip.mp4` | Sign-in gate, synthetic data banner, and the 4 certified KPI cards (`2,303` Contracts, `Nov 2026 MTD` Logins, `5,373` Timecards, `1,859` Expenses) with explicit period labels. |
| `02_multiturn_adoption_and_nonadditivity.mp4` | 3-turn context memory (`MTD` -> `6-month trend` with amber dotted partial-month marker -> `Rollout Wave` breakdown proving `COUNT(DISTINCT APPUserId)` deduplication) + SQL/lineage drawer. |
| `03_rollout_vs_observed_activity_gap.mp4` | Resolving `Western region` -> `AMER`, contrasting `SIMULATED EXTENSION` go-live status against observed Gold events, and surfacing `ROL-LATAM-EXP` (`LIVE` with zero expense submissions). |
| `04_persona_rls_and_governance_guardrails.mp4` | Unsupported BU breakdown refusal, switching Persona to `EMEA Rollout Director` (`SESSION_CONTEXT` RLS), cross-region refusal, and prompt-injection defense. |
| `05_medallion_catalog_and_dataops_lineage.mp4` | Navigating **Data Catalog** (`Governed KPI Dictionary`, `Source-to-Answer Lineage`, `DataOps & Quality Checks` watermark `127,985` & orphan quarantine, `Medallion Table Preview`) and **About**. |

## Reproducing the Kit

```bash
# 1. Record 1080p videos and screenshots against a running CORE Pulse instance
APP_ACCESS_CODE=my-access-code python scripts/record_presentation_kit.py http://localhost:8502 presentation_kit

# 2. Build both the 12-slide .pptx and standalone .html executive decks
python scripts/build_executive_deck.py
```
