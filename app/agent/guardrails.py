"""Safety, prompt-injection, scope-boundary, and numeric/non-additivity guardrails for CORE Pulse."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.semantic.service import ToolPayload, semantic_catalog

INJECTION_PATTERNS = [
    (r"\bignore\s+(all\s+)?(previous|prior|system)\s+instructions\b",
     "Prompt-injection attempt blocked: system governance rules cannot be overridden."),
    (r"\b(drop\s+table|truncate\s+table|delete\s+from|insert\s+into|update\s+\w+\s+set|alter\s+table|xp_cmdshell)\b",
     "Arbitrary or mutating SQL is strictly blocked. CORE Pulse executes only read-only parameterized semantic tools."),
    (r"\bselect\b.{1,80}\bfrom\b\s+(source_sim|bronze|silver|gold|sys|information_schema|app_user)",
     "Direct raw SQL queries and raw user-row extraction are blocked. Ask a business question using CORE Pulse's governed KPIs."),
    (r"\b(openai_api_key|mssql_sa_password|mssql_app_password|app_access_code|secret|api[_\s-]?key|password|env\s+var|\.env)\b",
     "Credential and environment inspection requests are blocked by security policy."),
    (r"\b(bncdb|bvcoreprod|prod_sql|corporate\s+vpn|connect\s+to\s+prod)\b",
     "External/corporate database connectivity is disabled. CORE Pulse operates strictly on isolated synthetic pilot data."),
    (r"\b(export|dump|list|show)\s+(all\s+)?(raw\s+)?(employee\s+names|emails|app_user\s+rows|individual\s+employees)\b",
     "Employee-level PII/raw user table exfiltration is blocked. CORE Pulse reports governed aggregate adoption counts only."),
]

NAIVE_SUM_CLAIM_RE = re.compile(
    r"\b(sum\s+of\s+(all\s+)?waves\s+equals|adding\s+wave\s+1\s+and\s+wave\s+2\s+gives\s+total|total\s+unique\s+employees\s+is\s+the\s+sum)\b",
    re.IGNORECASE,
)

NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([+-]?\d{1,3}(?:,\d{3})+|[+-]?\d+(?:\.\d+)?)(?![A-Za-z0-9_])")


@dataclass
class GuardrailVerdict:
    ok: bool
    reason: str = ""
    used_template: bool = False


def check_prompt_safety(question: str) -> str | None:
    """Return a fail-closed refusal message if the prompt attempts injection, raw SQL, secret theft, or exfiltration."""
    q = (question or "").strip()
    for pat, msg in INJECTION_PATTERNS:
        if re.search(pat, q, flags=re.IGNORECASE | re.DOTALL):
            return msg
    return None


def check_out_of_scope(question: str) -> str | None:
    """Return a polite scope-boundary explanation if the question targets unbuilt Release 2–4 domains."""
    q = (question or "").strip().lower()
    # Allow explicit rollout/module status questions like "is lab testing live?"
    if any(w in q for w in ("rollout", "module", "which modules", "status", "instrumented")):
        return None
    for item in semantic_catalog().get("out_of_scope_topics", []):
        if re.search(item["pattern"], q, flags=re.IGNORECASE):
            return item["reason"]
    return None


def _allowed_numbers(payload: ToolPayload) -> set[str]:
    blob = " ".join([
        payload.headline,
        " ".join(payload.facts),
        " ".join(payload.warnings),
        payload.period_label,
    ])
    if payload.df is not None and not payload.df.empty:
        blob += " " + payload.df.to_string()
    allowed: set[str] = {"1", "2", "3", "4", "6", "12", "18", "30", "2025", "2026"}
    for m in NUMBER_TOKEN_RE.finditer(blob):
        raw = m.group(1).lstrip("+")
        allowed.add(raw.replace(",", ""))
        try:
            fval = float(raw.replace(",", ""))
            allowed.add(str(int(round(fval))))
            allowed.add(f"{fval:.1f}")
        except ValueError:
            pass
    return allowed


def verify_prose(prose: str, payload: ToolPayload) -> GuardrailVerdict:
    """Verify every number in LLM-generated prose is grounded in the structured ToolPayload and non-additivity holds."""
    if not prose or not prose.strip():
        return GuardrailVerdict(ok=False, reason="empty_llm_output", used_template=True)
    if payload.kpi_name == "Employees Logging In" and NAIVE_SUM_CLAIM_RE.search(prose):
        return GuardrailVerdict(ok=False, reason="non_additive_violation", used_template=True)

    allowed = _allowed_numbers(payload)
    # Strip ISO dates like 2026-11-17 or 2025-06 before scanning standalone numeric claims
    scrubbed = re.sub(r"\b202\d-\d{2}(?:-\d{2})?\b", " ", prose)
    scrubbed = re.sub(r"\bdays?\s+1[–-](\d{1,2})\b", " ", scrubbed, flags=re.IGNORECASE)
    scrubbed = re.sub(r"\bOct\s+1[–-](\d{1,2})\b", " ", scrubbed, flags=re.IGNORECASE)
    scrubbed = re.sub(r"\bNov\s+1[–-](\d{1,2})\b", " ", scrubbed, flags=re.IGNORECASE)
    scrubbed = re.sub(r"\bWave\s+[1-4]\b", " ", scrubbed, flags=re.IGNORECASE)

    bad = []
    for m in NUMBER_TOKEN_RE.finditer(scrubbed):
        tok = m.group(1).lstrip("+").replace(",", "")
        if tok not in allowed:
            bad.append(m.group(1))
    if bad:
        return GuardrailVerdict(ok=False, reason=f"ungrounded_numbers:{','.join(bad[:3])}", used_template=True)
    return GuardrailVerdict(ok=True, reason="verified", used_template=False)


def deterministic_prose(payload: ToolPayload) -> str:
    """Render clean, 100% deterministic markdown prose directly from ToolPayload."""
    lines = [payload.headline]
    if payload.facts:
        lines.append("")
        for f in payload.facts[:5]:
            lines.append(f"- {f}")
    for w in payload.warnings[:2]:
        lines.append(f"\n> **Governance note:** {w}")
    return "\n".join(lines).strip()
