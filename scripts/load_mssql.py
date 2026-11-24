"""Provision SQL Server 2022 [core_pulse] database, run Medallion ETL, and enforce SESSION_CONTEXT RLS.

Usage:
    DB_BACKEND=mssql python scripts/load_mssql.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import env  # noqa: E402
from app.db import clear_engine_cache, mssql_url  # noqa: E402
from pipelines.medallion import run_medallion_pipeline  # noqa: E402


def _exec_batches(conn, sql_text: str) -> None:
    batches = [b.strip() for b in re.split(r"^\s*GO\s*$", sql_text, flags=re.MULTILINE | re.IGNORECASE) if b.strip()]
    for b in batches:
        conn.execute(text(b))


def provision_and_load() -> dict:
    os.environ["DB_BACKEND"] = "mssql"
    clear_engine_cache()

    db_name = env("PULSE_DB_NAME") or ("core_pulse" if env("DB_NAME") == "iris" else env("DB_NAME", "core_pulse")) or "core_pulse"
    app_user = env("PULSE_MSSQL_APP_USER") or ("pulse_reader" if env("MSSQL_APP_USER") == "iris_reader" else env("MSSQL_APP_USER", "pulse_reader")) or "pulse_reader"
    app_pw = env("MSSQL_APP_PASSWORD")
    if not app_pw or not env("MSSQL_SA_PASSWORD"):
        raise RuntimeError("MSSQL_SA_PASSWORD and MSSQL_APP_PASSWORD must be set in environment or .env")

    # 1. Connect to master with autocommit to create [core_pulse] database and [pulse_reader] login
    master_eng = create_engine(mssql_url(admin=True, database="master"), isolation_level="AUTOCOMMIT")
    with master_eng.connect() as conn:
        conn.execute(text(f"IF DB_ID(N'{db_name}') IS NULL CREATE DATABASE [{db_name}];"))
        safe_pw = app_pw.replace("'", "''")
        conn.execute(text(f"""
            IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'{app_user}')
                CREATE LOGIN [{app_user}] WITH PASSWORD = N'{safe_pw}', CHECK_POLICY = OFF;
            ELSE
                ALTER LOGIN [{app_user}] WITH PASSWORD = N'{safe_pw}';
        """))

    # If security policy / schemabound functions exist from an earlier run, drop them before full reset DDL
    admin_eng = create_engine(mssql_url(admin=True, database=db_name))
    with admin_eng.begin() as conn:
        conn.execute(text("""
            IF EXISTS (SELECT 1 FROM sys.security_policies WHERE name = 'core_pulse_rls_policy')
                DROP SECURITY POLICY rls.core_pulse_rls_policy;
            IF OBJECT_ID('rls.fn_store_access', 'IF') IS NOT NULL
                DROP FUNCTION rls.fn_store_access;
            IF OBJECT_ID('rls.fn_region_access', 'IF') IS NOT NULL
                DROP FUNCTION rls.fn_region_access;
        """))

    # 2. Run full Medallion ETL on SQL Server [core_pulse]
    from app.config import data_as_of_date
    from app.db import get_engine
    from scripts.reset_demo_data import reset_all
    etl_summary = reset_all()
    # Run incremental idempotency check on SQL Server too!
    idem_summary = run_medallion_pipeline(get_engine(admin=True), as_of=data_as_of_date())

    # 3. Create database user [pulse_reader], grant least-privilege permissions, and apply RLS
    rls_sql = (ROOT / "sql" / "rls_mssql.sql").read_text(encoding="utf-8")
    with admin_eng.begin() as conn:
        conn.execute(text(f"""
            IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{app_user}')
                CREATE USER [{app_user}] FOR LOGIN [{app_user}];
        """))
        for ro_schema in ("goldview", "gold", "silver", "bronze", "source_sim", "reference", "dataops", "rls"):
            conn.execute(text(f"GRANT SELECT ON SCHEMA::[{ro_schema}] TO [{app_user}];"))
        conn.execute(text("IF SCHEMA_ID(N'app') IS NULL EXEC('CREATE SCHEMA [app]');"))
        _exec_batches(conn, rls_sql)
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::[app] TO [{app_user}];"))

    clear_engine_cache()

    # 4. Verify native SQL Server SESSION_CONTEXT RLS as [pulse_reader]
    from app.db import get_engine
    with get_engine(user_id="global_program_lead").connect() as conn:
        glob_cnt = int(conn.execute(text("SELECT COUNT(*) FROM goldview.v_core_adoption")).scalar())
    with get_engine(user_id="amer_ops_vp").connect() as conn:
        amer_cnt = int(conn.execute(text("SELECT COUNT(*) FROM goldview.v_core_adoption")).scalar())
        amer_regs = [r[0] for r in conn.execute(text("SELECT DISTINCT RegionCode FROM goldview.v_core_adoption WHERE RegionCode IS NOT NULL")).fetchall()]
    with get_engine(user_id="emea_rollout_director").connect() as conn:
        emea_cnt = int(conn.execute(text("SELECT COUNT(*) FROM goldview.v_core_adoption")).scalar())
        emea_regs = [r[0] for r in conn.execute(text("SELECT DISTINCT RegionCode FROM goldview.v_core_adoption WHERE RegionCode IS NOT NULL")).fetchall()]

    out = {
        "database": db_name,
        "reader_login": app_user,
        "etl_run_1": etl_summary,
        "etl_run_2_idempotency": idem_summary,
        "rls_verification": {
            "global_program_lead_rows": glob_cnt,
            "amer_ops_vp_rows": amer_cnt,
            "amer_ops_vp_regions": amer_regs,
            "emea_rollout_director_rows": emea_cnt,
            "emea_rollout_director_regions": emea_regs,
        },
    }
    print(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    provision_and_load()
