"""Pytest configuration and shared fixtures for CORE Pulse."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DB_BACKEND", "duckdb")
os.environ.setdefault("APP_ACCESS_CODE", "my-access-code")
os.environ.setdefault("APP_HISTORY_BACKEND", "sqlite")
os.environ.setdefault("AS_OF_DATE", "2026-11-17")


@pytest.fixture(scope="session", autouse=True)
def ensure_duckdb_built():
    from app.db import duckdb_path
    from scripts.reset_demo_data import reset_all

    if not duckdb_path().exists():
        reset_all()
    yield
