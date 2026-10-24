"""Unit-switch check (round 22 verifier): every benchmark-length number recomputed with t = model calls.

The paper prices the block as c = b (t p_r + p_w), one cache read per model call plus one 1-hour cache write. Its
benchmark-length t is the CLI's num_turns (16.6 in the main study), which counts tool round trips; the contexts behind
f are counted in model calls (distinct assistant message ids with a real model id; scripts/context_cost.py). This
script recounts every benchmark session in model calls (scripts/turns_vs_calls.py method) and prints each benchmark-
length number of main.tex twice: as now (num_turns) and with model calls. Two variants for the calls column:
  V1  only t changes; s (S_gross) kept as in analysis/exposure2_breakeven.json;
  V2  t changes and S_gross = S_net + O_bench is recomputed with O_bench (the benchmark block's own cost, added back
      to the measured saving) also priced over model calls, so both terms share one unit.
Each "turns" value is checked against the JSON it came from (reproduction lines), so the calls values use the same
code path. Per-context values (45.3 / 81.6 calls) are already in model calls; under V2 they shift only through s, so
they are printed too.

usage: python -I scripts/unit_switch_check.py   ->   prints; also written to scripts/unit_switch_check_out.txt
Inputs: <study>/runs_tables (runs, usage, notes_tokens, num_turns); stream.jsonl logs (BENCH and RUNS, as turns_vs_calls.py);
analysis/exposure2_breakeven.json, breakeven2d.json, round9_numbers.json, round13_numbers.json, f_sessions.json;
recompute_cost.PRICES. Counts and dollar aggregates only; no transcript content is printed.
"""
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
AN = STUDY / "analysis"
OUT = HERE / "unit_switch_check_out.txt"
sys.path.insert(0, str(HERE))
from recompute_cost import PRICES, list_cost  # noqa: E402
from turns_vs_calls import count, load, stream_path  # noqa: E402

P_R, P_W = PRICES["claude-opus-5-5"][2] / 1e6, PRICES["claude-opus-5-5"][3] / 1e6
STUDY = {"main": ["main-2026-09-28"], "replication": ["abl-opus55-2026-10-22"],
         "new_tasks": ["tasks2-opus55-2026-10-22"],
         "pooled_main_new": ["main-2026-09-28", "tasks2-opus55-2026-10-22"]}
eb = json.loads((AN / "exposure2_breakeven.json").read_text(encoding="utf-8"))
b2 = json.loads((AN / "breakeven2d.json").read_text(encoding="utf-8"))
r9 = json.loads((AN / "round9_numbers.json").read_text(encoding="utf-8"))["live_ab_sizing"]
r13 = json.loads((AN / "round13_numbers.json").read_text(encoding="utf-8"))
fs = json.loads((AN / "f_sessions.json").read_text(encoding="utf-8"))["primary"]
SIZES = {k: v for k, v in eb["block_sizes_tokens"].items()} if isinstance(eb["block_sizes_tokens"], dict) else {}
K = b2["K_control_A_mean_cost_usd"]                      # 0.1717
K_POST = b2["K_post_cutoff_A_mean_cost_main_usd"]        # 0.4193
U_COST = b2["u_range_from_controls"]["cost"]             # -0.037 .. 0.0663 .. 0.1569
U_TOK = b2["u_range_from_controls"]["tokens"]            # -0.0532 ..
K6 = r13["six_nonempty_controls"]["K6_usd"]
U6_LO = r13["six_nonempty_controls"]["cost"]["u_ci_low"]
SD_CTRL = r13["sample_size_to_measure_u"]["sd_log_cost_none_control_sessions"]
SD_MAIN, SD_ALL = r9["sd_log_cost_none_sessions_main"], r9["sd_log_cost_none_sessions_4_opus_studies"]
Z13, Z9 = 1.96 + 0.8416, 1.959964 + 0.841621             # as round13_numbers.py / round9_numbers.py

_cache = {}


def calls_of(study, run_id):
    key = (study, run_id)
    if key not in _cache:
        p = stream_path(study, run_id)
        _cache[key] = count(p)[0] if p else None
    return _cache[key]


def sessions(studies, post=True):
    pt = defaultdict(lambda: defaultdict(list))
    missing = 0
    for st in studies:
        for r in load(st):
            if (r["stratum"] == "post-cutoff") != post or r["condition"] not in ("A", "C"):
                continue
            res = r.get("result") or {}
            ca = calls_of(st, r["run_id"])
            missing += ca is None
            pt[r["task"]][r["condition"]].append({
                "cost": list_cost(r["agent"]["model"], res.get("usage") or {}), "turns": res.get("num_turns") or 0,
                "calls": ca or 0, "notes": (r.get("condition_config") or {}).get("notes_tokens") or 0})
    return {t: cs for t, cs in sorted(pt.items()) if cs.get("A") and cs.get("C")}, missing


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def terms(pt, unit):
    s_net = mean(mean(s["cost"] for s in pt[t]["A"]) - mean(s["cost"] for s in pt[t]["C"]) for t in pt)
    o_bench = mean(mean(s["notes"] * (s[unit] * P_R + P_W) for s in pt[t]["C"]) for t in pt)
    t_c = mean(mean(s[unit] for s in pt[t]["C"]) for t in pt)
    return s_net, o_bench, t_c


def c_of(b, t):
    return b * (t * P_R + P_W)


def fstar(c, s, u, k=K):
    return 0.0 if u * k >= c else min(1.0, (c - u * k) / (s - u * k))


L = []


def say(x=""):
    L.append(x)


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


say("unit_switch_check.py: benchmark-length numbers with t = CLI num_turns (as in the paper) and t = model calls")
say(f"prices p_r = ${P_R * 1e6:.2f}, p_w = ${P_W * 1e6:.2f} per MTok; K = ${K}; K_post = ${K_POST}; "
    f"block sizes {SIZES}")

# ------------------------------------------------------------------ per-study terms
ST = {}
say("\n[1] Per-study terms (post-cutoff C sessions; task means)")
for key, sts in STUDY.items():
    pt, miss = sessions(sts)
    sn, ob_t, t_t = terms(pt, "turns")
    _, ob_c, t_c = terms(pt, "calls")
    ref = eb["studies"][key]
    ST[key] = {"S_net": sn, "S_turns": sn + ob_t, "S_calls": sn + ob_c, "t_turns": t_t, "t_calls": t_c,
               "S_json": ref["S_gross_usd"], "t_json": ref["mean_C_turns"]}
    say(f"  {key}: tasks {len(pt)}, missing streams {miss}; num_turns {t_t:.2f} (json {ref['mean_C_turns']:.2f}), "
        f"model calls {t_c:.2f}; S_gross at turns ${sn + ob_t:.5f} (json ${ref['S_gross_usd']:.5f}, "
        f"{'MATCH' if abs(sn + ob_t - ref['S_gross_usd']) < 1e-9 else 'DIFF'}), S_gross with O_bench at calls "
        f"${sn + ob_c:.5f}")

m = ST["main"]


def S(key, var):
    return ST[key]["S_json"] if var in ("turns", "V1") else ST[key]["S_calls"]


def T(key, var):
    return ST[key]["t_turns"] if var == "turns" else ST[key]["t_calls"]


VARS = ("turns", "V1", "V2")

# ------------------------------------------------------------------ worked example and Table ctxcost benchmark row
say("\n[2] Worked example (704 tokens, main study): c, f* at u = 0, c/K; Table ctxcost benchmark row")
for v in VARS:
    c = c_of(704, T("main", v))
    say(f"  {v:5s}: t = {T('main', v):.2f}, c = ${c:.5f}, s = ${S('main', v):.5f}, f*(u=0) = {pct(c / S('main', v), 2)}, "
        f"c/K = {pct(c / K, 2)}")

# ------------------------------------------------------------------ range over sizes and savings
say("\n[3] u = 0 break-even over 4 block sizes x 4 savings (paper: 9.1--30.2%; 704/main .. 1,320/new tasks)")
for v in VARS:
    vals = {(sk, bk): c_of(b, T(sk, v)) / S(sk, v) for sk in STUDY for bk, b in SIZES.items()}
    lo, hi = min(vals.values()), max(vals.values())
    say(f"  {v:5s}: 704/main {pct(vals[('main', 'G_median_nonempty')])}, 1,320/new {pct(vals[('new_tasks', 'AI_mean_nonempty')])}; "
        f"min {pct(lo)}, max {pct(hi)}")
    say(f"         App. D line 808 set: main 704 {pct(vals[('main', 'G_median_nonempty')])}, 1,024.5 "
        f"{pct(vals[('main', 'AI_median_nonempty')])}, 1,014 {pct(vals[('main', 'G_mean_nonempty')])}, 1,320 "
        f"{pct(vals[('main', 'AI_mean_nonempty')])}; new tasks 704 {pct(vals[('new_tasks', 'G_median_nonempty')])}, "
        f"1,024.5 {pct(vals[('new_tasks', 'AI_median_nonempty')])}, 1,320 {pct(vals[('new_tasks', 'AI_mean_nonempty')])}")

# ------------------------------------------------------------------ interval bounds
say("\n[4] f* at the u interval bounds and c/K over the 16 scenarios (App. D)")
for v in VARS:
    c = c_of(704, T("main", v)); s = S("main", v)
    fc = [fstar(c_of(b, T(sk, v)), S(sk, v), U_COST["u_ci_low"]) for sk in STUDY for b in SIZES.values()]
    ft = [fstar(c_of(b, T(sk, v)), S(sk, v), U_TOK["u_ci_low"]) for sk in STUDY for b in SIZES.values()]
    ua = [c_of(b, T(sk, v)) / K for sk in STUDY for b in SIZES.values()]
    say(f"  {v:5s}: 704/main f* at u = {U_COST['u_ci_low']} {pct(fstar(c, s, U_COST['u_ci_low']))}, at u = "
        f"{U_TOK['u_ci_low']} {pct(fstar(c, s, U_TOK['u_ci_low']))}; 16 scenarios: cost bound {pct(min(fc))}--"
        f"{pct(max(fc))}, token bound {pct(min(ft))}--{pct(max(ft))}, pays at every f from u = {pct(min(ua))}--{pct(max(ua))}")
    say(f"         K = ${K_POST}: c/K {pct(c / K_POST)}, f* at u = {U_COST['u_ci_low']} "
        f"{pct(fstar(c, s, U_COST['u_ci_low'], K_POST), 0)}; six non-empty controls (K = ${K6}, u = {U6_LO}): f* "
        f"{pct(fstar(c, s, U6_LO, K6), 0)}, c/K6 {pct(c / K6)}; weight ratio K/s {K / s:.2f}")

# ------------------------------------------------------------------ sample size to tell u = 0 from u = c/K
say("\n[5] Sessions per arm to tell u = 0 from u = c/K (round13 method: c/K rounded to 4 decimals, Z = 2.8016)")
for v in VARS:
    cK = round(c_of(704, T("main", v)) / K, 4)
    d = -math.log(1 - cK)
    ns = [math.ceil(2 * Z13 ** 2 * sd ** 2 / d ** 2) for sd in (SD_CTRL, SD_MAIN, SD_ALL)]
    say(f"  {v:5s}: c/K {cK}: SD {SD_CTRL} -> {ns[0]}, SD {SD_MAIN} -> {ns[1]}, SD {SD_ALL} -> {ns[2]}")
say(f"  (round13_numbers.json at turns: {r13['sample_size_to_measure_u']['n_per_arm_sd_controls']}, "
    f"{r13['sample_size_to_measure_u']['n_per_arm_sd_post_cutoff_main']}, "
    f"{r13['sample_size_to_measure_u']['n_per_arm_sd_post_cutoff_4_opus']})")

# ------------------------------------------------------------------ live A/B over all sessions
say("\n[6] Live A/B over all sessions (round9 method; SDs as rounded in round9_numbers.json)")
for v in VARS:
    c = c_of(704, T("main", v)); s = S("main", v)
    row = []
    for f in (0.1, 0.2):
        dd = (f * s - c) / K_POST
        delta = -math.log(1 - dd)
        row.append(f"f = {f}: net {pct(dd, 2)}, n {round(2 * Z9 ** 2 * SD_MAIN ** 2 / delta ** 2):,}--"
                   f"{round(2 * Z9 ** 2 * SD_ALL ** 2 / delta ** 2):,}")
    say(f"  {v:5s}: " + "; ".join(row))
say(f"  (round9_numbers.json at turns: f = 0.2 net {r9['diluted_net_saving_share_f_0.2']}, n "
    f"{r9['sessions_per_arm_all_sessions_f_0.2_main_sd']}--{r9['sessions_per_arm_all_sessions_f_0.2_all_sd']}; f = 0.1 "
    f"net {r9['diluted_net_saving_share_f_0.1']})")

# ------------------------------------------------------------------ size cap
say("\n[7] Size cap b_max = f s / (t p_r + p_w) at u = 0, tokens per unit f (main / replication / new tasks)")
for v in VARS:
    co = [S(k, v) / (T(k, v) * P_R + P_W) for k in ("main", "replication", "new_tasks")]
    say(f"  {v:5s}: {co[0]:,.0f} / {co[1]:,.0f} / {co[2]:,.0f}; main at f = 0.1 {0.1 * co[0]:,.0f}, at 0.2 {0.2 * co[0]:,.0f}")

# ------------------------------------------------------------------ fleet and per-size costs
say("\n[8] Fleet of 1,000 sessions a day, f = 0.2, u = 0, main study; c at other sizes")
for v in VARS:
    t, s = T("main", v), S("main", v)
    parts = []
    for b in (764, 704):
        c = c_of(b, t)
        parts.append(f"{b} tokens: pays ${1000 * c:.2f} (${c:.4f}/session), saves ${200 * s:.2f}, net ${200 * s - 1000 * c:.2f}")
    say(f"  {v:5s}: " + "; ".join(parts))
    say(f"         c at 423 / 764 / 1,329 tokens: ${c_of(423, t):.4f} / ${c_of(764, t):.4f} / ${c_of(1329, t):.4f}; "
        f"11,100 tokens: ${c_of(11100, t):.3f} vs s ${s:.3f}")

# ------------------------------------------------------------------ control sessions
say("\n[9] Control sessions (main + new tasks, C): c of the 704-token block; benchmark block's own cost / K")
recs_c = []
for st in STUDY["pooled_main_new"]:
    for r in load(st):
        if r["stratum"] != "post-cutoff" and r["condition"] == "C":
            recs_c.append((r, calls_of(st, r["run_id"])))
tt = statistics.mean((r.get("result") or {}).get("num_turns") or 0 for r, _ in recs_c)
tc = statistics.mean(ca for _, ca in recs_c)
ov_t = statistics.mean(((r.get("condition_config") or {}).get("notes_tokens") or 0) *
                       (((r.get("result") or {}).get("num_turns") or 0) * P_R + P_W) for r, _ in recs_c)
ov_c = statistics.mean(((r.get("condition_config") or {}).get("notes_tokens") or 0) * (ca * P_R + P_W)
                       for r, ca in recs_c)
say(f"  sessions {len(recs_c)}: num_turns {tt:.2f} -> c ${c_of(704, tt):.4f}; model calls {tc:.2f} -> c ${c_of(704, tc):.4f}")
say(f"  benchmark block's own cost / K: at turns {pct(ov_t / K)} (breakeven2d.json "
    f"{pct(b2['benchmark_block_overhead_share_of_K'])}); at calls {pct(ov_c / K)}")

# ------------------------------------------------------------------ per-context values under V2
say("\n[10] Per-context values (already model calls); V2 changes only s")
FA = (fs["strict"]["share"], fs["upper"]["share"])
FP = (fs["given_edit_py"]["strict"]["share"], fs["given_edit_py"]["upper"]["share"])
for v in ("turns", "V2"):
    s = S("main", v)
    for name, t, ff in (("all contexts", 45.26, FA), ("Python-editing", 81.55, FP)):
        c = c_of(704, t)
        un = [(c - f * s) / (K * (1 - f)) for f in ff]
        say(f"  {v:5s} {name}: f*(u=0) {pct(c / s, 2)}, f*(u=6.63%) {pct(fstar(c, s, U_COST['u_point']), 2)}, "
            f"f*(u=-3.7%) {pct(fstar(c, s, U_COST['u_ci_low']))}, u needed at f_strict {pct(un[0])}, at f_upper "
            f"{pct(un[1])}, cap {ff[0] * s / (t * P_R + P_W):.0f} / {ff[1] * s / (t * P_R + P_W):.0f} tokens, "
            f"fleet saves ${1000 * ff[0] * s:.2f} / ${1000 * ff[1] * s:.2f}")
    hi = fstar(c_of(1320, 45.26), S("new_tasks", v), 0)
    say(f"  {v:5s} all-context u = 0 range 704/main .. 1,320/new: {pct(c_of(704, 45.26) / s)} .. {pct(hi)}; "
        f"$0.56 per session / s = {0.56 / s:.2f}")

say("\n[11b] Sessions per arm to tell u = 0 from u = c/K at the contexts' length (Table 3 Default/Size basis)")
for name, t in (("all contexts", 45.26), ("Python-editing", 81.55)):
    cK = round(c_of(704, t) / K, 4)
    d = -math.log(1 - cK)
    ns = [math.ceil(2 * Z13 ** 2 * sd ** 2 / d ** 2) for sd in (SD_CTRL, SD_MAIN, SD_ALL)]
    say(f"  {name}: c/K {cK}: SD {SD_CTRL} -> {ns[0]}, SD {SD_MAIN} -> {ns[1]}, SD {SD_ALL} -> {ns[2]}")

say("\n[11] Ratio of contexts' length to benchmark length: 45.26 / num_turns "
    f"{45.26 / m['t_turns']:.2f}; 45.26 / calls {45.26 / m['t_calls']:.2f}")


# ------------------------------------------------------------------ re-runs of two existing scripts with t = calls
class _Sink:
    """Stands in for a script's output path so that nothing is written."""
    def __init__(self):
        self.text = None
        self.name = "(not written)"

    def write_text(self, text, encoding=None):
        self.text = text


def header_breakeven_calls():
    """round13_numbers.header_breakeven (App. D 'Header break-even') with t = model calls.
    V1: c over calls, s's add-back (each arm's own benchmark block) over num_turns; V2: both over calls."""
    import round13_numbers as rn
    rt = STUDY / "runs_tables"

    def per_task(study, mode):
        by = {}
        for r in rn.load([rt / study]):
            if r.get("stratum") != "post-cutoff" or r["condition"] not in ("A", "C", "H"):
                continue
            mm = rn.metrics(r)
            nt = (r.get("condition_config") or {}).get("notes_tokens") or 0
            ca = calls_of(study, r["run_id"])
            t_c = mm["turns"] if mode == "turns" else ca
            t_o = ca if mode == "V2" else mm["turns"]
            by.setdefault(r["task"], {}).setdefault(r["condition"], []).append(
                (mm["cost"], nt * (t_o * P_R + P_W), t_c, nt))
        return {t: {a: tuple(statistics.mean(x[i] for x in cs[a]) for i in range(4)) for a in ("A", "C", "H")}
                for t, cs in by.items() if all(cs.get(a) for a in ("A", "C", "H"))}
    res = {}
    for mode in VARS:
        abl, t2 = per_task("abl-opus55-2026-10-22", mode), per_task("tasks2-opus55-2026-10-22", mode)
        conc = per_task("conc-opus55-2026-10-23", mode)
        pools = {"registered": {**abl, **t2}, "post_hoc": {**abl, **rn.average_studies(t2, conc)},
                 "replication": abl, "new_tasks": t2, "concurrent": conc}
        res[mode] = {k: rn.header_breakeven(v, P_R * 1e6, P_W * 1e6, 704) for k, v in pools.items()}
    ref = r13["header_breakeven_u0"]
    say("\n[12] Header break-even (App. D), round13_numbers.header_breakeven re-run; turns rows checked against "
        "round13_numbers.json")
    for mode in VARS:
        for k, v in res[mode].items():
            H, C = v["H"], v["C"]
            chk = ""
            if mode == "turns":
                rk = {"registered": "registered_replication_plus_new", "post_hoc": "post_hoc_25_task_pool"}.get(k, k)
                ok = (ref[rk]["H"]["f_star_u0"] == H["f_star_u0"] and ref[rk]["C"]["f_star_u0_704"] == C["f_star_u0_704"])
                chk = " MATCH" if ok else " DIFF"
            say(f"  {mode:5s} {k}: H s ${H['S_gross_usd']:.3f}, f* {pct(H['f_star_u0'])} (never {pct(H['share_draws_never_breaks_even'])}); "
                f"C s ${C['S_gross_usd']:.3f}, f* at 704 {pct(C['f_star_u0_704'])} (never {pct(C['share_draws_never_breaks_even_704'])}), at bench size {pct(C['f_star_u0_bench'])}; "
                f"H/C gross {pct(v['header_share_of_gross_saving'], 0)}; P(fH > fC704) "
                f"{pct(v['share_draws_f_star_H_above_f_star_C_704'], 0)}{chk}")


def blocksize_calls():
    """blocksize_breakeven.analyse (App. D 'Block size and break-even', convenience sample) with t = model calls.
    V1: the benchmark block's add-back stays over num_turns (notes scaled so that notes x (calls p_r + p_w) equals
    notes x (num_turns p_r + p_w)); V2: add-back over calls."""
    import blocksize_breakeven as bb
    from recompute_cost import list_cost as lc
    import contextlib
    import io
    ref = json.loads((AN / "blocksize_breakeven.json").read_text(encoding="utf-8"))
    orig, orig_out = bb.sessions, bb.OUT
    runs = {"turns": ref}
    for mode in ("V1", "V2"):
        def sessions(studies, stratum="post-cutoff", _m=mode):
            pt = defaultdict(lambda: defaultdict(list))
            for st in studies:
                for r in bb.load(st):
                    if (r["stratum"] == "post-cutoff") != (stratum == "post-cutoff") or r["condition"] not in ("A", "C"):
                        continue
                    res = r.get("result") or {}
                    ca = calls_of(st, r["run_id"]) or 0
                    nt_ = res.get("num_turns") or 0
                    notes = (r.get("condition_config") or {}).get("notes_tokens") or 0
                    if _m == "V1" and notes:
                        notes = notes * (nt_ * P_R + P_W) / (ca * P_R + P_W)
                    pt[r["task"]][r["condition"]].append({
                        "cost": lc(r["agent"]["model"], res.get("usage") or {}), "turns": ca, "notes": notes})
            return {t: cs for t, cs in sorted(pt.items()) if cs.get("A") and cs.get("C")}
        sink = _Sink()
        bb.sessions, bb.OUT = sessions, sink
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            bb.analyse()
        runs[mode] = json.loads(sink.text)
    bb.sessions, bb.OUT = orig, orig_out
    say("\n[13] Convenience-sample break-even (App. D), blocksize_breakeven.analyse re-run "
        "(turns rows = blocksize_breakeven.json)")
    for key in ("main", "pooled_main_new", "new_tasks", "replication"):
        for mode in VARS:
            st = runs[mode]["break_even"]["studies"][key]
            bs = st["by_block_size"]
            row = []
            for name in ("real_median_nonempty", "benchmark_mean_423", "real_p75_nonempty"):
                if name in bs:
                    x = bs[name]
                    row.append(f"{name} ({x['T_tokens']:g}) {pct(x['break_even_share'])} "
                               f"[{pct(x['break_even_share_ci95'][0])}, {pct(x['break_even_share_ci95'][1])}] "
                               f"c ${x['overhead_per_session_usd']:.4f}")
            say(f"  {mode:5s} {key}: t {st['mean_C_turns']:.2f}, S_gross ${st['S_gross_usd']['value']:.4f}; " + "; ".join(row))
    for mode in VARS:
        d = runs[mode]
        mean_ne = d["block_sizes"]["imported"]["tokens_nonempty"].get("mean")
        vals = []
        for key in ("main", "replication", "new_tasks"):
            st = d["break_even"]["studies"][key]
            vals.append(f"{key} {pct(mean_ne * (st['mean_C_turns'] * P_R + P_W) / st['S_gross_usd']['value'])}")
        cm = mean_ne * (d["break_even"]["studies"]["main"]["mean_C_turns"] * P_R + P_W)
        say(f"  {mode:5s} mean non-empty block {mean_ne:g} tokens: c (main) ${cm:.4f}; f* " + ", ".join(vals))


say("\n[14] Figure breakeven2d scenarios (704/main, 1,025/main, 1,320/new tasks): f* at u = 0 and u where f* reaches 0")
for v in VARS:
    row = []
    for sk, b in (("main", 704), ("main", 1024.5), ("new_tasks", 1320)):
        c = c_of(b, T(sk, v))
        row.append(f"{b:g}/{sk}: f*(0) {pct(c / S(sk, v))}, zero at u = {pct(c / K, 2)}")
    say(f"  {v:5s}: " + "; ".join(row))
say("  (V1 per-call breakdown for App. D: main 11.31 calls, replication 12.00, new tasks 8.79; s at calls / s at "
    f"turns = {ST['main']['S_calls'] / ST['main']['S_json']:.4f})")


try:
    header_breakeven_calls()
except Exception as e:  # inputs outside the study folder (stream logs) missing
    say(f"\n[12] header break-even re-run skipped: {type(e).__name__}")
try:
    blocksize_calls()
except Exception as e:  # realworld blocks missing
    say(f"\n[13] convenience-sample re-run skipped: {type(e).__name__}: {e}")
txt = "\n".join(L)
print(txt)
OUT.write_text(txt + "\n", encoding="utf-8")
