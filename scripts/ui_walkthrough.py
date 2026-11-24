"""Headless Playwright E2E UI walkthrough & User Guide screenshot generator for CORE Pulse.

Usage:
    APP_ACCESS_CODE=my-access-code python scripts/ui_walkthrough.py http://localhost:8502 results/ui_walkthrough docs/img [rules,llm]

Walks through:
  1. Sign-in screen (`01_signin.png`)
  2. Executive KPI Overview Strip + Home (`02_home_kpis.png`)
  3. Multi-turn adoption conversation:
     - Turn 1: "How many employees logged into CORE this month?"
     - Turn 2: "Show the six-month trend." (`04_monthly_trend_partial.png`)
     - Turn 3: "Which rollout wave is most active?" (`03_chat_wave_nonadditive.png`)
  4. Unsupported BU attribution + Persona RLS refusal (`05_rls_and_unsupported_bu.png`)
  5. Rollout Explorer (`SIMULATED EXTENSION` + `ROL-LATAM-EXP` zero-activity gap, `06_rollout_explorer.png`)
  6. Data Catalog, Medallion Lineage & DataOps Watermarks (`07_catalog_lineage.png`)
  7. Optional live LLM walkthrough (`ollama/qwen2.5-coder:14b`) verifying MCP tool call + guardrail drawer.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8502"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "results/ui_walkthrough")
IMG_DIR = Path(sys.argv[3] if len(sys.argv) > 3 else "docs/img")
PARTS = (sys.argv[4] if len(sys.argv) > 4 else "rules,llm").split(",")
CODE = os.environ.get("APP_ACCESS_CODE", "my-access-code")
USER = "Alex Morgan"
MSG = "[data-testid='stChatMessage']"

RESULTS: list[dict] = []


def log(rec: dict) -> None:
    RESULTS.append(rec)
    print(json.dumps(rec), flush=True)


def chat_ready(page) -> None:
    page.locator("[data-testid='stChatInputTextArea']").wait_for(timeout=120_000)
    time.sleep(1.5)


def open_settings(page) -> None:
    sb = page.locator("[data-testid='stSidebar']")
    if not sb.get_by_text("Persona (RLS)").is_visible():
        sb.get_by_text("Settings", exact=True).scroll_into_view_if_needed()
        sb.get_by_text("Settings", exact=True).click()
        time.sleep(1.0)


def set_model(page, target_label: str) -> None:
    open_settings(page)
    sb = page.locator("[data-testid='stSidebar']")
    box = sb.locator("[data-testid='stSelectbox']").filter(has_text="Model (LiteLLM)")
    inp = box.locator("input[role='combobox']")
    inp.scroll_into_view_if_needed()
    if target_label not in inp.input_value():
        inp.click()
        time.sleep(0.6)
        page.get_by_role("option", name=target_label, exact=True).click()
        time.sleep(2.0)


def set_persona(page, persona_name: str, expected_scope_substr: str) -> None:
    open_settings(page)
    sb = page.locator("[data-testid='stSidebar']")
    box = sb.locator("[data-testid='stSelectbox']").filter(has_text="Persona (RLS)")
    inp = box.locator("input[role='combobox']")
    inp.scroll_into_view_if_needed()
    inp.click()
    time.sleep(0.6)
    page.get_by_role("option", name=persona_name, exact=True).click()
    time.sleep(2.0)
    open_settings(page)
    sb.get_by_text(expected_scope_substr).wait_for(timeout=45_000)
    chat_ready(page)


def wait_answer(page, before: int, timeout_s: int = 120) -> float:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        msgs = page.locator(MSG)
        if msgs.count() >= before + 2:
            txt = msgs.last.inner_text()
            done = (
                "Suggested follow-ups" in txt
                or "How I got this" in txt
                or "Sorry, you don't have access" in txt
                or "Choose what you would like to change" in txt
                or "blocked" in txt
            )
            if done and "Querying governed CORE Medallion" not in txt:
                time.sleep(2.2)
                return time.time() - t0
        time.sleep(0.5)
    raise TimeoutError("Timed out waiting for assistant answer")


def ask_q(page, question: str, timeout_s: int = 120) -> tuple[float, str]:
    before = page.locator(MSG).count()
    box = page.locator("[data-testid='stChatInputTextArea']")
    box.fill(question)
    box.press("Enter")
    dt = wait_answer(page, before, timeout_s=timeout_s)
    last_txt = page.locator(MSG).last.inner_text()
    return dt, last_txt


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 920}, device_scale_factor=2.5)
        page = ctx.new_page()

        # 1. Sign-in page + screenshot 01
        page.goto(f"{BASE}/?model=rules" if "rules" in PARTS else BASE, wait_until="networkidle")
        page.wait_for_selector("text=Sign in to CORE Pulse", timeout=90_000)
        time.sleep(1.0)
        page.screenshot(path=str(IMG_DIR / "01_signin.png"))
        page.get_by_label("Your name").fill(USER)
        page.get_by_label("Access code").fill(CODE)
        page.get_by_role("button", name="Sign in").click()
        chat_ready(page)
        log({"step": "01_signin", "ok": "CORE Pulse" in page.inner_text("body")})

        if "rules" in PARTS:
            time.sleep(1.0)
            page.screenshot(path=str(IMG_DIR / "02_home_kpis.png"))
            body_home = page.inner_text("body")
            log({
                "step": "02_home_kpis",
                "ok": (
                    all(s in body_home for s in ("2,303", "5,373", "1,859", "Synthetic data", "Developed and maintained by Rohan Luniya"))
                    and all(bad not in body_home for bad in ("Operational Rollout", "Measure adoption"))
                ),
            })

            # Turn 1: MTD Logins
            dt1, t1 = ask_q(page, "How many employees logged into CORE this month?")
            log({"step": "03_turn1_mtd_logins", "seconds": round(dt1, 2), "ok": "Nov 2026 MTD" in t1})

            # Turn 2: 6-Month Trend
            dt2, t2 = ask_q(page, "Show the six-month trend.")
            page.locator(MSG).last.scroll_into_view_if_needed()
            time.sleep(1.0)
            page.screenshot(path=str(IMG_DIR / "04_monthly_trend_partial.png"))
            log({"step": "04_turn2_6m_trend", "seconds": round(dt2, 2), "ok": "Employees Logging In" in t2 and "2026-10" in t2})

            # Turn 3: Wave Breakdown & Non-Additivity + How I got this drawer
            dt3, t3 = ask_q(page, "Which rollout wave is most active?")
            page.locator(MSG).last.locator("summary", has_text="How I got this").click()
            time.sleep(1.2)
            page.locator(MSG).last.scroll_into_view_if_needed()
            page.screenshot(path=str(IMG_DIR / "03_chat_wave_nonadditive.png"))
            log({"step": "05_turn3_wave_nonadditive", "seconds": round(dt3, 2), "ok": "Wave 1" in t3 and "Non-additive" in t3})

            # Unsupported BU + Persona RLS
            page.get_by_role("button", name=re.compile("New conversation")).click()
            chat_ready(page)
            dt4, t4 = ask_q(page, "Can you show Employees Logging In by Business Unit?")
            set_persona(page, "EMEA Rollout Director", "EMEA")
            dt5, t5 = ask_q(page, "What is current CORE adoption in AMER?")
            page.screenshot(path=str(IMG_DIR / "05_rls_and_unsupported_bu.png"))
            log({
                "step": "06_unsupported_bu_and_rls",
                "seconds": round(dt4 + dt5, 2),
                "ok": ("Business Unit" in t4) and ("don't have access" in t5),
            })

            # Reset persona back to Global Lead
            set_persona(page, "Global CORE Program Lead", "All Regions")

            # Navigate to Rollout Explorer
            page.get_by_role("link", name=re.compile("Rollout Explorer")).click()
            page.wait_for_selector("text=Filter by Rollout Status", timeout=60_000)
            time.sleep(2.0)
            page.screenshot(path=str(IMG_DIR / "06_rollout_explorer.png"))
            ro_txt = page.inner_text("body")
            log({"step": "07_rollout_explorer", "ok": "ROL-LATAM-EXP" in ro_txt and "3 Onboarding" in ro_txt})

            # Navigate to Data Catalog
            page.get_by_role("link", name=re.compile("Data Catalog")).click()
            page.wait_for_selector("text=Data Catalog, Medallion Architecture & DataOps", timeout=60_000)
            page.get_by_role("tab", name=re.compile("Source-to-Answer Lineage")).click()
            time.sleep(1.5)
            page.screenshot(path=str(IMG_DIR / "07_catalog_lineage.png"))
            cat_txt = page.inner_text("body")
            log({"step": "08_data_catalog_lineage", "ok": "goldview.v_core_adoption" in cat_txt})

            # Navigate to User Guide and verify guide content
            page.get_by_role("link", name=re.compile("User Guide")).click()
            page.wait_for_selector("text=CORE Pulse — User Guide", timeout=60_000)
            time.sleep(1.5)
            log({"step": "09_user_guide", "ok": "Persona Row-Level Security" in page.inner_text("body")})

        if "llm" in PARTS:
            if not page.locator("[data-testid='stChatInputTextArea']").is_visible():
                page.get_by_role("link", name=re.compile("Chat")).click()
                chat_ready(page)
            if "rules" in PARTS:
                set_model(page, "ollama/qwen2.5-coder:14b")
                page.get_by_role("button", name=re.compile("New conversation")).click()
                chat_ready(page)
            for step_nm, q_txt, must_sub in [
                ("llm_1_overall", "What is current CORE adoption overall?", "2,303"),
                ("llm_2_expenses_gap", "Which entities are live on Expenses, and which live entities have zero expense submissions?", "rol-latam-exp"),
                ("llm_3_dataops", "How fresh is the dataset, and did any mapping or orphan checks fail in the latest run?", "pass"),
            ]:
                dt_l, txt_l = ask_q(page, q_txt, timeout_s=180)
                page.screenshot(path=str(OUT / f"{step_nm}.png"))
                log({"step": step_nm, "mode": "llm", "seconds": round(dt_l, 2), "ok": must_sub in txt_l.lower()})

        browser.close()

    (OUT / "walkthrough.jsonl").write_text("\n".join(json.dumps(r) for r in RESULTS) + "\n", encoding="utf-8")
    passed = sum(1 for r in RESULTS if r.get("ok"))
    print(f"WALKTHROUGH_DONE {passed}/{len(RESULTS)} steps ok", flush=True)
    if passed != len(RESULTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
