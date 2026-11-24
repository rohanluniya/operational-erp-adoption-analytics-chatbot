"""Reset and rebuild the deterministic CORE Pulse demo database (DuckDB or SQL Server).

Usage:
    uv run python scripts/reset_demo_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import backend, data_as_of_date, demo_seed  # noqa: E402
from app.db import clear_engine_cache, duckdb_path, get_engine  # noqa: E402
from pipelines.medallion import create_medallion_ddl, run_medallion_pipeline, seed_source_and_reference  # noqa: E402


def reset_all() -> dict:
    if backend() == "duckdb":
        p = duckdb_path()
        if p.exists():
            p.unlink()
    clear_engine_cache()
    eng = get_engine(admin=True)
    create_medallion_ddl(eng, reset_all=True)
    src_counts = seed_source_and_reference(eng, seed=demo_seed(), as_of=data_as_of_date())
    res = run_medallion_pipeline(eng, as_of=data_as_of_date())
    res["backend"] = backend()
    res["source_tables_seeded"] = len(src_counts)
    clear_engine_cache()
    return res


if __name__ == "__main__":
    summary = reset_all()
    print("RESET_DEMO_COMPLETE", json.dumps(summary), flush=True)
