"""Analysis for PROTOCOL_ADDENDUM section 11 (E-irr, E-anchor, E-case). Writes I1/analysis/addendum5_*.json.

usage: python addendum5_analysis.py [irr|anchor|case ...]   (default: all whose studies have records)

Reuses recompute_cost.load/metrics/ratio_ci (geometric mean of per-task median ratios, task bootstrap 10,000, seed
20261001), stale_tests.signflip/fisher_two_sided and the pooled_old_new bootstrap of mean per-task differences.
Studies are merged per task: a condition label may be renamed per study (e.g. the drift-check A of the irr study is
"An"), so that runs of the same task from different studies can be compared.
"""
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
import recompute_cost  # noqa: E402
from recompute_cost import load, metrics, ratio_ci  # noqa: E402
from stale_tests import fisher_two_sided, signflip  # noqa: E402
from pooled_old_new import boot_mean  # noqa: E402

recompute_cost.PRICES.setdefault("claude-sonnet-4-5", (3.0, 15.0, 0.30, 6.0, 3.75))

# RUNS_RESULTS: folder with one subfolder per study (harness results or the exported per-run tables in runs/);
# ANALYSIS_OUT: where the JSON outputs go
RES = Path(os.environ.get("RUNS_RESULTS", "since_cutoff_runs/results"))
MAIN = (RES / "main-2026-09-28" if "RUNS_RESULTS" in os.environ
        else Path.home() / "projects" / "since-cutoff-benchmark" / "results" / "main-2026-09-28")
OUT = Path(os.environ.get("ANALYSIS_OUT", HERE.parent / "analysis"))
METRICS = ("total_tokens", "list_cost_usd", "turns", "wall_s", "output_tokens")


def stale_of(r):
    v = (r.get("process") or {}).get("stale_in_first_edit")
    if v is None:
        v = r.get("stale_in_first_edit")
    return v


def collect(specs, tasks=None):
    """specs: [(study_dir, {cond: label})]. Returns per_task[task][label] -> list of metric dicts, strata."""
    per_task = defaultdict(lambda: defaultdict(list))
    strata = {}
    for d, rename in specs:
        for r in load(d):
            t = r["task"]
            if tasks is not None and t not in tasks:
                continue
            c = rename.get(r["condition"]) if rename is not None else r["condition"]
            if c is None:
                continue
            m = metrics(r, d)
            m["stale"] = stale_of(r)
            m["study"] = d.name
            per_task[t][c].append(m)
            strata[t] = r["stratum"]
    return per_task, strata


def pass_contrast(per_task, treat, ctrl):
    rows = {t: cs for t, cs in per_task.items() if cs.get(treat) and cs.get(ctrl)}
    if not rows:
        return None
    pt = {t: sum(m["passed"] for m in cs[treat]) / len(cs[treat]) for t, cs in rows.items()}
    pc = {t: sum(m["passed"] for m in cs[ctrl]) / len(cs[ctrl]) for t, cs in rows.items()}
    diffs = [pt[t] - pc[t] for t in rows]
    lo, hi, lo90 = boot_mean(diffs)
    p, k = signflip(diffs)
    return {"tasks": len(rows), f"{treat}_pass": f"{sum(sum(m['passed'] for m in cs[treat]) for cs in rows.values())}/"
            f"{sum(len(cs[treat]) for cs in rows.values())}",
            f"{ctrl}_pass": f"{sum(sum(m['passed'] for m in cs[ctrl]) for cs in rows.values())}/"
            f"{sum(len(cs[ctrl]) for cs in rows.values())}",
            "mean_diff": sum(diffs) / len(diffs), "ci95": [lo, hi], "one_sided_95_lower": lo90,
            "signflip_p": p, "tasks_with_difference": k}


def stale_contrast(per_task, treat, ctrl):
    per = {}
    for t, cs in per_task.items():
        a = [m["stale"] for m in cs.get(ctrl, []) if m["stale"] is not None]
        b = [m["stale"] for m in cs.get(treat, []) if m["stale"] is not None]
        if a and b:
            per[t] = (sum(a), len(a), sum(b), len(b))
    if not per:
        return None
    sc = sum(v[0] for v in per.values()); nc = sum(v[1] for v in per.values())
    st = sum(v[2] for v in per.values()); nt = sum(v[3] for v in per.values())
    diffs = [v[0] / v[1] - v[2] / v[3] for v in per.values()]
    p, k = signflip(diffs)
    return {f"{ctrl}_stale": f"{sc}/{nc}", f"{treat}_stale": f"{st}/{nt}",
            "fisher_p_run_level": fisher_two_sided(sc, nc - sc, st, nt - st), "signflip_p_task_level": p,
            "tasks_with_difference": k,
            "per_task": {t: {ctrl: f"{v[0]}/{v[1]}", treat: f"{v[2]}/{v[3]}"} for t, v in sorted(per.items())
                         if v[0] or v[2]}}


def ratios(per_task, pairs):
    return {pair: {m: ratio_ci(per_task, *pair.split("/"), m) for m in METRICS} for pair in pairs}


def totals(per_task):
    out = defaultdict(lambda: defaultdict(float))
    for cs in per_task.values():
        for c, ms in cs.items():
            o = out[c]
            for m in ms:
                o["runs"] += 1; o["passed"] += m["passed"]; o["list_cost_usd"] += m["list_cost_usd"]
                o["budget_stops"] += m["budget_stop"]; o["compactions"] += m["compactions"]
    for o in out.values():
        o["mean_list_cost_usd"] = o["list_cost_usd"] / o["runs"] if o["runs"] else None
    return out


def split(per_task, strata):
    post = {t: cs for t, cs in per_task.items() if strata[t] == "post-cutoff"}
    ctrl = {t: cs for t, cs in per_task.items() if strata[t] != "post-cutoff"}
    return post, ctrl


def per_task_medians(per_task, conds):
    out = {}
    for t, cs in sorted(per_task.items()):
        out[t] = {c: {"n": len(cs[c]), "passed": sum(m["passed"] for m in cs[c]),
                      "median_tokens": statistics.median(m["total_tokens"] for m in cs[c]),
                      "median_list_cost_usd": round(statistics.median(m["list_cost_usd"] for m in cs[c]), 4),
                      "median_turns": statistics.median(m["turns"] or 0 for m in cs[c])}
                  for c in conds if cs.get(c)}
    return out


# -- E-irr ----------------------------------------------------------------------------------------------------------
def analyse_irr():
    t2 = RES / "tasks2-opus55-2026-10-22"
    irr = RES / "irr-opus55-2026-10-22"
    per_task, strata = collect([(t2, {"A": "A", "C": "C", "H": "H"}), (irr, {"R": "R", "A": "An"})])
    post, ctrl = split(per_task, strata)
    pairs = ["C/R", "R/A", "R/H", "C/A", "H/A", "C/H", "R/An"]
    covered = {"pl02", "st01"}
    out = {"studies": [t2.name, irr.name], "tasks_post": sorted(post), "tasks_controls": sorted(ctrl),
           "totals_post": totals(post), "totals_controls": totals(ctrl),
           "ratios_post": ratios(post, pairs), "ratios_controls": ratios(ctrl, pairs),
           "ratios_all11": ratios(per_task, pairs),
           "drift_An_over_A_all11": {m: ratio_ci(per_task, "An", "A", m) for m in METRICS},
           "ratios_post_uncovered": ratios({t: cs for t, cs in post.items() if t not in covered}, ["C/R", "R/A", "C/A"]),
           "ratios_post_covered": ratios({t: cs for t, cs in post.items() if t in covered}, ["C/R", "R/A", "C/A"]),
           "pass_post": {p: pass_contrast(post, *p.split("/")) for p in ("R/A", "C/R", "R/H", "An/A")},
           "pass_controls": {p: pass_contrast(ctrl, *p.split("/")) for p in ("R/A", "C/R")},
           "stale_post": {p: stale_contrast(post, *p.split("/")) for p in ("C/R", "R/A")},
           "per_task": per_task_medians(per_task, ["A", "An", "H", "R", "C"])}
    r = out["ratios_post"]
    ci = lambda pair: (r[pair]["total_tokens"]["lo"], r[pair]["total_tokens"]["hi"])
    i1 = ci("C/R")[1] < 1
    i2 = ci("R/A")[1] < 1 and ci("C/R")[0] <= 1 <= ci("C/R")[1]
    d = out["drift_An_over_A_all11"]["total_tokens"]
    out["rules"] = {"I1_content_matters": i1, "I2_priming": i2,
                    "verdict": "I1 met" if i1 else ("I2 met" if i2 else "inconclusive"),
                    "drift_ci_excludes_1": not (d["lo"] <= 1 <= d["hi"])}
    return out


# -- E-anchor -------------------------------------------------------------------------------------------------------
ANCHOR_TASKS = ["ant02", "ant04", "hf02", "hf03", "hf04", "mcp06", "oai01", "oai02", "oai03",
                "mi01", "mi02", "pl01", "pl02", "st01", "st02"]


def analyse_anchor():
    s1 = RES / "anchor-s45-main-2026-10-22"
    s2 = RES / "anchor-s45-tasks2-2026-10-22"
    per_task, strata = collect([(s1, None), (s2, None)])
    out = {"studies": [s1.name, s2.name], "tasks": sorted(per_task), "totals": totals(per_task),
           "ratios": ratios(per_task, ["C/A"]), "pass": pass_contrast(per_task, "C", "A"),
           "stale": stale_contrast(per_task, "C", "A")}
    covered = {"hf03", "st01"}
    out["ratios_uncovered"] = ratios({t: cs for t, cs in per_task.items() if t not in covered}, ["C/A"])
    out["ratios_covered"] = ratios({t: cs for t, cs in per_task.items() if t in covered}, ["C/A"])
    a_pass = sum(m["passed"] for cs in per_task.values() for m in cs.get("A", []))
    a_n = sum(len(cs.get("A", [])) for cs in per_task.values())
    out["A_pass_rate"] = a_pass / a_n if a_n else None
    out["ceiling_rule_fires"] = (a_pass / a_n) >= 0.90 if a_n else None
    tok = out["ratios"]["C/A"]["total_tokens"]
    pr = out["pass"]
    out["rules"] = {"K1_pass": (not out["ceiling_rule_fires"]) and pr["ci95"][0] > 0 and pr["signflip_p"] < 0.05,
                    "K2_tokens": tok["hi"] < 1,
                    "K3_stale": bool(out["stale"]) and out["stale"]["signflip_p_task_level"] < 0.05}
    # Opus 5.5 on the same 15 tasks (descriptive): main study (A/C) + tasks2 (A/C)
    opus, _ = collect([(MAIN, {"A": "A", "C": "C"}), (RES / "tasks2-opus55-2026-10-22", {"A": "A", "C": "C"})],
                      tasks=set(ANCHOR_TASKS))
    out["opus55_same_tasks"] = {"ratios": ratios(opus, ["C/A"]), "pass": pass_contrast(opus, "C", "A"),
                                "totals": totals(opus)}
    out["per_task"] = per_task_medians(per_task, ["A", "C"])
    return out


# -- E-case ---------------------------------------------------------------------------------------------------------
def run_boot_ratio(a, b, resamples=10000, seed=20261001):
    rnd = random.Random(seed)
    obs = statistics.median(a) / statistics.median(b)
    bs = sorted(statistics.median([rnd.choice(a) for _ in a]) / statistics.median([rnd.choice(b) for _ in b])
                for _ in range(resamples))
    return {"ratio": obs, "lo": bs[int(0.025 * resamples)], "hi": bs[int(0.975 * resamples) - 1]}


def analyse_case():
    s = RES / "case-opus55-2026-10-22"
    per_task, strata = collect([(s, None)])
    out = {"study": s.name, "totals": totals(per_task), "per_task": {}}
    for t, cs in sorted(per_task.items()):
        row = per_task_medians({t: cs}, ["A", "C"])[t]
        for c in ("A", "C"):
            if cs.get(c):
                row[c]["mean_list_cost_usd"] = round(sum(m["list_cost_usd"] for m in cs[c]) / len(cs[c]), 4)
                row[c]["stale_first_edit"] = f"{sum(1 for m in cs[c] if m['stale'])}/" \
                                             f"{sum(1 for m in cs[c] if m['stale'] is not None)}"
                row[c]["median_wall_s"] = statistics.median(m["wall_s"] for m in cs[c])
        if cs.get("A") and cs.get("C"):
            row["C_over_A_run_bootstrap"] = {m: run_boot_ratio([x[m] for x in cs["C"]], [x[m] for x in cs["A"]])
                                             for m in ("total_tokens", "list_cost_usd", "turns", "wall_s")}
        out["per_task"][t] = row
    out["ratios_geo_2tasks"] = ratios(per_task, ["C/A"])
    return out


def main():
    which = sys.argv[1:] or ["irr", "anchor", "case"]
    fns = {"irr": analyse_irr, "anchor": analyse_anchor, "case": analyse_case}
    for w in which:
        res = fns[w]()
        path = OUT / f"addendum5_{w}.json"
        path.write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
        print("wrote", path)


if __name__ == "__main__":
    main()
