"""Configuration helpers: config/settings.yaml + .env environment overrides."""
from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


@lru_cache(maxsize=1)
def settings() -> dict:
    with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def data_as_of_date() -> date:
    """Deterministic dataset ceiling date from config/settings.yaml (default 2026-11-17)."""
    return date.fromisoformat(str(settings()["as_of_date"]))


def as_of_date() -> date:
    """Effective as-of date: AS_OF_DATE or DEMO_AS_OF_DATE env override, bounded by data_as_of_date()."""
    raw = env("AS_OF_DATE") or env("DEMO_AS_OF_DATE")
    chosen = date.fromisoformat(raw) if raw else data_as_of_date()
    return min(chosen, data_as_of_date())


def demo_seed() -> int:
    raw = env("DEMO_SEED")
    return int(raw) if raw else int(settings().get("seed", 42))


def backend() -> str:
    return (env("DB_BACKEND", "duckdb") or "duckdb").lower()
