"""Analysis for PROTOCOL_ADDENDUM section 13 (concurrent A/C/H/R/G ablation). Writes I1/analysis/conc_ablation.json.

usage: python conc_analysis.py [--reps 1,2]     (default: every rep that is complete for all 11 tasks x 5 conditions)

Only the runs of conc-opus55-2026-10-23 are used for the pre-registered contrasts (all five conditions concurrent).
Reuses addendum5_analysis (collect, ratios = recompute_cost.ratio_ci: geometric mean over tasks of per-task median
ratios, task bootstrap 10,000, seed 20261001; pass_contrast / stale_contrast with exact sign-flip; boot_mean).
Token tests: exact sign-flip over the per-task log ratios (log of the ratio of per-task medians), two-sided; Holm over
the pre-registered family {C/G, C/R, G/H}. Cross-day comparisons with tasks2 / irr studies are descriptive.
"""
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from addendum5_analysis import (  # noqa: E402
    METRICS, OUT, RES, collect, pass_contrast, per_task_medians, ratios, split, stale_contrast, totals)
from pooled_old_new import boot_mean  # noqa: E402
from recompute_cost import load, ratio_ci  # noqa: E402
from stale_tests import signflip  # noqa: E402

CONC = RES / "conc-opus55-2026-10-23"
T2 = RES / "tasks2-opus55-2026-10-22"
IRR = RES / "irr-opus55-2026-10-22"
CONDS = ["A", "C", "H", "R", "G"]
FAMILY = ["C/G", "C/R", "G/H"]
COVERED = {"pl02", "st01"}


def log_ratios(per_task, treat, ctrl, metric="total_tokens"):
    out = {}
    for t, cs in per_task.items():
        a = [m[metric] for m in cs.get(treat, []) if m[metric]]
        b = [m[metric] for m in cs.get(ctrl, []) if m[metric]]
        if a and b:
            out[t] = math.log(statistics.median(a) / statistics.median(b))
    return out


def holm(pvals):
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, adj, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        adj[k] = run
    return adj


def delta(per_task, treat, ctrl, key):
    """Mean per-task difference treat - ctrl in a 0/1 field, CI, one-sided bounds."""
    diffs = []
    for cs in per_task.values():
        a = [m[key] for m in cs.get(ctrl, []) if m[key] is not None]
        b = [m[key] for m in cs.get(treat, []) if m[key] is not None]
        if a and b:
            diffs.append(sum(b) / len(b) - sum(a) / len(a))
    if not diffs:
        return None
    lo, hi, lo90 = boot_mean(diffs)
    _, _, lo90_neg = boot_mean([-d for d in diffs])
    return {"tasks": len(diffs), "mean_diff": sum(diffs) / len(diffs), "ci95": [lo, hi],
            "one_sided_95_lower": lo90, "one_sided_95_upper": -lo90_neg}


def complete_reps(recs, n_tasks=11):
    by = {}
    for r in recs:
        by.setdefault(r["rep"], set()).add((r["task"], r["condition"]))
    return sorted(k for k, v in by.items() if len(v) >= n_tasks * len(CONDS))


def main():
    args = sys.argv[1:]
    recs = load(CONC)
    reps = complete_reps(recs)
    if "--reps" in args:
        reps = [int(x) for x in args[args.index("--reps") + 1].split(",")]
    keep = set(reps)
    # restrict to the chosen reps: collect() reads records through addendum5_analysis.load, so filter there
    import addendum5_analysis as a5
    orig = a5.load
    a5.load = lambda d: [r for r in orig(d) if d != CONC or r["rep"] in keep]
    per_task, strata = a5.collect([(CONC, {c: c for c in CONDS})])
    a5.load = orig
    post, ctrl = split(per_task, strata)
    pairs = ["C/G", "C/R", "G/H", "C/A", "G/A", "H/A", "R/A", "C/H", "R/H", "G/R"]
    out = {"study": CONC.name, "reps_analysed": reps, "runs_analysed": sum(len(v) for cs in per_task.values()
                                                                            for v in cs.values()),
           "tasks_post": sorted(post), "tasks_controls": sorted(ctrl),
           "totals_post": totals(post), "totals_controls": totals(ctrl),
           "ratios_post": ratios(post, pairs), "ratios_controls": ratios(ctrl, ["C/A", "G/A", "H/A", "R/A", "C/G"]),
           "ratios_all11": ratios(per_task, pairs)}
    # pre-registered token tests (8 post-cutoff tasks)
    tests = {}
    for p in pairs:
        lr = log_ratios(post, *p.split("/"))
        pv, k = signflip(list(lr.values()))
        tests[p] = {"signflip_p": pv, "tasks": k, "tasks_below_1": sum(v < 0 for v in lr.values()),
                    "per_task_ratio": {t: round(math.exp(v), 3) for t, v in sorted(lr.items())}}
    adj = holm({p: tests[p]["signflip_p"] for p in FAMILY})
    for p in FAMILY:
        tests[p]["holm_p"] = adj[p]
    out["token_tests_post"] = tests
    # coverage split (descriptive)
    for name, sel in (("covered", COVERED), ("uncovered", set(post) - COVERED)):
        sub = {t: cs for t, cs in post.items() if t in sel}
        out[f"ratios_{name}"] = ratios(sub, pairs)
    # pass / stale
    out["pass_post"] = {p: pass_contrast(post, *p.split("/")) for p in ("C/A", "G/A", "H/A", "R/A", "C/G", "C/R",
                                                                        "G/H")}
    out["pass_controls"] = {p: pass_contrast(ctrl, *p.split("/")) for p in ("C/A", "G/A", "H/A", "R/A")}
    out["stale_post"] = {p: stale_contrast(post, *p.split("/")) for p in ("C/A", "G/A", "H/A", "R/A", "C/G")}
    out["stale_delta_post"] = {p: delta(post, *p.split("/"), "stale") for p in ("C/A", "G/A", "H/A", "R/A")}
    out["per_task"] = per_task_medians(per_task, CONDS)
    # mechanism (exploratory): reads of installed package sources
    reads = {}
    for rec in load(CONC):
        if rec["rep"] not in keep or rec["stratum"] != "post-cutoff":
            continue
        v = (rec.get("process") or {}).get("site_packages_reads")
        if v is not None:
            reads.setdefault(rec["condition"], []).append(v)
    out["site_packages_reads_post_mean"] = {c: sum(v) / len(v) for c, v in sorted(reads.items())}
    # cross-day comparison with the earlier studies (descriptive): same condition, different day
    old, ostrata = collect([(T2, {"A": "A_t2", "C": "C_t2", "H": "H_t2"}), (IRR, {"R": "R_irr", "A": "A_irr"})])
    merged = {t: dict(cs) for t, cs in per_task.items()}
    for t, cs in old.items():
        merged.setdefault(t, {}).update(cs)
    mpost = {t: cs for t, cs in merged.items() if strata.get(t, ostrata.get(t)) == "post-cutoff"}
    out["cross_day_all11"] = {p: ratio_ci(merged, *p.split("/"), "total_tokens")
                              for p in ("A/A_t2", "C/C_t2", "H/H_t2", "R/R_irr", "A/A_irr")}
    out["cross_day_post"] = {p: ratio_ci(mpost, *p.split("/"), "total_tokens")
                             for p in ("A/A_t2", "C/C_t2", "H/H_t2", "R/R_irr", "C_t2/R_irr")}
    # rules
    r = out["ratios_post"]
    tok = {p: r[p]["total_tokens"] for p in pairs}

    def below(p):
        return tok[p]["hi"] < 1

    def verdict(p):
        if below(p) and tests[p]["holm_p"] < 0.05:
            return "supported"
        if below(p):
            return "CI below 1 but Holm p >= .05 (suggestive)"
        return "not supported"
    gh = tok["G/H"]
    out["rules"] = {
        "M1_C_lt_G": verdict("C/G"),
        "M2_C_lt_R": verdict("C/R"),
        "M3_G_vs_H": ("G cheaper than H" if gh["hi"] < 1 and tests["G/H"]["holm_p"] < 0.05 else
                      "H cheaper than G" if gh["lo"] > 1 and tests["G/H"]["holm_p"] < 0.05 else
                      "no difference shown"),
        "earlier_R_result": ("confirmed (concurrent C/R CI below 1)" if below("C/R") else
                             "not replicated (concurrent C/R CI includes 1)" if tok["C/R"]["lo"] <= 1 <= tok["C/R"]["hi"]
                             else "reversed (C/R CI above 1)"),
        "N_pass_noninferior_vs_A": {p: (out["pass_post"][p] or {}).get("one_sided_95_lower", -1) >= -0.10
                                    for p in ("C/A", "G/A", "H/A", "R/A")},
        "N_stale_noninferior_vs_A": {p: (out["stale_delta_post"][p] or {}).get("one_sided_95_upper", 1) <= 0.10
                                     for p in ("C/A", "G/A", "H/A", "R/A")},
        "N_controls_pass_noninferior_vs_A": {p: (out["pass_controls"][p] or {}).get("one_sided_95_lower", -1) >= -0.10
                                             for p in ("C/A", "G/A", "H/A", "R/A")},
        "ceiling_A_post": out["pass_post"]["C/A"]["A_pass"] if out["pass_post"]["C/A"] else None,
    }
    OUT.mkdir(exist_ok=True)
    name = "conc_ablation.json" if "--reps" not in args else f"conc_ablation_reps{''.join(map(str, reps))}.json"
    (OUT / name).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("reps", reps, "runs", out["runs_analysed"])
    print(json.dumps(out["rules"], indent=1))
    for p in pairs:
        x = r[p]
        print(p, {m: (round(x[m]["ratio"], 3), round(x[m]["lo"], 3), round(x[m]["hi"], 3)) for m in
                  ("total_tokens", "list_cost_usd", "turns") if x[m]},
              "p", round(tests[p]["signflip_p"], 4), "holm", round(tests[p].get("holm_p", float("nan")), 4))


if __name__ == "__main__":
    main()
