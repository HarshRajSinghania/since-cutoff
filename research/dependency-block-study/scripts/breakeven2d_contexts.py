"""Figure 4 data (round 22): break-even share f* against u in one unit (model calls), at the length of the agent
contexts behind f and with K measured from those contexts' logged usage.

usage: python -I breakeven2d_contexts.py <I1 dir>   ->   <I1>/analysis/breakeven2d_contexts.json
No model sessions; reads analysis/exposure2_breakeven.json (gross saving s per study, block sizes, prices),
analysis/breakeven_unified.json (contexts' mean model calls t_ctx, measured K per context, the benchmark's model
calls, the control-task u and its bootstrap interval, f_strict and f_upper) and analysis/breakeven2d.json (benchmark K).

Model as breakeven2d.py: c = b (t p_r + p_w) with t in model calls; f*(u) = (c - uK) / (s - uK), clipped to [0, 1],
and 0 once u >= c / K. s is kept as published (its add-back of the benchmark block's own cost priced over CLI turns;
an internal review variant V1). Curves for the three block-size / saving pairs of the earlier Figure 4. Benchmark-length
values in model calls are in scripts/unit_switch_check_out.txt (each study at its own calls per session).
"""
import json
import sys
from pathlib import Path

CURVES = [("main", "G_median_nonempty"), ("main", "AI_median_nonempty"), ("new_tasks", "AI_mean_nonempty")]


def f_star(c, s, uK):
    if uK >= c:
        return 0.0
    return min(1.0, (c - uK) / (s - uK))


def main():
    i1 = Path(sys.argv[1])
    an = i1 / "analysis"
    be = json.loads((an / "exposure2_breakeven.json").read_text(encoding="utf-8"))
    uni = json.loads((an / "breakeven_unified.json").read_text(encoding="utf-8"))
    b2 = json.loads((an / "breakeven2d.json").read_text(encoding="utf-8"))
    p_r, p_w = be["prices_usd_per_mtok"]["cache_read"], be["prices_usd_per_mtok"]["cache_write_1h"]
    base = uni["terms"]["bases"]["all"]
    t_ctx, K_ctx = base["t_ctx"], base["K_ctx"]
    u_pt, u_ci, _ = uni["benchmark_draws"]["u_pooled10"]
    out = {"generated_by": "scripts/breakeven2d_contexts.py",
           "inputs": ["analysis/exposure2_breakeven.json", "analysis/breakeven_unified.json", "analysis/breakeven2d.json"],
           "unit": "model calls (distinct assistant messages)",
           "t_ctx_calls": round(t_ctx, 2), "K_ctx_usd": round(K_ctx, 4),
           "t_bench_calls": round(uni["terms"]["t_bench_calls"], 2), "K_bench_usd": b2["K_control_A_mean_cost_usd"],
           "u_control": {"point": round(u_pt, 5), "ci95": [round(u_ci[0], 5), round(u_ci[1], 5)]},
           "f_measured_all_contexts": {"strict": base["f_point"]["strict"], "upper": base["f_point"]["upper"]},
           "curves": {}}
    for skey, bkey in CURVES:
        st = be["studies"][skey]
        s, T = st["S_gross_usd"], st["by_block_size"][bkey]["T_tokens"]
        d = {"T_tokens": T, "s_usd": round(s, 5)}
        for name, t, K in (("contexts", t_ctx, K_ctx),):
            c = T * (t * p_r + p_w) / 1e6
            d[name] = {"c_usd": round(c, 5), "f_star_u0": round(c / s, 4), "u_pays_at_every_f": round(c / K, 4),
                       "f_star_curve": [[round(u / 10000, 4), round(f_star(c, s, u / 10000 * K), 4)]
                                        for u in range(-300, 151, 5)]}
        out["curves"][f"{skey}|{bkey}"] = d
    (an / "breakeven2d_contexts.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k, v in out["curves"].items():
        print(k, v["T_tokens"], {n: (v[n]["c_usd"], v[n]["f_star_u0"], v[n]["u_pays_at_every_f"])
                                 for n in ("contexts",)})


if __name__ == "__main__":
    main()
