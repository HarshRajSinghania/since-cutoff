"""Analysis for PROTOCOL_ADDENDUM section 14 (lockfile-only header L; optional wrong block W).

usage: python lockhdr_analysis.py [--reps1 1,2,3] [--reps2 1,2] [--wrong] [--out NAME]
  default: every replicate that is complete (all planned runs of that rep valid) in each study.

Studies (all arms of a study run concurrently in the same randomised blocks):
  S1 lockhdr-tasks2-opus55-2026-10-23: A, C, H, L x 11 tasks (8 post-cutoff, 3 controls) x 3 reps
  S2 lockhdr-orig-opus55-2026-10-23:   A, H, L x 17 original post-cutoff tasks x 2 reps
  W  wrong-tasks2-opus55-2026-10-23:   A, W x 11 tasks x 3 reps (optional, section 14.2)

Primary metrics: total tokens (geometric mean over tasks of per-task median ratios, task bootstrap 10,000, seed
20261001: recompute_cost.ratio_ci) and list-price cost per solved task (sum of cost / number of passed sessions per arm,
pooled over tasks; ratio with a task bootstrap, as token_breakdown.py). Exact two-sided sign-flip over per-task log
ratios: tokens = log of the ratio of per-task medians; cost per solved = log of the ratio of per-task
(sum cost / max(passes, 0.5)). Holm within each pre-registered family:
  F1 (S1, 8 post-cutoff tasks): {L/A, H/L, C/L} x {tokens, cost per solved} = 6 tests
  F2 (pooled 25 post-cutoff tasks = S1's 8 + S2's 17): {L/A, H/L} x {tokens, cost per solved} = 4 tests
Equivalence (H/L, TOST at 5% each side = 90% bootstrap CI inside [0.85, 1/0.85]).
"""
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import addendum5_analysis as a5  # noqa: E402
from addendum5_analysis import (  # noqa: E402
    METRICS, OUT, RES, pass_contrast, per_task_medians, ratios, split, stale_contrast, totals)
from pooled_old_new import boot_mean  # noqa: E402
from recompute_cost import load, ratio_ci  # noqa: E402
from stale_tests import signflip as _signflip_enum  # noqa: E402

S1 = RES / "lockhdr-tasks2-opus55-2026-10-23"
S2 = RES / "lockhdr-orig-opus55-2026-10-23"
SW = RES / "wrong-tasks2-opus55-2026-10-23"
CONC = RES / "conc-opus55-2026-10-23"
ABL = RES / "abl-opus55-2026-10-22"
S1_CONDS, S2_CONDS = ["A", "C", "H", "L"], ["A", "H", "L"]
F1, F2 = ["L/A", "H/L", "C/L"], ["L/A", "H/L"]
COVERED = {"pl02", "st01", "ant01", "ant03", "hf01", "hf02", "hf03"}   # C's lines name the task's change
PILOT = {"ant01", "mcp01"}
EQ = (0.85, 1 / 0.85)
B, SEED = 10000, 20261001


def signflip(diffs):
    """Exact two-sided sign-flip p over all 2^n sign vectors (zeros dropped), as stale_tests.signflip; for n > 16
    the same count is computed exactly by meet-in-the-middle (sums of the two halves, sorted, bisect)."""
    import bisect
    d = [x for x in diffs if abs(x) > 1e-12]
    if len(d) <= 16:
        return _signflip_enum(d)
    obs = abs(sum(d))
    h = len(d) // 2

    def sums(xs):
        out = [0.0]
        for x in xs:
            out = [s + x for s in out] + [s - x for s in out]
        return out
    left, right = sums(d[:h]), sorted(sums(d[h:]))
    n_r, hits = len(right), 0
    for a in left:
        hits += n_r - bisect.bisect_left(right, obs - 1e-12 - a)      # a + b >= obs
        hits += bisect.bisect_right(right, -obs + 1e-12 - a)          # a + b <= -obs
    return hits / 2 ** len(d), len(d)


def complete_reps(d, n_runs_per_rep):
    plan = [json.loads(x) for x in open(d / "plan.jsonl", encoding="utf-8")]
    want = {}
    for p in plan:
        want.setdefault(p["rep"], set()).add(p["run_id"])
    got = {r["run_id"] for r in load(d)}
    return sorted(k for k, v in want.items() if v <= got and len(v) == n_runs_per_rep.get(k, len(v)))


def collect(specs):
    """specs: [(dir, reps, rename)] -> per_task, strata (filters records to the chosen reps)."""
    orig = a5.load
    keep = {d: set(reps) for d, reps, _ in specs}
    a5.load = lambda d: [r for r in orig(d) if r["rep"] in keep.get(d, {r["rep"]})]
    try:
        return a5.collect([(d, rename) for d, _, rename in specs])
    finally:
        a5.load = orig


def log_ratios_tokens(per_task, treat, ctrl):
    out = {}
    for t, cs in per_task.items():
        a = [m["total_tokens"] for m in cs.get(treat, []) if m["total_tokens"]]
        b = [m["total_tokens"] for m in cs.get(ctrl, []) if m["total_tokens"]]
        if a and b:
            out[t] = math.log(statistics.median(a) / statistics.median(b))
    return out


def cps_task(ms):
    return sum(m["list_cost_usd"] for m in ms) / max(sum(m["passed"] for m in ms), 0.5)


def log_ratios_cps(per_task, treat, ctrl):
    return {t: math.log(cps_task(cs[treat]) / cps_task(cs[ctrl])) for t, cs in per_task.items()
            if cs.get(treat) and cs.get(ctrl)}


def cost_per_solved(per_task, treat, ctrl):
    rows = {t: cs for t, cs in sorted(per_task.items()) if cs.get(treat) and cs.get(ctrl)}
    tasks = list(rows)
    if not tasks:
        return None

    def f(sel):
        r = {}
        for c in (treat, ctrl):
            cost = sum(m["list_cost_usd"] for t in sel for m in rows[t][c])
            p = sum(m["passed"] for t in sel for m in rows[t][c])
            r[c] = cost / p if p else None
        return r[treat] / r[ctrl] if r[treat] and r[ctrl] else None
    rnd = random.Random(SEED)
    bs = []
    for _ in range(B):
        v = f([tasks[rnd.randrange(len(tasks))] for _ in tasks])
        if v is not None:
            bs.append(v)
    bs.sort()
    q = lambda p: bs[min(len(bs) - 1, int(p * len(bs)))]
    out = {"tasks": len(tasks), "ratio": f(tasks), "lo": q(0.025), "hi": bs[int(0.975 * len(bs)) - 1],
           "lo90": q(0.05), "hi90": bs[int(0.95 * len(bs)) - 1]}
    for c in (treat, ctrl):
        cost = sum(m["list_cost_usd"] for t in tasks for m in rows[t][c])
        p = sum(m["passed"] for t in tasks for m in rows[t][c])
        n = sum(len(rows[t][c]) for t in tasks)
        out[c] = {"usd_per_solved": cost / p if p else None, "passed": p, "sessions": n, "total_list_cost_usd": cost}
    return out


def tokens_ci90(per_task, treat, ctrl):
    logs = list(log_ratios_tokens(per_task, treat, ctrl).values())
    rnd = random.Random(SEED)
    bs = sorted(math.exp(sum(rnd.choice(logs) for _ in logs) / len(logs)) for _ in range(B))
    return [bs[int(0.05 * B)], bs[int(0.95 * B) - 1]]


def holm(pvals):
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, adj, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        adj[k] = run
    return adj


def test_block(per_task, pairs):
    out = {}
    for p in pairs:
        t, c = p.split("/")
        tok = ratio_ci(per_task, t, c, "total_tokens")
        lt = log_ratios_tokens(per_task, t, c)
        lc = log_ratios_cps(per_task, t, c)
        pt, kt = signflip(list(lt.values()))
        pc, kc = signflip(list(lc.values()))
        cps = cost_per_solved(per_task, t, c)
        out[p] = {
            "tokens": {**tok, "ci90": tokens_ci90(per_task, t, c), "signflip_p": pt, "tasks": kt,
                       "tasks_below_1": sum(v < 0 for v in lt.values()),
                       "per_task_ratio": {k: round(math.exp(v), 3) for k, v in sorted(lt.items())}},
            "cost_per_solved": {**cps, "signflip_p": pc, "tasks_below_1": sum(v < 0 for v in lc.values()),
                                "per_task_ratio": {k: round(math.exp(v), 3) for k, v in sorted(lc.items())}},
            "other": {m: ratio_ci(per_task, t, c, m) for m in METRICS if m != "total_tokens"},
        }
    return out


def family(tests, pairs):
    pv = {}
    for p in pairs:
        pv[f"{p}:tokens"] = tests[p]["tokens"]["signflip_p"]
        pv[f"{p}:cost_per_solved"] = tests[p]["cost_per_solved"]["signflip_p"]
    adj = holm(pv)
    for k, v in adj.items():
        p, m = k.split(":")
        tests[p][m]["holm_p"] = v
    return adj


def verdict(x):
    """x: a metric block with ratio/lo/hi/holm_p."""
    if x["hi"] < 1 and x["holm_p"] < 0.05:
        return "supported (CI below 1, Holm p < .05)"
    if x["lo"] > 1 and x["holm_p"] < 0.05:
        return "reversed (CI above 1, Holm p < .05)"
    if x["hi"] < 1:
        return "suggestive (CI below 1, Holm p >= .05)"
    if x["lo"] > 1:
        return "suggestive reverse (CI above 1, Holm p >= .05)"
    return "no difference shown"


def hl_rule(tests):
    tok, cps = tests["H/L"]["tokens"], tests["H/L"]["cost_per_solved"]
    eq_tok = EQ[0] <= tok["ci90"][0] and tok["ci90"][1] <= EQ[1]
    eq_cps = EQ[0] <= cps["lo90"] and cps["hi90"] <= EQ[1]
    adds = (tok["hi"] < 1 and tok["holm_p"] < 0.05) or (cps["hi"] < 1 and cps["holm_p"] < 0.05)
    if adds:
        return "cutoff-version information adds beyond pinned versions (H cheaper than L)"
    if eq_tok and eq_cps:
        return "L equivalent to H within +-15% on both primary metrics (cutoff-version information adds nothing measurable)"
    if eq_tok or eq_cps:
        return "L equivalent to H within +-15% on one primary metric only; otherwise inconclusive"
    return "inconclusive (no difference shown, equivalence not shown)"


def study_part(per_task, strata, conds, pairs, label):
    post, ctrl = split(per_task, strata)
    out = {"label": label, "tasks_post": sorted(post), "tasks_controls": sorted(ctrl),
           "runs": sum(len(v) for cs in per_task.values() for v in cs.values()),
           "totals_post": totals(post), "totals_controls": totals(ctrl),
           "tests_post": test_block(post, pairs)}
    vsA = [f"{c}/A" for c in conds if c != "A"]
    out["pass_post"] = {p: pass_contrast(post, *p.split("/")) for p in vsA + [x for x in pairs if x not in vsA]}
    out["stale_post"] = {p: stale_contrast(post, *p.split("/")) for p in vsA}
    out["stale_delta_post"] = {p: delta(post, *p.split("/"), "stale") for p in vsA}
    out["pass_delta_post"] = {p: delta(post, *p.split("/"), "passed") for p in vsA}
    if ctrl:
        out["ratios_controls"] = ratios(ctrl, vsA + [x for x in pairs if x not in vsA])
        out["pass_controls"] = {p: pass_contrast(ctrl, *p.split("/")) for p in vsA}
        out["pass_delta_controls"] = {p: delta(ctrl, *p.split("/"), "passed") for p in vsA}
        out["cost_per_solved_controls"] = {p: cost_per_solved(ctrl, *p.split("/")) for p in vsA}
    for name, sel in (("covered", COVERED), ("uncovered", set(post) - COVERED)):
        sub = {t: cs for t, cs in post.items() if t in sel}
        if sub:
            out[f"ratios_{name}"] = ratios(sub, pairs)
    out["per_task"] = per_task_medians(per_task, conds)
    out["ni"] = {
        "pass_post_lower_ge_-10pp": {p: (out["pass_delta_post"][p] or {}).get("one_sided_95_lower", -1) >= -0.10
                                     for p in vsA},
        "stale_post_upper_le_+10pp": {p: (out["stale_delta_post"][p] or {}).get("one_sided_95_upper", 1) <= 0.10
                                      for p in vsA},
    }
    if ctrl:
        out["ni"]["pass_controls_lower_ge_-10pp"] = {
            p: (out["pass_delta_controls"][p] or {}).get("one_sided_95_lower", -1) >= -0.10 for p in vsA}
    return out


def delta(per_task, treat, ctrl, key):
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


def reads(d, reps):
    out = {}
    for rec in load(d):
        if rec["rep"] not in reps or rec["stratum"] != "post-cutoff":
            continue
        v = (rec.get("process") or {}).get("site_packages_reads")
        if v is not None:
            out.setdefault(rec["condition"], []).append(v)
    return {c: sum(v) / len(v) for c, v in sorted(out.items())}


def arg(args, name):
    return [int(x) for x in args[args.index(name) + 1].split(",")] if name in args else None


REN1 = REN2 = None


def main():
    global S1, S2, REN1, REN2
    args = sys.argv[1:]
    if "--smoke" in args:   # pipeline test on earlier studies, relabelled (G -> L in section 13; C -> L in section 7)
        S1, REN1 = CONC, {"A": "A", "C": "C", "H": "H", "G": "L"}
        S2, REN2 = ABL, {"A": "A", "H": "H", "C": "L"}
    out = {"section": "PROTOCOL_ADDENDUM 14", "equivalence_margin": EQ, "smoke_test": "--smoke" in args}
    # ---- S1 ----
    if (S1 / "runs.jsonl").exists():
        reps1 = arg(args, "--reps1") or complete_reps(S1, {})
        pt1, st1 = collect([(S1, reps1, REN1)])
        pairs1 = ["L/A", "H/L", "C/L", "H/A", "C/A", "C/H"]
        s1 = study_part(pt1, st1, S1_CONDS, pairs1, "S1 tasks2 (A, C, H, L)")
        s1["reps_analysed"] = reps1
        s1["family_F1_holm"] = family(s1["tests_post"], F1)
        s1["verdicts_F1"] = {f"{p}:{m}": verdict(s1["tests_post"][p][m]) for p in F1
                             for m in ("tokens", "cost_per_solved")}
        s1["H_vs_L_rule_F1"] = hl_rule(s1["tests_post"])
        s1["site_packages_reads_post_mean"] = reads(S1, set(reps1))
        # cross-day (descriptive): same arm in the section-13 study
        if (CONC / "runs.jsonl").exists() and S1 != CONC:
            old, _ = collect([(CONC, [1, 2, 3], {"A": "A_conc", "C": "C_conc", "H": "H_conc"})])
            post1, _ = split(pt1, st1)
            m = {t: {**post1[t], **old.get(t, {})} for t in post1}
            s1["cross_day_post"] = {p: ratio_ci(m, *p.split("/"), "total_tokens")
                                    for p in ("A/A_conc", "C/C_conc", "H/H_conc")}
        out["S1"] = s1
    # ---- S2 ----
    if (S2 / "runs.jsonl").exists():
        reps2 = arg(args, "--reps2") or complete_reps(S2, {})
        pt2, st2 = collect([(S2, reps2, REN2)])
        pairs2 = ["L/A", "H/L", "H/A"]
        s2 = study_part(pt2, st2, S2_CONDS, pairs2, "S2 original 17 (A, H, L)")
        s2["reps_analysed"] = reps2
        s2["tests_post_without_pilot"] = test_block({t: cs for t, cs in pt2.items() if t not in PILOT}, pairs2)
        s2["site_packages_reads_post_mean"] = reads(S2, set(reps2))
        if (ABL / "runs.jsonl").exists() and S2 != ABL:
            old, _ = collect([(ABL, [1, 2, 3], {"A": "A_abl", "H": "H_abl"})])
            m = {t: {**pt2[t], **old.get(t, {})} for t in pt2}
            s2["cross_day_post"] = {p: ratio_ci(m, *p.split("/"), "total_tokens") for p in ("A/A_abl", "H/H_abl")}
        out["S2"] = s2
        # ---- pooled 25 (F2) ----
        if "S1" in out and reps2:
            pt1, st1 = collect([(S1, out["S1"]["reps_analysed"], REN1)])
            post1, _ = split(pt1, st1)
            post2, _ = split(pt2, st2)
            pooled = {**{t: {c: v for c, v in cs.items() if c in S2_CONDS} for t, cs in post1.items()}, **post2}
            pairs = ["L/A", "H/L", "H/A"]
            pool = {"tasks": sorted(pooled), "tests": test_block(pooled, pairs),
                    "tests_without_pilot": test_block({t: cs for t, cs in pooled.items() if t not in PILOT}, pairs),
                    "pass": {p: pass_contrast(pooled, *p.split("/")) for p in ("L/A", "H/A", "H/L")},
                    "pass_delta": {p: delta(pooled, *p.split("/"), "passed") for p in ("L/A", "H/A")},
                    "stale": {p: stale_contrast(pooled, *p.split("/")) for p in ("L/A", "H/A", "H/L")},
                    "stale_delta": {p: delta(pooled, *p.split("/"), "stale") for p in ("L/A", "H/A")}}
            for name, sel in (("covered", COVERED), ("uncovered", set(pooled) - COVERED)):
                pool[f"ratios_{name}"] = ratios({t: cs for t, cs in pooled.items() if t in sel}, pairs)
            pool["family_F2_holm"] = family(pool["tests"], F2)
            pool["verdicts_F2"] = {f"{p}:{m}": verdict(pool["tests"][p][m]) for p in F2
                                   for m in ("tokens", "cost_per_solved")}
            pool["H_vs_L_rule_F2"] = hl_rule(pool["tests"])
            out["pooled25"] = pool
    # ---- W (optional) ----
    if (SW / "runs.jsonl").exists():
        repsw = arg(args, "--repsw") or complete_reps(SW, {})
        ptw, stw = collect([(SW, repsw, None)])
        sw = study_part(ptw, stw, ["A", "W"], ["W/A"], "W harm check (A, W)")
        sw["reps_analysed"] = repsw
        sw["site_packages_reads_post_mean"] = reads(SW, set(repsw))
        pc, sc = sw["pass_post"].get("W/A"), sw["stale_post"].get("W/A")
        sd = sw["stale_delta_post"].get("W/A")
        sw["rules"] = {
            "harm_pass": bool(pc) and pc["ci95"][1] < 0 and pc["signflip_p"] < 0.05,
            "harm_stale": bool(sd) and sd["ci95"][0] > 0 and bool(sc) and sc["signflip_p_task_level"] < 0.05}
        out["W"] = sw
    OUT.mkdir(exist_ok=True)
    name = args[args.index("--out") + 1] if "--out" in args else "lockhdr_ablation.json"
    (OUT / name).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    for k in ("S1", "S2", "pooled25", "W"):
        if k not in out:
            continue
        o = out[k]
        tests = o.get("tests_post") or o.get("tests")
        print("==", k, "reps", o.get("reps_analysed"), "tasks", len(o.get("tasks_post") or o.get("tasks")))
        for p, x in tests.items():
            t, c = x["tokens"], x["cost_per_solved"]
            print(f"  {p}: tokens {t['ratio']:.3f} [{t['lo']:.3f}, {t['hi']:.3f}] p={t['signflip_p']:.4f}"
                  f" holm={t.get('holm_p', float('nan')):.4f} | cps {c['ratio']:.3f} [{c['lo']:.3f}, {c['hi']:.3f}]"
                  f" p={c['signflip_p']:.4f} holm={c.get('holm_p', float('nan')):.4f}")
        for key in ("verdicts_F1", "H_vs_L_rule_F1", "verdicts_F2", "H_vs_L_rule_F2", "ni"):
            if key in o:
                print(" ", key, json.dumps(o[key]))
    print("->", OUT / name)


if __name__ == "__main__":
    main()
