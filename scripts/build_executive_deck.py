"""Generate the 12-Slide CORE Pulse Executive Presentation Kit:
  1. `presentation_kit/CORE_Pulse_Executive_Presentation.pptx` (native 16:9 widescreen PowerPoint with embedded 1080p MP4s, poster frames, vector Medallion diagrams, and speaker notes)
  2. `presentation_kit/CORE_Pulse_Executive_Deck.html` (standalone interactive widescreen HTML5 deck with embedded 1080p MP4s and keyboard navigation)

Designed for business & data leadership: emphasizes how structured Medallion Data Engineering makes
conversational BI effortless, trustworthy, and repeatable using free, lightweight open-source models.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "presentation_kit"
VID = KIT / "videos"
IMG = KIT / "screenshots"
OUT_PPTX = KIT / "CORE_Pulse_Executive_Presentation.pptx"
OUT_HTML = KIT / "CORE_Pulse_Executive_Deck.html"

NAVY = RGBColor(0x0B, 0x1F, 0x3A)
TEAL = RGBColor(0x0F, 0x76, 0x6E)
TEAL_BG = RGBColor(0xE6, 0xF4, 0xF1)
INDIGO = RGBColor(0x37, 0x30, 0xA3)
INDIGO_BG = RGBColor(0xEE, 0xF0, 0xFB)
RED = RGBColor(0xDC, 0x26, 0x26)
RED_BG = RGBColor(0xFE, 0xF2, 0xF2)
BRONZE = RGBColor(0x92, 0x40, 0x0E)
BRONZE_BG = RGBColor(0xFE, 0xF3, 0xC7)
SILVER = RGBColor(0x33, 0x41, 0x55)
SILVER_BG = RGBColor(0xF1, 0xF5, 0xF9)
GOLD = RGBColor(0xB4, 0x53, 0x09)
GOLD_BG = RGBColor(0xFE, 0xF9, 0xC3)
SLATE = RGBColor(0x47, 0x55, 0x69)
BORDER = RGBColor(0xCB, 0xD5, 0xE1)
BG = RGBColor(0xF8, 0xFA, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def set_bg(slide, color: RGBColor) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_box(slide, x, y, w, h, fill_rgb=WHITE, line_rgb=BORDER, line_pt=1.0, radius=True):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    sh = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius and len(sh.adjustments) > 0:
        sh.adjustments[0] = 0.04
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill_rgb
    if line_rgb is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line_rgb
        sh.line.width = Pt(line_pt)
    return sh


def add_text(slide, x, y, w, h, text, size=14, bold=False, color=NAVY, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(4)
    tf.margin_top = tf.margin_bottom = Pt(2)
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text.replace("`", "")
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = "Calibri"
    return tb


def add_bullets(slide, x, y, w, h, items: list[tuple[str, str]], size=12.0, space_after=6):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, (lead, rest) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(space_after)
        r1 = p.add_run()
        r1.text = f"• {lead.replace('`', '')}: " if lead else "• "
        r1.font.size = Pt(size)
        r1.font.bold = True
        r1.font.color.rgb = NAVY
        r1.font.name = "Calibri"
        r2 = p.add_run()
        r2.text = rest.replace("`", "")
        r2.font.size = Pt(size)
        r2.font.bold = False
        r2.font.color.rgb = SLATE
        r2.font.name = "Calibri"
    return tb


def slide_header(slide, kicker: str, title: str, badge: str, num: int) -> None:
    set_bg(slide, BG)
    add_text(slide, 0.55, 0.32, 9.5, 0.28, kicker.upper(), size=10.5, bold=True, color=TEAL)
    add_text(slide, 0.55, 0.56, 10.1, 0.55, title, size=22.5, bold=True, color=NAVY)
    b = add_box(slide, 10.75, 0.44, 2.02, 0.38, fill_rgb=INDIGO_BG, line_rgb=INDIGO, line_pt=0.8)
    p = b.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = badge
    r.font.size = Pt(9.8)
    r.font.bold = True
    r.font.color.rgb = INDIGO
    r.font.name = "Calibri"
    add_box(slide, 0.55, 1.16, 12.22, 0.02, fill_rgb=BORDER, line_rgb=None, radius=False)
    add_text(slide, 0.55, 7.12, 9.5, 0.25,
             "CORE Pulse · From Structured Medallion Data Engineering to Effortless Conversational BI",
             size=9, color=SLATE)
    add_text(slide, 11.5, 7.12, 1.25, 0.25, f"{num} / 12", size=9.5, bold=True, color=SLATE, align=PP_ALIGN.RIGHT)


def add_callout(slide, y: float, text: str) -> None:
    add_box(slide, 0.55, y, 12.22, 0.56, fill_rgb=TEAL_BG, line_rgb=TEAL, line_pt=1.2)
    add_text(slide, 0.72, y + 0.10, 11.9, 0.38, text, size=11.8, bold=True, color=NAVY)


def add_video_slide(prs, num: int, kicker: str, title: str, badge: str,
                    mp4_name: str, poster_name: str, card_title: str,
                    bullets: list[tuple[str, str]], thumb1: str, thumb2: str, notes: str) -> None:
    sl = prs.slides.add_slide(prs.slide_layouts[6])
    slide_header(sl, kicker, title, badge, num)
    add_box(sl, 0.53, 1.36, 7.58, 4.64, fill_rgb=NAVY, line_rgb=BORDER, line_pt=1.2)
    add_text(sl, 0.68, 1.42, 7.2, 0.28, f"▶  {mp4_name}  (Click video in PowerPoint slideshow to play 1080p clip)",
             size=10, bold=True, color=WHITE)
    mp4_path = VID / mp4_name
    poster_path = IMG / poster_name
    if mp4_path.exists() and poster_path.exists():
        sl.shapes.add_movie(
            str(mp4_path),
            Inches(0.56), Inches(1.73), Inches(7.52), Inches(4.23),
            poster_frame_image=str(poster_path),
            mime_type="video/mp4",
        )
    if (IMG / thumb1).exists():
        sl.shapes.add_picture(str(IMG / thumb1), Inches(0.55), Inches(6.08), width=Inches(3.68))
    if (IMG / thumb2).exists():
        sl.shapes.add_picture(str(IMG / thumb2), Inches(4.40), Inches(6.08), width=Inches(3.68))

    add_box(sl, 8.30, 1.36, 4.47, 5.62, fill_rgb=WHITE, line_rgb=TEAL, line_pt=1.5)
    add_box(sl, 8.30, 1.36, 4.47, 0.08, fill_rgb=TEAL, line_rgb=None, radius=False)
    add_text(sl, 8.48, 1.54, 4.1, 0.4, card_title, size=15, bold=True, color=NAVY)
    add_bullets(sl, 8.45, 2.00, 4.18, 4.85, bullets, size=11.8, space_after=8)
    sl.notes_slide.notes_text_frame.text = notes


def build_pptx() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # SLIDE 1: HERO & ICEBERG
    s1 = prs.slides.add_slide(blank)
    set_bg(s1, NAVY)
    add_box(s1, 0.55, 0.52, 5.35, 0.36, fill_rgb=TEAL, line_rgb=None)
    add_text(s1, 0.68, 0.56, 5.15, 0.28, "FROM AI-READY DATA ENGINEERING TO CONVERSATIONAL BI", size=9.6, bold=True, color=WHITE)
    add_text(s1, 0.55, 1.05, 7.1, 1.35, "CORE Pulse: Turning Clean Data\nInto Instant Rollout Intelligence", size=29, bold=True, color=WHITE)
    add_text(s1, 0.55, 2.48, 7.0, 1.35,
             "Showing how a clean, structured Medallion data foundation (Bronze → Silver → Gold → Certified View) "
             "makes it fast and effortless to launch an intuitive conversational assistant—so leaders can ask "
             "plain-English rollout questions and get trusted answers, charts, and Excel exports in seconds.",
             size=14.0, color=RGBColor(0xE2, 0xE8, 0xF0))

    hero_kpis = [
        ("90% Data Foundation", "Clean Bronze → Silver → Gold tables do the heavy lifting"),
        ("8–10s Answers", "Plain-English questions return insights, tables & charts"),
        ("Free Open-Source AI", "Lightweight local open-source models at $0 API cost"),
    ]
    for i, (kv, kl) in enumerate(hero_kpis):
        bx = 0.55 + i * 2.38
        add_box(s1, bx, 4.22, 2.24, 1.50, fill_rgb=RGBColor(0x13, 0x2F, 0x54), line_rgb=TEAL, line_pt=1.2)
        add_text(s1, bx + 0.12, 4.36, 2.0, 0.4, kv, size=15.0, bold=True, color=RGBColor(0x5E, 0xEA, 0xD4))
        add_text(s1, bx + 0.12, 4.80, 2.0, 0.80, kl, size=10.2, color=WHITE)

    add_box(s1, 0.55, 6.02, 7.0, 0.68, fill_rgb=RGBColor(0x1E, 0x29, 0x3B), line_rgb=RGBColor(0xF5, 0x9E, 0x0B), line_pt=1.0)
    add_text(s1, 0.70, 6.14, 6.7, 0.44,
             "Synthetic data – prototype for demonstration only. Fictional company, people and figures.",
             size=10.8, bold=True, color=RGBColor(0xFD, 0xE6, 0x8A))

    # Iceberg card on right
    add_box(s1, 7.95, 0.52, 4.82, 6.42, fill_rgb=WHITE, line_rgb=TEAL, line_pt=2.0)
    add_text(s1, 8.15, 0.68, 4.4, 0.32, "THE ANALYTICS & AI ICEBERG", size=11.5, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    add_box(s1, 8.20, 1.08, 4.32, 1.18, fill_rgb=INDIGO_BG, line_rgb=INDIGO, line_pt=1.2)
    add_text(s1, 8.32, 1.14, 4.1, 0.24, "VISIBLE SURFACE (10%) — EASY CONVERSATIONAL UX", size=9.2, bold=True, color=INDIGO)
    add_box(s1, 8.32, 1.43, 2.0, 0.68, fill_rgb=INDIGO, line_rgb=None)
    add_text(s1, 8.36, 1.50, 1.92, 0.55, "CORE Pulse Chat\nRollout & Lineage UI", size=9.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_box(s1, 10.40, 1.43, 2.0, 0.68, fill_rgb=WHITE, line_rgb=INDIGO, line_pt=1.0)
    add_text(s1, 10.44, 1.50, 1.92, 0.55, "Power BI · Tableau\nExcel Exports", size=9.5, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(s1, 8.20, 2.38, 4.32, 0.26, "─── STRUCTURED DATA ENGINEERING (90%) ───", size=9.2, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    layers = [
        ("Certified Semantic Layer", "goldview.v_core_adoption · Governed KPIs · Access Control", TEAL_BG, TEAL),
        ("Gold Layer — Business Facts", "37,116 Clean Events · Daily User Activity · 1,216 Rollups", GOLD_BG, GOLD),
        ("Silver Layer — Clean & Conformed", "Standardized Org Hierarchy · Service Accounts Excluded", SILVER_BG, SILVER),
        ("Bronze & DataOps Tracking", "16 CORE Source Tables · Incremental Watermarks · QA Checks", BRONZE_BG, BRONZE),
    ]
    for idx_l, (lt, ld, lbg, lbd) in enumerate(layers):
        ly = 2.72 + idx_l * 0.98
        add_box(s1, 8.20, ly, 4.32, 0.84, fill_rgb=lbg, line_rgb=lbd, line_pt=1.1)
        add_text(s1, 8.34, ly + 0.08, 4.05, 0.28, lt, size=10.5, bold=True, color=NAVY)
        add_text(s1, 8.34, ly + 0.38, 4.05, 0.36, ld, size=9.5, color=SLATE)

    # SLIDE 2: WHY ROLLOUT ANALYTICS DRIFTS WITHOUT DATA ENGINEERING
    s2 = prs.slides.add_slide(blank)
    slide_header(s2, "Executive Context", "Why Rollout Reporting Breaks Without Clean Data Engineering", "Problem → Solution", 2)
    traps = [
        ("1. Double-Counting Active Users", "Adding Wave 1 + Wave 2 logins inflates headcount whenever specialists work across multiple regions. Our Gold layer deduplicates unique employees automatically at every level.", RED_BG, RED),
        ("2. Shifting Historical Dates", "Grouping contracts by start date or expenses by last-modified date changes past months whenever records are edited. CORE Pulse locks strictly to original creation and submission dates.", RED_BG, RED),
        ("3. 'Live' on Paper vs. Real Usage", "A tracker marking Expenses 'Live' in a country does not mean teams are submitting claims. CORE Pulse compares go-live status directly against actual recorded transactions.", INDIGO_BG, INDIGO),
        ("4. Mid-Month False Alarms", "Comparing 17 days of November against a full 31-day October creates fake 'adoption drops'. CORE Pulse compares month-to-date fairly against the same 17 days of the prior month.", TEAL_BG, TEAL),
    ]
    for i, (tt, td, bgc, bdc) in enumerate(traps):
        cx = 0.55 + (i % 2) * 6.22
        cy = 1.40 + (i // 2) * 2.15
        add_box(s2, cx, cy, 5.98, 1.92, fill_rgb=bgc, line_rgb=bdc, line_pt=1.4)
        add_text(s2, cx + 0.20, cy + 0.16, 5.58, 0.36, tt, size=15, bold=True, color=NAVY)
        add_text(s2, cx + 0.20, cy + 0.60, 5.58, 1.15, td, size=12.2, color=SLATE)
    add_callout(s2, 5.88, "Core Takeaway: Solve business rules once in the Medallion data pipeline—then every dashboard and AI chat stays 100% aligned.")

    # SLIDE 3: 5-STAGE MEDALLION ARCHITECTURE
    s3 = prs.slides.add_slide(blank)
    slide_header(s3, "Data Engineering Foundation", "How the Data Was Structured: 5-Stage Medallion Pipeline", "Medallion ETL", 3)
    stages = [
        ("1. SOURCE", "16 Operational Tables", ["Business Units & Projects", "Application Login Logs", "Timecards & Statuses", "Expense Reports & Lines"], "Raw operational grain", SILVER_BG, SILVER),
        ("2. BRONZE", "Raw Landing + Audit", ["16 bronze.core_* tables", "Explicit column mapping", "Extract timestamps", "Incremental log watermark"], "Zero duplicate loads", BRONZE_BG, BRONZE),
        ("3. SILVER", "Cleaned & Standardized", ["Unified org & wave hierarchy", "Service accounts removed", "Draft records separated", "Orphan rows quarantined"], "10 conformed tables", SILVER_BG, TEAL),
        ("4. GOLD", "Curated Business Facts", ["Unified adoption events", "Daily unique user activity", "Daily KPI snapshots", "Pre-validated parity"], "37,116 clean events", GOLD_BG, GOLD),
        ("5. CERTIFIED", "Ready for AI & BI", ["goldview.v_core_adoption", "Current & Monthly views", "Wave, Entity & BU levels", "Role-based data security"], "Single source of truth", TEAL_BG, INDIGO),
    ]
    for idx_s, (pill, sh_t, s_bul, foot, bgc, bdc) in enumerate(stages):
        sx = 0.55 + idx_s * 2.48
        add_box(s3, sx, 1.40, 2.34, 4.30, fill_rgb=WHITE, line_rgb=bdc, line_pt=1.5)
        add_box(s3, sx + 0.12, 1.54, 2.10, 0.32, fill_rgb=bgc, line_rgb=bdc, line_pt=0.8)
        add_text(s3, sx + 0.14, 1.57, 2.06, 0.26, pill, size=9.5, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
        add_text(s3, sx + 0.12, 1.96, 2.10, 0.34, sh_t, size=13, bold=True, color=NAVY)
        add_bullets(s3, sx + 0.08, 2.36, 2.18, 2.65, [("", b) for b in s_bul], size=10.5, space_after=5)
        add_text(s3, sx + 0.12, 5.26, 2.10, 0.30, foot, size=10.5, bold=True, color=TEAL)
    add_callout(s3, 5.92, "Repeatable Engineering: Automated watermarks and data-quality checks ensure every refresh is clean, auditable, and idempotent.")

    # SLIDE 4: FOUR CERTIFIED KPIS & SEMANTIC BOUNDARIES
    s4 = prs.slides.add_slide(blank)
    slide_header(s4, "Governed Business Rules", "Four Certified Adoption KPIs & Clear Reporting Boundaries", "Certified KPIs", 4)
    kpi_cards = [
        ("Contracts Created · 2,303", "Distinct Projects Created (by Creation Date)",
         "Available Overall, by Wave, by Adoption Entity, and by Business Unit. Always anchored to creation date rather than planned start date.", TEAL),
        ("Employees Logging In · 419", "Unique Active Employees (Excluding Service Accounts)",
         "Available Overall, by Wave, and by Entity. Automatically deduplicated at every level; blocked at Business Unit until HR home-BU data is linked.", INDIGO),
        ("Timesheets Submitted · 5,373", "Formal Submitted Timecards (by Submission Date)",
         "Includes timecards later approved or exported; excludes unsubmitted drafts. Blocked at Business Unit because one timecard can span multiple BUs.", TEAL),
        ("Expense Reports · 1,859", "Submitted Expense Claims (by Submission Date)",
         "Available Overall, by Wave, by Adoption Entity, and by Business Unit. Anchored to initial submission date regardless of post-submission edits.", INDIGO),
    ]
    for i, (kt, kf, kd, bdc) in enumerate(kpi_cards):
        cx = 0.55 + (i % 2) * 6.22
        cy = 1.38 + (i // 2) * 2.16
        add_box(s4, cx, cy, 5.98, 1.96, fill_rgb=WHITE, line_rgb=bdc, line_pt=1.5)
        add_text(s4, cx + 0.18, cy + 0.14, 5.6, 0.36, kt, size=15, bold=True, color=NAVY)
        add_text(s4, cx + 0.18, cy + 0.52, 5.6, 0.32, kf, size=11, bold=True, color=TEAL)
        add_text(s4, cx + 0.18, cy + 0.90, 5.6, 0.92, kd, size=11.5, color=SLATE)
    add_callout(s4, 5.90, "Built-In Honesty: Where a Business Unit breakdown isn't supported by source data yet, the assistant explains why instead of guessing.")

    # SLIDES 5–9: 5 MODULAR 1080p DEMO VIDEO CHAPTERS
    add_video_slide(
        prs, 5, "Live Walkthrough · Chapter 1", "Sign-In, Personal Workspace & Clear Executive KPI Summary", "Video 01",
        "01_signin_and_executive_kpi_strip.mp4", "02_executive_kpi_strip.png", "Simple, Intuitive Start",
        [
            ("Personal Conversation History", "Each signed-in leader gets their own saved conversations, pinned threads, and filter context."),
            ("Crystal-Clear Time Labels", "Top KPI cards clearly separate All-Time Cumulative, Last Closed Month (Oct), and Current MTD (Nov 1–17)."),
            ("Fair Mid-Month Context", "Nov 1–17 MTD is shown right alongside Oct 1–17 so leaders see true momentum at a glance."),
            ("Guided Prompt Buttons", "One-click starter questions let any executive explore adoption immediately with zero training."),
        ],
        "01_signin_gate.png", "03_overall_adoption_snapshot.png",
        "Chapter 1 shows how easy it is to sign in, read the four headline KPIs, and ask an overview question.",
    )

    add_video_slide(
        prs, 6, "Live Walkthrough · Chapter 2", "Natural Follow-Up Questions & Automatic User Deduplication", "Video 02",
        "02_multiturn_adoption_and_nonadditivity.mp4", "06_wave_nonadditivity_and_sql.png", "Conversational Flow",
        [
            ("Remembers Context", "Ask 'How many employees logged in this month?' then simply say 'Show the six-month trend.'"),
            ("Visual Partial-Month Cue", "In-progress November plots as an amber dotted marker so no one mistakes it for a drop."),
            ("Smart Wave Breakdown", "Asking 'Which rollout wave is most active?' shows each wave AND the true deduplicated global total."),
            ("One-Click Proof & Export", "Download any table to CSV/Excel or expand 'How I got this' to see exact lineage and SQL."),
        ],
        "05_six_month_trend_partial_flag.png", "06_wave_nonadditivity_and_sql.png",
        "Chapter 2 demonstrates natural multi-turn follow-ups, partial-month chart clarity, and cross-wave user deduplication.",
    )

    add_video_slide(
        prs, 7, "Live Walkthrough · Chapter 3", "Tracking Rollout Go-Live vs. Actual Field Usage", "Video 03",
        "03_rollout_vs_observed_activity_gap.mp4", "09_rollout_zero_activity_gap.png", "Actionable Rollout Tracking",
        [
            ("Understands Business Terms", "Asking about the 'Western region' automatically maps to Americas (AMER)."),
            ("Go-Live vs. Real Activity", "Compares rollout tracker status against actual recorded transactions in the Gold layer."),
            ("Clear Module Scope", "Distinguishes instrumented Release 1 modules from status-only future modules."),
            ("Instant Gap Detection", "Immediately spotlights Latin America Expenses: marked LIVE since October with zero submissions."),
        ],
        "08_rollout_explorer_full.png", "09_rollout_zero_activity_gap.png",
        "Chapter 3 shows how leaders spot silent rollout gaps where a module went live on paper but has zero field usage.",
    )

    add_video_slide(
        prs, 8, "Live Walkthrough · Chapter 4", "Role-Based Data Security & Clear Governance Guardrails", "Video 04",
        "04_persona_rls_and_governance_guardrails.mp4", "11_persona_rls_refusal.png", "Enterprise Access Control",
        [
            ("Honest Data Boundaries", "Explains clearly why Logins and Timecards aren't split by Business Unit rather than inventing numbers."),
            ("Role-Based Security (RLS)", "Switching to EMEA Rollout Director automatically scopes both filters and database queries to EMEA."),
            ("Polite Scope Refusals", "Asking for Americas figures while signed in as EMEA Director is cleanly declined."),
            ("Safe Read-Only Design", "Blocks any attempt to run raw database commands or access individual employee records."),
        ],
        "10_unsupported_bu_governance.png", "12_prompt_injection_blocked.png",
        "Chapter 4 highlights role-based access control, cascading scope filters, and safe read-only boundaries.",
    )

    add_video_slide(
        prs, 9, "Live Walkthrough · Chapter 5", "Self-Service Data Catalog, Lineage & Pipeline Health", "Video 05",
        "05_medallion_catalog_and_dataops_lineage.mp4", "15_dataops_watermark_and_parity.png", "Complete Transparency",
        [
            ("Plain-English KPI Dictionary", "Business and BI teams read the exact same metric definitions right inside the app."),
            ("Source-to-Answer Lineage", "Traces every KPI from raw operational tables through Bronze, Silver, and Gold to the chat answer."),
            ("Live Pipeline Health", "Shows the latest refresh timestamp, incremental load watermark, and step-by-step run status."),
            ("Exception Visibility", "Surfaces quarantined test apps and orphan records openly without polluting executive totals."),
        ],
        "14_catalog_medallion_lineage.png", "15_dataops_watermark_and_parity.png",
        "Chapter 5 tours the built-in Data Catalog, lineage map, and DataOps pipeline health dashboard.",
    )

    # SLIDE 10: WHY CLEAN DATA MAKES AI EASY & FREE TO RUN
    s10 = prs.slides.add_slide(blank)
    slide_header(s10, "How It Works", "Why Clean Medallion Data Makes Conversational AI Simple & Low-Cost", "Data + Lightweight AI", 10)
    add_box(s10, 0.55, 1.40, 5.95, 4.35, fill_rgb=WHITE, line_rgb=TEAL, line_pt=1.5)
    add_text(s10, 0.75, 1.56, 5.5, 0.36, "1. Structured Data Does 90% of the Work", size=15, bold=True, color=NAVY)
    add_bullets(s10, 0.72, 2.00, 5.55, 3.6, [
        ("Pre-Built Business Queries", "10 governed read-only query templates cover snapshots, trends, waves, entities, BUs, rollout gaps, and lineage."),
        ("Zero AI Math or Guessing", "SQL Server / DuckDB computes every count; the AI simply routes the question and summarizes verified facts."),
        ("Shared Across Every Tool", "The exact same Gold view (goldview.v_core_adoption) powers CORE Pulse, Power BI, Tableau, and Excel."),
        ("Dual-Database Ready", "Runs identically on enterprise SQL Server 2022 (with native Row-Level Security) or portable local DuckDB."),
    ], size=11.5, space_after=7)

    add_box(s10, 6.80, 1.40, 5.97, 4.35, fill_rgb=WHITE, line_rgb=INDIGO, line_pt=1.5)
    add_text(s10, 7.00, 1.56, 5.5, 0.36, "2. Free, Lightweight Open-Source AI Layer", size=15, bold=True, color=NAVY)
    add_bullets(s10, 6.97, 2.00, 5.55, 3.6, [
        ("Compact Open-Source Models", "Uses free, lightweight open-source models (Apache 2.0) because heavy reasoning isn't needed when data is clean."),
        ("$0 Per-Query API Cost", "No per-user or per-token cloud AI fees—hosted privately inside our own environment."),
        ("100% Data Privacy", "No company schemas, operational records, or questions ever need to leave our infrastructure."),
        ("Instant Rule-Based Fallback", "Also includes a built-in instant mode (< 1 second) that works even with zero AI model running."),
    ], size=11.5, space_after=7)
    add_callout(s10, 5.92, "The Pattern: Invest once in structured Medallion data → add a thin conversational layer on top in days, not months.")

    # SLIDE 11: BUSINESS EXPERIENCE, SPEED & TRUST (NO ML JARGON!)
    s11 = prs.slides.add_slide(blank)
    slide_header(s11, "Business Experience & Trust", "Fast Answers, Built-In Data Accuracy & Repeatable Delivery", "8–10s Response", 11)
    add_box(s11, 0.55, 1.40, 5.85, 4.35, fill_rgb=WHITE, line_rgb=TEAL, line_pt=1.5)
    add_text(s11, 0.75, 1.56, 5.4, 0.36, "What Leaders Can Rely On Every Time", size=15, bold=True, color=NAVY)
    add_bullets(s11, 0.72, 2.00, 5.45, 3.6, [
        ("No Double-Counted Users", "Employees active across multiple waves or portals are always deduplicated accurately."),
        ("Immutable History", "Contracts and expense claims stay locked to creation/submission dates—later edits never shift prior months."),
        ("Workflow-Aware Counts", "Approved and exported timecards stay counted, while unsubmitted drafts and service accounts are excluded."),
        ("Complete Org Coverage", "New Business Units appear automatically even before optional local hierarchy mappings are added."),
        ("Verified Number Check", "Every figure in the written summary is automatically cross-checked against the table before display."),
    ], size=11.3, space_after=6)

    add_box(s11, 6.65, 1.40, 6.12, 4.35, fill_rgb=WHITE, line_rgb=INDIGO, line_pt=1.5)
    add_text(s11, 6.85, 1.56, 5.7, 0.36, "Everyday Speed & Simplicity", size=15, bold=True, color=NAVY)
    add_bullets(s11, 6.82, 2.00, 5.75, 3.6, [
        ("~8–10 Seconds per Question", "Typical response time on lightweight open-source AI—returning narrative, table, and chart together."),
        ("Under 1 Second in Instant Mode", "Deterministic mode answers standard adoption questions virtually instantaneously."),
        ("Zero SQL or Training Needed", "Leaders use sidebar filters, click follow-up prompts, or ask 'that's not right' to adjust scope."),
        ("Ready-to-Share Outputs", "One-click CSV and Excel downloads plus full User Guide built right into the tool."),
        ("Reusable Blueprint", "Just like IRIS for Finance, CORE Pulse proves any clean Medallion dataset can become conversational fast."),
    ], size=11.3, space_after=6)
    add_callout(s11, 5.92, "Proven Across Two Domains: Finance (IRIS) + Operations Rollout (CORE Pulse) on the exact same architecture.")

    # SLIDE 12: PRODUCTION LIFT & MODULAR RELEASE 2–4 ROADMAP
    s12 = prs.slides.add_slide(blank)
    slide_header(s12, "Next Steps & Scale", "Connecting Live CORE Data & Plugging In Future Domains", "Roadmap", 12)
    roadmap = [
        ("Release 1 (Ready Now)", "CORE Rollout & Adoption", "Contracts, Unique Logins, Timecards, Expenses, Rollout Explorer, Lineage & Conversational BI.", TEAL_BG, TEAL),
        ("Release 2 (Next)", "Project Delivery & Backlog", "Project/Service/Phase/Task lifecycle, turnaround cycle times, and delivery backlog.", INDIGO_BG, INDIGO),
        ("Release 3 (Planned)", "Scheduling & Qualifications", "Field inspector dispatch utilization, safety licences, and certification compliance.", SILVER_BG, SILVER),
        ("Release 4 (Planned)", "Lab Throughput & Billing", "Laboratory sample volume, certificate turnaround, and milestone invoicing.", GOLD_BG, GOLD),
    ]
    for idx_r, (r_tag, r_dom, r_desc, bgc, bdc) in enumerate(roadmap):
        rx = 0.55 + idx_r * 3.10
        add_box(s12, rx, 1.40, 2.92, 2.55, fill_rgb=bgc, line_rgb=bdc, line_pt=1.4)
        add_text(s12, rx + 0.14, 1.54, 2.64, 0.28, r_tag, size=10.5, bold=True, color=bdc)
        add_text(s12, rx + 0.14, 1.86, 2.64, 0.36, r_dom, size=13.5, bold=True, color=NAVY)
        add_text(s12, rx + 0.14, 2.30, 2.64, 1.50, r_desc, size=11.0, color=SLATE)

    add_box(s12, 0.55, 4.18, 12.22, 1.55, fill_rgb=WHITE, line_rgb=NAVY, line_pt=1.3)
    add_text(s12, 0.75, 4.30, 11.8, 0.32, "3 Simple Steps to Connect Live Production Data (Zero UI Rewrite)", size=13.5, bold=True, color=NAVY)
    add_bullets(s12, 0.72, 4.65, 11.8, 1.0, [
        ("1. Point Bronze to CORE Replica", "Swap synthetic source tables for read-only replicas of production CORE SQL Server."),
        ("2. Enable Single Sign-On", "Connect Microsoft Entra ID / Active Directory groups to our existing role-based security rules."),
        ("3. Link HR Home-BU Feed", "Add worker home-BU mapping when ready to unlock Business Unit login breakdowns."),
    ], size=11.0, space_after=3)
    add_callout(s12, 5.92, "Plug-In Scale: Every new operational domain adds its own Gold table and KPI catalog—Replicating the assistant takes days.")

    OUT_PPTX.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT_PPTX))
    print(f"Saved PowerPoint deck: {OUT_PPTX} ({OUT_PPTX.stat().st_size // 1024} KB)")


def build_html() -> None:
    html_doc = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CORE Pulse — Executive Architecture &amp; Live Demo Deck</title>
<style>
  :root {
    --navy: #0B1F3A; --teal: #0F766E; --teal-light: #E6F4F1;
    --indigo: #3730A3; --indigo-light: #EEF0FB;
    --slate: #475569; --border: #E2E8F0; --bg: #F8FAFC; --card: #FFFFFF;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100%; height: 100%; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    background: #071324; color: var(--navy);
  }
  .deck-shell { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; }
  .slide-viewport {
    position: relative; width: min(96vw, calc((100vh - 64px) * 16 / 9)); aspect-ratio: 16 / 9;
    background: var(--bg); border-radius: 16px; box-shadow: 0 28px 80px rgba(0,0,0,0.55); overflow: hidden;
  }
  .slide { position: absolute; inset: 0; display: none; flex-direction: column; padding: 34px 46px 26px; background: var(--bg); }
  .slide.active { display: flex; }
  .slide.hero { background: linear-gradient(135deg, #081A33 0%, #0F766E 58%, #3730A3 100%); color: #FFF; }
  .s-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; border-bottom: 2px solid var(--border); padding-bottom: 10px; }
  .kicker { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--teal); margin-bottom: 3px; }
  .s-title { font-size: clamp(1.3rem, 2.0vw, 1.88rem); font-weight: 800; color: var(--navy); line-height: 1.18; }
  .s-badge { background: var(--indigo-light); color: var(--indigo); font-size: 0.75rem; font-weight: 700; padding: 5px 12px; border-radius: 999px; white-space: nowrap; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; flex: 1; min-height: 0; }
  .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 13px; flex: 1; min-height: 0; }
  .grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; flex: 1; min-height: 0; }
  .grid-video { display: grid; grid-template-columns: 1.52fr 1fr; gap: 20px; flex: 1; min-height: 0; align-items: stretch; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 15px 17px; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
  .card.teal { border-top: 4px solid var(--teal); }
  .card.indigo { border-top: 4px solid var(--indigo); }
  .card.red { border-top: 4px solid #DC2626; background: #FFFDFD; }
  .card h3 { font-size: 1.0rem; font-weight: 700; color: var(--navy); }
  .card p, .card li { font-size: 0.84rem; line-height: 1.44; color: var(--slate); }
  .card ul { padding-left: 18px; display: flex; flex-direction: column; gap: 6px; }
  .card li strong { color: var(--navy); }
  code { background: #EEF2FF; color: #3730A3; padding: 1px 6px; border-radius: 5px; font-family: ui-monospace, Menlo, monospace; font-size: 0.88em; font-weight: 600; }
  .callout { background: linear-gradient(90deg, var(--teal-light) 0%, var(--indigo-light) 100%); border-left: 5px solid var(--teal); border-radius: 10px; padding: 10px 15px; font-size: 0.86rem; color: var(--navy); font-weight: 600; margin-top: 12px; }
  .vid-col { display: flex; flex-direction: column; gap: 8px; min-height: 0; }
  .vid-frame { background: #0B1628; border-radius: 12px; overflow: hidden; border: 2px solid #CBD5E1; }
  .vid-bar { background: #0F172A; color: #E2E8F0; font-size: 0.74rem; font-weight: 600; padding: 5px 12px; display: flex; justify-content: space-between; }
  .vid-frame video { width: 100%; aspect-ratio: 16 / 9; object-fit: contain; background: #0F172A; display: block; }
  .thumb-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .thumb-row img { width: 100%; height: 76px; object-fit: cover; object-position: top; border-radius: 8px; border: 1px solid var(--border); }
  .nav-bar { display: flex; align-items: center; gap: 14px; margin-top: 10px; color: #CBD5E1; font-size: 0.84rem; }
  .nav-bar button { background: #1E293B; color: #FFF; border: 1px solid #334155; border-radius: 8px; padding: 6px 14px; cursor: pointer; font-weight: 600; }
  .nav-bar button:hover { background: var(--teal); border-color: var(--teal); }
</style>
</head>
<body>
<div class="deck-shell">
  <div class="slide-viewport">

    <!-- Slide 1 -->
    <section class="slide hero active">
      <div style="display:grid; grid-template-columns: 1.35fr 1fr; gap: 26px; flex:1; align-items:center;">
        <div style="display:flex; flex-direction:column; gap:16px;">
          <span style="background:rgba(255,255,255,0.16); width:fit-content; padding:5px 12px; border-radius:999px; font-size:0.76rem; font-weight:700; letter-spacing:0.08em;">FROM AI-READY DATA ENGINEERING TO CONVERSATIONAL BI</span>
          <h1 style="font-size:clamp(1.9rem, 3.0vw, 2.75rem); font-weight:800; line-height:1.12;">CORE Pulse: Turning Clean Data Into Instant Rollout Intelligence</h1>
          <p style="font-size:0.98rem; line-height:1.5; color:#E2E8F0;">Showing how a clean, structured Medallion data foundation (<code>Bronze</code> &rarr; <code>Silver</code> &rarr; <code>Gold</code> &rarr; <code>Certified View</code>) makes it fast and effortless to launch an intuitive conversational assistant—so leaders can ask plain-English rollout questions and get trusted answers, charts, and Excel exports in seconds.</p>
          <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:4px;">
            <div style="background:rgba(15,23,42,0.55); border:1px solid #5EEAD4; border-radius:10px; padding:12px;">
              <div style="font-size:1.22rem; font-weight:800; color:#5EEAD4;">90% Data Foundation</div>
              <div style="font-size:0.78rem; color:#E2E8F0; margin-top:4px;">Clean Bronze &rarr; Silver &rarr; Gold tables do the heavy lifting</div>
            </div>
            <div style="background:rgba(15,23,42,0.55); border:1px solid #5EEAD4; border-radius:10px; padding:12px;">
              <div style="font-size:1.22rem; font-weight:800; color:#5EEAD4;">8&ndash;10s Answers</div>
              <div style="font-size:0.78rem; color:#E2E8F0; margin-top:4px;">Plain-English questions return insights, tables &amp; charts</div>
            </div>
            <div style="background:rgba(15,23,42,0.55); border:1px solid #5EEAD4; border-radius:10px; padding:12px;">
              <div style="font-size:1.22rem; font-weight:800; color:#5EEAD4;">Free Open-Source AI</div>
              <div style="font-size:0.78rem; color:#E2E8F0; margin-top:4px;">Lightweight local open-source models at $0 API cost</div>
            </div>
          </div>
          <div style="background:rgba(245,158,11,0.18); border:1px solid #FBBF24; border-radius:8px; padding:8px 12px; font-size:0.82rem; color:#FEF3C7;">
            <b>Synthetic data &ndash; prototype for demonstration only.</b> Fictional company, people and figures.
          </div>
        </div>
        <div class="card teal" style="color:var(--navy); gap:10px;">
          <h3 style="color:var(--teal); text-transform:uppercase; font-size:0.82rem; letter-spacing:0.08em;">The Analytics &amp; AI Iceberg</h3>
          <div style="background:var(--indigo-light); border:1px solid var(--indigo); border-radius:8px; padding:10px;">
            <div style="font-size:0.72rem; font-weight:800; color:var(--indigo);">VISIBLE SURFACE (10%) &mdash; EASY CONVERSATIONAL UX</div>
            <div style="font-size:0.84rem; font-weight:700; margin-top:4px;">CORE Pulse Chat &middot; Rollout Explorer &middot; Power BI / Tableau / Excel</div>
          </div>
          <div style="text-align:center; font-size:0.72rem; font-weight:800; color:var(--teal);">&mdash;&mdash; STRUCTURED DATA ENGINEERING (90%) &mdash;&mdash;</div>
          <div style="background:#E6F4F1; border-left:4px solid #0F766E; padding:8px 10px; border-radius:6px; font-size:0.80rem;"><b>Certified Semantic Layer:</b> <code>goldview.v_core_adoption</code> &middot; Governed KPIs &middot; Access Control</div>
          <div style="background:#FEF9C3; border-left:4px solid #B45309; padding:8px 10px; border-radius:6px; font-size:0.80rem;"><b>Gold Layer:</b> <code>37,116</code> clean events &middot; Daily User Activity &middot; <code>1,216</code> certified rollups</div>
          <div style="background:#F1F5F9; border-left:4px solid #334155; padding:8px 10px; border-radius:6px; font-size:0.80rem;"><b>Silver Layer:</b> Standardized Org &amp; Wave Hierarchy &middot; Service Accounts Excluded</div>
          <div style="background:#FEF3C7; border-left:4px solid #92400E; padding:8px 10px; border-radius:6px; font-size:0.80rem;"><b>Bronze &amp; DataOps:</b> 16 CORE Operational Tables &middot; Incremental Load Watermarks</div>
        </div>
      </div>
    </section>

    <!-- Slide 2 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Executive Context</div><div class="s-title">Why Rollout Reporting Breaks Without Clean Data Engineering</div></div><span class="s-badge">Problem &rarr; Solution</span></div>
      <div class="grid-2">
        <div class="card red"><h3>1. Double-Counting Active Users</h3><p>Adding Wave 1 + Wave 2 logins inflates headcount whenever specialists work across multiple regional portals. Our Gold layer deduplicates unique employees automatically at every level.</p></div>
        <div class="card red"><h3>2. Shifting Historical Dates</h3><p>Grouping contracts by start date or expenses by last-modified date rewrites past months when records are edited. CORE Pulse locks strictly to original creation and submission dates.</p></div>
        <div class="card indigo"><h3>3. &ldquo;Live&rdquo; on Paper vs. Real Usage</h3><p>A tracker marking Expenses <code>LIVE</code> in a country does not prove field teams submit claims. CORE Pulse compares go-live status directly against actual recorded Gold transactions.</p></div>
        <div class="card teal"><h3>4. Mid-Month False Alarms</h3><p>Comparing 17 days of November against a full 31-day October manufactures fake adoption drops. CORE Pulse benchmarks month-to-date fairly against the same 17 days of October.</p></div>
      </div>
      <div class="callout">Core Takeaway: Solve business rules once in the Medallion data pipeline &mdash; then every dashboard and AI chat stays 100% aligned.</div>
    </section>

    <!-- Slide 3 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Data Engineering Foundation</div><div class="s-title">How the Data Was Structured: 5-Stage Medallion Pipeline</div></div><span class="s-badge">Medallion ETL</span></div>
      <div class="grid-5">
        <div class="card"><h3>1. Source</h3><ul><li>16 CORE tables</li><li>Business Units &amp; Projects</li><li>Application Login Logs</li><li>Timecards &amp; Expenses</li></ul></div>
        <div class="card teal"><h3>2. Bronze</h3><ul><li>16 <code>bronze.core_*</code> tables</li><li>Explicit column mapping</li><li>Extract timestamps</li><li>Incremental watermark</li></ul></div>
        <div class="card indigo"><h3>3. Silver</h3><ul><li>10 conformed tables</li><li>Unified org &amp; wave hierarchy</li><li>Service accounts removed</li><li>Orphan rows quarantined</li></ul></div>
        <div class="card teal"><h3>4. Gold</h3><ul><li><code>37,116</code> clean events</li><li>Daily unique user activity</li><li>Daily KPI snapshots</li><li>Pre-validated parity</li></ul></div>
        <div class="card indigo"><h3>5. Certified View</h3><ul><li><code>goldview.v_core_adoption</code></li><li>Current &amp; Monthly views</li><li>Wave, Entity &amp; BU grains</li><li>Role-based security</li></ul></div>
      </div>
      <div class="callout">Repeatable Engineering: Automated watermarks and data-quality checks ensure every refresh is clean, auditable, and free of duplicates.</div>
    </section>

    <!-- Slide 4 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Governed Business Rules</div><div class="s-title">Four Certified Adoption KPIs &amp; Clear Reporting Boundaries</div></div><span class="s-badge">Certified KPIs</span></div>
      <div class="grid-2">
        <div class="card teal"><h3>Contracts Created &middot; 2,303</h3><p>Distinct projects created, anchored strictly to creation date. Available Overall, by Rollout Wave, by Adoption Entity, and by Business Unit.</p></div>
        <div class="card indigo"><h3>Employees Logging In &middot; 419</h3><p>Unique non-service employees signing in. <b>Automatically deduplicated at every grain.</b> Blocked at Business Unit until HR home-BU data is connected.</p></div>
        <div class="card teal"><h3>Timesheets Submitted &middot; 5,373</h3><p>Formal submitted timecards (including approved/exported; excluding drafts). Blocked at Business Unit because a single timecard can span multiple BUs.</p></div>
        <div class="card indigo"><h3>Expense Reports &middot; 1,859</h3><p>Submitted expense claims anchored to initial submission date. Available Overall, by Rollout Wave, by Adoption Entity, and by Business Unit.</p></div>
      </div>
      <div class="callout">Built-In Honesty: Where a Business Unit breakdown isn't supported by source data yet, CORE Pulse explains why instead of guessing.</div>
    </section>

    <!-- Slide 5 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Live Walkthrough &middot; Chapter 1</div><div class="s-title">Sign-In, Personal Workspace &amp; Clear Executive KPI Summary</div></div><span class="s-badge">1080p Demo 01</span></div>
      <div class="grid-video">
        <div class="vid-col">
          <div class="vid-frame"><div class="vid-bar"><span>&#9654; 01_signin_and_executive_kpi_strip.mp4</span><span>1080p H.264</span></div><video controls preload="metadata" poster="screenshots/02_executive_kpi_strip.png" src="videos/01_signin_and_executive_kpi_strip.mp4"></video></div>
          <div class="thumb-row"><img src="screenshots/01_signin_gate.png" alt="Sign in" /><img src="screenshots/03_overall_adoption_snapshot.png" alt="Overall snapshot" /></div>
        </div>
        <div class="card teal"><h3>Simple, Intuitive Start</h3><ul>
          <li><strong>Personal Conversation History:</strong> Sign-in keeps each leader's last 10 threads, pinned reviews, and filters separate.</li>
          <li><strong>Crystal-Clear Time Labels:</strong> KPI cards separate All-Time Cumulative, Last Closed Month (Oct), and Current MTD (Nov 1&ndash;17).</li>
          <li><strong>Fair Mid-Month Context:</strong> Shows Nov 1&ndash;17 right alongside Oct 1&ndash;17 equivalent days.</li>
          <li><strong>Guided Starter Prompts:</strong> One-click buttons let any leader explore adoption with zero training.</li>
        </ul></div>
      </div>
    </section>

    <!-- Slide 6 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Live Walkthrough &middot; Chapter 2</div><div class="s-title">Natural Follow-Up Questions &amp; Automatic User Deduplication</div></div><span class="s-badge">1080p Demo 02</span></div>
      <div class="grid-video">
        <div class="vid-col">
          <div class="vid-frame"><div class="vid-bar"><span>&#9654; 02_multiturn_adoption_and_nonadditivity.mp4</span><span>1080p H.264</span></div><video controls preload="metadata" poster="screenshots/06_wave_nonadditivity_and_sql.png" src="videos/02_multiturn_adoption_and_nonadditivity.mp4"></video></div>
          <div class="thumb-row"><img src="screenshots/05_six_month_trend_partial_flag.png" alt="6M trend" /><img src="screenshots/06_wave_nonadditivity_and_sql.png" alt="Wave non-additivity" /></div>
        </div>
        <div class="card indigo"><h3>Conversational Flow</h3><ul>
          <li><strong>Remembers Context:</strong> Ask <code>How many employees logged in this month?</code> then simply say <code>Show the six-month trend.</code></li>
          <li><strong>Partial-Month Visual Cue:</strong> In-progress November plots as an amber dotted diamond so no one misreads it as a drop.</li>
          <li><strong>Smart Wave Breakdown:</strong> Shows Wave 1&ndash;4 active users alongside the true deduplicated global total (<code>419</code>).</li>
          <li><strong>One-Click Proof &amp; Export:</strong> Download CSV/Excel or expand <code>How I got this</code> for lineage and SQL.</li>
        </ul></div>
      </div>
    </section>

    <!-- Slide 7 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Live Walkthrough &middot; Chapter 3</div><div class="s-title">Tracking Rollout Go-Live vs. Actual Field Usage</div></div><span class="s-badge">1080p Demo 03</span></div>
      <div class="grid-video">
        <div class="vid-col">
          <div class="vid-frame"><div class="vid-bar"><span>&#9654; 03_rollout_vs_observed_activity_gap.mp4</span><span>1080p H.264</span></div><video controls preload="metadata" poster="screenshots/09_rollout_zero_activity_gap.png" src="videos/03_rollout_vs_observed_activity_gap.mp4"></video></div>
          <div class="thumb-row"><img src="screenshots/08_rollout_explorer_full.png" alt="Rollout Explorer" /><img src="screenshots/09_rollout_zero_activity_gap.png" alt="Zero activity gap" /></div>
        </div>
        <div class="card teal"><h3>Actionable Rollout Tracking</h3><ul>
          <li><strong>Business Language Mapping:</strong> Asking about the <code>Western region</code> maps automatically to Americas (<code>AMER</code>).</li>
          <li><strong>Go-Live vs. Real Activity:</strong> Compares rollout tracker status directly against recorded Gold transactions.</li>
          <li><strong>Clear Module Scope:</strong> Distinguishes instrumented Release 1 modules from status-only future modules.</li>
          <li><strong>Instant Gap Detection:</strong> Spotlights Latin America Expenses &mdash; marked <code>LIVE</code> since October with <b>zero submissions</b>.</li>
        </ul></div>
      </div>
    </section>

    <!-- Slide 8 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Live Walkthrough &middot; Chapter 4</div><div class="s-title">Role-Based Data Security &amp; Clear Governance Guardrails</div></div><span class="s-badge">1080p Demo 04</span></div>
      <div class="grid-video">
        <div class="vid-col">
          <div class="vid-frame"><div class="vid-bar"><span>&#9654; 04_persona_rls_and_governance_guardrails.mp4</span><span>1080p H.264</span></div><video controls preload="metadata" poster="screenshots/11_persona_rls_refusal.png" src="videos/04_persona_rls_and_governance_guardrails.mp4"></video></div>
          <div class="thumb-row"><img src="screenshots/10_unsupported_bu_governance.png" alt="Unsupported BU" /><img src="screenshots/12_prompt_injection_blocked.png" alt="Injection blocked" /></div>
        </div>
        <div class="card indigo"><h3>Enterprise Access Control</h3><ul>
          <li><strong>Honest Data Boundaries:</strong> Explains clearly why Logins and Timecards aren't split by Business Unit.</li>
          <li><strong>Role-Based Security (RLS):</strong> Switching to <code>EMEA Rollout Director</code> scopes filters and database queries strictly to EMEA.</li>
          <li><strong>Polite Scope Refusals:</strong> Out-of-scope Americas queries under the EMEA role are cleanly declined.</li>
          <li><strong>Safe Read-Only Design:</strong> Blocks any attempt to run raw database commands or view individual employee rows.</li>
        </ul></div>
      </div>
    </section>

    <!-- Slide 9 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Live Walkthrough &middot; Chapter 5</div><div class="s-title">Self-Service Data Catalog, Lineage &amp; Pipeline Health</div></div><span class="s-badge">1080p Demo 05</span></div>
      <div class="grid-video">
        <div class="vid-col">
          <div class="vid-frame"><div class="vid-bar"><span>&#9654; 05_medallion_catalog_and_dataops_lineage.mp4</span><span>1080p H.264</span></div><video controls preload="metadata" poster="screenshots/15_dataops_watermark_and_parity.png" src="videos/05_medallion_catalog_and_dataops_lineage.mp4"></video></div>
          <div class="thumb-row"><img src="screenshots/14_catalog_medallion_lineage.png" alt="Lineage" /><img src="screenshots/15_dataops_watermark_and_parity.png" alt="DataOps" /></div>
        </div>
        <div class="card teal"><h3>Complete Transparency</h3><ul>
          <li><strong>Plain-English KPI Dictionary:</strong> Business and BI teams read the exact same metric rules inside the app.</li>
          <li><strong>Source-to-Answer Lineage:</strong> Traces every KPI from operational tables through Bronze, Silver, and Gold to the answer.</li>
          <li><strong>Live Pipeline Health:</strong> Displays refresh timestamps, incremental load watermarks, and quality checks.</li>
          <li><strong>Exception Visibility:</strong> Surfaces quarantined test apps and orphan records openly without skewing KPIs.</li>
        </ul></div>
      </div>
    </section>

    <!-- Slide 10 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">How It Works</div><div class="s-title">Why Clean Medallion Data Makes Conversational AI Simple &amp; Low-Cost</div></div><span class="s-badge">Data + Lightweight AI</span></div>
      <div class="grid-2">
        <div class="card teal"><h3>1. Structured Data Does 90% of the Work</h3><ul>
          <li><strong>Pre-Built Business Queries:</strong> Governed read-only query templates cover snapshots, trends, waves, entities, BUs, rollout gaps, and lineage.</li>
          <li><strong>Zero AI Math or Guessing:</strong> The database computes every count; AI simply matches the user's question and summarizes verified facts.</li>
          <li><strong>Shared Across Every Tool:</strong> The exact same <code>goldview.v_core_adoption</code> layer powers CORE Pulse, Power BI, Tableau, and Excel.</li>
          <li><strong>Dual-Database Ready:</strong> Runs identically on enterprise SQL Server 2022 (with native Row-Level Security) or portable local DuckDB.</li>
        </ul></div>
        <div class="card indigo"><h3>2. Free, Lightweight Open-Source AI Layer</h3><ul>
          <li><strong>Compact Open-Source Models:</strong> Uses free, small open-source models (Apache 2.0) because heavy reasoning isn't needed when data is clean.</li>
          <li><strong>$0 Per-Query API Cost:</strong> No per-user or per-token cloud AI bills &mdash; hosted privately inside our own environment.</li>
          <li><strong>100% Data Privacy:</strong> No company schemas, operational records, or business questions ever leave our infrastructure.</li>
          <li><strong>Instant Rule-Based Mode:</strong> Also includes a built-in instant mode (&lt; 1 second) that works even without an AI model.</li>
        </ul></div>
      </div>
      <div class="callout">The Pattern: Invest once in structured Medallion data &rarr; add a thin conversational layer on top in days, not months.</div>
    </section>

    <!-- Slide 11 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Business Experience &amp; Trust</div><div class="s-title">Fast Answers, Built-In Data Accuracy &amp; Repeatable Delivery</div></div><span class="s-badge">8&ndash;10s Response</span></div>
      <div class="grid-2">
        <div class="card teal"><h3>What Leaders Can Rely On Every Time</h3><ul>
          <li><strong>No Double-Counted Users:</strong> Employees active across multiple waves or portals are always deduplicated accurately.</li>
          <li><strong>Immutable History:</strong> Contracts and expense claims stay locked to creation/submission dates &mdash; edits never shift prior months.</li>
          <li><strong>Workflow-Aware Counts:</strong> Approved and exported timecards stay counted, while drafts and service accounts are excluded.</li>
          <li><strong>Complete Org Coverage:</strong> New Business Units appear automatically even before optional local mappings are added.</li>
          <li><strong>Verified Number Check:</strong> Every figure in the written summary is cross-checked against the table before display.</li>
        </ul></div>
        <div class="card indigo"><h3>Everyday Speed &amp; Simplicity</h3><ul>
          <li><strong>~8&ndash;10 Seconds per Question:</strong> Typical response time on lightweight open-source AI &mdash; returning narrative, table, and chart together.</li>
          <li><strong>Under 1 Second in Instant Mode:</strong> Built-in rule-based mode answers standard adoption questions instantaneously.</li>
          <li><strong>Zero SQL or Training Needed:</strong> Leaders use sidebar filters, click follow-up prompts, or say <code>that's not right</code> to adjust scope.</li>
          <li><strong>Ready-to-Share Outputs:</strong> One-click CSV and Excel downloads plus a visual User Guide built right into the app.</li>
          <li><strong>Reusable Blueprint:</strong> Alongside IRIS for Finance, CORE Pulse proves any clean Medallion dataset can become conversational fast.</li>
        </ul></div>
      </div>
      <div class="callout">Proven Across Two Domains: Finance (IRIS) + Operations Rollout (CORE Pulse) running on the exact same architecture.</div>
    </section>

    <!-- Slide 12 -->
    <section class="slide">
      <div class="s-top"><div><div class="kicker">Next Steps &amp; Scale</div><div class="s-title">Connecting Live CORE Data &amp; Plugging In Future Domains</div></div><span class="s-badge">Roadmap</span></div>
      <div class="grid-4">
        <div class="card teal"><h3>Release 1 (Ready Now)</h3><p><b>CORE Rollout &amp; Adoption:</b> Contracts, Unique Logins, Timecards, Expenses, Rollout Explorer, Lineage &amp; Conversational BI.</p></div>
        <div class="card indigo"><h3>Release 2 (Next)</h3><p><b>Project Delivery &amp; Backlog:</b> Project/Service/Phase/Task lifecycle, turnaround cycle times, and delivery backlog.</p></div>
        <div class="card teal"><h3>Release 3 (Planned)</h3><p><b>Scheduling &amp; Qualifications:</b> Field inspector dispatch utilization, safety licences, and certification compliance.</p></div>
        <div class="card indigo"><h3>Release 4 (Planned)</h3><p><b>Lab Throughput &amp; Billing:</b> Laboratory sample volume, certificate turnaround, and milestone invoicing.</p></div>
      </div>
      <div class="card" style="margin-top:12px;">
        <h3>3 Simple Steps to Connect Live Production Data (Zero UI Rewrite)</h3>
        <p><b>1. Point Bronze to CORE Replica:</b> Swap synthetic source tables for read-only replicas of production CORE SQL Server &nbsp;|&nbsp; <b>2. Enable Single Sign-On:</b> Connect Microsoft Entra ID groups to existing role-based security rules &nbsp;|&nbsp; <b>3. Link HR Home-BU Feed:</b> Unlock Business Unit login breakdowns when HR master data is connected.</p>
      </div>
    </section>

  </div>
  <div class="nav-bar">
    <button onclick="go(-1)">&larr; Prev</button>
    <span id="counter">Slide 1 / 12</span>
    <button onclick="go(1)">Next &rarr;</button>
  </div>
</div>
<script>
  const slides = Array.from(document.querySelectorAll('.slide'));
  let idx = 0;
  function show(n) {
    slides.forEach(s => { s.classList.remove('active'); s.querySelectorAll('video').forEach(v => v.pause()); });
    idx = (n + slides.length) % slides.length;
    slides[idx].classList.add('active');
    document.getElementById('counter').textContent = 'Slide ' + (idx + 1) + ' / ' + slides.length;
  }
  function go(d) { show(idx + d); }
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') go(1);
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') go(-1);
  });
</script>
</body>
</html>
"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html_doc, encoding="utf-8")
    print(f"Saved HTML5 deck: {OUT_HTML} ({OUT_HTML.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build_pptx()
    build_html()
