"""Round-7 checks: header share of the saving in every analysis, main study against replication per task, exact
control bounds, and turns and wall time with exact tests. Existing runs only.
usage: python -I round7_checks.py <I1 dir>   ->   <I1>/analysis/round7_checks.json
(in the supplementary archive: RUNS_TABLES=runs python scripts/round7_checks.py .)

Estimator as in round6_header.py: per task, log(median treat run / median ctrl run); geometric mean over tasks; 95%
percentile task bootstrap (10,000 resamples, seed 20261001); exact two-sided sign-flip test over per-task log ratios.

1. Header share of C's log saving in every analysis, including the post hoc 25-task pool of round6_header.json.
2. Main study against replication on the 17 shared post-cutoff tasks: per-task log C/A ratios (cost, tokens), Pearson
   and Spearman correlation, sign agreement, and the anthropic / non-anthropic split.
3. Control tasks: exact (Clopper-Pearson) one-sided 95% lower bounds on C's control pass rate, all controls and
   controls with a non-empty block, per Claude study and pooled; runs are treated as independent. Because A passed
   every control run, Delta(C-A) >= (C's lower bound - 1) is a conservative exact bound on the difference.
   Also C/A cost and tokens over the controls with a non-empty block (main + new tasks).
4. Turns and wall time C/A with exact sign-flip p (main study, replication, new tasks).
"""
import json
import math
import os
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from round6_header import STUDIES, load, per_task, logs, summary, met, r4  # noqa: E402

ANT = {"ant01", "ant02", "ant03", "ant04", "ant05"}


def pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sxy / (sx * sy)


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def cp_lower_one_sided(x, n, alpha=0.05):
    """Clopper-Pearson one-sided lower bound: smallest p with P(X >= x | p) >= alpha."""
    if x == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if 1 - binom_cdf(x - 1, n, mid) < alpha:
            lo = mid
        else:
            hi = mid
    return hi


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    recs = {k: load(rt, v) for k, v in STUDIES.items()}
    recs["sonnet45"] = load(rt, "anchor-s45-main-2026-10-22") + load(rt, "anchor-s45-tasks2-2026-10-22")
    pts = {k: per_task(v) for k, v in recs.items()}
    out = {"generated_by": "scripts/round7_checks.py", "estimator": __doc__.strip().splitlines()[5:8]}

    # 1. header share of C's log saving
    def share(h, c):
        return r4(math.log(h) / math.log(c))
    r6 = json.load(open(i1 / "analysis" / "round6_header.json", encoding="utf-8"))
    pool = r6["pool_randomised_H_post_hoc"]
    hs = {s: r6["per_study"][s]["header_share_of_log_saving"] for s in ("replication", "new_tasks", "concurrent")}
    r3 = json.load(open(i1 / "analysis" / "round3_stats.json", encoding="utf-8"))["header_share"]["pool repl+new"]
    hs["registered_pool_repl+new"] = {m: r4(r3[m]["share"]) for m in ("cost", "tokens")}
    hs["post_hoc_pool_25_tasks"] = {m: share(pool["H/A"][m + ", 25 tasks"]["ratio"], pool["C/A"][m + ", 25 tasks"]["ratio"])
                                    for m in ("cost", "tokens")}
    out["header_share_of_log_saving"] = hs

    # 2. main vs replication per task
    mr = {}
    for m in ("cost", "tokens"):
        lm = logs(pts["main"], "C", "A", m)
        lr = logs(pts["replication"], "C", "A", m)
        tasks = sorted(set(lm) & set(lr))
        x, y = [lm[t] for t in tasks], [lr[t] for t in tasks]
        mr[m] = {"tasks": len(tasks), "pearson_r_log_ratios": r4(pearson(x, y)),
                 "spearman_rho": r4(pearson(ranks(x), ranks(y))),
                 "same_sign": sum((a < 0) == (b < 0) for a, b in zip(x, y)),
                 "both_below_1": sum(a < 0 and b < 0 for a, b in zip(x, y)),
                 "per_task": {t: [r4(math.exp(lm[t])), r4(math.exp(lr[t]))] for t in tasks}}
        for name, keep in (("anthropic", lambda t: t in ANT), ("non_anthropic", lambda t: t not in ANT)):
            sub = [t for t in tasks if keep(t)]
            mr[m][name] = {"main": r4(math.exp(sum(lm[t] for t in sub) / len(sub))),
                           "replication": r4(math.exp(sum(lr[t] for t in sub) / len(sub))), "tasks": len(sub)}
    out["main_vs_replication_per_task_C/A"] = mr

    # 3. controls: exact bounds
    ctl = {}
    pooled = {"all": [0, 0], "non_empty": [0, 0]}
    for s in ("main", "new_tasks", "concurrent", "sonnet55", "haiku55"):
        runs = [r for r in recs[s] if r["stratum"] != "post-cutoff" and r["condition"] == "C"]
        a_runs = [r for r in recs[s] if r["stratum"] != "post-cutoff" and r["condition"] == "A"]
        ne = [r for r in runs if (r.get("condition_config") or {}).get("notes_tokens", 0) > 0]
        row = {}
        for name, rr in (("all", runs), ("non_empty", ne)):
            x, n = sum(met(r)["passed"] for r in rr), len(rr)
            pooled[name][0] += x
            pooled[name][1] += n
            lb = cp_lower_one_sided(x, n) if n else None
            row[name] = {"C_pass": f"{x}/{n}", "tasks": len({r["task"] for r in rr}),
                         "cp_lower_95_one_sided": r4(lb) if lb is not None else None,
                         "delta_lower_bound_points": round(100 * (lb - 1), 1) if lb is not None else None}
        row["A_pass"] = f"{sum(met(r)['passed'] for r in a_runs)}/{len(a_runs)}"
        ctl[s] = row
    for name in ("main+new_tasks", ):
        for sub in ("all", "non_empty"):
            x = sum(int(ctl[s][sub]["C_pass"].split("/")[0]) for s in ("main", "new_tasks"))
            n = sum(int(ctl[s][sub]["C_pass"].split("/")[1]) for s in ("main", "new_tasks"))
            lb = cp_lower_one_sided(x, n)
            ctl.setdefault(name, {})[sub] = {"C_pass": f"{x}/{n}", "cp_lower_95_one_sided": r4(lb),
                                             "delta_lower_bound_points": round(100 * (lb - 1), 1)}
    for sub, (x, n) in pooled.items():
        lb = cp_lower_one_sided(x, n)
        ctl.setdefault("all_five_claude_studies_with_controls", {})[sub] = {
            "C_pass": f"{x}/{n}", "cp_lower_95_one_sided": r4(lb), "delta_lower_bound_points": round(100 * (lb - 1), 1)}
    # C/A over non-empty-block controls, main + new tasks
    ptc = {s: per_task(recs[s], post=False) for s in ("main", "new_tasks")}
    nonempty = set()
    for s in ("main", "new_tasks"):
        for r in recs[s]:
            if r["stratum"] != "post-cutoff" and r["condition"] == "C" and \
                    (r.get("condition_config") or {}).get("notes_tokens", 0) > 0:
                nonempty.add(r["task"])
    ctl["non_empty_block_control_tasks"] = sorted(nonempty)
    for m in ("cost", "tokens"):
        v = {}
        for s in ("main", "new_tasks"):
            for t, x in logs(ptc[s], "C", "A", m).items():
                if t in nonempty:
                    v[t] = x
        ctl["C/A_non_empty_controls_main+new_" + m] = summary(v)
        allv = {}
        for s in ("main", "new_tasks"):
            allv.update(logs(ptc[s], "C", "A", m))
        ctl["C/A_all_controls_main+new_" + m] = summary(allv)
    out["controls_exact"] = ctl

    # 4. turns and wall time with sign-flip
    tw = {}
    for s in ("main", "replication", "new_tasks"):
        tw[s] = {}
        for m in ("turns", "wall"):
            v = {}
            for t in pts[s]:
                a = [r for r in recs[s] if r["task"] == t and r["condition"] == "A" and r["stratum"] == "post-cutoff"]
                c = [r for r in recs[s] if r["task"] == t and r["condition"] == "C" and r["stratum"] == "post-cutoff"]
                key = (lambda r: r["result"]["num_turns"]) if m == "turns" else (lambda r: r["wall_s"])
                v[t] = math.log(statistics.median(key(r) for r in c) / statistics.median(key(r) for r in a))
            tw[s][m] = summary(v)
    out["turns_wall_C/A"] = tw

    (i1 / "analysis" / "round7_checks.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
