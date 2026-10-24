"""Round-9 numbers for the paper (no model sessions; existing run tables and analysis JSONs only).

usage: python -I round9_numbers.py <I1 dir>   ->   <I1>/analysis/round9_numbers.json
(in the supplementary archive: RUNS_TABLES=runs python scripts/round9_numbers.py .)

1. Block-size cap from the break-even model: the block pays for itself while
   b * (t * p_r + p_w) <= f * s, so b_max(f) = f * s / (t * p_r + p_w), with s the gross saving per affected session and
   t the mean C turns of the study (inputs from analysis/exposure2_breakeven.json; Opus 5.5 list prices).
2. Fleet example (re-derived): 1,000 sessions a day, share f = 0.2 affected, 764-token block, main-study s and turns.
3. Random-effects (DerSimonian-Laird) estimate of C/A list cost over the four Opus 5.5 studies (main, replication,
   new tasks, concurrent), each treated as one run day. Per-study log ratio and its standard error come from the
   per-task log ratios of the paper's estimator (SE = SD / sqrt(tasks)). The studies share tasks (main and replication;
   new tasks and concurrent), so they are not independent and the interval is approximate.
4. Live A/B sizing (illustrative): session-level SD of log list cost of None sessions on post-cutoff tasks in the Opus
   studies; sessions per arm for an unpaired two-sided 5% test with 80% power,
   n = 2 * (z_0.975 + z_0.80)^2 * SD^2 / delta^2, for (a) the diluted net effect over all sessions,
   d = (f * s - overhead of a 704-token block) / mean None cost per session, and (b) a 15% or 20% saving on affected sessions only.
   Assumes independent sessions with our benchmark's spread; real fleets are likely more variable.
5. Runtime bound for the 14 true uses checked by running code (0 failures): Wilson 95% upper bound, the same interval
   as the paper's 0/60 bound (analysis/exposure2.json).
"""
import json
import math
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from round5_table1 import load, metrics  # noqa: E402

Z = 1.959964 + 0.841621


def wilson_upper(k, n, z=1.959964):
    p = k / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre + half) / den


def per_task_logs(recs, treat, ctrl, metric):
    by = {}
    for r in recs:
        if r.get("stratum") != "post-cutoff":
            continue
        m = metrics(r)
        by.setdefault(r["task"], {}).setdefault(r["condition"], []).append(m[metric])
    logs = []
    for t, cs in sorted(by.items()):
        a, b = cs.get(treat), cs.get(ctrl)
        if a and b:
            logs.append(math.log(statistics.median(a) / statistics.median(b)))
    return logs


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    be = json.loads((i1 / "analysis" / "exposure2_breakeven.json").read_text(encoding="utf-8"))
    p_r, p_w = be["prices_usd_per_mtok"]["cache_read"], be["prices_usd_per_mtok"]["cache_write_1h"]
    out = {"generated_by": "scripts/round9_numbers.py", "inputs": ["analysis/exposure2_breakeven.json",
                                                                    "runs_tables/*/runs.jsonl"]}

    # 1. Block-size cap.
    cap = {}
    for name in ("main", "replication", "new_tasks"):
        st = be["studies"][name]
        per_tok = (st["mean_C_turns"] * p_r + p_w) / 1e6
        s = st["S_gross_usd"]
        cap[name] = {"S_gross_usd": round(s, 4), "mean_C_turns": round(st["mean_C_turns"], 2),
                     "overhead_usd_per_block_token": per_tok,
                     "tokens_per_unit_f": round(s / per_tok),
                     **{f"b_max_tokens_at_f_{f}": round(f * s / per_tok) for f in (0.05, 0.1, 0.2, 0.3)}}
    out["block_size_cap"] = cap

    # 2. Fleet example.
    m = cap["main"]
    ov764 = 764 * m["overhead_usd_per_block_token"]
    s = be["studies"]["main"]["S_gross_usd"]
    out["fleet_example"] = {"sessions_per_day": 1000, "f": 0.2, "block_tokens": 764,
                            "block_cost_per_day_usd": round(1000 * ov764, 2),
                            "gross_saving_per_day_usd": round(1000 * 0.2 * s, 2),
                            "net_saving_per_day_usd": round(1000 * (0.2 * s - ov764), 2)}
    ov704 = 704 * m["overhead_usd_per_block_token"]  # median non-empty block of the random sample
    out["fleet_example_704"] = {"sessions_per_day": 1000, "f": 0.2, "block_tokens": 704,
                                "block_cost_per_day_usd": round(1000 * ov704, 2),
                                "gross_saving_per_day_usd": round(1000 * 0.2 * s, 2),
                                "net_saving_per_day_usd": round(1000 * (0.2 * s - ov704), 2)}

    # 3. Random effects over the four Opus studies (C/A list cost).
    studies = {"main": ["main-2026-09-28"], "replication": ["abl-opus55-2026-10-22"],
               "new_tasks": ["tasks2-opus55-2026-10-22"], "concurrent": ["conc-opus55-2026-10-23"]}
    ys, vs, rows = [], [], {}
    none_logcost = {}
    none_cost = {}
    for name, dirs in studies.items():
        recs = load([rt / d for d in dirs])
        logs = per_task_logs(recs, "C", "A", "cost")
        y = sum(logs) / len(logs)
        se = statistics.stdev(logs) / math.sqrt(len(logs))
        ys.append(y)
        vs.append(se * se)
        rows[name] = {"tasks": len(logs), "ratio": round(math.exp(y), 4), "se_log": round(se, 4),
                      "normal_ci95": [round(math.exp(y - 1.959964 * se), 3), round(math.exp(y + 1.959964 * se), 3)]}
        a = [metrics(r)["cost"] for r in recs if r.get("stratum") == "post-cutoff" and r["condition"] == "A"]
        none_logcost[name] = [math.log(c) for c in a]
        none_cost[name] = a
    w = [1 / v for v in vs]
    yfe = sum(wi * yi for wi, yi in zip(w, ys)) / sum(w)
    q = sum(wi * (yi - yfe) ** 2 for wi, yi in zip(w, ys))
    k = len(ys)
    c = sum(w) - sum(wi * wi for wi in w) / sum(w)
    tau2 = max(0.0, (q - (k - 1)) / c)
    wr = [1 / (v + tau2) for v in vs]
    yre = sum(wi * yi for wi, yi in zip(wr, ys)) / sum(wr)
    sere = math.sqrt(1 / sum(wr))
    i2 = max(0.0, (q - (k - 1)) / q) if q > 0 else 0.0
    out["random_effects_CA_cost_opus"] = {
        "per_study": rows, "Q": round(q, 3), "df": k - 1, "tau2": round(tau2, 5), "I2": round(i2, 3),
        "fixed_ratio": round(math.exp(yfe), 4),
        "re_ratio": round(math.exp(yre), 4),
        "re_ci95": [round(math.exp(yre - 1.959964 * sere), 4), round(math.exp(yre + 1.959964 * sere), 4)],
        "note": "DerSimonian-Laird; studies share tasks, so approximate"}

    # 4. Live A/B sizing (illustrative).
    sd_main = statistics.stdev(none_logcost["main"])
    allA = [x for v in none_logcost.values() for x in v]
    sd_all = statistics.stdev(allA)
    mean_cost_main = statistics.mean(none_cost["main"])
    live = {"sd_log_cost_none_sessions_main": round(sd_main, 3), "sd_log_cost_none_sessions_4_opus_studies": round(sd_all, 3),
            "none_sessions_main": len(none_logcost["main"]), "none_sessions_4_opus_studies": len(allA),
            "mean_none_cost_main_usd": round(mean_cost_main, 4)}
    for f in (0.1, 0.2):
        d = (f * s - ov704) / mean_cost_main
        delta = -math.log(1 - d)
        live[f"diluted_net_saving_share_f_{f}"] = round(d, 4)
        for lab, sd in (("main_sd", sd_main), ("all_sd", sd_all)):
            live[f"sessions_per_arm_all_sessions_f_{f}_{lab}"] = round(2 * Z * Z * sd * sd / delta ** 2)
    for sav in (0.15, 0.20):
        delta = math.log(1 / (1 - sav))
        for lab, sd in (("main_sd", sd_main), ("all_sd", sd_all)):
            live[f"sessions_per_arm_affected_only_{int(sav * 100)}pct_{lab}"] = round(2 * Z * Z * sd * sd / delta ** 2)
    live["assumptions"] = ("unpaired two-sided 5% test, 80% power, independent sessions, session-level SD of log cost "
                           "as in our None sessions on post-cutoff tasks; 704-token block (median non-empty block of the random sample); main-study gross saving "
                           "and turns; mean None cost of the main study as the per-session cost")
    out["live_ab_sizing"] = live

    # 5. Runtime bound for the executed true uses.
    ex = json.loads((i1 / "analysis" / "exposure2.json").read_text(encoding="utf-8"))["audit"]
    n_exec = ex["runtime_basis_tp"]["snippet"]
    out["runtime_bounds"] = {"executed_true_uses": n_exec, "static_true_uses": ex["runtime_basis_tp"]["static"],
                             "wilson95_upper_0_of_executed": round(wilson_upper(0, n_exec), 4),
                             "wilson95_upper_0_of_60": round(wilson_upper(0, 60), 4)}

    (i1 / "analysis" / "round9_numbers.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
