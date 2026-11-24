"""Persona Row-Level Security (RLS) helpers for CORE Pulse.

Enforced natively in SQL Server (`sql/rls_mssql.sql`) via `SESSION_CONTEXT('user_id')` AND
mirrored in Python so DuckDB and pre-query scope checks behave identically.
"""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import text

from app.db import get_engine

ALL_REGIONS = ("AMER", "EMEA", "APAC")


@dataclass(frozen=True)
class UserScope:
    user_id: str
    display_name: str
    scope_label: str
    is_global: bool
    regions: tuple[str, ...]
    entities: tuple[str, ...]
    waves: tuple[int, ...]
    business_units: tuple[str, ...]


def get_user_scope(user_id: str) -> UserScope:
    eng = get_engine()
    with eng.connect() as conn:
        prow = conn.execute(
            text("SELECT display_name, scope_label FROM rls.app_persona WHERE user_id = :u"),
            {"u": user_id},
        ).fetchone()
        if prow is None:
            return UserScope(user_id=user_id, display_name=user_id, scope_label="No access",
                             is_global=False, regions=(), entities=(), waves=(), business_units=())
        regs = [
            r[0] for r in conn.execute(
                text("SELECT region_code FROM rls.user_region_access WHERE user_id = :u ORDER BY region_code"),
                {"u": user_id},
            ).fetchall()
        ]
        is_global = set(regs) >= set(ALL_REGIONS)
        if not regs:
            return UserScope(user_id=user_id, display_name=prow[0], scope_label=prow[1],
                             is_global=False, regions=(), entities=(), waves=(), business_units=())
        placeholders = ", ".join(f":r{i}" for i in range(len(regs)))
        params = {f"r{i}": r for i, r in enumerate(regs)}
        orgs = conn.execute(
            text(f"""
                SELECT BusinessUnit, AdoptionEntity, AdoptionWaveNumber
                FROM silver.organization
                WHERE RegionCode IN ({placeholders})
                ORDER BY BusinessUnit
            """),
            params,
        ).fetchall()
        bus = tuple(sorted({r[0] for r in orgs}))
        ents = tuple(sorted({r[1] for r in orgs}))
        waves = tuple(sorted({int(r[2]) for r in orgs if r[2] is not None}))
        return UserScope(
            user_id=user_id,
            display_name=str(prow[0]),
            scope_label=str(prow[1]),
            is_global=is_global,
            regions=tuple(regs),
            entities=ents,
            waves=waves,
            business_units=bus,
        )


def check_scope_allowed(scope: UserScope, region: str | None = None, entity: str | None = None,
                        wave: int | None = None, business_unit: str | None = None) -> str | None:
    """Return a polite refusal message if the requested filter falls outside the persona's RLS scope."""
    if not scope.regions:
        return "Your persona has no data access assigned. Please contact BI Governance."
    if scope.is_global:
        return None
    if region and region not in scope.regions:
        return (f"Sorry, you don't have access to region **{region}**. "
                f"Your current persona (**{scope.display_name}**) is scoped to **{scope.scope_label}**.")
    if entity and entity not in scope.entities:
        return (f"Sorry, you don't have access to adoption entity **{entity}**. "
                f"Your current persona (**{scope.display_name}**) covers: {', '.join(scope.entities)}.")
    if wave is not None and int(wave) not in scope.waves:
        return (f"Sorry, you don't have access to **Wave {wave}**. "
                f"Your current persona (**{scope.display_name}**) covers {', '.join(f'Wave {w}' for w in scope.waves)}.")
    if business_unit and business_unit not in scope.business_units:
        return (f"Sorry, you don't have access to Business Unit **{business_unit}**. "
                f"Your current persona (**{scope.display_name}**) covers: {', '.join(scope.business_units)}.")
    return None
