"""List-price cost and paired efficiency ratios (PROTOCOL_ADDENDUM section 2.5, G1, P1, P2).

usage: python recompute_cost.py <study results dir> [--exclude ant01,mcp01] [--pairs C/A,H/A,C/H]
Per run: list_cost_usd from the token usage in runs.jsonl at list prices (table below). Ratios: geometric mean over
post-cutoff tasks of (median treat / median ctrl), 95% percentile CI from a task bootstrap (10,000 resamples, seed
20261001), as in bench/stats.py. Also counts budget stops, compactions (compact_boundary events in stream.jsonl) and
first valid attempt per planned run.
"""
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# $ per MTok: input, output, cache read, 1h cache write, 5m cache write.
# Anthropic list prices, checked 2026-10-24 against https://platform.claude.com/docs/en/about-claude/pricing
# (cache reads are 0.05x input on Opus 5.5 and Sonnet 5.5, 0.1x on Haiku 5.5; Haiku 5.5 prices are the tier for
# prompts up to 100,000 tokens, and no logged Haiku request exceeded 68,124 prompt tokens).
# Before 2026-10-24 the Sonnet 5.5 cache-read price here was 0.20 (0.1x input); the list price is 0.10.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 8.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10, 4.0, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.20, 0.125),
}


def list_cost(model, usage):
    p_in, p_out, p_cr, p_w1h, p_w5m = PRICES[model]
    cc = usage.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens"); w5m = cc.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:
        w1h, w5m = usage.get("cache_creation_input_tokens", 0), 0
    return (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out +
            usage.get("cache_read_input_tokens", 0) * p_cr + (w1h or 0) * p_w1h + (w5m or 0) * p_w5m) / 1e6


def load(d: Path):
    recs = [json.loads(l) for l in open(d / "runs.jsonl", encoding="utf-8")]
    recs = [r for r in recs if r.get("valid") and not r.get("pilot")]
    seen, out = set(), []
    for r in sorted(recs, key=lambda r: (r["run_id"], r["attempt"])):
        if r["run_id"] in seen:
            continue
        seen.add(r["run_id"]); out.append(r)
    return out


def metrics(r, d: Path):
    res = r.get("result") or {}
    u = res.get("usage") or {}
    model = r["agent"]["model"]
    tot = sum(u.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                    "cache_creation_input_tokens"))
    compactions = 0
    sp = d / "runs" / r["attempt_id"] / "stream.jsonl"
    if sp.exists():
        compactions = sum(1 for line in open(sp, encoding="utf-8", errors="replace") if "compact_boundary" in line)
    return {"list_cost_usd": list_cost(model, u), "cli_cost_usd": res.get("total_cost_usd"), "total_tokens": tot,
            "output_tokens": u.get("output_tokens"), "turns": res.get("num_turns"), "wall_s": r.get("wall_s"),
            "compactions": compactions, "budget_stop": "budget" in str(res.get("subtype") or ""),
            "passed": bool((r.get("grade") or {}).get("passed"))}


def ratio_ci(per_task, treat, ctrl, metric, resamples=10000, seed=20261001):
    logs = []
    for t, cs in per_task.items():
        a = [m[metric] for m in cs.get(treat, []) if m[metric]]
        b = [m[metric] for m in cs.get(ctrl, []) if m[metric]]
        if a and b:
            logs.append(math.log(statistics.median(a) / statistics.median(b)))
    if not logs:
        return None
    rnd = random.Random(seed)
    bs = sorted(math.exp(sum(rnd.choice(logs) for _ in logs) / len(logs)) for _ in range(resamples))
    return {"ratio": math.exp(sum(logs) / len(logs)), "lo": bs[int(0.025 * resamples)],
            "hi": bs[int(0.975 * resamples) - 1], "tasks": len(logs)}


def main():
    args = sys.argv[1:]
    exclude, pairs = set(), ["C/A"]
    if "--exclude" in args:
        i = args.index("--exclude"); exclude = set(args[i + 1].split(",")); del args[i:i + 2]
    if "--pairs" in args:
        i = args.index("--pairs"); pairs = args[i + 1].split(","); del args[i:i + 2]
    d = Path(args[0])
    recs = load(d)
    per_task = defaultdict(lambda: defaultdict(list))
    strata = {}
    summary = defaultdict(lambda: defaultdict(float))
    for r in recs:
        m = metrics(r, d)
        strata[r["task"]] = r["stratum"]
        per_task[r["task"]][r["condition"]].append(m)
        s = summary[r["condition"]]
        s["runs"] += 1; s["passed"] += m["passed"]; s["list_cost_usd"] += m["list_cost_usd"]
        s["cli_cost_usd"] += m["cli_cost_usd"] or 0; s["compactions"] += m["compactions"]; s["budget_stops"] += m["budget_stop"]
    out = {"study": d.name, "excluded_tasks": sorted(exclude), "runs_analysed": len(recs),
           "totals_by_condition": summary, "ratios": {}}
    for scope in ("post-cutoff", "controls"):
        sel = {t: cs for t, cs in per_task.items() if t not in exclude and
               ((strata[t] == "post-cutoff") == (scope == "post-cutoff"))}
        for pair in pairs:
            treat, ctrl = pair.split("/")
            for metric in ("total_tokens", "list_cost_usd", "cli_cost_usd", "turns", "wall_s", "output_tokens"):
                out["ratios"].setdefault(scope, {}).setdefault(pair, {})[metric] = ratio_ci(sel, treat, ctrl, metric)
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
