"""Analysis for PROTOCOL_ADDENDUM section 12 (deployment iteration, condition C2). Writes <study>/analysis/iter_C2.json.

usage: python iter_analysis.py

Merges the A/C/H runs of tasks2-opus55-2026-10-22 (3 reps) with the C2 (3 reps) and concurrent A/C (1 rep, labelled
"An"/"Cn") runs of iter-opus55-2026-10-22, per task. Reuses addendum5_analysis (collect, ratios = recompute_cost
.ratio_ci: geometric mean of per-task median ratios, task bootstrap 10,000, seed 20261001; pass_contrast /
stale_contrast with exact sign-flip; pooled_old_new.boot_mean).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from addendum5_analysis import (  # noqa: E402
    METRICS, OUT, RES, collect, pass_contrast, per_task_medians, ratios, split, stale_contrast, totals)
from pooled_old_new import boot_mean  # noqa: E402
from recompute_cost import load, ratio_ci  # noqa: E402

T2 = RES / "tasks2-opus55-2026-10-22"
IT = RES / "iter-opus55-2026-10-22"
STRATA = {"newly_covered": {"pl01", "mi01"}, "covered_both": {"pl02", "st01"},
          "covered_neither": {"pl03", "pl04", "st02", "mi02"}}


def stale_delta(per_task, treat, ctrl):
    """Mean per-task stale-first-edit difference treat - ctrl, 95% CI and one-sided 95% upper bound."""
    diffs = []
    for cs in per_task.values():
        a = [m["stale"] for m in cs.get(ctrl, []) if m["stale"] is not None]
        b = [m["stale"] for m in cs.get(treat, []) if m["stale"] is not None]
        if a and b:
            diffs.append(sum(b) / len(b) - sum(a) / len(a))
    if not diffs:
        return None
    lo, hi, _ = boot_mean(diffs)
    _, _, lo90_neg = boot_mean([-d for d in diffs])
    return {"tasks": len(diffs), "mean_diff": sum(diffs) / len(diffs), "ci95": [lo, hi],
            "one_sided_95_upper": -lo90_neg}


def main():
    per_task, strata = collect([(T2, {"A": "A", "C": "C", "H": "H"}),
                                (IT, {"C2": "C2", "A": "An", "C": "Cn"})])
    post, ctrl = split(per_task, strata)
    pairs = ["C2/C", "C2/A", "C/A", "C2/H", "H/A", "C2/Cn", "C2/An", "Cn/An"]
    out = {"studies": [T2.name, IT.name], "tasks_post": sorted(post), "tasks_controls": sorted(ctrl),
           "totals_post": totals(post), "totals_controls": totals(ctrl),
           "ratios_post": ratios(post, pairs), "ratios_controls": ratios(ctrl, ["C2/C", "C2/A", "C/A"]),
           "ratios_all11": ratios(per_task, ["C2/C", "C2/A", "C/A"]),
           "drift_all11": {"An/A": {m: ratio_ci(per_task, "An", "A", m) for m in METRICS},
                           "Cn/C": {m: ratio_ci(per_task, "Cn", "C", m) for m in METRICS}},
           "strata": {}}
    for name, ts in STRATA.items():
        sub = {t: cs for t, cs in post.items() if t in ts}
        out["strata"][name] = {"tasks": sorted(sub), "ratios": ratios(sub, ["C2/C", "C2/A", "C/A"]),
                               "pass": {p: pass_contrast(sub, *p.split("/")) for p in ("C2/A", "C2/C")},
                               "stale": {p: stale_contrast(sub, *p.split("/")) for p in ("C2/C", "C2/A")}}
    out["pass_post"] = {p: pass_contrast(post, *p.split("/")) for p in ("C2/A", "C2/C", "C/A", "Cn/C", "An/A")}
    out["pass_controls"] = {p: pass_contrast(ctrl, *p.split("/")) for p in ("C2/A", "C2/C")}
    out["stale_post"] = {p: stale_contrast(post, *p.split("/")) for p in ("C2/C", "C2/A", "C/A")}
    out["stale_delta_post"] = {p: stale_delta(post, *p.split("/")) for p in ("C2/C", "C2/A")}
    out["per_task"] = per_task_medians(per_task, ["A", "An", "H", "C", "Cn", "C2"])
    # site-packages reads (exploratory mechanism, as 0.6/0.9.1): harness process.site_packages_reads
    reads = {}
    for d, rename in ((T2, {"A": "A", "C": "C", "H": "H"}), (IT, {"C2": "C2", "A": "An", "C": "Cn"})):
        for rec in load(d):
            if rec["stratum"] != "post-cutoff":
                continue
            v = (rec.get("process") or {}).get("site_packages_reads")
            if v is not None:
                reads.setdefault(rename[rec["condition"]], []).append(v)
    out["site_packages_reads_post_mean"] = {c: sum(v) / len(v) for c, v in sorted(reads.items())}

    r = out["ratios_post"]
    tok = r["C2/C"]["total_tokens"]
    k2_no_worse = tok["hi"] <= 1.10 and r["C2/A"]["total_tokens"]["ratio"] <= r["C/A"]["total_tokens"]["ratio"]
    k4 = {p: (out["pass_post"][p] or {}).get("one_sided_95_lower") for p in ("C2/A", "C2/C")}
    k3 = {p: (out["stale_delta_post"][p] or {}).get("one_sided_95_upper") for p in ("C2/C", "C2/A")}
    drift = {k: not (v["total_tokens"]["lo"] <= 1 <= v["total_tokens"]["hi"]) for k, v in out["drift_all11"].items()}
    out["rules"] = {
        "K1_coverage": "2/8 -> 4/8 (recorded before sessions)",
        "K2_no_worse": k2_no_worse, "K2_improvement_shown": tok["hi"] < 1,
        "K3_stale_noninferior": {p: (v is not None and v <= 0.10) for p, v in k3.items()},
        "K4_pass_noninferior": {p: (v is not None and v >= -0.10) for p, v in k4.items()},
        "drift_ci_excludes_1": drift,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "iter_C2.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(json.dumps(out["rules"], indent=1))
    for p in pairs:
        x = r[p]
        print(p, {m: (round(x[m]["ratio"], 3), round(x[m]["lo"], 3), round(x[m]["hi"], 3)) for m in
                  ("total_tokens", "list_cost_usd", "turns", "wall_s") if x[m]})


if __name__ == "__main__":
    main()
