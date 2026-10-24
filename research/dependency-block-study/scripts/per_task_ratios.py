"""Per-task C/A total-token ratios for the forest plot (requested in an internal review). Existing run data only.

usage: python per_task_ratios.py          -> writes <study>/analysis/per_task_ratios.json (study names only, no paths)
env:   RUNS_RESULTS, BENCH_RESULTS, ANALYSIS_OUT as in token_breakdown.py.

Cells: every post-cutoff task x Opus 5.5 study with both A and C sessions (first valid attempt per planned run):
  main-2026-09-28 (17 original tasks), abl-opus55-2026-10-22 (replication, same 17), tasks2-opus55-2026-10-22 (8 new
  tasks); case-opus55-2026-10-22 (cs01, cs02, real repository, 5 reps) is reported as a separate set and not plotted.
  The pilot (ant01, mcp01) is excluded by protocol; the iter study's single-rep A/C comparators are not used.
Per cell (C/A of total tokens = input + cache read + cache write + output):
  median_ratio  ratio of per-arm medians (the paper's per-task statistic);
  gm_ratio      ratio of geometric means; its 95% CI is a Welch t interval on log tokens (plotted; honest with 3 reps)
                and, as a secondary check, a percentile bootstrap of reps within arm (10,000, seed 20261001).
Per task (combined over the studies that ran it): log ratio = mean over studies of the per-study log gm ratio
  (stratified by study, so the month between main and replication does not enter the contrast); Welch-Satterthwaite
  variance/df over the 2S arm components; for new tasks this is the single tasks2 cell.
Summaries: geometric mean over tasks of the combined per-task ratio, task bootstrap (10,000, seed 20261001), for all
  25, covered (notes name the task's change), uncovered, original, new, and without the pilot-exposed tasks.
Flags: covered (condition_config.notes_covered of the C runs), pilot_exposed (ant01, mcp01), task_set.
"""
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from scipy import stats

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from token_breakdown import load_runs, session  # noqa: E402

RES = Path(os.environ.get("RUNS_RESULTS", "since_cutoff_runs/results"))
BENCH = Path(os.environ.get("BENCH_RESULTS", Path.home() / "projects" / "since-cutoff-benchmark" / "results"))
OUT = Path(os.environ.get("ANALYSIS_OUT", HERE.parent / "analysis"))
B, SEED = 10000, 20261001
PILOT = {"ant01", "mcp01"}
STUDIES = [("main", BENCH / "main-2026-09-28", "original"), ("replication", RES / "abl-opus55-2026-10-22", "original"),
           ("tasks2", RES / "tasks2-opus55-2026-10-22", "new"), ("case", RES / "case-opus55-2026-10-22", "case")]


def welch(la, lc):
    """la, lc: log tokens of A and C runs -> (diff, var, df)."""
    va, vc = statistics.variance(la), statistics.variance(lc)
    sa, sc = va / len(la), vc / len(lc)
    return statistics.mean(lc) - statistics.mean(la), sa, sc, len(la) - 1, len(lc) - 1


def t_ci(diff, comps):
    """comps: [(s_i, df_i)] variance components of diff -> 95% CI on the ratio scale."""
    var = sum(s for s, _ in comps)
    df = var ** 2 / sum((s ** 2) / d for s, d in comps if s > 0) if var > 0 else float("inf")
    q = stats.t.ppf(0.975, df)
    se = math.sqrt(var)
    return [math.exp(diff - q * se), math.exp(diff + q * se)], df


def boot_cell(a, c, seed=SEED):
    rnd = random.Random(seed)
    la, lc = [math.log(x) for x in a], [math.log(x) for x in c]
    bs = sorted(math.exp(statistics.mean(rnd.choice(lc) for _ in lc) - statistics.mean(rnd.choice(la) for _ in la))
                for _ in range(B))
    return [bs[int(0.025 * B)], bs[int(0.975 * B) - 1]]


def gm_summary(logs, seed=SEED):
    if not logs:
        return None
    rnd = random.Random(seed)
    bs = sorted(math.exp(sum(rnd.choice(logs) for _ in logs) / len(logs)) for _ in range(B))
    return {"ratio": math.exp(sum(logs) / len(logs)), "lo": bs[int(0.025 * B)], "hi": bs[int(0.975 * B) - 1],
            "tasks": len(logs)}


def main():
    cells = defaultdict(dict)
    meta = {}
    for label, d, tset in STUDIES:
        per = defaultdict(lambda: defaultdict(list))
        cov = {}
        for r in load_runs(d):
            if r["stratum"] != "post-cutoff" or r["condition"] not in ("A", "C"):
                continue
            s = session(r)
            per[r["task"]][r["condition"]].append(s)
            if r["condition"] == "C":
                cov[r["task"]] = bool((r.get("condition_config") or {}).get("notes_covered"))
        for t, cs in per.items():
            if not (cs.get("A") and cs.get("C")):
                continue
            a = [s["total"] for s in cs["A"]]; c = [s["total"] for s in cs["C"]]
            diff, sa, sc, da, dc = welch([math.log(x) for x in a], [math.log(x) for x in c])
            ci, df = t_ci(diff, [(sa, da), (sc, dc)])
            cells[t][label] = {
                "study": d.name, "n_A": len(a), "n_C": len(c),
                "median_tokens_A": statistics.median(a), "median_tokens_C": statistics.median(c),
                "median_ratio": statistics.median(c) / statistics.median(a),
                "gm_ratio": math.exp(diff), "ci95_welch_t": ci, "welch_df": df, "ci95_bootstrap_reps": boot_cell(a, c),
                "pass_A": f"{sum(s['passed'] for s in cs['A'])}/{len(a)}",
                "pass_C": f"{sum(s['passed'] for s in cs['C'])}/{len(c)}",
                "_comps": [(sa, da), (sc, dc)], "_diff": diff}
            meta[t] = {"task_set": tset, "covered": cov[t], "pilot_exposed": t in PILOT,
                       "library": next(iter(load_runs_lib(d, t)), None)}
    tasks = {}
    for t in sorted(cells, key=lambda t: (meta[t]["task_set"] != "original", meta[t]["task_set"] == "case", t)):
        cs = cells[t]
        diffs = [v["_diff"] for v in cs.values()]
        comb = sum(diffs) / len(diffs)
        comps = [(s / len(diffs) ** 2, d) for v in cs.values() for s, d in v["_comps"]]
        ci, df = t_ci(comb, comps)
        tasks[t] = dict(meta[t], studies=sorted(cs), combined={
            "gm_ratio": math.exp(comb), "ci95_welch_t": ci, "welch_df": df,
            "median_ratio_geomean_over_studies": math.exp(sum(math.log(v["median_ratio"]) for v in cs.values()) / len(cs))},
            per_study={k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in cs.items()})
    bench = {t: v for t, v in tasks.items() if v["task_set"] != "case"}

    def logs(sel, key="gm_ratio"):
        return [math.log(v["combined"][key]) for v in sel.values()]
    groups = {"all": bench,
              "covered": {t: v for t, v in bench.items() if v["covered"]},
              "uncovered": {t: v for t, v in bench.items() if not v["covered"]},
              "original": {t: v for t, v in bench.items() if v["task_set"] == "original"},
              "new": {t: v for t, v in bench.items() if v["task_set"] == "new"},
              "all_without_pilot": {t: v for t, v in bench.items() if not v["pilot_exposed"]},
              "uncovered_without_pilot": {t: v for t, v in bench.items() if not v["covered"] and not v["pilot_exposed"]}}
    summaries = {g: {"tasks": sorted(sel), "gm_of_combined_gm_ratio": gm_summary(logs(sel)),
                     "gm_of_median_ratio": gm_summary(logs(sel, "median_ratio_geomean_over_studies"))}
                 for g, sel in groups.items()}
    below1 = [t for t, v in bench.items() if v["combined"]["ci95_welch_t"][1] < 1]
    above1 = [t for t, v in bench.items() if v["combined"]["ci95_welch_t"][0] > 1]
    point_below = [t for t, v in bench.items() if v["combined"]["gm_ratio"] < 1]
    out = {"generated_by": "scripts/per_task_ratios.py", "method": __doc__.split("Cells:")[1].strip(),
           "metric": "C/A total tokens (input + cache_read + cache_write + output), Claude Opus 5.5, post-cutoff tasks",
           "studies": {label: d.name for label, d, _ in STUDIES},
           "counts": {"benchmark_tasks": len(bench), "covered": len(groups["covered"]),
                      "uncovered": len(groups["uncovered"]), "point_estimate_below_1": len(point_below),
                      "ci_entirely_below_1": below1, "ci_entirely_above_1": above1},
           "summaries": summaries, "tasks": tasks}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "per_task_ratios.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print("wrote per_task_ratios.json")


_LIB = {}


def load_runs_lib(d, t):
    if d not in _LIB:
        _LIB[d] = {r["task"]: r.get("library") for r in load_runs(d)}
    return [_LIB[d].get(t)]


if __name__ == "__main__":
    main()
