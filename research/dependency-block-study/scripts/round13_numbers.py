"""Round-13 numbers (requested in internal reviews of a draft). No model sessions.

usage: python -I round13_numbers.py <I1 dir>   ->   <I1>/analysis/round13_numbers.json
(in the supplementary archive: RUNS_TABLES=runs python scripts/round13_numbers.py .)
Inputs: analysis/breakeven2d.json, exposure2_breakeven.json, round7_checks.json, round9_numbers.json,
f_sessions.json and the run tables of the Opus studies with a header-only arm (replication, new tasks, concurrent)
and of the main + new-task controls.

1. Header break-even. The model of breakeven2d.py at u = 0: f* = c / s, with c = b (t p_r + p_w) the block's
   cost in every session (b tokens, t mean turns of a treated post-cutoff session, one cache read per turn, one 1-hour
   cache write) and s the gross saving per affected session: the task-averaged mean (A - X) list-cost saving per
   post-cutoff session plus arm X's own benchmark-block overhead (as blocksize_breakeven.py), for X = C (full block)
   and X = H (header alone), computed on the same tasks and sessions. Pools: the registered replication + new-task
   pool (abl + tasks2; 25 tasks) and the post hoc 25-task pool of round6_header.py (replication's 17 original tasks;
   each new task averaged over the new-task and concurrent studies); also each study alone. Block sizes: the full
   block at the random sample's median non-empty block (704 tokens) and at the arm's own benchmark mean; the header at
   its benchmark mean (about 245 tokens; it names one package, so a real header with at least one package is no
   smaller). Uncertainty: task-cluster bootstrap (10,000, seed 20261001; one draw for both arms), percentile CIs, and
   the share of draws in which the header's gross saving is at most its cost (never breaks even).
2. Size cap at the measured f: b_max = f s / (t p_r + p_w) with the main study's gross saving and turns, at
   f = 2.1% (Python-editing f_strict) and 0.84% (all runs), against the benchmark header's size.
3. Fleet example at the measured f: 1,000 sessions a day, 704-token block, main-study saving and turns, u = 0.
4. Sample size to measure u: an unpaired two-sided 5% test with 80% power on log list cost,
   n = 2 (1.96 + 0.84)^2 SD^2 / delta^2 sessions per arm, delta = -ln(1 - c/K) (telling u = 0 from u = c/K = 4.7%),
   SD = session-level SD of log cost of None sessions: control tasks (main + new; sessions that need no changed API)
   and, as in round9_numbers.py, post-cutoff tasks (0.45 main, 0.51 four Opus studies).
5. Six non-empty controls: r on the six main + new controls whose block was non-empty (round7_checks.json),
   K6 = mean A cost on those tasks, u = 1 - r bounds, f* at the bounds for the 704-token block and main saving.
6. Measured f over all runs: u needed at f_strict = 0.84% of all agent runs.
7. Weight of u against f: dnet/du = (1 - f) K, dnet/df = s - uK, ratio at f = 0, u = 0 and at f = 2.1%.
8. c at control-task turns: the same block's cost at the mean C turns of the main + new control sessions.
9. f* at the cost interval's lower bound over all 16 scenarios of breakeven2d.json (main text uses the cost interval).
10. s > c condition: the block pays at every f iff u >= c/K and s >= c; reported per scenario.
"""
import json
import math
import os
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from round5_table1 import load, metrics  # noqa: E402

B, SEED = 10000, 20261001
Z = 1.96 + 0.8416


def pct(xs, lo=2.5, hi=97.5):
    xs = sorted(xs)
    n = len(xs)

    def q(p):
        k = (n - 1) * p / 100
        f = math.floor(k)
        c = min(f + 1, n - 1)
        return xs[f] + (xs[c] - xs[f]) * (k - f)
    return [q(lo), q(hi)]


def per_task(recs, arms, p_r, p_w):
    """task -> arm -> (mean cost, mean own-block overhead, mean turns) over post-cutoff sessions."""
    by = {}
    for r in recs:
        if r.get("stratum") != "post-cutoff" or r["condition"] not in arms:
            continue
        m = metrics(r)
        nt = (r.get("condition_config") or {}).get("notes_tokens") or 0
        by.setdefault(r["task"], {}).setdefault(r["condition"], []).append(
            (m["cost"], nt * (m["turns"] * p_r + p_w) / 1e6, m["turns"], nt))
    out = {}
    for t, cs in by.items():
        if all(cs.get(a) for a in arms):
            out[t] = {a: tuple(statistics.mean(x[i] for x in cs[a]) for i in range(4)) for a in arms}
    return out


def average_studies(*pts):
    """Per-task average of several studies' per-task values (tasks present in all)."""
    common = set.intersection(*(set(p) for p in pts))
    return {t: {a: tuple(statistics.mean(p[t][a][i] for p in pts) for i in range(4)) for a in pts[0][t]}
            for t in common}


def terms(pt, tasks, arm):
    s_net = statistics.mean(pt[t]["A"][0] - pt[t][arm][0] for t in tasks)
    o_bench = statistics.mean(pt[t][arm][1] for t in tasks)
    turns = statistics.mean(pt[t][arm][2] for t in tasks)
    tok = statistics.mean(pt[t][arm][3] for t in tasks)
    return s_net, o_bench, turns, tok


def header_breakeven(pt, p_r, p_w, T_real):
    tasks = sorted(pt)

    def calc(sel):
        r = {}
        for arm in ("C", "H"):
            s_net, o_b, turns, tok = terms(pt, sel, arm)
            r[arm] = {"S_net": s_net, "O_bench": o_b, "S_gross": s_net + o_b, "turns": turns, "bench_tokens": tok}
        per_tok = {a: (r[a]["turns"] * p_r + p_w) / 1e6 for a in ("C", "H")}
        c_H = r["H"]["bench_tokens"] * per_tok["H"]
        c_C_real = T_real * per_tok["C"]
        c_C_bench = r["C"]["bench_tokens"] * per_tok["C"]

        def fs(c, s):
            return c / s if s > c else float("inf")
        return r, {"c_H": c_H, "c_C_704": c_C_real, "c_C_bench": c_C_bench,
                   "f_star_H_bench": fs(c_H, r["H"]["S_gross"]),
                   "f_star_C_704": fs(c_C_real, r["C"]["S_gross"]),
                   "f_star_C_bench": fs(c_C_bench, r["C"]["S_gross"])}

    r, f = calc(tasks)
    rnd = random.Random(SEED)
    draws = []
    for _ in range(B):
        idx = [tasks[rnd.randrange(len(tasks))] for _ in tasks]
        draws.append(calc(idx))
    fh = [d[1]["f_star_H_bench"] for d in draws]
    fc = [d[1]["f_star_C_704"] for d in draws]
    sh = [d[0]["H"]["S_gross"] for d in draws]
    sc = [d[0]["C"]["S_gross"] for d in draws]
    cap = lambda x: min(x, 1.0)  # noqa: E731  (a share above 1 = never breaks even)
    out = {"tasks": len(tasks),
           "H": {"S_net_usd": round(r["H"]["S_net"], 5), "O_bench_usd": round(r["H"]["O_bench"], 5),
                 "S_gross_usd": round(r["H"]["S_gross"], 5), "S_gross_ci95": [round(x, 5) for x in pct(sh)],
                 "mean_turns": round(r["H"]["turns"], 3), "bench_tokens_mean": round(r["H"]["bench_tokens"], 1),
                 "c_usd": round(f["c_H"], 5), "f_star_u0": round(cap(f["f_star_H_bench"]), 4),
                 "f_star_u0_ci95_capped_at_1": [round(cap(x), 4) for x in pct([cap(x) for x in fh])],
                 "share_draws_never_breaks_even": round(sum(x == float("inf") or x > 1 for x in fh) / B, 4)},
           "C": {"S_net_usd": round(r["C"]["S_net"], 5), "O_bench_usd": round(r["C"]["O_bench"], 5),
                 "S_gross_usd": round(r["C"]["S_gross"], 5), "S_gross_ci95": [round(x, 5) for x in pct(sc)],
                 "mean_turns": round(r["C"]["turns"], 3), "bench_tokens_mean": round(r["C"]["bench_tokens"], 1),
                 "c_704_usd": round(f["c_C_704"], 5), "f_star_u0_704": round(cap(f["f_star_C_704"]), 4),
                 "f_star_u0_704_ci95_capped_at_1": [round(cap(x), 4) for x in pct([cap(x) for x in fc])],
                 "share_draws_never_breaks_even_704": round(sum(x == float("inf") or x > 1 for x in fc) / B, 4),
                 "c_bench_usd": round(f["c_C_bench"], 5), "f_star_u0_bench": round(cap(f["f_star_C_bench"]), 4)},
           "header_share_of_gross_saving": round(r["H"]["S_gross"] / r["C"]["S_gross"], 4),
           "share_draws_f_star_H_above_f_star_C_704": round(sum(a > b for a, b in zip(fh, fc)) / B, 4)}
    return out


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    an = i1 / "analysis"
    b2 = json.loads((an / "breakeven2d.json").read_text(encoding="utf-8"))
    be = json.loads((an / "exposure2_breakeven.json").read_text(encoding="utf-8"))
    r7 = json.loads((an / "round7_checks.json").read_text(encoding="utf-8"))
    r9 = json.loads((an / "round9_numbers.json").read_text(encoding="utf-8"))
    fs = json.loads((an / "f_sessions.json").read_text(encoding="utf-8"))
    p_r, p_w = be["prices_usd_per_mtok"]["cache_read"], be["prices_usd_per_mtok"]["cache_write_1h"]
    T = be["block_sizes_tokens"]["G_median_nonempty"]
    main_st = be["studies"]["main"]
    S_main, t_main = main_st["S_gross_usd"], main_st["mean_C_turns"]
    c_main = main_st["by_block_size"]["G_median_nonempty"]["overhead_per_session_usd"]
    K = b2["K_control_A_mean_cost_usd"]
    out = {"generated_by": "scripts/round13_numbers.py",
           "inputs": ["analysis/breakeven2d.json", "analysis/exposure2_breakeven.json", "analysis/round7_checks.json",
                      "analysis/round9_numbers.json", "analysis/f_sessions.json",
                      "runs_tables/{abl-opus55-2026-10-22,tasks2-opus55-2026-10-22,conc-opus55-2026-10-23,"
                      "main-2026-09-28}/runs.jsonl"],
           "method": __doc__.split("usage:")[0].strip()}

    # 1. Header break-even
    abl = per_task(load([rt / "abl-opus55-2026-10-22"]), ("A", "C", "H"), p_r, p_w)
    t2 = per_task(load([rt / "tasks2-opus55-2026-10-22"]), ("A", "C", "H"), p_r, p_w)
    conc = per_task(load([rt / "conc-opus55-2026-10-23"]), ("A", "C", "H"), p_r, p_w)
    pools = {"registered_replication_plus_new": {**abl, **t2},
             "post_hoc_25_task_pool": {**abl, **average_studies(t2, conc)},
             "replication": abl, "new_tasks": t2, "concurrent": conc}
    out["header_breakeven_u0"] = {k: header_breakeven(v, p_r, p_w, T) for k, v in pools.items()}
    out["header_breakeven_u0"]["note"] = ("H = header alone at its benchmark size (one package named; a real header is "
                                          "no smaller); C = full block at 704 tokens (random-sample median non-empty "
                                          "block) and at its benchmark size; s and c on the same tasks and sessions")

    # 2. Size cap at the measured f
    per_tok_main = (t_main * p_r + p_w) / 1e6
    f_py = fs["primary"]["given_edit_py"]["strict"]["share"]
    f_all = fs["primary"]["strict"]["share"]
    h_tok = out["header_breakeven_u0"]["registered_replication_plus_new"]["H"]["bench_tokens_mean"]
    out["size_cap_at_measured_f"] = {
        "b_max_per_unit_f_main": round(S_main / per_tok_main, 1),
        "f_strict_python_editing": f_py, "b_max_tokens_at_f_python_editing": round(f_py * S_main / per_tok_main, 1),
        "b_max_tokens_at_f_0.021": round(0.021 * S_main / per_tok_main, 1),
        "f_strict_all_runs": f_all, "b_max_tokens_at_f_all_runs": round(f_all * S_main / per_tok_main, 1),
        "benchmark_header_tokens_mean": h_tok, "note": "u = 0; main-study gross saving and turns"}

    # 3. Fleet example at the measured f (paper rounds f to 2.1%)
    f_r = 0.021
    out["fleet_example_measured_f"] = {
        "sessions_per_day": 1000, "f": f_r, "block_tokens": T,
        "block_cost_usd_per_day": round(1000 * c_main, 2), "gross_saving_usd_per_day": round(1000 * f_r * S_main, 2),
        "net_usd_per_day": round(1000 * f_r * S_main - 1000 * c_main, 2), "u": 0}

    # 4. Sample size to measure u
    recs = load([rt / "main-2026-09-28", rt / "tasks2-opus55-2026-10-22"])
    ctrl_A = [math.log(metrics(r)["cost"]) for r in recs if r.get("stratum") != "post-cutoff" and r["condition"] == "A"]
    sd_ctrl = statistics.stdev(ctrl_A)
    u_pivot = b2["scenarios"]["main|G_median_nonempty"]["K_control"]["u_pays_at_every_f"]
    delta = -math.log(1 - u_pivot)
    n = lambda sd: math.ceil(2 * Z ** 2 * sd ** 2 / delta ** 2)  # noqa: E731
    sd_main = r9["live_ab_sizing"]["sd_log_cost_none_sessions_main"]
    sd_all = r9["live_ab_sizing"]["sd_log_cost_none_sessions_4_opus_studies"]
    out["sample_size_to_measure_u"] = {
        "u_pivot_c_over_K": u_pivot, "delta_log": round(delta, 4),
        "sd_log_cost_none_control_sessions": round(sd_ctrl, 3), "none_control_sessions": len(ctrl_A),
        "n_per_arm_sd_controls": n(sd_ctrl), "n_per_arm_sd_post_cutoff_main": n(sd_main),
        "n_per_arm_sd_post_cutoff_4_opus": n(sd_all),
        "test": "unpaired two-sided 5%, 80% power, independent sessions; tells u = 0 from u = c/K"}

    # 5. Six non-empty controls
    ne = r7["controls_exact"]
    ne_tasks = set(ne["non_empty_block_control_tasks"])
    a6 = [metrics(r)["cost"] for r in recs if r.get("stratum") != "post-cutoff" and r["condition"] == "A"
          and r["task"] in ne_tasks]
    K6 = statistics.mean(a6)
    six = {"tasks": sorted(ne_tasks), "K6_usd": round(K6, 4), "A_sessions": len(a6)}
    for key, metric in (("tokens", "C/A_non_empty_controls_main+new_tokens"),
                        ("cost", "C/A_non_empty_controls_main+new_cost")):
        x = ne[metric]
        u_lo, u_hi = 1 - x["hi"], 1 - x["lo"]
        fstar = (lambda u: 0.0 if u * K6 >= c_main else min(1.0, (c_main - u * K6) / (S_main - u * K6)))
        six[key] = {"ratio": x["ratio"], "ci95": [x["lo"], x["hi"]], "signflip_p": x["signflip_p"],
                    "u_ci_low": round(u_lo, 4), "u_point": round(1 - x["ratio"], 4), "u_ci_high": round(u_hi, 4),
                    "f_star_704_main_at_u_ci_low": round(fstar(u_lo), 4)}
    six["u_pays_at_every_f_704_main"] = round(c_main / K6, 4)
    out["six_nonempty_controls"] = six

    # 6. u needed at the all-run f_strict (704-token block, main saving, K from the 10 controls)
    out["u_needed_at_f_all_runs"] = {"f": f_all, "u": round((c_main - f_all * S_main) / ((1 - f_all) * K), 4),
                                     "f_python_editing_rounded": 0.021,
                                     "u_at_f_python_editing": round((c_main - 0.021 * S_main) / ((1 - 0.021) * K), 4)}

    # 7. Weight of u against f
    out["weight_u_vs_f"] = {"dnet_du_f0": round(K, 4), "dnet_df_u0": round(S_main, 4),
                            "ratio_f0_u0": round(K / S_main, 3),
                            "ratio_f_0.021_u0": round((1 - 0.021) * K / S_main, 3)}

    # 8. c at control-task turns
    c_turns = [metrics(r)["turns"] for r in recs if r.get("stratum") != "post-cutoff" and r["condition"] == "C"]
    t_ctrl = statistics.mean(c_turns)
    out["c_at_control_turns"] = {"mean_C_turns_controls": round(t_ctrl, 2), "mean_C_turns_post_cutoff_main": round(t_main, 2),
                                 "c_704_control_turns_usd": round(T * (t_ctrl * p_r + p_w) / 1e6, 5),
                                 "c_704_post_cutoff_turns_usd": round(c_main, 5)}

    # 9-10. Scenarios at the cost interval; s > c
    sc = {}
    for k, v in b2["scenarios"].items():
        kc = v["K_control"]
        sc[k] = {"T": v["T_tokens"], "f_star_u0": v["f_star_u0"], "f_star_cost_low": kc["f_star_cost"]["u_ci_low"],
                 "f_star_tokens_low": kc["f_star_tokens"]["u_ci_low"], "s_gt_c": v["S_gross_usd"] > v["O_usd"]}
    worst_cost = max(sc.items(), key=lambda kv: kv[1]["f_star_cost_low"])
    worst_tok = max(sc.items(), key=lambda kv: kv[1]["f_star_tokens_low"])
    out["scenarios_cost_interval"] = {
        "u_cost_ci_low": b2["u_range_from_controls"]["cost"]["u_ci_low"],
        "u_cost_ci_high": b2["u_range_from_controls"]["cost"]["u_ci_high"],
        "f_star_cost_low_range": [min(x["f_star_cost_low"] for x in sc.values()), worst_cost[1]["f_star_cost_low"]],
        "worst_scenario_cost_low": worst_cost[0],
        "f_star_tokens_low_range": [min(x["f_star_tokens_low"] for x in sc.values()), worst_tok[1]["f_star_tokens_low"]],
        "worst_scenario_tokens_low": worst_tok[0],
        "all_s_gt_c": all(x["s_gt_c"] for x in sc.values()),
        "per_scenario": sc,
        "s_gt_c_11100_token_block_main": S_main > 11100 * per_tok_main,
        "c_11100_token_block_main_usd": round(11100 * per_tok_main, 4)}

    p = an / "round13_numbers.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k in ("header_breakeven_u0",):
        for pk, pv in out[k].items():
            if isinstance(pv, dict):
                print(pk, "H f*", pv["H"]["f_star_u0"], pv["H"]["f_star_u0_ci95_capped_at_1"], "never",
                      pv["H"]["share_draws_never_breaks_even"], "| C704 f*", pv["C"]["f_star_u0_704"],
                      pv["C"]["f_star_u0_704_ci95_capped_at_1"], "never", pv["C"]["share_draws_never_breaks_even_704"], "C bench", pv["C"]["f_star_u0_bench"],
                      "H/C gross", pv["header_share_of_gross_saving"], "P(fH>fC)",
                      pv["share_draws_f_star_H_above_f_star_C_704"], "Htok", pv["H"]["bench_tokens_mean"],
                      "SgH", pv["H"]["S_gross_usd"], "SgC", pv["C"]["S_gross_usd"])
    for k in ("size_cap_at_measured_f", "fleet_example_measured_f", "sample_size_to_measure_u",
              "six_nonempty_controls", "u_needed_at_f_all_runs", "weight_u_vs_f", "c_at_control_turns"):
        print(k, json.dumps(out[k]))
    s = dict(out["scenarios_cost_interval"])
    s.pop("per_scenario")
    print("scenarios", json.dumps(s))
    print("wrote", p)


if __name__ == "__main__":
    main()
