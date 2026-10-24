"""Round-3 statistics (requested in an internal review): exact sign-flip p on per-task log ratios, cost per solved
task without the pilot tasks, summed cost ratios, header share of the saving, control-pass exact bound, block overhead.

usage: python round3_stats.py            -> writes <study>/analysis/round3_stats.json
env:   RUNS_TABLES (default <study>/runs_tables). Existing run tables only; no new sessions.

Estimators are the paper's: per task, median over runs of treat and ctrl, log(median treat / median ctrl); the exact
two-sided sign-flip test enumerates all 2^n sign assignments of the non-zero per-task log ratios (meet in the middle
for n > 20). Cost is list cost (recompute_cost.list_cost).
"""
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import bisect

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from recompute_cost import list_cost  # noqa: E402

RT = Path(os.environ.get("RUNS_TABLES", HERE.parent / "runs_tables"))
OUT = HERE.parent / "analysis" / "round3_stats.json"
PILOT = {"ant01", "mcp01"}
SEED, B = 20261001, 10000


def load(study):
    recs = [json.loads(l) for l in open(RT / study / "runs.jsonl", encoding="utf-8")]
    recs = [r for r in recs if r.get("valid") and not r.get("pilot")]
    seen, out = set(), []
    for r in sorted(recs, key=lambda r: (r["run_id"], r["attempt"])):
        if r["run_id"] not in seen:
            seen.add(r["run_id"]); out.append(r)
    return out


def per_task(study, stratum="post-cutoff", exclude=()):
    pt = defaultdict(lambda: defaultdict(list))
    for r in load(study):
        if r["task"] in exclude:
            continue
        if (r["stratum"] == "post-cutoff") != (stratum == "post-cutoff"):
            continue
        u = (r.get("result") or {}).get("usage") or {}
        tot = sum(u.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                        "cache_creation_input_tokens"))
        pt[r["task"]][r["condition"]].append({
            "cost": list_cost(r["agent"]["model"], u), "tokens": tot,
            "passed": bool((r.get("grade") or {}).get("passed"))})
    return pt


def logs(pt, treat, ctrl, metric):
    out = {}
    for t, cs in pt.items():
        a = [m[metric] for m in cs.get(treat, []) if m[metric]]
        b = [m[metric] for m in cs.get(ctrl, []) if m[metric]]
        if a and b:
            out[t] = math.log(statistics.median(a) / statistics.median(b))
    return out


def signflip(vals):
    d = [x for x in vals if abs(x) > 1e-12]
    n = len(d)
    if n == 0:
        return 1.0, 0
    obs = abs(sum(d)) - 1e-12

    def sums(x):
        s = [0.0]
        for v in x:
            s = [a + v for a in s] + [a - v for a in s]
        return s
    h = n // 2
    s1, s2 = sums(d[:h]), sorted(sums(d[h:]))
    hits = 0
    for a in s1:  # count b with a+b >= obs or a+b <= -obs
        hits += len(s2) - bisect.bisect_left(s2, obs - a)
        hits += bisect.bisect_right(s2, -obs - a)
    return hits / 2 ** n, n


def gm(lr):
    v = list(lr.values())
    return math.exp(sum(v) / len(v))


def merge(*pts):
    out = {}
    for p in pts:
        for t, cs in p.items():
            assert t not in out
            out[t] = cs
    return out


def cost_per_solved(pt, treat, ctrl):
    def cps(arm, tasks):
        c = sum(m["cost"] for t in tasks for m in pt[t].get(arm, []))
        s = sum(m["passed"] for t in tasks for m in pt[t].get(arm, []))
        return c / s
    tasks = [t for t in pt if pt[t].get(treat) and pt[t].get(ctrl)]
    rnd = random.Random(SEED)
    bs = []
    for _ in range(B):
        smp = [rnd.choice(tasks) for _ in tasks]
        try:
            bs.append(cps(treat, smp) / cps(ctrl, smp))
        except ZeroDivisionError:
            continue
    bs.sort()
    return {"treat": cps(treat, tasks), "ctrl": cps(ctrl, tasks), "ratio": cps(treat, tasks) / cps(ctrl, tasks),
            "lo": bs[int(0.025 * len(bs))], "hi": bs[int(0.975 * len(bs)) - 1], "tasks": len(tasks)}


def summed_ratio(pt, treat, ctrl):
    c = lambda arm: sum(m["cost"] for cs in pt.values() for m in cs.get(arm, []))  # noqa: E731
    return c(treat) / c(ctrl)


def test(pt, treat, ctrl):
    res = {}
    for metric in ("cost", "tokens"):
        lr = logs(pt, treat, ctrl, metric)
        p, n = signflip(lr.values())
        res[metric] = {"ratio": gm(lr), "signflip_p": p, "tasks": n, "below_1": sum(v < 0 for v in lr.values())}
    return res


def main():
    main_ = per_task("main-2026-09-28")
    repl = per_task("abl-opus55-2026-10-22")
    new = per_task("tasks2-opus55-2026-10-22")
    conc = per_task("conc-opus55-2026-10-23")
    son = per_task("gen-sonnet55-2026-10-21")
    hai = per_task("gen-haiku55-2026-10-21")
    out = {"note": "exact two-sided sign-flip on per-task log median ratios (post-cutoff tasks)", "signflip": {}}
    sf = out["signflip"]
    sf["main C/A"] = test(main_, "C", "A")
    sf["replication C/A"] = test(repl, "C", "A")
    sf["replication H/A"] = test(repl, "H", "A")
    sf["replication C/H"] = test(repl, "C", "H")
    sf["new C/A"] = test(new, "C", "A")
    sf["new H/A"] = test(new, "H", "A")
    sf["new C/H"] = test(new, "C", "H")
    for p in ("C/A", "H/A", "R/A", "G/A", "C/H"):
        sf["concurrent " + p] = test(conc, *p.split("/"))
    sf["pool main+new C/A"] = test(merge(main_, new), "C", "A")
    sf["pool repl+new C/A"] = test(merge(repl, new), "C", "A")
    sf["sonnet C/A"] = test(son, "C", "A")
    sf["haiku C/A"] = test(hai, "C", "A")
    # without pilot
    mx = {t: v for t, v in main_.items() if t not in PILOT}
    rx = {t: v for t, v in repl.items() if t not in PILOT}
    sf["main C/A w/o pilot"] = test(mx, "C", "A")
    sf["replication C/A w/o pilot"] = test(rx, "C", "A")
    conc_ctrl = per_task("conc-opus55-2026-10-23", stratum="controls")
    sf["concurrent controls G/A"] = test(conc_ctrl, "G", "A")

    cps = out["cost_per_solved"] = {}
    cps["main"] = cost_per_solved(main_, "C", "A")
    cps["main w/o pilot"] = cost_per_solved(mx, "C", "A")
    cps["replication"] = cost_per_solved(repl, "C", "A")
    cps["replication w/o pilot"] = cost_per_solved(rx, "C", "A")
    cps["sonnet"] = cost_per_solved(son, "C", "A")
    cps["sonnet w/o pilot"] = cost_per_solved({t: v for t, v in son.items() if t not in PILOT}, "C", "A")
    cps["sonnet H/A"] = cost_per_solved(son, "H", "A")

    out["summed_cost_ratio"] = {"main C/A": summed_ratio(main_, "C", "A"),
                                "replication C/A": summed_ratio(repl, "C", "A"),
                                "sonnet C/A": summed_ratio(son, "C", "A")}

    # header share of C's log saving: ln(H/A) / ln(C/A)
    hs = out["header_share"] = {}
    for name, pt in (("replication", repl), ("new", new), ("concurrent", conc),
                     ("pool repl+new", merge(repl, new))):
        hs[name] = {}
        for metric in ("cost", "tokens"):
            ca = gm(logs(pt, "C", "A", metric)); ha = gm(logs(pt, "H", "A", metric))
            hs[name][metric] = {"C/A": ca, "H/A": ha, "share": math.log(ha) / math.log(ca)}

    # coverage split (tasks whose change the frozen 0.4.1 notes named; recorded before the runs), total tokens
    cov_orig, cov_new = {"ant01", "ant03", "hf01", "hf02", "hf03"}, {"pl02", "st01"}
    cv = out["coverage_split_tokens"] = {}
    for name, pt, cov, pairs in (("main", main_, cov_orig, ("C/A",)), ("replication", repl, cov_orig, ("C/A", "C/H")),
                                 ("new", new, cov_new, ("C/A", "C/H")), ("concurrent", conc, cov_new, ("C/A", "C/H"))):
        for p in pairs:
            lr = logs(pt, *p.split("/"), "tokens")
            c = {t: v for t, v in lr.items() if t in cov}
            u = {t: v for t, v in lr.items() if t not in cov}
            cv[f"{name} {p}"] = {"covered": gm(c), "covered_tasks": len(c), "uncovered": gm(u),
                                 "uncovered_tasks": len(u)}

    # exact one-sided 95% Clopper-Pearson lower bound for 21/21 and 30/30 control passes
    out["control_pass_lower_bound_one_sided_95"] = {"21/21": 0.05 ** (1 / 21), "30/30": 0.05 ** (1 / 30)}

    # block overhead per C session in the main study: cache-read tokens of the block (notes_tokens x turns) at $0.20
    # per MTok plus one 1-hour cache write of the block at $8 per MTok
    recs = [r for r in load("main-2026-09-28") if r["condition"] == "C" and r["stratum"] == "post-cutoff"]
    nt = [r["condition_config"]["notes_tokens"] for r in recs]
    reads = [r["condition_config"]["notes_tokens"] * (r["result"]["num_turns"] or 0) for r in recs]
    out["block_overhead_main_C_postcutoff"] = {
        "mean_notes_tokens": statistics.mean(nt), "mean_read_tokens": statistics.mean(reads),
        "read_cost_usd": statistics.mean(reads) * 0.20 / 1e6,
        "one_write_cost_usd": statistics.mean(nt) * 8.0 / 1e6,
        "total_usd": statistics.mean(reads) * 0.20 / 1e6 + statistics.mean(nt) * 8.0 / 1e6}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
