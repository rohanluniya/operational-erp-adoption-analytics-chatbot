"""Run the 15-question CORE Pulse Golden Evaluation across rules and LiteLLM/Ollama models.

Saves 100% measured outputs to `results/eval/evaluation_summary.json` and `results/eval/eval_report.md`.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.graph import ask  # noqa: E402


def evaluate_model(model_name: str, items: list[dict]) -> dict:
    rows = []
    latencies = []
    status_ok = 0
    tool_ok = 0
    fact_ok = 0
    guardrail_ok = 0

    for item in items:
        t0 = time.time()
        ans, _ = ask(item["question"], user_id=item["persona"], model=model_name)
        dt = time.time() - t0
        latencies.append(dt)

        got_status = ans.status
        calls = ans.diagnostics.get("tool_calls") or []
        got_tool = calls[0]["name"] if calls else ""
        blob = ans.answer_markdown + " " + json.dumps(ans.table_records, default=str)

        st_match = got_status == item["expected_status"]
        tl_match = (got_tool == item["expected_tool"]) if item["expected_tool"] else (got_tool == "")
        fc_match = all(tok.lower() in blob.lower() for tok in item.get("must_contain", []))
        gr_match = bool(ans.diagnostics.get("guardrail", {}).get("ok", True))

        status_ok += int(st_match)
        tool_ok += int(tl_match)
        fact_ok += int(fc_match)
        guardrail_ok += int(gr_match)

        rows.append({
            "id": item["id"],
            "question": item["question"],
            "expected_status": item["expected_status"],
            "got_status": got_status,
            "expected_tool": item["expected_tool"],
            "got_tool": got_tool,
            "status_pass": st_match,
            "tool_pass": tl_match,
            "fact_pass": fc_match,
            "guardrail_pass": gr_match,
            "template_used": ans.diagnostics.get("guardrail", {}).get("template", True),
            "latency_s": round(dt, 3),
        })

    n = len(items)
    return {
        "model": model_name,
        "questions": n,
        "status_accuracy": f"{status_ok}/{n}",
        "tool_accuracy": f"{tool_ok}/{n}",
        "fact_accuracy": f"{fact_ok}/{n}",
        "guardrail_pass": f"{guardrail_ok}/{n}",
        "median_latency_s": round(statistics.median(latencies), 3),
        "p95_latency_s": round(sorted(latencies)[min(n - 1, int(0.95 * n))], 3),
        "details": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="rules,ollama/qwen2.5-coder:14b,ollama/gpt-oss:20b")
    args = ap.parse_args()

    spec = yaml.safe_load((ROOT / "tests" / "golden_questions.yaml").read_text(encoding="utf-8"))
    items = spec["questions"]
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    summaries = []
    for m in models:
        print(f"Evaluating model: {m} ({len(items)} questions) ...", flush=True)
        res = evaluate_model(m, items)
        summaries.append(res)
        print(
            f"  -> {m}: status={res['status_accuracy']} tool={res['tool_accuracy']} "
            f"fact={res['fact_accuracy']} median={res['median_latency_s']}s",
            flush=True,
        )

    out_dir = ROOT / "results" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evaluation_summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")

    md = [
        "# CORE Pulse — Golden Evaluation Report",
        "",
        "| Mode / Model | Questions | Status Match | Tool Match | Grounded Fact Match | Guardrail Pass | Median Latency (s) | P95 Latency (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        md.append(
            f"| `{s['model']}` | {s['questions']} | **{s['status_accuracy']}** | **{s['tool_accuracy']}** | "
            f"**{s['fact_accuracy']}** | **{s['guardrail_pass']}** | {s['median_latency_s']:.2f} | {s['p95_latency_s']:.2f} |"
        )
    (out_dir / "eval_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Saved evaluation results to {out_dir}")


if __name__ == "__main__":
    main()
