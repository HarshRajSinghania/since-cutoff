"""Workstream B analysis (PROTOCOL_ADDENDUM section 10): Qwen3-Coder in mini-swe-agent, conditions A vs C.

usage: python openagent_analyze.py <study dir> [<study dir> ...] [--exclude k1,k2] [--reps 1,2,3] [--out file.json]
       [--pairs C/A,H/A,C/H] [--only-tasks k1,k2]   (section 10a: H study dir added, 17 original tasks)
Reads <study>/runs/*/record.json (schema since-cutoff-bench/openagent-run@1). Task strata are re-assigned for the
model's cutoff (2025-04) as pre-registered in section 10: treatment = every task whose change postdates 2025-04;
controls = pl90, pl91 (polars 1.0.0, 2024-07); other = oai04 (no-change verified only from openai 2.44.0) and oai05
(pinned-behind at 2.44.0, itself post-cutoff for this model), reported descriptively.
Per scope: pass rate (per-task proportions; mean C-A difference, 95% task bootstrap CI, exact two-sided sign-flip by
dynamic programming over per-task differences), McNemar on task majorities, C/A ratios (geometric mean of per-task
medians; task bootstrap) for total tokens, turns, wall time; stale first edit (per-task rates, sign-flip; Fisher at
run level). Floor rule: if both A and C treatment pass rates < 10%, the pass-rate test is reported but not interpreted.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

CONTROLS = {"pl90", "pl91"}
OTHER = {"oai04", "oai05"}
TREAT_EXTRA = {"pd01", "pd02", "pd03", "lc01", "lc02", "st90"}  # Opus-era controls; changes after 2025-04
SEED, B = 20261001, 10000


def scope_of(task: str, stratum: str) -> str:
    if task in CONTROLS:
        return "controls"
    if task in OTHER:
        return "other"
    if stratum == "post-cutoff" or task in TREAT_EXTRA:
        return "treatment"
    raise ValueError(f"unclassified task {task} ({stratum})")


def load(dirs, exclude, reps):
    recs = []
    for d in dirs:
        for p in sorted(Path(d).glob("runs/*/record.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("dry_run") or r["task"] in exclude or (reps and int(r["rep"]) not in reps):
                continue
            recs.append(r)
    return recs


def metrics(r):
    pr = r.get("process") or {}
    fe = pr.get("first_edit")
    return {"passed": bool((r.get("grade") or {}).get("passed")), "total_tokens": pr.get("total_tokens") or 0,
            "turns": pr.get("turns") or 0, "wall_s": r.get("wall_s") or 0.0,
            "stale_first": None if not fe else bool(fe.get("stale")), "stale_final": bool(pr.get("stale_in_final")),
            "exit": (r.get("exit") or {}).get("status")}


def signflip_exact(diffs):
    """Exact two-sided sign-flip p over per-task differences (rational values; DP over attainable sums)."""
    d = [Fraction(x).limit_denominator(1000) for x in diffs if abs(x) > 1e-12]
    if not d:
        return 1.0, 0
    obs = abs(sum(d))
    dist = {Fraction(0): 1}
    for x in d:
        nd = defaultdict(int)
        for s, c in dist.items():
            nd[s + x] += c
            nd[s - x] += c
        dist = nd
    hits = sum(c for s, c in dist.items() if abs(s) >= obs)
    return hits / 2 ** len(d), len(d)


def boot_mean(xs):
    rnd = random.Random(SEED)
    bs = sorted(sum(rnd.choice(xs) for _ in xs) / len(xs) for _ in range(B))
    return bs[int(0.025 * B)], bs[int(0.975 * B) - 1], bs[int(0.05 * B)]


def ratio_ci(rows, metric):
    logs = []
    for cs in rows.values():
        a = [m[metric] for m in cs["C"] if m[metric]]
        b = [m[metric] for m in cs["A"] if m[metric]]
        if a and b:
            logs.append(math.log(statistics.median(a) / statistics.median(b)))
    if not logs:
        return None
    rnd = random.Random(SEED)
    bs = sorted(math.exp(sum(rnd.choice(logs) for _ in logs) / len(logs)) for _ in range(B))
    return {"ratio": math.exp(sum(logs) / len(logs)), "lo": bs[int(0.025 * B)], "hi": bs[int(0.975 * B) - 1],
            "tasks": len(logs)}


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def fisher_two_sided(a, b, c, d):
    """2x2 [[a,b],[c,d]]; exact two-sided (sum of tables no more likely than observed)."""
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d

    def pr(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)
    p0 = pr(a)
    return min(1.0, sum(pr(x) for x in range(max(0, c1 - r2), min(r1, c1) + 1) if pr(x) <= p0 * (1 + 1e-9)))


def analyse_scope(rows, T="C", K="A"):
    rows = {t: {"C": cs[T], "A": cs[K]} for t, cs in rows.items()}  # C = treatment, A = comparison below
    out = {"tasks": len(rows)}
    pa = {t: sum(m["passed"] for m in cs["A"]) / len(cs["A"]) for t, cs in rows.items()}
    pc = {t: sum(m["passed"] for m in cs["C"]) / len(cs["C"]) for t, cs in rows.items()}
    nA = sum(len(cs["A"]) for cs in rows.values()); nC = sum(len(cs["C"]) for cs in rows.values())
    sA = sum(m["passed"] for cs in rows.values() for m in cs["A"])
    sC = sum(m["passed"] for cs in rows.values() for m in cs["C"])
    diffs = [pc[t] - pa[t] for t in rows]
    lo, hi, lo1 = boot_mean(diffs) if diffs else (None, None, None)
    p, k = signflip_exact(diffs)
    maj = lambda cs, c: sum(m["passed"] for m in cs[c]) * 2 > len(cs[c])  # noqa: E731
    b = sum(1 for cs in rows.values() if maj(cs, "C") and not maj(cs, "A"))
    c = sum(1 for cs in rows.values() if maj(cs, "A") and not maj(cs, "C"))
    out["pass"] = {"A": f"{sA}/{nA}", "C": f"{sC}/{nC}", "A_rate": sA / nA if nA else None,
                   "C_rate": sC / nC if nC else None, "delta_mean_task": sum(diffs) / len(diffs) if diffs else None,
                   "delta_ci95": [lo, hi], "delta_one_sided_lower95": lo1, "signflip_p": p, "tasks_with_difference": k,
                   "mcnemar_majority": {"C_only": b, "A_only": c, "p": mcnemar_exact(b, c)},
                   "floor": bool(nA and nC and sA / nA < 0.10 and sC / nC < 0.10),
                   "per_task": {t: {"A": round(pa[t], 3), "C": round(pc[t], 3)} for t in sorted(rows)}}
    out["ratios_C_over_A"] = {m: ratio_ci(rows, m) for m in ("total_tokens", "turns", "wall_s")}
    # stale first edit (runs without any edit of a target file are excluded from the rate)
    st = {}
    for t, cs in rows.items():
        a = [m["stale_first"] for m in cs["A"] if m["stale_first"] is not None]
        cc = [m["stale_first"] for m in cs["C"] if m["stale_first"] is not None]
        if a and cc:
            st[t] = (sum(a), len(a), sum(cc), len(cc))
    sa = sum(v[0] for v in st.values()); na = sum(v[1] for v in st.values())
    sc = sum(v[2] for v in st.values()); nc = sum(v[3] for v in st.values())
    ps, ks = signflip_exact([v[2] / v[3] - v[0] / v[1] for v in st.values()])
    out["stale_first_edit"] = {"A": f"{sa}/{na}", "C": f"{sc}/{nc}", "A_rate": sa / na if na else None,
                               "C_rate": sc / nc if nc else None, "tasks": len(st), "signflip_p": ps,
                               "tasks_with_difference": ks,
                               "fisher_run_level_p": fisher_two_sided(sa, na - sa, sc, nc - sc) if na and nc else None}
    fa = sum(m["stale_final"] for cs in rows.values() for m in cs["A"])
    fc = sum(m["stale_final"] for cs in rows.values() for m in cs["C"])
    out["stale_in_final"] = {"A": f"{fa}/{nA}", "C": f"{fc}/{nC}"}
    no_edit = {cnd: sum(1 for cs in rows.values() for m in cs[cnd] if m["stale_first"] is None) for cnd in "AC"}
    out["runs_without_target_edit"] = no_edit
    out["medians"] = {cnd: {m: statistics.median([x[m] for cs in rows.values() for x in cs[cnd]])
                            for m in ("total_tokens", "turns", "wall_s")} for cnd in "AC"}
    return out


def main():
    args = sys.argv[1:]
    exclude, reps, outp, pairs, only = set(), set(), None, ["C/A"], set()
    for flag in ("--exclude", "--reps", "--out", "--pairs", "--only-tasks"):
        if flag in args:
            i = args.index(flag); v = args[i + 1]; del args[i:i + 2]
            if flag == "--exclude":
                exclude = set(v.split(","))
            elif flag == "--pairs":
                pairs = v.split(",")
            elif flag == "--only-tasks":
                only = set(v.split(","))
            elif flag == "--reps":
                reps = {int(x) for x in v.split(",")}
            else:
                outp = Path(v)
    recs = load(args, exclude, reps)
    if only:
        recs = [r for r in recs if r["task"] in only]
    valid = [r for r in recs if r.get("valid")]
    invalid = [r for r in recs if not r.get("valid")]
    exits = defaultdict(int)
    for r in recs:
        exits[(r.get("exit") or {}).get("status") or "?"] += 1
    per = defaultdict(lambda: {"A": [], "C": [], "H": []})
    scope = {}
    for r in valid:
        per[r["task"]][r["condition"]].append(metrics(r))
        scope[r["task"]] = scope_of(r["task"], r["stratum"])
    out = {"studies": [Path(a).name for a in args], "excluded_tasks": sorted(exclude), "reps": sorted(reps) or "all",
           "sessions": len(recs), "valid": len(valid), "invalid": len(invalid),
           "invalid_reasons": sorted({str(r.get("invalid_reason"))[:120] for r in invalid}),
           "exit_status_counts": dict(exits), "results": {}}
    for sc in ("treatment", "controls", "other"):
        for pair in pairs:
            T, K = pair.split("/")
            rows = {t: cs for t, cs in per.items() if scope[t] == sc and cs[T] and cs[K]}
            if rows:
                key = sc if pair == "C/A" else f"{sc} {T}/{K}"
                out["results"][key] = analyse_scope(rows, T, K)
    text = json.dumps(out, indent=2, default=float)
    if outp:
        outp.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
