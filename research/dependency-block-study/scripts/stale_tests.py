"""Stale-first-edit tests (PROTOCOL_ADDENDUM G4/X2 and section 6).

usage: python stale_tests.py <study results dir> [<more dirs> ...] [--exclude ant01,mcp01] [--pair C,A]
For each study: run-level counts + Fisher exact (two-sided, ignores clustering) and the task-level exact sign-flip
over per-task differences of stale rates (tasks where both arms made at least one first edit). With several study
dirs: pooled sign-flip over tasks of the per-task difference averaged across studies (X2).
"""
import csv
import itertools
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def load(d: Path):
    rows = [r for r in csv.DictReader(open(d / "runs.csv", encoding="utf-8"))
            if r["valid"] == "True" and r["pilot"] != "True" and r["stratum"] == "post-cutoff"]
    # first valid attempt of each planned run only
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: (r["run_id"], int(r["attempt"]))):
        if r["run_id"] in seen:
            continue
        seen.add(r["run_id"])
        out.append(r)
    return out


def fisher_two_sided(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    def p(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n1 + n2, k)
    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1) if p(x) <= p0 * (1 + 1e-9)))


def signflip(diffs):
    d = [x for x in diffs if abs(x) > 1e-12]
    if not d:
        return 1.0, 0
    obs = abs(sum(d))
    hits = sum(1 for signs in itertools.product((1, -1), repeat=len(d))
               if abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-12)
    return hits / 2 ** len(d), len(d)


def rates(rows, treat, ctrl, exclude):
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["task"] in exclude or r["stale_in_first_edit"] in ("", "None"):
            continue
        by[r["task"]][r["condition"]].append(r["stale_in_first_edit"] == "True")
    per = {}
    for t, cs in by.items():
        if cs.get(treat) and cs.get(ctrl):
            per[t] = (sum(cs[ctrl]) / len(cs[ctrl]), sum(cs[treat]) / len(cs[treat]),
                      sum(cs[ctrl]), len(cs[ctrl]), sum(cs[treat]), len(cs[treat]))
    return per


def main():
    args = sys.argv[1:]
    exclude = set()
    treat, ctrl = "C", "A"
    if "--exclude" in args:
        i = args.index("--exclude"); exclude = set(args[i + 1].split(",")); del args[i:i + 2]
    if "--pair" in args:
        i = args.index("--pair"); treat, ctrl = args[i + 1].split(","); del args[i:i + 2]
    out = {"pair": f"{treat} vs {ctrl}", "exclude": sorted(exclude), "studies": {}}
    pooled = defaultdict(list)
    for d in map(Path, args):
        per = rates(load(d), treat, ctrl, exclude)
        sc = sum(v[2] for v in per.values()); nc = sum(v[3] for v in per.values())
        st = sum(v[4] for v in per.values()); nt = sum(v[5] for v in per.values())
        diffs = [v[0] - v[1] for v in per.values()]
        p, k = signflip(diffs)
        favour = sum(1 for x in diffs if x > 0), sum(1 for x in diffs if x < 0)
        out["studies"][d.name] = {
            f"{ctrl}_stale": f"{sc}/{nc}", f"{treat}_stale": f"{st}/{nt}",
            f"{ctrl}_rate": sc / nc if nc else None, f"{treat}_rate": st / nt if nt else None,
            "fisher_p_run_level": fisher_two_sided(sc, nc - sc, st, nt - st) if nc and nt else None,
            "tasks_with_difference": k, f"tasks_favouring_{treat}": favour[0], f"tasks_favouring_{ctrl}": favour[1],
            "signflip_p_task_level": p,
            "per_task": {t: {ctrl: f"{v[2]}/{v[3]}", treat: f"{v[4]}/{v[5]}"} for t, v in sorted(per.items())
                         if v[2] or v[4]}}
        for t, v in per.items():
            pooled[t].append(v[0] - v[1])
    if len(args) > 1:
        diffs = [sum(v) / len(v) for v in pooled.values()]
        p, k = signflip(diffs)
        out["pooled_X2"] = {"tasks": len(diffs), "tasks_with_difference": k,
                            "mean_rate_difference": sum(diffs) / len(diffs) if diffs else None,
                            "signflip_p": p}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
