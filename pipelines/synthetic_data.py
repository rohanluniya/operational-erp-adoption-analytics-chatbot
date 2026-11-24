"""Deterministic synthetic world generator for CORE Pulse.

Generates 18 calendar months (2025-06-01 .. 2026-11-17) across 3 regions (AMER, EMEA, APAC),
7 countries, 10 CORE business units, 5 adoption entities, 4 rollout waves, 8 applications,
420 non-service users + 12 service accounts, and all 16 normalized CORE source tables plus
the clearly marked SIMULATED EXTENSION rollout_registry and module_catalog.

Includes all 12 adversarial edge-case fixtures required by §3 of the specification.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd

from app.config import data_as_of_date, demo_seed


# 10 CORE Business Units across 3 Regions, 7 Countries, 5 Adoption Entities, 4 Waves
BUSINESS_UNITS = [
    # (id, code, name, company_code, company_name, country, status, bu_type, active, region_code, region_desc, entity, wave)
    (101, "BU-US-FLD-01", "US Field & Pipeline Inspection", "ENT-US01", "North America Field Services Inc.", "US", "ACTIVE", "FIELD", 1, "AMER", "Americas", "North America Field Ops", 1),
    (102, "BU-US-INF-02", "US Infrastructure & Civil Testing", "ENT-US01", "North America Field Services Inc.", "US", "ACTIVE", "TESTING", 1, "AMER", "Americas", "North America Field Ops", 1),
    (103, "BU-CA-CERT-03", "Canada Conformity & Equipment Cert", "ENT-CA01", "Canada Assurance & Cert Ltd.", "CA", "ACTIVE", "CERT", 1, "AMER", "Americas", "North America Cert & Labs", 1),
    (104, "BU-FR-IND-04", "France Industrial Inspection", "ENT-FR01", "Europe Industrial Controle SAS", "FR", "ACTIVE", "FIELD", 1, "EMEA", "Europe, Middle East & Africa", "Europe Industrial & Testing", 2),
    (105, "BU-DE-LAB-05", "Germany Analytical & Materials Lab", "ENT-DE01", "Deutschland Materials Lab GmbH", "DE", "ACTIVE", "LAB", 1, "EMEA", "Europe, Middle East & Africa", "Europe Industrial & Testing", 2),
    (106, "BU-AE-MAR-06", "MEA Marine & Energy Verification", "ENT-AE01", "Gulf Marine Verification FZCO", "AE", "ACTIVE", "MARINE", 1, "EMEA", "Europe, Middle East & Africa", "MEA Energy & Marine", 2),
    (107, "BU-SG-MAR-07", "Singapore Marine & Offshore", "ENT-SG01", "Asia-Pacific Marine Pte Ltd.", "SG", "ACTIVE", "MARINE", 1, "APAC", "Asia-Pacific", "APAC Certification & Marine", 3),
    (108, "BU-SG-LAB-08", "APAC Environmental & Food Lab", "ENT-SG01", "Asia-Pacific Marine Pte Ltd.", "SG", "ACTIVE", "LAB", 1, "APAC", "Asia-Pacific", "APAC Certification & Marine", 3),
    (109, "BU-BR-FLD-09", "Brazil Field & Mining Inspection", "ENT-BR01", "Sudamerica Field Services Ltda", "BR", "ACTIVE", "FIELD", 1, "AMER", "Americas", "Latin America Operations", 4),
    # Edge Case #7: Present in CORE BusinessUnit but intentionally absent from optional local enrichment!
    (110, "BU-AU-REN-10", "Australia Renewables Verification", "ENT-AU01", "Oceania Renewables Pty Ltd.", "AU", "ACTIVE", "ENERGY", 1, "APAC", "Asia-Pacific", "APAC Certification & Marine", 3),
]

APPLICATIONS = [
    # (app_id, app_code, app_name, entity, wave, opt_bu, mapping_status, region_code, launch_ym)
    (1, "CORE-PORTAL-NA", "CORE Field Portal — North America", "North America Field Ops", 1, None, "CONFIRMED", "AMER", (2025, 6)),
    (2, "CORE-CERT-NA", "CORE Cert & Lab Workbench — NA", "North America Cert & Labs", 1, None, "CONFIRMED", "AMER", (2025, 6)),
    (3, "CORE-IND-EU", "CORE Industrial Hub — Europe", "Europe Industrial & Testing", 2, None, "CONFIRMED", "EMEA", (2025, 9)),
    (4, "CORE-MEA-OPS", "CORE Marine & Energy — MEA", "MEA Energy & Marine", 2, None, "CONFIRMED", "EMEA", (2025, 10)),
    (5, "CORE-APAC-HUB", "CORE Operations Hub — APAC", "APAC Certification & Marine", 3, None, "CONFIRMED", "APAC", (2026, 5)),
    (6, "CORE-LATAM-OPS", "CORE Field Portal — Latin America", "Latin America Operations", 4, None, "CONFIRMED", "AMER", (2026, 10)),
    # Edge Case #12: Unconfirmed / excluded apps for mapping exception & filtering tests
    (7, "CORE-LEGACY-SYNC", "CORE Legacy Bridge Connector", "Europe Industrial & Testing", 2, None, "REVIEW", "EMEA", (2025, 9)),
    (8, "CORE-SANDBOX-UAT", "CORE Training & UAT Sandbox", "Unassigned Sandbox", 0, None, "EXCLUDED", "AMER", (2025, 6)),
]

MODULE_CATALOG = [
    ("CORE_LOGIN", "CORE Application Login", "Enterprise authentication and workspace sign-in telemetry", "INSTRUMENTED", "CONFIRMED"),
    ("PROJECTS", "Projects & Contracts", "Client contract and inspection project setup (Project.Project)", "INSTRUMENTED", "CONFIRMED"),
    ("TIMECARDS", "Timesheets & Timecards", "Employee weekly timecard submission workflow (Timesheet.Timecard)", "INSTRUMENTED", "CONFIRMED"),
    ("EXPENSES", "Expense Reports", "Field travel and lab consumable expense reports (Expense.ExpenseReport)", "INSTRUMENTED", "CONFIRMED"),
    ("INSPECTOR_SCHED", "Inspector Scheduling", "Field inspector dispatch and shift rostering (future release)", "NOT_INSTRUMENTED", "SIMULATED_EXTENSION"),
    ("QUALIFICATIONS", "Inspector Qualifications", "NDT, pressure-equipment, and safety licence tracking (future release)", "NOT_INSTRUMENTED", "SIMULATED_EXTENSION"),
    ("LAB_TESTING", "Laboratory Sample Testing", "LIMS specimen intake and certificate issuance (future release)", "NOT_INSTRUMENTED", "SIMULATED_EXTENSION"),
    ("INVOICING", "Client Billing & Invoicing", "Milestone and time-and-materials invoice generation (future release)", "NOT_INSTRUMENTED", "SIMULATED_EXTENSION"),
]


def _month_starts(first_ym: tuple[int, int], as_of: date) -> list[date]:
    out = []
    y, m = first_ym
    while (y, m) <= (as_of.year, as_of.month):
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _month_end(ms: date, as_of: date) -> date:
    last_day = calendar.monthrange(ms.year, ms.month)[1]
    me = date(ms.year, ms.month, last_day)
    return min(me, as_of)


def generate_all(seed: int | None = None, as_of: date | None = None) -> dict[str, pd.DataFrame]:
    """Return deterministic DataFrames for all 16 source_sim.* tables + reference.* tables."""
    seed = demo_seed() if seed is None else seed
    as_of = data_as_of_date() if as_of is None else as_of
    rng = np.random.default_rng(seed)
    months = _month_starts((2025, 6), as_of)

    # 1. source_sim.business_unit & reference.local_org_enrichment
    bu_rows, enrich_rows = [], []
    for (buid, code, name, ccode, cname, country, status, btype, active, rcode, rdesc, entity, wave) in BUSINESS_UNITS:
        bu_rows.append({
            "BusinessUnitId": buid,
            "BusinessUnit": code,
            "BusinessUnitName": name,
            "CompanyCode": ccode,
            "CompanyName": cname,
            "CountryCode": country,
            "Status": status,
            "Type": btype,
            "Active": active,
            "RegionCode": rcode,
            "RegionDesc": rdesc,
            "CreatedDate": datetime(2024, 1, 15, 8, 0, 0),
            "ModifiedDate": datetime(2025, 6, 1, 9, 0, 0),
        })
        # Edge Case #7: BU-AU-REN-10 is absent from local_org_enrichment
        if code != "BU-AU-REN-10":
            enrich_rows.append({
                "OrganizationCode": code,
                "AdoptionEntity": entity,
                "AdoptionWaveNumber": wave,
                "DivisionName": f"{rdesc} TIC Division",
            })
    df_bu = pd.DataFrame(bu_rows)
    df_local_enrich = pd.DataFrame(enrich_rows)

    # Complete BU -> Entity/Wave governance lookup (used by silver.organization fallback for BU-AU-REN-10)
    bu_gov = {r[1]: (r[11], r[12], r[9], r[5]) for r in BUSINESS_UNITS}

    # 2. source_sim.application & reference.application_mapping_seed
    app_rows, app_map_rows = [], []
    for (aid, acode, aname, ent, wave, obu, mstat, rcode, _) in APPLICATIONS:
        app_rows.append({
            "ApplicationId": aid,
            "ApplicationCode": acode,
            "ApplicationName": aname,
            "IsActive": 1,
            "CreatedDate": datetime(2025, 1, 10, 8, 0, 0),
        })
        app_map_rows.append({
            "ApplicationCode": acode,
            "AdoptionEntity": ent,
            "AdoptionWaveNumber": wave,
            "BusinessUnit": obu,
            "RegionCode": rcode,
            "MappingStatus": mstat,
        })
    df_app = pd.DataFrame(app_rows)
    df_app_map = pd.DataFrame(app_map_rows)

    # 3. source_sim.application_log_type & timecard_status
    df_log_type = pd.DataFrame([
        {"ApplicationLogTypeId": 1, "Name": "Application Login", "Description": "Interactive user login"},
        {"ApplicationLogTypeId": 2, "Name": "Session Timeout", "Description": "Idle timeout event"},
        {"ApplicationLogTypeId": 3, "Name": "Token Refresh", "Description": "Background OAuth refresh"},
        {"ApplicationLogTypeId": 4, "Name": "Failed Login", "Description": "Invalid credential attempt"},
    ])
    df_tc_status = pd.DataFrame([
        {"TimecardStatusId": 1, "StatusName": "Time Entry"},
        {"TimecardStatusId": 2, "StatusName": "Rejected"},
        {"TimecardStatusId": 3, "StatusName": "Submitted"},
        {"TimecardStatusId": 4, "StatusName": "Approved"},
        {"TimecardStatusId": 5, "StatusName": "Exported"},
    ])

    # 4. source_sim.app_user (NO sensitive auth attributes!)
    # Entity user pools: Wave 1 NA Field (115), Wave 1 NA Cert (65), Wave 2 EU Ind (95), Wave 2 MEA (50), Wave 3 APAC (75), Wave 4 LatAm (30) = 430 users + 2 special + 12 service
    entity_pools = [
        ("North America Field Ops", 1, "AMER", 115),
        ("North America Cert & Labs", 1, "AMER", 65),
        ("Europe Industrial & Testing", 2, "EMEA", 95),
        ("MEA Energy & Marine", 2, "EMEA", 50),
        ("APAC Certification & Marine", 3, "APAC", 75),
        ("Latin America Operations", 4, "AMER", 30),
    ]
    user_rows = []
    user_primary_app: dict[int, int] = {}
    entity_to_app = {
        "North America Field Ops": 1,
        "North America Cert & Labs": 2,
        "Europe Industrial & Testing": 3,
        "MEA Energy & Marine": 4,
        "APAC Certification & Marine": 5,
        "Latin America Operations": 6,
    }
    uid = 1001
    for ent, _wv, rcode, count in entity_pools:
        for _ in range(count):
            user_rows.append({
                "APPUserId": uid,
                "EmployeeId": f"EMP-{uid}",
                "ContactId": uid + 50000,
                "LDAPId": f"u{uid}@rl-inspection.example",
                "IsServiceAccount": 0,
            })
            user_primary_app[uid] = entity_to_app[ent]
            uid += 1

    # Cross-entity specialist pool (18 employees who legitimately log into both Wave 1 & Wave 2 apps, making sums > distinct!)
    cross_users = list(range(1001, 1019))

    # Edge Case #1: Explicit dual-wave user U9001
    user_rows.append({"APPUserId": 9001, "EmployeeId": "EMP-9001", "ContactId": 59001,
                      "LDAPId": "u9001@rl-inspection.example", "IsServiceAccount": 0})
    # Edge Case #2: Explicit multi-login-same-day user U9002
    user_rows.append({"APPUserId": 9002, "EmployeeId": "EMP-9002", "ContactId": 59002,
                      "LDAPId": "u9002@rl-inspection.example", "IsServiceAccount": 0})
    user_primary_app[9001] = 1
    user_primary_app[9002] = 1

    # Edge Case #3: 12 Service accounts (IsServiceAccount = 1)
    svc_ids = []
    for s in range(1, 13):
        sid = 9500 + s
        svc_ids.append(sid)
        user_rows.append({
            "APPUserId": sid,
            "EmployeeId": None,
            "ContactId": None,
            "LDAPId": f"svc_core_{s:02d}@rl-inspection.example",
            "IsServiceAccount": 1,
        })
    df_users = pd.DataFrame(user_rows)

    # 5. source_sim.project, project_service, project_phase, project_task, project_task_timeline_event
    bu_launch = {
        "BU-US-FLD-01": (2025, 6), "BU-US-INF-02": (2025, 6), "BU-CA-CERT-03": (2025, 7),
        "BU-FR-IND-04": (2025, 9), "BU-DE-LAB-05": (2025, 10), "BU-AE-MAR-06": (2025, 11),
        "BU-SG-MAR-07": (2026, 5), "BU-SG-LAB-08": (2026, 6), "BU-AU-REN-10": (2026, 7),
        "BU-BR-FLD-09": (2026, 10),
    }
    bu_base_proj = {
        "BU-US-FLD-01": 28, "BU-US-INF-02": 22, "BU-CA-CERT-03": 18,
        "BU-FR-IND-04": 24, "BU-DE-LAB-05": 19, "BU-AE-MAR-06": 14,
        "BU-SG-MAR-07": 20, "BU-SG-LAB-08": 16, "BU-AU-REN-10": 11,
        "BU-BR-FLD-09": 9,
    }
    seasonal_mult = {1: 0.90, 2: 0.94, 3: 1.08, 4: 1.05, 5: 1.10, 6: 1.14,
                     7: 1.02, 8: 0.88, 9: 1.12, 10: 1.18, 11: 1.06, 12: 0.92}

    proj_rows, svc_rows, phase_rows, task_rows, tl_rows = [], [], [], [], []
    bu_tasks: dict[str, list[int]] = {r[1]: [] for r in BUSINESS_UNITS}
    pid, sid_seq, ph_seq, tid_seq, tl_seq = 10001, 20001, 30001, 40001, 50001

    for m_idx, ms in enumerate(months):
        me = _month_end(ms, as_of)
        days_in_m = calendar.monthrange(ms.year, ms.month)[1]
        avail_days = (me - ms).days + 1
        frac = avail_days / days_in_m
        for (_buid, bcode, bname, _cc, _cn, _co, _st, btype, _act, _rc, _rd, _ent, wave) in BUSINESS_UNITS:
            ly, lm = bu_launch[bcode]
            months_live = (ms.year - ly) * 12 + (ms.month - lm)
            if months_live < 0:
                continue
            ramp = min(1.0, 0.38 + 0.14 * months_live) if wave >= 3 else min(1.0, 0.65 + 0.06 * months_live)
            expected = bu_base_proj[bcode] * seasonal_mult[ms.month] * ramp * frac * (1.0 + 0.012 * m_idx)
            n_proj = max(1, int(rng.poisson(expected)))
            for _ in range(n_proj):
                day_off = int(rng.integers(0, avail_days))
                c_dt = datetime(ms.year, ms.month, 1 + day_off, int(rng.integers(7, 19)), int(rng.integers(0, 60)))
                p_start = (c_dt + timedelta(days=int(rng.integers(3, 25)))).date()
                is_closed = 1 if (as_of - c_dt.date()).days > 150 and rng.random() < 0.45 else 0
                proj_rows.append({
                    "ProjectId": pid,
                    "CreatedDate": c_dt,
                    "BusinessUnit": bcode,
                    "ProjectName": f"{btype.title()} Contract #{pid}",
                    "ParentContractCode": f"CTR-{bcode[-2:]}-{pid // 5}",
                    "FlexContractNumber": f"FLX-{pid}",
                    "ProjectStatusId": 4 if is_closed else 2,
                    "ProjectStartDate": p_start,
                    "ActualEndDate": (p_start + timedelta(days=90)) if is_closed else None,
                    "Billable": 1,
                    "IsClosed": is_closed,
                    "CurrencyCode": "USD",
                    "ModifiedDate": c_dt + timedelta(days=2),
                    "ProposedStartDate": p_start,
                })
                # 1 service -> 1 phase -> 2 tasks per project
                svc_rows.append({
                    "ProjectServiceId": sid_seq,
                    "ProjectId": pid,
                    "ServiceCode": f"SVC-{btype[:3]}",
                    "ServiceName": f"{btype.title()} Service",
                })
                phase_rows.append({
                    "ProjectPhaseId": ph_seq,
                    "ProjectServiceId": sid_seq,
                    "PhaseName": "Field Execution & Reporting",
                })
                for t_i in range(2):
                    act_hrs = round(float(rng.uniform(4.0, 36.0)), 1)
                    task_rows.append({
                        "ProjectTaskId": tid_seq,
                        "ProjectPhaseId": ph_seq,
                        "TaskName": "Site Inspection" if t_i == 0 else "Compliance Report",
                        "ActualHours": act_hrs,
                        "AssignedUserId": int(rng.integers(1001, 1430)),
                    })
                    bu_tasks[bcode].append(tid_seq)
                    tl_rows.append({
                        "TimelineEventId": tl_seq,
                        "ProjectTaskId": tid_seq,
                        "EventType": "TASK_ASSIGNED" if t_i == 0 else "TASK_ACTIVE",
                        "EventDateTime": c_dt + timedelta(days=1),
                    })
                    tid_seq += 1
                    tl_seq += 1
                pid += 1
                sid_seq += 1
                ph_seq += 1

    # Edge Case #6: Project created in Oct 2026 (2026-10-28), ProjectStartDate in Dec 2026 (2026-12-01)
    proj_rows.append({
        "ProjectId": 99001,
        "CreatedDate": datetime(2026, 10, 28, 14, 30, 0),
        "BusinessUnit": "BU-US-FLD-01",
        "ProjectName": "Future-Start Pipeline Integrity Contract (Fixture #6)",
        "ParentContractCode": "CTR-FIX-06",
        "FlexContractNumber": "FLX-99001",
        "ProjectStatusId": 1,
        "ProjectStartDate": date(2026, 12, 1),
        "ActualEndDate": None,
        "Billable": 1,
        "IsClosed": 0,
        "CurrencyCode": "USD",
        "ModifiedDate": datetime(2026, 10, 29, 9, 0, 0),
        "ProposedStartDate": date(2026, 12, 5),
    })

    # 6. source_sim.application_log
    log_rows = []
    log_id = 100001
    app_launch_map = {a[0]: a[8] for a in APPLICATIONS}

    for m_idx, ms in enumerate(months):
        me = _month_end(ms, as_of)
        days_in_m = calendar.monthrange(ms.year, ms.month)[1]
        avail_days = (me - ms).days + 1
        frac = avail_days / days_in_m

        for u in range(1001, uid):
            aid = user_primary_app[u]
            ly, lm = app_launch_map[aid]
            m_live = (ms.year - ly) * 12 + (ms.month - lm)
            if m_live < 0:
                continue
            # Ramp-up probability of user being active in month
            active_prob = min(0.88, 0.35 + 0.11 * m_live) if aid in (5, 6) else min(0.86, 0.58 + 0.03 * m_idx)
            # In partial month, scale login probability slightly by elapsed fraction
            if frac < 1.0:
                active_prob *= (0.55 + 0.45 * frac)
            if rng.random() < active_prob:
                n_days = max(1, int(rng.integers(2, max(3, int(9 * frac) + 2))))
                chosen_days = rng.choice(range(1, avail_days + 1), size=min(n_days, avail_days), replace=False)
                for d in sorted(chosen_days):
                    dt = datetime(ms.year, ms.month, int(d), int(rng.integers(6, 19)), int(rng.integers(0, 60)))
                    log_rows.append({
                        "ApplicationLogId": log_id,
                        "ApplicationLogTypeId": 1,
                        "ApplicationId": aid,
                        "APPUserId": u,
                        "CreatedDate": dt,
                        "ClientHost": "web-client",
                    })
                    log_id += 1
                    # Cross-entity specialist also logs into Wave 2 Europe app on same month!
                    if u in cross_users and (ms.year, ms.month) >= (2025, 10) and rng.random() < 0.45:
                        log_rows.append({
                            "ApplicationLogId": log_id,
                            "ApplicationLogTypeId": 1,
                            "ApplicationId": 3,
                            "APPUserId": u,
                            "CreatedDate": dt + timedelta(minutes=25),
                            "ClientHost": "web-client",
                        })
                        log_id += 1

        # Service account logins (Edge Case #3 - must NEVER count as Employees Logging In)
        for sid in svc_ids[:6]:
            dt = datetime(ms.year, ms.month, min(avail_days, 3), 2, 15, 0)
            log_rows.append({
                "ApplicationLogId": log_id,
                "ApplicationLogTypeId": 1,
                "ApplicationId": 1,
                "APPUserId": sid,
                "CreatedDate": dt,
                "ClientHost": "batch-worker",
            })
            log_id += 1

        # Non-login events (Token Refresh / Session Timeout) - must be excluded
        for _ in range(15):
            dt = datetime(ms.year, ms.month, int(rng.integers(1, avail_days + 1)), 12, 0, 0)
            log_rows.append({
                "ApplicationLogId": log_id,
                "ApplicationLogTypeId": int(rng.choice([2, 3, 4])),
                "ApplicationId": 1,
                "APPUserId": int(rng.integers(1001, 1100)),
                "CreatedDate": dt,
                "ClientHost": "web-client",
            })
            log_id += 1

        # Edge Case #12: REVIEW & EXCLUDED app logins
        if (ms.year, ms.month) >= (2026, 1):
            for unmapped_app in (7, 8):
                log_rows.append({
                    "ApplicationLogId": log_id,
                    "ApplicationLogTypeId": 1,
                    "ApplicationId": unmapped_app,
                    "APPUserId": 1025,
                    "CreatedDate": datetime(ms.year, ms.month, 2, 10, 0, 0),
                    "ClientHost": "legacy-sync",
                })
                log_id += 1

    # Edge Case #1: U9001 logs into Wave 1 (app 1) AND Wave 2 (app 3) on the exact same days (2026-10-14 & 2026-11-10)
    for dt_fix in (datetime(2026, 10, 14, 9, 0, 0), datetime(2026, 11, 10, 9, 0, 0)):
        for app_fix in (1, 3):
            log_rows.append({
                "ApplicationLogId": log_id,
                "ApplicationLogTypeId": 1,
                "ApplicationId": app_fix,
                "APPUserId": 9001,
                "CreatedDate": dt_fix + timedelta(minutes=10 * app_fix),
                "ClientHost": "fixture-dual-wave",
            })
            log_id += 1

    # Edge Case #2: U9002 logs into app 1 FIVE times on 2026-11-05 (distinct user count = 1, event count = 5)
    for hr in (8, 10, 13, 15, 17):
        log_rows.append({
            "ApplicationLogId": log_id,
            "ApplicationLogTypeId": 1,
            "ApplicationId": 1,
            "APPUserId": 9002,
            "CreatedDate": datetime(2026, 11, 5, hr, 12, 0),
            "ClientHost": "fixture-multi-login",
        })
        log_id += 1

    log_rows.sort(key=lambda r: (r["CreatedDate"], r["ApplicationLogId"]))
    for idx_l, r in enumerate(log_rows, start=100001):
        r["ApplicationLogId"] = idx_l

    # 7. source_sim.timecard, timecard_row, timecard_entry
    # Story arc: EMEA (Wave 2) has strong timecard adoption; Wave 3 ramps strongly in H2 2026
    tc_rows, tcrow_rows, tcent_rows = [], [], []
    tc_id, tcr_id, tce_id = 60001, 70001, 80001
    bu_tc_rate = {
        "BU-US-FLD-01": 62, "BU-US-INF-02": 48, "BU-CA-CERT-03": 38,
        "BU-FR-IND-04": 74, "BU-DE-LAB-05": 66, "BU-AE-MAR-06": 44,
        "BU-SG-MAR-07": 42, "BU-SG-LAB-08": 34, "BU-AU-REN-10": 22,
        "BU-BR-FLD-09": 16,
    }
    for m_idx, ms in enumerate(months):
        me = _month_end(ms, as_of)
        days_in_m = calendar.monthrange(ms.year, ms.month)[1]
        avail_days = (me - ms).days + 1
        frac = avail_days / days_in_m
        for (_buid, bcode, *_rest, entity, wave) in BUSINESS_UNITS:
            ly, lm = bu_launch[bcode]
            m_live = (ms.year - ly) * 12 + (ms.month - lm)
            if m_live < 0:
                continue
            ramp = min(1.0, 0.42 + 0.14 * m_live) if wave >= 3 else min(1.0, 0.72 + 0.04 * m_live)
            n_tc = max(2, int(rng.poisson(bu_tc_rate[bcode] * ramp * frac * (1.0 + 0.015 * m_idx))))
            tasks_pool = bu_tasks[bcode]
            for _ in range(n_tc):
                day_off = int(rng.integers(0, avail_days))
                sub_dt = datetime(ms.year, ms.month, 1 + day_off, int(rng.integers(8, 20)), 0)
                # 10% unsubmitted drafts (Status 1, SubmittedDate=None); submitted ones move across 2/3/4/5!
                if rng.random() < 0.10:
                    status_id = 1
                    submitted_dt = None
                    approved_dt = None
                    exported_dt = None
                else:
                    status_id = int(rng.choice([2, 3, 4, 5], p=[0.05, 0.20, 0.45, 0.30]))
                    submitted_dt = sub_dt
                    approved_dt = (sub_dt + timedelta(days=2)) if status_id in (4, 5) else None
                    exported_dt = (sub_dt + timedelta(days=5)) if status_id == 5 else None
                emp_u = int(rng.integers(1001, uid))
                tc_rows.append({
                    "TimecardId": tc_id,
                    "APPUserId": emp_u,
                    "PeriodStartDate": ms,
                    "TimecardStatusId": status_id,
                    "CreatedDate": sub_dt - timedelta(days=1),
                    "SubmittedDate": submitted_dt,
                    "ApprovedDate": approved_dt,
                    "ExportedDate": exported_dt,
                })
                ptask = int(rng.choice(tasks_pool)) if tasks_pool else None
                tcrow_rows.append({
                    "TimecardRowId": tcr_id,
                    "TimecardId": tc_id,
                    "ProjectTaskId": ptask,
                    "ContractCode": f"CTR-{bcode[-2:]}",
                })
                tcent_rows.append({
                    "TimecardEntryId": tce_id,
                    "TimecardRowId": tcr_id,
                    "EntryDate": sub_dt.date(),
                    "HoursWorked": round(float(rng.uniform(6.0, 40.0)), 1),
                })
                tc_id += 1
                tcr_id += 1
                tce_id += 1

    # Edge Case #4: Timecard submitted in Oct 2026 and later Approved & Exported (counts ONCE in Oct 2026)
    tc_rows.append({
        "TimecardId": 99101,
        "APPUserId": 1005,
        "PeriodStartDate": date(2026, 10, 1),
        "TimecardStatusId": 5,  # Exported!
        "CreatedDate": datetime(2026, 10, 10, 9, 0, 0),
        "SubmittedDate": datetime(2026, 10, 12, 16, 30, 0),
        "ApprovedDate": datetime(2026, 10, 14, 11, 0, 0),
        "ExportedDate": datetime(2026, 10, 18, 6, 0, 0),
    })
    tcrow_rows.append({"TimecardRowId": 99201, "TimecardId": 99101, "ProjectTaskId": bu_tasks["BU-US-FLD-01"][0], "ContractCode": "CTR-01"})
    tcent_rows.append({"TimecardEntryId": 99301, "TimecardRowId": 99201, "EntryDate": date(2026, 10, 11), "HoursWorked": 38.0})

    # Edge Case #4b: Draft Timecard (Status=1, SubmittedDate=None) -> NEVER counted
    tc_rows.append({
        "TimecardId": 99102,
        "APPUserId": 1006,
        "PeriodStartDate": date(2026, 10, 1),
        "TimecardStatusId": 1,
        "CreatedDate": datetime(2026, 10, 20, 9, 0, 0),
        "SubmittedDate": None,
        "ApprovedDate": None,
        "ExportedDate": None,
    })

    # Edge Case #9: Multi-BU Timecard (rows spanning BU-US-FLD-01 and BU-FR-IND-04) -> counted ONCE in OVERALL, never duplicated or assigned a fake BU!
    tc_rows.append({
        "TimecardId": 99103,
        "APPUserId": 1007,
        "PeriodStartDate": date(2026, 10, 1),
        "TimecardStatusId": 4,
        "CreatedDate": datetime(2026, 10, 17, 9, 0, 0),
        "SubmittedDate": datetime(2026, 10, 18, 17, 0, 0),
        "ApprovedDate": datetime(2026, 10, 19, 10, 0, 0),
        "ExportedDate": None,
    })
    tcrow_rows.append({"TimecardRowId": 99203, "TimecardId": 99103, "ProjectTaskId": bu_tasks["BU-US-FLD-01"][0], "ContractCode": "CTR-01"})
    tcrow_rows.append({"TimecardRowId": 99204, "TimecardId": 99103, "ProjectTaskId": bu_tasks["BU-FR-IND-04"][0], "ContractCode": "CTR-04"})
    tcent_rows.append({"TimecardEntryId": 99303, "TimecardRowId": 99203, "EntryDate": date(2026, 10, 15), "HoursWorked": 20.0})
    tcent_rows.append({"TimecardEntryId": 99304, "TimecardRowId": 99204, "EntryDate": date(2026, 10, 16), "HoursWorked": 20.0})

    # Edge Case #12: 3 Orphan TimecardRow records pointing to non-existent TimecardId 999999
    for orph_i in range(3):
        tcrow_rows.append({
            "TimecardRowId": 99800 + orph_i,
            "TimecardId": 999999,
            "ProjectTaskId": bu_tasks["BU-US-FLD-01"][0],
            "ContractCode": "CTR-ORPHAN",
        })

    # 8. source_sim.expense_report & expense_entry
    # Story arc: EMEA has noticeable expense lag (low rates in FR/DE); Edge Case #10: BU-BR-FLD-09 (LatAm Wave 4) is LIVE for Expenses since 2026-10-15 with ZERO observed expense submissions!
    exp_rows, expent_rows = [], []
    exp_id, expe_id = 30001, 40001
    bu_exp_rate = {
        "BU-US-FLD-01": 34, "BU-US-INF-02": 26, "BU-CA-CERT-03": 21,
        "BU-FR-IND-04": 9,  "BU-DE-LAB-05": 8,  "BU-AE-MAR-06": 15,   # EMEA expense adoption lag!
        "BU-SG-MAR-07": 22, "BU-SG-LAB-08": 18, "BU-AU-REN-10": 12,
        "BU-BR-FLD-09": 0,  # Edge Case #10: LIVE rollout with ZERO observed expense submissions!
    }
    for m_idx, ms in enumerate(months):
        me = _month_end(ms, as_of)
        days_in_m = calendar.monthrange(ms.year, ms.month)[1]
        avail_days = (me - ms).days + 1
        frac = avail_days / days_in_m
        for (_buid, bcode, *_rest, entity, wave) in BUSINESS_UNITS:
            if bu_exp_rate[bcode] == 0:
                continue
            ly, lm = bu_launch[bcode]
            m_live = (ms.year - ly) * 12 + (ms.month - lm)
            if m_live < 0:
                continue
            ramp = min(1.0, 0.40 + 0.13 * m_live) if wave >= 3 else min(1.0, 0.68 + 0.03 * m_live)
            n_exp = max(1, int(rng.poisson(bu_exp_rate[bcode] * ramp * frac * (1.0 + 0.01 * m_idx))))
            tasks_pool = bu_tasks[bcode]
            for _ in range(n_exp):
                day_off = int(rng.integers(0, avail_days))
                sub_dt = datetime(ms.year, ms.month, 1 + day_off, int(rng.integers(8, 20)), 15)
                is_sub = rng.random() >= 0.08
                exp_rows.append({
                    "ExpenseReportId": exp_id,
                    "APPUserId": int(rng.integers(1001, uid)),
                    "BusinessUnit": bcode,
                    "ReportStatus": "Approved" if is_sub and rng.random() < 0.7 else ("Submitted" if is_sub else "Draft"),
                    "CreatedDate": sub_dt - timedelta(days=1),
                    "SubmittedDate": sub_dt if is_sub else None,
                    "ModifiedDate": sub_dt + timedelta(days=1),
                    "CurrencyCode": "USD",
                })
                expent_rows.append({
                    "ExpenseEntryId": expe_id,
                    "ExpenseReportId": exp_id,
                    "ProjectTaskId": int(rng.choice(tasks_pool)) if tasks_pool else None,
                    "BusinessUnit": bcode,
                    "AmountUSD": round(float(rng.uniform(45.0, 920.0)), 2),
                    "ExpenseCategory": str(rng.choice(["Travel", "Site Lodging", "Mileage", "Lab Consumables"])),
                })
                exp_id += 1
                expe_id += 1

    # Edge Case #5: Expense report submitted in Oct 2026 (2026-10-22), edited in Nov 2026 (2026-11-04) -> counted ONCE in Oct 2026!
    exp_rows.append({
        "ExpenseReportId": 99501,
        "APPUserId": 1012,
        "BusinessUnit": "BU-US-FLD-01",
        "ReportStatus": "Approved",
        "CreatedDate": datetime(2026, 10, 21, 10, 0, 0),
        "SubmittedDate": datetime(2026, 10, 22, 14, 0, 0),
        "ModifiedDate": datetime(2026, 11, 4, 16, 45, 0),
        "CurrencyCode": "USD",
    })
    expent_rows.append({
        "ExpenseEntryId": 99601,
        "ExpenseReportId": 99501,
        "ProjectTaskId": bu_tasks["BU-US-FLD-01"][0],
        "BusinessUnit": "BU-US-FLD-01",
        "AmountUSD": 315.50,
        "ExpenseCategory": "Travel",
    })

    # Edge Case #12: 2 Orphan ExpenseEntry rows pointing to missing ExpenseReportId 888888
    for orph_e in range(2):
        expent_rows.append({
            "ExpenseEntryId": 99700 + orph_e,
            "ExpenseReportId": 888888,
            "ProjectTaskId": bu_tasks["BU-US-FLD-01"][0],
            "BusinessUnit": "BU-US-FLD-01",
            "AmountUSD": 99.00,
            "ExpenseCategory": "Orphan Fixture",
        })

    # 9. reference.module_catalog & reference.rollout_registry (SIMULATED EXTENSION)
    df_modules = pd.DataFrame([
        {
            "ModuleCode": mc,
            "ModuleName": mn,
            "Description": desc,
            "ActivityInstrumentation": inst,
            "MappingStatus": mstat,
        }
        for (mc, mn, desc, inst, mstat) in MODULE_CATALOG
    ])

    rollout_specs = [
        # (id, entity, bu, region, country, module, wave, status, planned, actual, elig_pop)
        ("ROL-NA-LOGIN", "North America Field Ops", None, "AMER", "US", "CORE_LOGIN", 1, "LIVE", date(2025, 6, 1), date(2025, 6, 1), 115),
        ("ROL-NA-PROJ", "North America Field Ops", "BU-US-FLD-01", "AMER", "US", "PROJECTS", 1, "LIVE", date(2025, 6, 1), date(2025, 6, 1), 65),
        ("ROL-NA-INF-PROJ", "North America Field Ops", "BU-US-INF-02", "AMER", "US", "PROJECTS", 1, "LIVE", date(2025, 6, 1), date(2025, 6, 5), 50),
        ("ROL-NA-TC", "North America Field Ops", None, "AMER", "US", "TIMECARDS", 1, "LIVE", date(2025, 6, 15), date(2025, 6, 15), 115),
        ("ROL-NA-EXP", "North America Field Ops", "BU-US-FLD-01", "AMER", "US", "EXPENSES", 1, "LIVE", date(2025, 7, 1), date(2025, 7, 1), 65),
        ("ROL-NA-SCHED", "North America Field Ops", "BU-US-FLD-01", "AMER", "US", "INSPECTOR_SCHED", 1, "LIVE", date(2026, 3, 1), date(2026, 3, 1), 65),  # LIVE, NOT INSTRUMENTED
        ("ROL-CA-LOGIN", "North America Cert & Labs", None, "AMER", "CA", "CORE_LOGIN", 1, "LIVE", date(2025, 6, 1), date(2025, 6, 10), 65),
        ("ROL-CA-PROJ", "North America Cert & Labs", "BU-CA-CERT-03", "AMER", "CA", "PROJECTS", 1, "LIVE", date(2025, 7, 1), date(2025, 7, 1), 65),
        ("ROL-CA-EXP", "North America Cert & Labs", "BU-CA-CERT-03", "AMER", "CA", "EXPENSES", 1, "LIVE", date(2025, 7, 15), date(2025, 7, 20), 65),
        ("ROL-CA-QUAL", "North America Cert & Labs", "BU-CA-CERT-03", "AMER", "CA", "QUALIFICATIONS", 1, "ONBOARDING", date(2026, 11, 1), None, 65),

        ("ROL-EU-LOGIN", "Europe Industrial & Testing", None, "EMEA", "FR", "CORE_LOGIN", 2, "LIVE", date(2025, 9, 1), date(2025, 9, 1), 95),
        ("ROL-EU-PROJ", "Europe Industrial & Testing", "BU-FR-IND-04", "EMEA", "FR", "PROJECTS", 2, "LIVE", date(2025, 9, 1), date(2025, 9, 8), 52),
        ("ROL-DE-PROJ", "Europe Industrial & Testing", "BU-DE-LAB-05", "EMEA", "DE", "PROJECTS", 2, "LIVE", date(2025, 10, 1), date(2025, 10, 1), 43),
        ("ROL-EU-TC", "Europe Industrial & Testing", None, "EMEA", "FR", "TIMECARDS", 2, "LIVE", date(2025, 10, 1), date(2025, 10, 1), 95),
        ("ROL-EU-EXP", "Europe Industrial & Testing", "BU-FR-IND-04", "EMEA", "FR", "EXPENSES", 2, "LIVE", date(2025, 11, 1), date(2025, 12, 1), 52),
        ("ROL-DE-LAB", "Europe Industrial & Testing", "BU-DE-LAB-05", "EMEA", "DE", "LAB_TESTING", 2, "ONBOARDING", date(2026, 12, 1), None, 43),

        ("ROL-MEA-LOGIN", "MEA Energy & Marine", None, "EMEA", "AE", "CORE_LOGIN", 2, "LIVE", date(2025, 10, 1), date(2025, 10, 5), 50),
        ("ROL-MEA-PROJ", "MEA Energy & Marine", "BU-AE-MAR-06", "EMEA", "AE", "PROJECTS", 2, "LIVE", date(2025, 11, 1), date(2025, 11, 1), None),  # Edge Case #10: unknown eligible pop
        ("ROL-MEA-INV", "MEA Energy & Marine", "BU-AE-MAR-06", "EMEA", "AE", "INVOICING", 2, "PAUSED", date(2026, 8, 1), None, 50),

        ("ROL-APAC-LOGIN", "APAC Certification & Marine", None, "APAC", "SG", "CORE_LOGIN", 3, "LIVE", date(2026, 5, 1), date(2026, 5, 1), 75),
        ("ROL-SG-PROJ", "APAC Certification & Marine", "BU-SG-MAR-07", "APAC", "SG", "PROJECTS", 3, "LIVE", date(2026, 5, 1), date(2026, 5, 4), 35),
        ("ROL-SGLAB-PROJ", "APAC Certification & Marine", "BU-SG-LAB-08", "APAC", "SG", "PROJECTS", 3, "LIVE", date(2026, 6, 1), date(2026, 6, 1), 24),
        ("ROL-AU-PROJ", "APAC Certification & Marine", "BU-AU-REN-10", "APAC", "AU", "PROJECTS", 3, "LIVE", date(2026, 7, 1), date(2026, 7, 1), 16),
        ("ROL-APAC-TC", "APAC Certification & Marine", None, "APAC", "SG", "TIMECARDS", 3, "LIVE", date(2026, 6, 1), date(2026, 6, 1), 75),
        ("ROL-APAC-SCHED", "APAC Certification & Marine", "BU-SG-MAR-07", "APAC", "SG", "INSPECTOR_SCHED", 3, "PLANNED", date(2027, 2, 1), None, 35),

        ("ROL-LATAM-LOGIN", "Latin America Operations", None, "AMER", "BR", "CORE_LOGIN", 4, "LIVE", date(2026, 10, 1), date(2026, 10, 3), 30),
        ("ROL-LATAM-PROJ", "Latin America Operations", "BU-BR-FLD-09", "AMER", "BR", "PROJECTS", 4, "LIVE", date(2026, 10, 1), date(2026, 10, 5), 30),
        # Edge Case #10: LIVE instrumented rollout with ZERO observed activity!
        ("ROL-LATAM-EXP", "Latin America Operations", "BU-BR-FLD-09", "AMER", "BR", "EXPENSES", 4, "LIVE", date(2026, 10, 15), date(2026, 10, 15), 30),
        ("ROL-LATAM-TC", "Latin America Operations", None, "AMER", "BR", "TIMECARDS", 4, "ONBOARDING", date(2026, 12, 1), None, 30),
        ("ROL-LATAM-INV", "Latin America Operations", "BU-BR-FLD-09", "AMER", "BR", "INVOICING", 4, "PLANNED", date(2027, 3, 1), None, 30),
        ("ROL-LEGACY-RET", "North America Field Ops", "BU-US-FLD-01", "AMER", "US", "INVOICING", 1, "RETIRED", date(2025, 6, 1), date(2025, 6, 1), 0),
    ]
    df_rollout = pd.DataFrame([
        {
            "RolloutId": rid,
            "AdoptionEntity": ent,
            "BusinessUnit": bu,
            "RegionCode": rc,
            "CountryCode": cc,
            "ModuleCode": mod,
            "AdoptionWaveNumber": wv,
            "RolloutStatus": st,
            "PlannedGoLiveDate": pl,
            "ActualGoLiveDate": ac,
            "EligiblePopulation": ep,
            "StatusEffectiveDate": ac or pl,
            "MappingStatus": "SIMULATED_EXTENSION",
        }
        for (rid, ent, bu, rc, cc, mod, wv, st, pl, ac, ep) in rollout_specs
    ])

    # BU fallback governance table for silver.organization when local_org_enrichment has no match (BU-AU-REN-10)
    df_bu_wave_map = pd.DataFrame([
        {"BusinessUnit": code, "AdoptionEntity": ent, "AdoptionWaveNumber": wv}
        for (_id, code, *_mid, ent, wv) in BUSINESS_UNITS
    ])

    return {
        "business_unit": df_bu,
        "project": pd.DataFrame(proj_rows),
        "project_service": pd.DataFrame(svc_rows),
        "project_phase": pd.DataFrame(phase_rows),
        "project_task": pd.DataFrame(task_rows),
        "project_task_timeline_event": pd.DataFrame(tl_rows),
        "application": df_app,
        "application_log_type": df_log_type,
        "app_user": df_users,
        "application_log": pd.DataFrame(log_rows),
        "timecard_status": df_tc_status,
        "timecard": pd.DataFrame(tc_rows),
        "timecard_row": pd.DataFrame(tcrow_rows),
        "timecard_entry": pd.DataFrame(tcent_rows),
        "expense_report": pd.DataFrame(exp_rows),
        "expense_entry": pd.DataFrame(expent_rows),
        # Reference / Simulated Extension tables
        "local_org_enrichment": df_local_enrich,
        "bu_wave_governance": df_bu_wave_map,
        "application_mapping_seed": df_app_map,
        "module_catalog": df_modules,
        "rollout_registry": df_rollout,
    }
