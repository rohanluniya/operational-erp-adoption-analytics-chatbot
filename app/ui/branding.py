"""CORE Pulse branding constants — single source of truth across UI, sidebar, and docs."""
from __future__ import annotations

from pathlib import Path

from app.config import settings

_CFG = settings()

APP_NAME = _CFG.get("app_name", "CORE Pulse")
APP_FULL_NAME = _CFG.get("app_full_name", "")
TAGLINE = _CFG.get("tagline", "")
OPERATIONAL_PLATFORM = _CFG.get("operational_platform", "CORE")
AUTHOR = _CFG.get("author", "Rohan Luniya")
AUTHOR_LINE = _CFG.get("author_line", f"Developed and maintained by {AUTHOR}")
VERSION = _CFG.get("version", "1.0.0")

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS / "core_pulse_logo.svg"

TEAL = "#0F766E"
INDIGO = "#3730A3"
INK = "#0B1F3A"


def page_title(page: str | None = None) -> str:
    if page:
        return f"{APP_NAME} · {page}"
    return f"{APP_NAME} · {APP_FULL_NAME}" if APP_FULL_NAME else APP_NAME


def footer_line() -> str:
    return f"{APP_NAME} v{VERSION} · {AUTHOR_LINE}"
