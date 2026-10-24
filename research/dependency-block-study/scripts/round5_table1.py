"""Round-5 Table 1 numbers from the de-identified per-run tables (no model sessions).

usage: python -I round5_table1.py <I1 dir>   ->   <I1>/analysis/round5_table1.json
(in the supplementary archive: RUNS_TABLES=runs python scripts/round5_table1.py .)

For each Table 1 study: A / C runs on post-cutoff (treatment) tasks, mean list cost per post-cutoff session for A and C,
C/A (and H/A where H ran) on total tokens and list cost with the paper's estimator (per task the ratio of median run
values, geometric mean over tasks), the exact two-sided sign-flip p over per-task log ratios (as round3_stats.py), and
the task-level standard deviation of the log C/A ratio, which sizes an A/B test:
n_tasks = ((z_0.975 + z_0.80) * SD / ln(1 / (1 - saving)))^2 (normal approximation of the one-sample test on log ratios).
Also: Figure 1 example (pl02 in the new-task study): runs, passes, median turns, tokens, list cost and package-source
reads per condition. Prices ($/MTok): as recompute_cost.py; Sonnet 4.5 as token_breakdown.py.
"""
import bisect
import json
import os
import math
import statistics
import sys
from pathlib import Path

PRICES = {  # input, output, cache read, 1h cache write, 5m cache write
    "claude-opus-5-5": (4.0, 20.0, 0.20, 8.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10, 4.0, 2.5),  # list price checked 2026-10-24 (was 0.20 before)
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.20, 0.125),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30, 6.0, 3.75),
}
PILOT = {"ant01", "mcp01"}
# Open-weight study: treatment set re-assigned for the April 2025 cutoff (addendum section 10).
QWEN_EXTRA = {"pd01", "pd02", "pd03", "lc01", "lc02", "st90"}


def signflip(vals):
    d = [x for x in vals if abs(x) > 1e-12]
    n = len(d)
    if n == 0:
        return 1.0
    obs = abs(sum(d)) - 1e-12

    def sums(x):
        s = [0.0]
        for v in x:
            s = [a + v for a in s] + [a - v for a in s]
        return s
    h = n // 2
    s1, s2 = sums(d[:h]), sorted(sums(d[h:]))
    hits = 0
    for a in s1:
        hits += len(s2) - bisect.bisect_left(s2, obs - a)
        hits += bisect.bisect_right(s2, -obs - a)
    return hits / 2 ** n


def load(paths):
    out, seen = [], set()
    for p in paths:
        recs = [json.loads(l) for l in open(p / "runs.jsonl", encoding="utf-8")]
        recs = [r for r in recs if r.get("valid") and not r.get("pilot")]
        for r in sorted(recs, key=lambda r: (r["run_id"], r["attempt"])):
            key = (p.name, r["run_id"])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


def metrics(r):
    if "process" in r and "total_tokens" in (r.get("process") or {}):  # open-weight record
        return {"tokens": r["process"]["total_tokens"], "cost": None,
                "passed": bool((r.get("grade") or {}).get("passed")), "turns": r["process"].get("turns"),
                "reads": None}
    u = (r.get("result") or {}).get("usage") or {}
    p_in, p_out, p_cr, p_w1h, p_w5m = PRICES[r["agent"]["model"]]
    cc = u.get("cache_creation") or {}
    w1h, w5m = cc.get("ephemeral_1h_input_tokens"), cc.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:
        w1h, w5m = u.get("cache_creation_input_tokens", 0), 0
    cost = (u.get("input_tokens", 0) * p_in + u.get("output_tokens", 0) * p_out
            + u.get("cache_read_input_tokens", 0) * p_cr + (w1h or 0) * p_w1h + (w5m or 0) * p_w5m) / 1e6
    tok = sum(u.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                    "cache_creation_input_tokens"))
    return {"tokens": tok, "cost": cost, "passed": bool((r.get("grade") or {}).get("passed")),
            "turns": (r.get("result") or {}).get("num_turns"),
            "reads": (r.get("process") or {}).get("site_packages_reads")}


def contrast(by, treat, ctrl, metric, exclude=()):
    logs = []
    for t, cs in sorted(by.items()):
        if t in exclude:
            continue
        a = [m[metric] for m in cs.get(treat, []) if m[metric]]
        b = [m[metric] for m in cs.get(ctrl, []) if m[metric]]
        if a and b:
            logs.append(math.log(statistics.median(a) / statistics.median(b)))
    if not logs:
        return None
    return {"ratio": round(math.exp(sum(logs) / len(logs)), 4), "signflip_p": signflip(logs), "tasks": len(logs),
            "sd_log_ratio": round(statistics.stdev(logs), 4) if len(logs) > 1 else None}


def study(paths, treatment):
    by, runs = {}, {}
    for r in load(paths):
        if not treatment(r):
            continue
        m = metrics(r)
        by.setdefault(r["task"], {}).setdefault(r["condition"], []).append(m)
        runs.setdefault(r["condition"], []).append(m)
    res = {"runs": {c: len(v) for c, v in sorted(runs.items())},
           "passed": {c: sum(m["passed"] for m in v) for c, v in sorted(runs.items())}}
    res["mean_list_cost_per_session"] = {c: (round(sum(m["cost"] for m in v) / len(v), 4)
                                             if v and v[0]["cost"] is not None else None)
                                         for c, v in sorted(runs.items())}
    for pair in ("C/A", "H/A"):
        t, c = pair.split("/")
        if t in runs and c in runs:
            res[pair] = {"tokens": contrast(by, t, c, "tokens")}
            if runs[t][0]["cost"] is not None:
                res[pair]["cost"] = contrast(by, t, c, "cost")
                res[pair]["cost_no_pilot"] = contrast(by, t, c, "cost", PILOT)
            res[pair]["tokens_no_pilot"] = contrast(by, t, c, "tokens", PILOT)
    return res


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    post = lambda r: r.get("stratum") == "post-cutoff"
    qwen_t = lambda r: r.get("stratum") == "post-cutoff" or r["task"] in QWEN_EXTRA
    only = lambda conds: (lambda r: post(r) and r["condition"] in conds)
    out = {"generated_by": "scripts/round5_table1.py", "estimator": "geometric mean over tasks of per-task "
           "median-run ratios; exact two-sided sign-flip over per-task log ratios", "studies": {}}
    S = out["studies"]
    S["main"] = study([rt / "main-2026-09-28"], only("AC"))
    S["replication"] = study([rt / "abl-opus55-2026-10-22"], only("ACH"))
    S["new_tasks"] = study([rt / "tasks2-opus55-2026-10-22"], only("ACH"))
    S["concurrent"] = study([rt / "conc-opus55-2026-10-23"], only("ACH"))
    S["sonnet55"] = study([rt / "gen-sonnet55-2026-10-21"], only("ACH"))
    S["haiku55"] = study([rt / "gen-haiku55-2026-10-21"], only("AC"))
    S["sonnet45"] = study([rt / "anchor-s45-main-2026-10-22", rt / "anchor-s45-tasks2-2026-10-22"], only("AC"))
    S["qwen3c_AC"] = study([rt / "openagent-qwen3c-main-2026-10-22", rt / "openagent-qwen3c-tasks2-2026-10-22"],
                           lambda r: qwen_t(r) and r["condition"] in "AC")
    S["qwen3c_orig17_ACH"] = study([rt / "openagent-qwen3c-main-2026-10-22", rt / "openagent-qwen3c-h-2026-10-23"],
                                   lambda r: post(r) and r["condition"] in "ACH")
    # A/B test sizing from the observed task-level SD of the log C/A cost ratio (80% power, two-sided 5%).
    z = 1.959964 + 0.841621
    sizing = {}
    for name in ("main", "replication", "new_tasks"):
        sd = S[name]["C/A"]["cost"]["sd_log_ratio"]
        sizing[name] = {"sd_log_cost_ratio": sd,
                        **{f"tasks_for_{int(s * 100)}pct_saving": round((z * sd / math.log(1 / (1 - s))) ** 2, 1)
                           for s in (0.15, 0.20)}}
    out["ab_test_sizing"] = sizing
    # Figure 1 example: pl02, new-task study.
    fig = {}
    for r in load([rt / "tasks2-opus55-2026-10-22"]):
        if r["task"] == "pl02":
            fig.setdefault(r["condition"], []).append(metrics(r))
    out["figure1_pl02"] = {c: {"runs": len(v), "passed": sum(m["passed"] for m in v),
                               "median_turns": statistics.median(m["turns"] for m in v),
                               "median_tokens": statistics.median(m["tokens"] for m in v),
                               "median_list_cost": round(statistics.median(m["cost"] for m in v), 4),
                               "median_site_packages_reads": statistics.median(m["reads"] for m in v)}
                           for c, v in sorted(fig.items())}
    (i1 / "analysis" / "round5_table1.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
