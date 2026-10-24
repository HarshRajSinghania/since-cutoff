"""Pooled secondary analysis, old + new tasks (PROTOCOL_ADDENDUM section 8): one Opus 5.5 study per task set.

usage: python pooled_old_new.py <study dir> <study dir> [...] [--exclude ant01,mcp01] [--pairs C/A[,H/A,C/H]]
Task keys must be disjoint across the study dirs (each task is taken from exactly one study). Per stratum
(post-cutoff, controls) and pair:
  - pass rate: per-task pass proportions, mean difference (treat - ctrl) with a 95% task bootstrap CI (10,000, seed
    20261001) and the exact two-sided sign-flip over per-task differences; one-sided 95% lower bound for controls;
  - efficiency: geometric mean over tasks of median ratios (total tokens, list cost, turns, wall), task bootstrap CI
    (recompute_cost.ratio_ci).
Stale first edits: use stale_tests.py with the same dirs (its pooled_X2 averages per task; with disjoint tasks this is
the per-task difference over all tasks).
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from recompute_cost import load, metrics, ratio_ci  # noqa: E402
from stale_tests import signflip  # noqa: E402


def boot_mean(xs, resamples=10000, seed=20261001):
    rnd = random.Random(seed)
    bs = sorted(sum(rnd.choice(xs) for _ in xs) / len(xs) for _ in range(resamples))
    return bs[int(0.025 * resamples)], bs[int(0.975 * resamples) - 1], bs[int(0.05 * resamples)]


def main():
    args = sys.argv[1:]
    exclude, pairs = set(), ["C/A"]
    if "--exclude" in args:
        i = args.index("--exclude"); exclude = set(args[i + 1].split(",")); del args[i:i + 2]
    if "--pairs" in args:
        i = args.index("--pairs"); pairs = args[i + 1].split(","); del args[i:i + 2]
    per_task = defaultdict(lambda: defaultdict(list))
    strata, source = {}, {}
    for d in map(Path, args):
        for r in load(d):
            t = r["task"]
            if t in exclude:
                continue
            if t in source and source[t] != d.name:
                raise SystemExit(f"task {t} appears in {source[t]} and {d.name}; pass disjoint task sets")
            source[t] = d.name
            strata[t] = r["stratum"]
            per_task[t][r["condition"]].append(metrics(r, d))
    out = {"studies": sorted(set(source.values())), "excluded_tasks": sorted(exclude), "results": {}}
    for scope in ("post-cutoff", "controls"):
        sel = {t: cs for t, cs in per_task.items() if (strata[t] == "post-cutoff") == (scope == "post-cutoff")}
        res = out["results"].setdefault(scope, {"tasks": len(sel)})
        for pair in pairs:
            treat, ctrl = pair.split("/")
            rows = {t: cs for t, cs in sel.items() if cs.get(treat) and cs.get(ctrl)}
            if not rows:
                continue
            pt = {t: sum(m["passed"] for m in cs[treat]) / len(cs[treat]) for t, cs in rows.items()}
            pc = {t: sum(m["passed"] for m in cs[ctrl]) / len(cs[ctrl]) for t, cs in rows.items()}
            diffs = [pt[t] - pc[t] for t in rows]
            lo, hi, lo1 = boot_mean(diffs)
            p, k = signflip(diffs)
            n_t = sum(len(cs[treat]) for cs in rows.values()); n_c = sum(len(cs[ctrl]) for cs in rows.values())
            s_t = sum(m["passed"] for cs in rows.values() for m in cs[treat])
            s_c = sum(m["passed"] for cs in rows.values() for m in cs[ctrl])
            res[pair] = {
                "tasks": len(rows), f"{ctrl}_pass": f"{s_c}/{n_c}", f"{treat}_pass": f"{s_t}/{n_t}",
                f"{ctrl}_rate": s_c / n_c, f"{treat}_rate": s_t / n_t,
                "delta_mean_task": sum(diffs) / len(diffs), "delta_ci95": [lo, hi], "delta_one_sided_lower95": lo1,
                "signflip_p": p, "tasks_with_difference": k,
                "differing_tasks": {t: f"{ctrl} {pc[t]:.2f} / {treat} {pt[t]:.2f}" for t in sorted(rows) if pc[t] != pt[t]},
                "ratios": {m: ratio_ci(rows, treat, ctrl, m) for m in ("total_tokens", "list_cost_usd", "turns", "wall_s")},
            }
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
