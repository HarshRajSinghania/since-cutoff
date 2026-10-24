"""Round-6 checks (requested in an internal review): the header-only arm on cost and tokens.

usage: python -I round6_header.py <I1 dir>   ->   <I1>/analysis/round6_header.json
(in the supplementary archive: RUNS_TABLES=runs python scripts/round6_header.py .)

Existing run tables only; no new sessions. Estimator as in the paper: per task, log(median treat run / median ctrl run)
over the post-cutoff tasks; geometric mean over tasks; 95% percentile task bootstrap (10,000 resamples, seed 20261001);
exact two-sided sign-flip test over the per-task log ratios (as round3_stats.py). List cost at Opus 5.5 list prices
(recompute_cost.list_cost).

1. Per study, for the three Opus studies in which H ran in the same randomised batches as A and C (replication,
   new tasks, concurrent): H/A, C/A and C/H on cost and tokens, all tasks and without the pilot tasks.
2. Post hoc pool of all randomised H evidence (25 tasks): the 17 original tasks from the replication; each of the
   8 new tasks' log ratio averaged over the new-task and the concurrent study. Also the 8 new tasks alone (two studies
   averaged) and the 23 tasks without the pilot tasks.
3. Combined Opus C/A estimate (post hoc, as review_checks.py): each original task's log ratio averaged over the main
   study and the replication, plus the 8 new tasks of the new-task study.
4. Token types per post-cutoff session by arm (cache writes, cache reads, input, output) and their share of cost.
5. Session time windows (started_at, UTC) per study and arm.
6. Failed control-task runs by arm in every Claude study; failing test runs per session (main study).
7. Sonnet 5.5 passes per task and arm (where the pass-rate gains come from).
8. Covered-task C/H in the replication with and without ant01; per-task C/H on pl02 and st01 in both new-task studies.
9. Break-even share at the mean non-empty real block (1,306 tokens) and the replication's break-even at 764 tokens.
"""
import bisect
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from recompute_cost import list_cost, PRICES  # noqa: E402

PILOT = {"ant01", "mcp01"}
COVERED = {"ant01", "ant03", "hf01", "hf02", "hf03", "pl02", "st01"}
SEED, B = 20261001, 10000
STUDIES = {
    "main": "main-2026-09-28",
    "replication": "abl-opus55-2026-10-22",
    "new_tasks": "tasks2-opus55-2026-10-22",
    "concurrent": "conc-opus55-2026-10-23",
    "sonnet55": "gen-sonnet55-2026-10-21",
    "haiku55": "gen-haiku55-2026-10-21",
    "irrelevant_earlier": "irr-opus55-2026-10-22",
    "notes_v2": "iter-opus55-2026-10-22",
}


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


def summary(logs):
    v = list(logs.values()) if isinstance(logs, dict) else list(logs)
    rnd = random.Random(SEED)
    bs = sorted(math.exp(sum(rnd.choice(v) for _ in v) / len(v)) for _ in range(B))
    return {"ratio": round(math.exp(sum(v) / len(v)), 4), "lo": round(bs[int(0.025 * B)], 4),
            "hi": round(bs[int(0.975 * B) - 1], 4), "signflip_p": round(signflip(v), 5), "tasks": len(v),
            "below_1": sum(x < 0 for x in v)}


def load(rt, study):
    recs = [json.loads(l) for l in open(rt / study / "runs.jsonl", encoding="utf-8")]
    recs = [r for r in recs if r.get("valid") and not r.get("pilot")]
    seen, out = set(), []
    for r in sorted(recs, key=lambda r: (r["run_id"], r["attempt"])):
        if r["run_id"] not in seen:
            seen.add(r["run_id"])
            out.append(r)
    return out


def met(r):
    u = (r.get("result") or {}).get("usage") or {}
    model = r["agent"]["model"]
    p_in, p_out, p_cr, p_w1h, p_w5m = PRICES.get(model, PRICES["claude-opus-5-5"])
    cw = u.get("cache_creation_input_tokens", 0)
    return {"cost": list_cost(model, u) if model in PRICES else None,
            "tokens": sum(u.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                 "cache_creation_input_tokens")),
            "cache_write": cw, "cache_read": u.get("cache_read_input_tokens", 0),
            "input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
            "cost_cache_write": cw * p_w1h / 1e6, "cost_cache_read": u.get("cache_read_input_tokens", 0) * p_cr / 1e6,
            "passed": bool((r.get("grade") or {}).get("passed")),
            "failing_pytest_runs": (r.get("process") or {}).get("failing_pytest_runs"),
            "turns": (r.get("result") or {}).get("num_turns")}


def per_task(recs, post=True):
    pt = defaultdict(lambda: defaultdict(list))
    for r in recs:
        if (r["stratum"] == "post-cutoff") == post:
            pt[r["task"]][r["condition"]].append(met(r))
    return pt


def logs(pt, treat, ctrl, metric, exclude=()):
    out = {}
    for t, cs in pt.items():
        if t in exclude:
            continue
        a = [m[metric] for m in cs.get(treat, []) if m[metric]]
        b = [m[metric] for m in cs.get(ctrl, []) if m[metric]]
        if a and b:
            out[t] = math.log(statistics.median(a) / statistics.median(b))
    return out


def r4(x):
    return round(x, 4)


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    recs = {k: load(rt, v) for k, v in STUDIES.items()}
    pts = {k: per_task(v) for k, v in recs.items()}
    out = {"generated_by": "scripts/round6_header.py", "estimator": __doc__.strip().splitlines()[3:7]}

    # 1. per study
    ps = {}
    for s in ("replication", "new_tasks", "concurrent"):
        ps[s] = {}
        for pair in ("H/A", "C/A", "C/H"):
            t, c = pair.split("/")
            ps[s][pair] = {m: summary(logs(pts[s], t, c, m)) for m in ("cost", "tokens")}
            ps[s][pair + " w/o pilot"] = {m: summary(logs(pts[s], t, c, m, PILOT)) for m in ("cost", "tokens")}
        # share of C's log saving recovered by H
        ps[s]["header_share_of_log_saving"] = {
            m: r4(sum(logs(pts[s], "H", "A", m).values()) / sum(logs(pts[s], "C", "A", m).values()))
            for m in ("cost", "tokens")}
    out["per_study"] = ps

    # 2. post hoc pool of randomised H evidence
    def pooled(treat, ctrl, metric, exclude=()):
        orig = logs(pts["replication"], treat, ctrl, metric, exclude)
        n1 = logs(pts["new_tasks"], treat, ctrl, metric, exclude)
        n2 = logs(pts["concurrent"], treat, ctrl, metric, exclude)
        new = {t: (n1[t] + n2[t]) / 2 for t in n1 if t in n2}
        return orig, new
    pool = {}
    for pair in ("H/A", "C/A", "C/H"):
        t, c = pair.split("/")
        pool[pair] = {}
        for m in ("cost", "tokens"):
            o, n = pooled(t, c, m)
            pool[pair][m + ", 25 tasks"] = summary({**o, **n})
            pool[pair][m + ", 8 new tasks (two studies averaged)"] = summary(n)
            o, n = pooled(t, c, m, PILOT)
            pool[pair][m + ", 23 tasks w/o pilot"] = summary({**o, **n})
    out["pool_randomised_H_post_hoc"] = pool

    # 3. combined Opus C/A (post hoc)
    comb = {}
    for m in ("cost", "tokens"):
        lm = logs(pts["main"], "C", "A", m)
        lr = logs(pts["replication"], "C", "A", m)
        ln = logs(pts["new_tasks"], "C", "A", m)
        v = [(lm[t] + lr[t]) / 2 for t in sorted(set(lm) & set(lr))] + list(ln.values())
        comb[m] = summary(v)
        comb[m]["saving_pct"] = round(100 * (1 - comb[m]["ratio"]), 1)
        comb[m]["saving_ci_pct"] = [round(100 * (1 - comb[m]["hi"]), 1), round(100 * (1 - comb[m]["lo"]), 1)]
    out["combined_opus_C_over_A_post_hoc"] = comb

    # 4. token types per post-cutoff session
    tt = {}
    for s in ("main", "replication", "new_tasks", "concurrent"):
        tt[s] = {}
        by = defaultdict(list)
        for r in recs[s]:
            if r["stratum"] == "post-cutoff":
                by[r["condition"]].append(met(r))
        for c in sorted(by):
            if c not in "ACHRG":
                continue
            v = by[c]
            mean = lambda k: sum(m[k] for m in v) / len(v)  # noqa: E731
            cost = mean("cost")
            tt[s][c] = {"sessions": len(v), "cache_write_tokens": round(mean("cache_write")),
                        "cache_read_tokens": round(mean("cache_read")), "input_tokens": round(mean("input")),
                        "output_tokens": round(mean("output")), "cost_usd": round(cost, 4),
                        "cache_write_share_of_cost": r4(mean("cost_cache_write") / cost),
                        "cache_read_share_of_cost": r4(mean("cost_cache_read") / cost),
                        "cache_read_share_of_tokens": r4(mean("cache_read") / mean("tokens"))}
    out["token_types_per_post_cutoff_session"] = tt

    # 5. time windows
    tw = {}
    for s in ("replication", "new_tasks", "concurrent"):
        by = defaultdict(list)
        for r in recs[s]:
            by[r["condition"]].append(r["started_at"])
        tw[s] = {c: [min(v), max(v)] for c, v in sorted(by.items())}
    out["started_at_windows_utc"] = tw

    # 6. control failures and failing test runs
    cf = {}
    for s, rr in recs.items():
        fails = defaultdict(list)
        n = defaultdict(int)
        for r in rr:
            if r["stratum"] != "post-cutoff":
                n[r["condition"]] += 1
                if not met(r)["passed"]:
                    fails[r["condition"]].append(f'{r["task"]} rep {r["rep"]}')
        cf[s] = {"control_runs": dict(n), "failed": {c: v for c, v in fails.items()}}
    out["control_failures"] = cf
    post_fail = defaultdict(list)
    for s in ("main", "replication", "new_tasks", "concurrent"):
        for r in recs[s]:
            if r["stratum"] == "post-cutoff" and r["condition"] in "ACHRG":
                m = met(r)
                if not m["passed"] and r["task"] in {"mi01"}:
                    post_fail[s].append(f'{r["task"]} {r["condition"]} rep {r["rep"]}')
    out["mi01_failures"] = dict(post_fail)
    fr = {}
    pt = pts["main"]
    for c in "AC":
        v = [m["failing_pytest_runs"] for t in pt for m in pt[t].get(c, [])]
        meds = [statistics.median(m["failing_pytest_runs"] for m in pt[t][c]) for t in pt if pt[t].get(c)]
        fr[c] = {"mean_per_session": r4(sum(v) / len(v)), "sessions": len(v),
                 "tasks_with_nonzero_median": sum(x > 0 for x in meds)}
    out["failing_test_runs_main_post_cutoff"] = fr

    # 7. Sonnet 5.5 passes per task
    son = defaultdict(lambda: defaultdict(int))
    for r in recs["sonnet55"]:
        if r["stratum"] == "post-cutoff":
            son[r["task"]][r["condition"]] += met(r)["passed"]
    gains = {}
    for arm in "CH":
        gains[arm + "-A"] = {t: son[t][arm] - son[t]["A"] for t in sorted(son) if son[t][arm] != son[t]["A"]}
    out["sonnet55_passes"] = {"per_task": {t: dict(v) for t, v in sorted(son.items())}, "differences": gains,
                              "totals": {a: sum(son[t][a] for t in son) for a in "ACH"}}

    # 8. covered-task C/H
    cov = {}
    lr = logs(pts["replication"], "C", "H", "tokens")
    covl = {t: v for t, v in lr.items() if t in COVERED}
    cov["replication_covered_C/H_tokens"] = {"all": r4(math.exp(sum(covl.values()) / len(covl))),
                                             "w/o ant01": r4(math.exp(sum(v for t, v in covl.items() if t != "ant01")
                                                                      / (len(covl) - 1))),
                                             "per_task": {t: r4(math.exp(v)) for t, v in sorted(covl.items())}}
    for s in ("new_tasks", "concurrent"):
        l2 = logs(pts[s], "C", "H", "tokens")
        cov[s + "_C/H_tokens_pl02_st01"] = {t: r4(math.exp(l2[t])) for t in ("pl02", "st01")}
    out["covered_C_over_H"] = cov

    # 9. break-even
    be = json.load(open(i1 / "analysis" / "blocksize_breakeven.json", encoding="utf-8"))
    mean_block = be["block_sizes"]["imported"]["tokens_nonempty"]["mean"]
    bes = {"mean_nonempty_block_tokens": round(mean_block, 1)}
    for s in ("main", "replication", "new_tasks"):
        st = be["break_even"]["studies"][s]
        o = mean_block * (st["mean_C_turns"] * 0.20 + 8.0) / 1e6
        bes[s] = {"overhead_at_mean_block_usd": round(o, 5),
                  "break_even_share_at_mean_block": r4(o / st["S_gross_usd"]["value"]),
                  "break_even_share_at_764": r4(st["by_block_size"]["real_median_nonempty"]["break_even_share"]),
                  "break_even_share_at_764_ci95": [r4(x) for x in
                                                   st["by_block_size"]["real_median_nonempty"]["break_even_share_ci95"]]}
    bes["note"] = "1,000 sessions a day, a fifth touching a listed package, main study: overhead 1000 x O(764), " \
                  "gross saving 200 x S_gross, net = gross - overhead"
    st = be["break_even"]["studies"]["main"]
    o764 = st["by_block_size"]["real_median_nonempty"]["overhead_per_session_usd"]
    bes["fleet_example_main"] = {"overhead_usd_per_day": round(1000 * o764, 2),
                                 "gross_saving_usd_per_day": round(200 * st["S_gross_usd"]["value"], 2),
                                 "net_saving_usd_per_day": round(200 * st["S_gross_usd"]["value"] - 1000 * o764, 2)}
    out["break_even"] = bes

    # 10. H/A for the Table 1 cost column: Sonnet 5.5 (all tasks) and the replication without the anthropic tasks
    ant = {"ant01", "ant02", "ant03", "ant04", "ant05"}
    out["table1_H_over_A_extra"] = {
        "sonnet55": {m: summary(logs(pts["sonnet55"], "H", "A", m)) for m in ("cost", "tokens")},
        "replication_w/o_anthropic": {m: summary(logs(pts["replication"], "H", "A", m, ant)) for m in ("cost", "tokens")},
        "replication_w/o_anthropic_C/H": {m: summary(logs(pts["replication"], "C", "H", m, ant))
                                          for m in ("cost", "tokens")}}

    (i1 / "analysis" / "round6_header.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
