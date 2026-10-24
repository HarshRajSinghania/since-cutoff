"""Round-15 numbers (requested in internal reviews of a draft): coverage split and Header-vs-Notes equivalence.
All analyses here are POST HOC and EXPLORATORY; none was pre-committed. No model sessions.

usage: python -I round15_coverage.py <study dir>   ->   <study>/analysis/round15_coverage.json
(in the published data folder: RUNS_TABLES=runs python scripts/round15_coverage.py data)
Inputs: run tables of the Opus 5.5 main study, replication, new-task study and concurrent five-arm study.

Estimator as in the paper (round3_stats.py, round6_header.py): per task, log(median treat run / median ctrl run) over
post-cutoff tasks, first valid attempt per planned run, pilot runs dropped; ratios are geometric means over tasks
("median-based"). List cost at Opus 5.5 list prices (recompute_cost.list_cost); tokens = input + output + cache read +
cache write.

Covered = the frozen 0.4.1 block named the task's change (recorded before the runs; checked here against
condition_config.notes_covered of the C runs): ant01, ant03, hf01, hf02, hf03 (original) and pl02, st01 (new).

1. Coverage split. For C/H (Notes/Header), C/A (Notes/None) and H/A (Header/None), on cost and tokens: geometric mean
   on covered and on uncovered tasks, each with a within-group task bootstrap 95% CI and an exact two-sided sign-flip p.
   Interaction = covered GM / uncovered GM (a ratio of ratios, i.e. the difference in mean log ratio): stratified task
   bootstrap 95% CI (resampling within each group) and an exact two-sided permutation p over all assignments of the
   coverage labels to tasks (|difference in mean log ratio| >= observed).
   Units: each study alone (replication, new tasks, concurrent; the main study for C/A only, as it had no H arm) and the
   post hoc 25-task pool of all randomised H evidence (round6_header.py: the 17 original tasks from the replication,
   each new task's log ratio averaged over the new-task and concurrent studies). Also a 25-task C/A pool that adds the
   main study (each original task averaged over main and replication). Subsets: all tasks, without ant01 (the tool was
   changed after ant01's pilot runs), and without both pilot tasks (ant01, mcp01).
2. Equivalence (TOST) of Notes against Header, C/H on cost and tokens, margin +-10% (equivalent iff the ratio lies in
   [0.90, 1.10]; the log-symmetric margin [1/1.1, 1.1] is reported too). Primary: task-cluster bootstrap (10,000,
   seed 20261001), equivalence at 5% iff the 90% percentile interval lies inside the margin; one-sided bootstrap p for
   each bound = share of draws beyond it, TOST p = the larger. Secondary: exact one-sided sign-flip tests of the log
   ratios shifted by each bound, TOST p = the larger. Per study and in both 25-task pools (post hoc pool as above;
   pre-committed replication + new pool), all tasks and without the pilot tasks. Also the smallest symmetric margin
   that the 90% interval would establish.
3. Round 16 additions (requested in an internal review; post hoc, exploratory):
   a. +-15% margin [0.85, 1/0.85], the equivalence margin that addendum section 14 pre-committed for the related H/L
      contrast, added to every TOST result of item 2 (same bootstrap draws and sign-flip tests).
   b. mcp01 sensitivity: Table 4 of the paper says the block covered mcp01's change "partly"; the coverage split of
      the 25-task pool (C/H, C/A, H/A; tokens and cost) repeated with mcp01 counted as covered (8 covered tasks).
   c. Leave-one-out over the covered tasks: the pool's C/H interaction (tokens and cost) with each covered task
      dropped in turn.
   d. Per-task C/H (tokens and cost) on the covered tasks in each study with an H arm (replication, new tasks,
      concurrent), to show where per-task directions differ between studies.
"""
import bisect
import itertools
import json
import math
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from round6_header import load, logs, per_task, signflip  # noqa: E402

SEED, B = 20261001, 10000
PILOT = {"ant01", "mcp01"}
COVERED = {"ant01", "ant03", "hf01", "hf02", "hf03", "pl02", "st01"}
STUDIES = {"main": "main-2026-09-28", "replication": "abl-opus55-2026-10-22",
           "new_tasks": "tasks2-opus55-2026-10-22", "concurrent": "conc-opus55-2026-10-23"}
MARGIN = (0.90, 1.10)
MARGIN_LOGSYM = (1 / 1.10, 1.10)
MARGIN_SEC14 = (0.85, 1 / 0.85)  # round 16: the margin pre-committed in addendum section 14 for H/L


def r4(x):
    return None if x is None else round(x, 4)


def gm(v):
    return math.exp(sum(v) / len(v)) if v else None


def pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    f = math.floor(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def boot_gm(v, seed=SEED):
    rnd = random.Random(seed)
    return [math.exp(sum(rnd.choice(v) for _ in v) / len(v)) for _ in range(B)]


def group(v):
    if not v:
        return {"tasks": 0}
    bs = boot_gm(v)
    return {"ratio": r4(gm(v)), "ci95": [r4(pct(bs, 0.025)), r4(pct(bs, 0.975))],
            "signflip_p": r4(signflip(v)), "tasks": len(v), "below_1": sum(x < 0 for x in v)}


def perm_p(cov, unc):
    """Exact two-sided permutation p of the difference in mean log ratio over all label assignments."""
    allv = cov + unc
    n, k = len(allv), len(cov)
    tot = sum(allv)
    obs = abs(sum(cov) / k - sum(unc) / (n - k)) - 1e-12
    hits = cnt = 0
    for idx in itertools.combinations(range(n), k):
        s = sum(allv[i] for i in idx)
        d = s / k - (tot - s) / (n - k)
        cnt += 1
        hits += abs(d) >= obs
    return hits / cnt, cnt


def split(lr, exclude=(), covered=None):
    covered = COVERED if covered is None else covered
    lr = {t: v for t, v in lr.items() if t not in exclude}
    cov = [v for t, v in sorted(lr.items()) if t in covered]
    unc = [v for t, v in sorted(lr.items()) if t not in covered]
    out = {"covered": group(cov), "uncovered": group(unc),
           "covered_tasks": sorted(t for t in lr if t in covered)}
    if cov and unc:
        rnd = random.Random(SEED)
        bs = []
        for _ in range(B):
            c = [rnd.choice(cov) for _ in cov]
            u = [rnd.choice(unc) for _ in unc]
            bs.append(math.exp(sum(c) / len(c) - sum(u) / len(u)))
        p, n_assign = perm_p(cov, unc)
        out["interaction_covered_over_uncovered"] = {
            "ratio": r4(gm(cov) / gm(unc)), "ci95_stratified_bootstrap": [r4(pct(bs, 0.025)), r4(pct(bs, 0.975))],
            "permutation_p_exact_two_sided": r4(p), "label_assignments": n_assign}
    return out


def tost(v, seed=SEED):
    bs = boot_gm(v, seed)
    lo90, hi90 = pct(bs, 0.05), pct(bs, 0.95)
    res = {"ratio": r4(gm(v)), "tasks": len(v), "ci90": [r4(lo90), r4(hi90)],
           "ci95": [r4(pct(bs, 0.025)), r4(pct(bs, 0.975))], "signflip_p_two_sided": r4(signflip(v))}
    for name, (a, b) in (("margin_0.90_1.10", MARGIN), ("margin_logsym_0.909_1.10", MARGIN_LOGSYM),
                         ("margin_0.85_1.176_section14", MARGIN_SEC14)):
        p_lo = sum(x <= a for x in bs) / B
        p_hi = sum(x >= b for x in bs) / B
        sf_lo = signflip_one_sided([x - math.log(a) for x in v], "greater")
        sf_hi = signflip_one_sided([x - math.log(b) for x in v], "less")
        res[name] = {"bootstrap_p_lower": r4(p_lo), "bootstrap_p_upper": r4(p_hi),
                     "bootstrap_tost_p": r4(max(p_lo, p_hi)),
                     "equivalent_at_5pct_bootstrap": bool(a < lo90 and hi90 < b),
                     "signflip_p_lower": r4(sf_lo), "signflip_p_upper": r4(sf_hi),
                     "signflip_tost_p": r4(max(sf_lo, sf_hi))}
    # smallest symmetric (in percent) margin m with 1-m < lo90 and hi90 < 1+m
    res["smallest_margin_established_pct"] = round(100 * max(1 - lo90, hi90 - 1), 1)
    return res


def signflip_one_sided(vals, alternative):
    """Exact one-sided sign-flip p for H0 symmetric about 0 against mean > 0 ('greater') or < 0 ('less')."""
    d = [x for x in vals if abs(x) > 1e-12]
    n = len(d)
    obs = sum(d)

    def sums(x):
        s = [0.0]
        for v in x:
            s = [a + v for a in s] + [a - v for a in s]
        return s
    h = n // 2
    s1, s2 = sums(d[:h]), sorted(sums(d[h:]))
    hits = 0
    for a in s1:
        if alternative == "greater":
            hits += len(s2) - bisect.bisect_left(s2, obs - a - 1e-12)
        else:
            hits += bisect.bisect_right(s2, obs - a + 1e-12)
    return hits / 2 ** n


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    recs = {k: load(rt, v) for k, v in STUDIES.items()}
    pts = {k: per_task(v) for k, v in recs.items()}
    out = {"generated_by": "scripts/round15_coverage.py", "label": "post hoc, exploratory (not pre-committed)",
           "method": __doc__.split("usage:")[0].strip() + "\n" + __doc__.split("condition_config")[0].split(
               "Estimator")[1].strip()}

    # coverage check against the logged flag
    flag = {}
    for s in ("main", "replication", "new_tasks", "concurrent"):
        for r in recs[s]:
            if r["condition"] == "C" and r["stratum"] == "post-cutoff":
                flag.setdefault(r["task"], set()).add(bool((r.get("condition_config") or {}).get("notes_covered")))
    logged = {t for t, v in flag.items() if True in v}
    out["coverage_check"] = {"covered_set": sorted(COVERED), "logged_notes_covered_true": sorted(logged),
                             "agree": logged == COVERED, "post_cutoff_tasks": len(flag)}

    subsets = {"all": (), "without_ant01": ("ant01",), "without_pilot_tasks": tuple(sorted(PILOT))}

    def pool(pair, metric):
        t, c = pair.split("/")
        orig = logs(pts["replication"], t, c, metric)
        n1, n2 = logs(pts["new_tasks"], t, c, metric), logs(pts["concurrent"], t, c, metric)
        return {**orig, **{k: (n1[k] + n2[k]) / 2 for k in n1 if k in n2}}

    def pool_ca_with_main(metric):
        lm, lr = logs(pts["main"], "C", "A", metric), logs(pts["replication"], "C", "A", metric)
        n1, n2 = logs(pts["new_tasks"], "C", "A", metric), logs(pts["concurrent"], "C", "A", metric)
        orig = {k: (lm[k] + lr[k]) / 2 for k in lm if k in lr}
        return {**orig, **{k: (n1[k] + n2[k]) / 2 for k in n1 if k in n2}}

    cs = out["coverage_split"] = {}
    for unit in ("replication", "new_tasks", "concurrent", "pool_25_randomised_H_post_hoc", "main",
                 "pool_25_C/A_with_main"):
        cs[unit] = {}
        pairs = ("C/A",) if unit in ("main", "pool_25_C/A_with_main") else ("C/H", "C/A", "H/A")
        for pair in pairs:
            for metric in ("tokens", "cost"):
                if unit == "pool_25_randomised_H_post_hoc":
                    lr = pool(pair, metric)
                elif unit == "pool_25_C/A_with_main":
                    lr = pool_ca_with_main(metric)
                else:
                    lr = logs(pts[unit], *pair.split("/"), metric)
                for sub, ex in subsets.items():
                    if unit in ("new_tasks", "concurrent") and sub != "all":
                        continue  # the pilot tasks are original tasks
                    cs[unit][f"{pair} {metric} {sub}"] = split(lr, ex)

    # difference between the C/H and H/A interactions is implied; report the per-task C/H on covered tasks
    pt_cov = {}
    for metric in ("tokens", "cost"):
        lr = pool("C/H", metric)
        pt_cov[metric] = {t: r4(math.exp(v)) for t, v in sorted(lr.items()) if t in COVERED}
    out["pool_25_per_task_C/H_covered"] = pt_cov

    # equivalence
    eq = out["equivalence_C_over_H"] = {}
    for unit in ("replication", "new_tasks", "concurrent", "pool_25_randomised_H_post_hoc",
                 "pool_25_replication_plus_new_precommitted"):
        eq[unit] = {}
        for metric in ("cost", "tokens"):
            if unit == "pool_25_randomised_H_post_hoc":
                lr = pool("C/H", metric)
            elif unit == "pool_25_replication_plus_new_precommitted":
                lr = {**logs(pts["replication"], "C", "H", metric), **logs(pts["new_tasks"], "C", "H", metric)}
            else:
                lr = logs(pts[unit], "C", "H", metric)
            eq[unit][metric] = tost(list(lr.values()))
            if unit in ("replication", "pool_25_randomised_H_post_hoc", "pool_25_replication_plus_new_precommitted"):
                eq[unit][metric + " without_pilot_tasks"] = tost([v for t, v in lr.items() if t not in PILOT])

    # round 16 (post hoc): mcp01 counted as covered; leave-one-out over covered tasks; per-study per-task C/H
    r16 = out["round16"] = {"label": "post hoc, exploratory (round 16 additions; not pre-committed)"}
    cov_mcp = COVERED | {"mcp01"}
    r16["mcp01_as_covered_pool_25"] = {
        f"{pair} {metric}": split(pool(pair, metric), covered=cov_mcp)
        for pair in ("C/H", "C/A", "H/A") for metric in ("tokens", "cost")}
    loo = r16["leave_one_covered_task_out_pool_25_C/H"] = {}
    for metric in ("tokens", "cost"):
        lr = pool("C/H", metric)
        loo[metric] = {}
        for t in sorted(COVERED):
            it = split(lr, (t,))["interaction_covered_over_uncovered"]
            loo[metric][f"without_{t}"] = it
        others = [v["permutation_p_exact_two_sided"] for k, v in loo[metric].items() if k != "without_ant01"]
        loo[metric]["p_range_without_any_task_but_ant01"] = [min(others), max(others)]
    per_study = r16["per_task_C/H_covered_by_study"] = {}
    for s in ("replication", "new_tasks", "concurrent"):
        per_study[s] = {}
        for metric in ("tokens", "cost"):
            lr = logs(pts[s], "C", "H", metric)
            per_study[s][metric] = {t: r4(math.exp(v)) for t, v in sorted(lr.items()) if t in COVERED}

    p = i1 / "analysis" / "round15_coverage.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for unit, d in cs.items():
        for k, v in d.items():
            it = v.get("interaction_covered_over_uncovered", {})
            print(f"{unit:32s} {k:32s} cov {v['covered'].get('ratio')} ({v['covered']['tasks']}) "
                  f"unc {v['uncovered'].get('ratio')} ({v['uncovered']['tasks']}) "
                  f"int {it.get('ratio')} {it.get('ci95_stratified_bootstrap')} p {it.get('permutation_p_exact_two_sided')}")
    for unit, d in eq.items():
        for k, v in d.items():
            m = v["margin_0.90_1.10"]
            print(f"TOST {unit:42s} {k:28s} {v['ratio']} 90%{v['ci90']} 95%{v['ci95']} bootTOST p {m['bootstrap_tost_p']}"
                  f" sf2 {v['signflip_p_two_sided']} sfTOST p {m['signflip_tost_p']} equiv {m['equivalent_at_5pct_bootstrap']}"
                  f" min margin {v['smallest_margin_established_pct']}%")
    for unit, d in eq.items():
        for k, v in d.items():
            m = v["margin_0.85_1.176_section14"]
            print(f"TOST15 {unit:42s} {k:28s} bootTOST p {m['bootstrap_tost_p']} sfTOST p {m['signflip_tost_p']}"
                  f" equiv {m['equivalent_at_5pct_bootstrap']}")
    for k, v in r16["mcp01_as_covered_pool_25"].items():
        it = v["interaction_covered_over_uncovered"]
        print(f"mcp01 covered  {k:12s} cov {v['covered']['ratio']} unc {v['uncovered']['ratio']} int {it['ratio']}"
              f" {it['ci95_stratified_bootstrap']} p {it['permutation_p_exact_two_sided']}")
    for metric, d in loo.items():
        for k, v in d.items():
            print(f"LOO {metric:6s} {k:36s} {v}")
    print("per-study covered C/H", json.dumps(per_study))
    print("coverage check", out["coverage_check"])
    print("wrote", p)


if __name__ == "__main__":
    main()
