"""Two-parameter break-even: share f of sessions that need a changed API, and the block's effect u on the other sessions.

usage: python -I breakeven2d.py <study dir>   ->   <study>/analysis/breakeven2d.json
(in the published data folder: RUNS_TABLES=runs python scripts/breakeven2d.py data)
No model sessions; existing run tables and analysis JSONs only.

Model (per session, Opus 5.5 list prices, all in USD):
    net(f, u) = f * S + (1 - f) * u * K - O(T)
  S     gross saving in a session that needs a changed API (measured A - C saving plus the benchmark block's own
        overhead; analysis/exposure2_breakeven.json, S_gross_usd of each Opus study);
  O(T)  overhead of a real block of T tokens in every session: T * (turns * p_r + p_w) (one cache read per turn, one
        1-hour cache write; exposure2_breakeven.json overhead_per_session_usd at the random sample's block sizes);
  u     relative cost change of a session that needs no changed API (positive = cheaper), K the mean cost of such a
        session. The earlier one-parameter model is u = 0, where f* = O / S.
Break-even: net = 0 gives f*(u) = (O - u K) / (S - u K), clipped to [0, 1]; the block pays at every f once
u >= O / K, and at a measured f it pays once u >= (O - f S) / ((1 - f) K).
Plausible range of u: 1 - r for the control-task ratio r of C/A on the pooled main + new-task controls (10 tasks;
analysis/pooled_main_tasks2.json, the paper's 0.92 [0.79, 1.05] in tokens, also 0.93 [0.84, 1.04] in cost), at its
point estimate and both 95% bounds. K: mean list cost of A sessions on those control tasks (runs tables), with the mean
A cost on the main study's post-cutoff tasks as a sensitivity. The measured r includes the benchmark block's own
overhead on the control sessions, so 1 - r understates u by that overhead's share of K (reported, not added).
Also reported: r on the controls whose block was empty (C and A then get the same CLAUDE.md, so r there is noise).
"""
import json
import math
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from round5_table1 import load, metrics  # noqa: E402

STUDIES = ("main-2026-09-28", "tasks2-opus55-2026-10-22")  # the pooled main + new-task controls
F_MEASURED = {"f_strict_python_editing": 0.021, "f_upper_python_editing": 0.177}  # analysis/f_sessions.json (rounded as in the paper)


def f_star(O, S, uK):
    if uK >= O:
        return 0.0
    return min(1.0, (O - uK) / (S - uK))  # rounded to 4 decimals by the caller


def ratio(by_task, metric):
    logs = []
    for t, cs in sorted(by_task.items()):
        a = [m[metric] for m in cs.get("A", [])]
        c = [m[metric] for m in cs.get("C", [])]
        if a and c:
            logs.append(math.log(statistics.median(c) / statistics.median(a)))
    return (math.exp(sum(logs) / len(logs)), len(logs)) if logs else (None, 0)


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    an = i1 / "analysis"
    be = json.loads((an / "exposure2_breakeven.json").read_text(encoding="utf-8"))
    pooled = json.loads((an / "pooled_main_tasks2.json").read_text(encoding="utf-8"))
    r9 = json.loads((an / "round9_numbers.json").read_text(encoding="utf-8"))
    p_r, p_w = be["prices_usd_per_mtok"]["cache_read"], be["prices_usd_per_mtok"]["cache_write_1h"]

    # Control sessions: mean A cost (K), benchmark-block overhead in C, empty-block ratio.
    recs = load([rt / s for s in STUDIES])
    ctrl = [r for r in recs if r.get("stratum") != "post-cutoff"]
    a_cost = [metrics(r)["cost"] for r in ctrl if r["condition"] == "A"]
    c_over = [(r.get("condition_config") or {}).get("notes_tokens", 0) * (metrics(r)["turns"] * p_r + p_w) / 1e6
              for r in ctrl if r["condition"] == "C"]
    K_ctrl = statistics.mean(a_cost)
    bench_over_ctrl = statistics.mean(c_over)
    by_task, empty = {}, set()
    for r in ctrl:
        if r["condition"] not in ("A", "C"):
            continue
        by_task.setdefault(r["task"], {}).setdefault(r["condition"], []).append(metrics(r))
        if r["condition"] == "C" and not (r.get("condition_config") or {}).get("notes_tokens"):
            empty.add(r["task"])
    empty_by = {t: cs for t, cs in by_task.items() if t in empty}
    r_empty_cost, n_empty = ratio(empty_by, "cost")
    r_empty_tok, _ = ratio(empty_by, "tokens")
    K_post = r9["live_ab_sizing"]["mean_none_cost_main_usd"]

    cr = pooled["results"]["controls"]["C/A"]["ratios"]
    u_ranges = {}
    for key, metric in (("tokens", "total_tokens"), ("cost", "list_cost_usd")):
        x = cr[metric]
        u_ranges[key] = {"ratio": round(x["ratio"], 4), "ratio_ci95": [round(x["lo"], 4), round(x["hi"], 4)],
                         "u_ci_low": round(1 - x["hi"], 4), "u_point": round(1 - x["ratio"], 4),
                         "u_ci_high": round(1 - x["lo"], 4)}

    sizes = {"G_median_nonempty": "random-sample median non-empty block",
             "AI_median_nonempty": "AI-stack median non-empty block",
             "G_mean_nonempty": "random-sample mean non-empty block",
             "AI_mean_nonempty": "AI-stack mean non-empty block"}
    savings = {"main": "main study", "new_tasks": "new tasks", "replication": "replication",
               "pooled_main_new": "main + new pool"}

    out = {"generated_by": "scripts/breakeven2d.py",
           "inputs": ["analysis/exposure2_breakeven.json", "analysis/pooled_main_tasks2.json",
                      "analysis/round9_numbers.json", "runs_tables/main-2026-09-28/runs.jsonl",
                      "runs_tables/tasks2-opus55-2026-10-22/runs.jsonl"],
           "model": "net(f,u) = f*S + (1-f)*u*K - O(T); f*(u) = (O - uK)/(S - uK) clipped to [0,1]; pays at every f "
                    "when u >= O/K. u > 0: sessions that need no changed API get cheaper.",
           "K_control_A_mean_cost_usd": round(K_ctrl, 4),
           "K_control_A_sessions": len(a_cost),
           "K_post_cutoff_A_mean_cost_main_usd": round(K_post, 4),
           "benchmark_block_overhead_control_C_mean_usd": round(bench_over_ctrl, 5),
           "benchmark_block_overhead_share_of_K": round(bench_over_ctrl / K_ctrl, 4),
           "empty_block_controls": {"tasks": n_empty, "tasks_list": sorted(empty),
                                    "per_task_CA_token_ratio": {t: round(statistics.median([m["tokens"] for m in cs["C"]])
                                                                         / statistics.median([m["tokens"] for m in cs["A"]]), 4)
                                                                for t, cs in sorted(empty_by.items())},
                                    "CA_cost_ratio": round(r_empty_cost, 4), "CA_token_ratio": round(r_empty_tok, 4),
                                    "note": "C and A get the same CLAUDE.md on these tasks; the ratio is noise"},
           "u_range_from_controls": u_ranges,
           "measured_f": F_MEASURED,
           "scenarios": {}}

    for skey, slabel in savings.items():
        st = be["studies"][skey]
        S = st["S_gross_usd"]
        for bkey, blabel in sizes.items():
            b = st["by_block_size"][bkey]
            O = b["overhead_per_session_usd"]
            sc = {"saving": slabel, "block": blabel, "T_tokens": b["T_tokens"], "S_gross_usd": round(S, 4),
                  "O_usd": O, "f_star_u0": round(O / S, 4)}
            for kname, K in (("K_control", K_ctrl), ("K_post_cutoff", K_post)):
                d = {"u_pays_at_every_f": round(O / K, 4)}
                for fname, fv in F_MEASURED.items():
                    d[f"u_needed_at_{fname}"] = round((O - fv * S) / ((1 - fv) * K), 4)
                for ukey, ur in u_ranges.items():
                    d[f"f_star_{ukey}"] = {lab: round(f_star(O, S, ur[lab] * K), 4)
                                           for lab in ("u_ci_low", "u_point", "u_ci_high")}
                d["f_star_curve"] = [[round(u / 1000, 3), round(f_star(O, S, u / 1000 * K), 4)]
                                     for u in range(-100, 251, 5)]
                sc[kname] = d
            out["scenarios"][f"{skey}|{bkey}"] = sc

    # Net-saving grid for the primary scenario (main-study saving, random-sample median block, K from controls).
    st = be["studies"]["main"]
    S, O = st["S_gross_usd"], st["by_block_size"]["G_median_nonempty"]["overhead_per_session_usd"]
    out["net_saving_grid_primary"] = {
        "scenario": "main|G_median_nonempty, K_control",
        "f": [round(i / 20, 2) for i in range(21)],
        "u": [round(j / 100, 2) for j in range(-10, 26)],
        "net_usd_per_session": [[round(f / 20 * S + (1 - f / 20) * (j / 100) * K_ctrl - O, 5)
                                 for j in range(-10, 26)] for f in range(21)],
        "net_share_of_K": [[round((f / 20 * S + (1 - f / 20) * (j / 100) * K_ctrl - O) / K_ctrl, 4)
                            for j in range(-10, 26)] for f in range(21)]}

    p = an / "breakeven2d.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    prim = out["scenarios"]["main|G_median_nonempty"]["K_control"]
    print("K_control", round(K_ctrl, 4), "bench share", round(bench_over_ctrl / K_ctrl, 4),
          "empty-block r cost/tok", round(r_empty_cost, 3), round(r_empty_tok, 3), n_empty)
    print("u ranges", u_ranges)
    for k, sc in out["scenarios"].items():
        kc = sc["K_control"]
        print(k, "f*u0", sc["f_star_u0"], "u_any", kc["u_pays_at_every_f"], "tok", kc["f_star_tokens"],
              "cost", kc["f_star_cost"], "u@2.1%", kc["u_needed_at_f_strict_python_editing"])
    print("wrote", p, "primary", prim["f_star_tokens"])


if __name__ == "__main__":
    main()
