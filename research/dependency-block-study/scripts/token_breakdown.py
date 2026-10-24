"""Token-type breakdown, turns decomposition and cost per solved task (requested in an internal review).

usage: python token_breakdown.py            -> writes <study>/analysis/token_breakdown.json
env:   RUNS_RESULTS (default since_cutoff_runs/results), BENCH_RESULTS (default
       ~/projects/since-cutoff-benchmark/results), ANALYSIS_OUT (default <study>/analysis). Output contains study names only.

Existing run data only (runs.jsonl; first valid attempt per planned run, as recompute_cost.load). Per session, the
CLI's cumulative `result.usage` gives four token types:
  input        = input_tokens                (uncached input)
  cache_read   = cache_read_input_tokens
  cache_write  = cache_creation_input_tokens (1h + 5m writes)
  output       = output_tokens               (includes thinking)
total = sum of the four (the paper's "total tokens"); list cost = recompute_cost.list_cost (list prices).

For each study, scope (post-cutoff primary; controls descriptive) and pair treat/ctrl:
  ratios      geometric mean over tasks of per-task median ratios, 95% task-cluster bootstrap (10,000, seed
              20261001; recompute_cost.ratio_ci, so total_tokens/list_cost match the earlier analyses exactly), for
              every token type, total, turns, tokens per turn (per session), list cost and cost per turn.
  composition share of each token type in each arm's tokens (task-averaged session means) and of list cost.
  saving_shares
              share of the absolute total-token (and list-cost) saving contributed by each type: per task, mean ctrl
              minus mean treat per type (means are additive, medians are not), averaged over tasks; CI from a joint
              task bootstrap of the same draw for all types.
  turns_decomposition
              per task with session means, total = turns x tokens-per-turn, so log(total ratio) = log(turns ratio) +
              log(tokens-per-turn ratio) exactly; geometric means over tasks, joint task bootstrap; "share explained
              by turns" = sum log turns ratio / sum log total ratio (same for list cost = turns x cost per turn).
  block_overhead (pairs where only treat has a notes block)
              notes_tokens x turns per treat session = the block's added (mostly cache-read) tokens, vs the mean
              saving per session.
  cost_per_solved
              total list cost / passed sessions per arm on the pair's tasks; treat/ctrl ratio with a task bootstrap
              (resample tasks, recompute both sums).
  token_vs_cost
              per-task log median-ratio of total tokens vs list cost: Pearson r and the paired gap.
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
from recompute_cost import PRICES, ratio_ci  # noqa: E402

PRICES.setdefault("claude-sonnet-4-5", (3.0, 15.0, 0.30, 6.0, 3.75))

RES = Path(os.environ.get("RUNS_RESULTS", "since_cutoff_runs/results"))
BENCH = Path(os.environ.get("BENCH_RESULTS", Path.home() / "projects" / "since-cutoff-benchmark" / "results"))
OUT = Path(os.environ.get("ANALYSIS_OUT", HERE.parent / "analysis"))
B, SEED = 10000, 20261001
TYPES = ("input", "cache_read", "cache_write", "output")
RATIO_METRICS = ("total", "input", "cache_read", "cache_write", "output", "turns", "tokens_per_turn",
                 "list_cost_usd", "cost_per_turn", "cost_input", "cost_cache_read", "cost_cache_write", "cost_output")


def load_runs(d: Path, pilot_ok=False):
    recs = [json.loads(l) for l in open(d / "runs.jsonl", encoding="utf-8")]
    recs = [r for r in recs if r.get("valid") and (pilot_ok or not r.get("pilot"))]
    seen, out = set(), []
    for r in sorted(recs, key=lambda r: (r["run_id"], r["attempt"])):
        if r["run_id"] not in seen:
            seen.add(r["run_id"]); out.append(r)
    return out


def session(r):
    res = r.get("result") or {}
    u = res.get("usage") or {}
    model = r["agent"]["model"]
    p_in, p_out, p_cr, p_w1h, p_w5m = PRICES[model]
    cc = u.get("cache_creation") or {}
    w1h, w5m = cc.get("ephemeral_1h_input_tokens"), cc.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:
        w1h, w5m = u.get("cache_creation_input_tokens", 0), 0
    m = {"input": u.get("input_tokens", 0), "cache_read": u.get("cache_read_input_tokens", 0),
         "cache_write": u.get("cache_creation_input_tokens", 0), "output": u.get("output_tokens", 0)}
    m["total"] = sum(m[k] for k in TYPES)
    m["turns"] = res.get("num_turns") or 0
    m["cost_input"] = m["input"] * p_in / 1e6
    m["cost_output"] = m["output"] * p_out / 1e6
    m["cost_cache_read"] = m["cache_read"] * p_cr / 1e6
    m["cost_cache_write"] = ((w1h or 0) * p_w1h + (w5m or 0) * p_w5m) / 1e6
    m["list_cost_usd"] = recompute_cost.list_cost(model, u)
    m["tokens_per_turn"] = m["total"] / m["turns"] if m["turns"] else None
    m["cost_per_turn"] = m["list_cost_usd"] / m["turns"] if m["turns"] else None
    m["cli_cost_usd"] = res.get("total_cost_usd")
    m["passed"] = bool((r.get("grade") or {}).get("passed"))
    m["notes_tokens"] = (r.get("condition_config") or {}).get("notes_tokens") or 0
    m["model"] = model
    return m


def collect(specs):
    """specs: [(dir, {cond: label} | None, pilot_ok)] -> per_task[task][label] = [session dicts], strata."""
    per_task = defaultdict(lambda: defaultdict(list))
    strata = {}
    for d, rename, pilot_ok in specs:
        for r in load_runs(d, pilot_ok):
            c = r["condition"] if rename is None else rename.get(r["condition"])
            if c is None:
                continue
            per_task[r["task"]][c].append(session(r))
            strata[r["task"]] = r["stratum"]
    return per_task, strata


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def pct(bs):
    bs = sorted(bs)
    return [bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs)) - 1]]


def boot_tasks(n, fn, seed=SEED):
    """Joint task bootstrap: fn(list of task indices) -> dict of floats; returns {key: [lo, hi]}."""
    rnd = random.Random(seed)
    acc = defaultdict(list)
    for _ in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        for k, v in fn(idx).items():
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                acc[k].append(v)
    return {k: pct(v) for k, v in acc.items()}


def analyse_pair(per_task, treat, ctrl, notes_pair):
    rows = {t: cs for t, cs in sorted(per_task.items()) if cs.get(treat) and cs.get(ctrl)}
    if not rows:
        return None
    tasks = list(rows)
    out = {"tasks": len(tasks), "task_ids": tasks,
           "runs": {treat: sum(len(cs[treat]) for cs in rows.values()), ctrl: sum(len(cs[ctrl]) for cs in rows.values())}}
    # 1. ratios of per-task medians
    out["ratios"] = {m: ratio_ci(rows, treat, ctrl, m, resamples=B, seed=SEED) for m in RATIO_METRICS}
    # per-task session means per arm
    mt = {t: {c: {k: mean(s[k] for s in rows[t][c]) for k in TYPES + ("total", "turns", "list_cost_usd",
                                                                      "cost_input", "cost_output", "cost_cache_read",
                                                                      "cost_cache_write", "notes_tokens")}
              for c in (treat, ctrl)} for t in tasks}
    # 2. composition (task-averaged session means)
    comp = {}
    for c in (ctrl, treat):
        tot = mean(mt[t][c]["total"] for t in tasks)
        cost = mean(mt[t][c]["list_cost_usd"] for t in tasks)
        comp[c] = {"mean_total_tokens": tot, "mean_turns": mean(mt[t][c]["turns"] for t in tasks),
                   "mean_list_cost_usd": cost,
                   "token_share": {k: mean(mt[t][c][k] for t in tasks) / tot for k in TYPES},
                   "mean_tokens": {k: mean(mt[t][c][k] for t in tasks) for k in TYPES},
                   "cost_share": {k: mean(mt[t][c]["cost_" + k] for t in tasks) / cost for k in TYPES}}
    out["composition"] = comp

    # 3. shares of the absolute saving
    def shares(idx):
        sel = [tasks[i] for i in idx]
        d = {k: mean(mt[t][ctrl][k] - mt[t][treat][k] for t in sel) for k in TYPES}
        dt = sum(d.values())
        dc = {k: mean(mt[t][ctrl]["cost_" + k] - mt[t][treat]["cost_" + k] for t in sel) for k in TYPES}
        dct = sum(dc.values())
        r = {"tok_saving_per_session": dt, "cost_saving_per_session": dct}
        for k in TYPES:
            r["tok_share_" + k] = d[k] / dt if dt else float("nan")
            r["cost_share_" + k] = dc[k] / dct if dct else float("nan")
        return r
    pt = shares(range(len(tasks)))
    ci = boot_tasks(len(tasks), shares)
    out["saving_shares"] = {
        "mean_token_saving_per_session": {"value": pt["tok_saving_per_session"], "ci95": ci["tok_saving_per_session"]},
        "mean_cost_saving_per_session_usd": {"value": pt["cost_saving_per_session"],
                                             "ci95": ci["cost_saving_per_session"]},
        "token_saving_share": {k: {"value": pt["tok_share_" + k], "ci95": ci.get("tok_share_" + k)} for k in TYPES},
        "cost_saving_share": {k: {"value": pt["cost_share_" + k], "ci95": ci.get("cost_share_" + k)} for k in TYPES},
        "token_saving_ci_excludes_0": ci["tok_saving_per_session"][0] > 0 or ci["tok_saving_per_session"][1] < 0,
        "cost_saving_ci_excludes_0": ci["cost_saving_per_session"][0] > 0 or ci["cost_saving_per_session"][1] < 0,
        "note": "shares of (mean ctrl - mean treat) per session, task-averaged; not interpretable when the saving's "
                "CI includes 0 (see *_ci_excludes_0)"}

    # 4. turns decomposition (session means per task: total = turns x tokens/turn)
    def decomp(idx):
        sel = [tasks[i] for i in idx]
        lt = [math.log(mt[t][treat]["total"] / mt[t][ctrl]["total"]) for t in sel]
        lu = [math.log(mt[t][treat]["turns"] / mt[t][ctrl]["turns"]) for t in sel]
        lc = [math.log(mt[t][treat]["list_cost_usd"] / mt[t][ctrl]["list_cost_usd"]) for t in sel]
        r = {"total": math.exp(mean(lt)), "turns": math.exp(mean(lu)),
             "tokens_per_turn": math.exp(mean(lt) - mean(lu)),
             "cost": math.exp(mean(lc)), "cost_per_turn": math.exp(mean(lc) - mean(lu)),
             "turns_share_of_token_saving": sum(lu) / sum(lt) if sum(lt) else float("nan"),
             "turns_share_of_cost_saving": sum(lu) / sum(lc) if sum(lc) else float("nan")}
        for k in ("cache_read", "cache_write", "output"):
            vals = [(mt[t][treat][k] / mt[t][treat]["turns"]) / (mt[t][ctrl][k] / mt[t][ctrl]["turns"])
                    for t in sel if mt[t][treat][k] and mt[t][ctrl][k]]
            r[k + "_per_turn"] = math.exp(mean(math.log(v) for v in vals)) if vals else None
        return r
    pt = decomp(range(len(tasks)))
    ci = boot_tasks(len(tasks), decomp)
    out["turns_decomposition"] = {k: {"value": v, "ci95": ci.get(k)} for k, v in pt.items()}
    out["turns_decomposition"]["note"] = ("ratio-of-means per task, geometric mean over tasks; total = turns x "
                                          "tokens_per_turn holds exactly; shares = sum log(turns ratio) / sum "
                                          "log(total ratio)")

    # 5. block overhead (treat has a notes block, ctrl has none)
    if notes_pair:
        oh = mean(mean(s["notes_tokens"] * s["turns"] for s in rows[t][treat]) for t in tasks)
        sav = mean(mt[t][ctrl]["total"] - mt[t][treat]["total"] for t in tasks)
        out["block_overhead"] = {
            "mean_notes_tokens": mean(mt[t][treat]["notes_tokens"] for t in tasks),
            "est_block_tokens_per_session": oh,
            "as_share_of_ctrl_total": oh / mean(mt[t][ctrl]["total"] for t in tasks),
            "mean_saving_per_session": sav,
            "gross_saving_before_block": sav + oh,
            "note": "notes_tokens (estimate) x turns per treat session: the block is re-read from cache on every "
                    "turn; gross = net saving + this overhead"}

    # 6. cost per solved task
    def cps(idx):
        sel = [tasks[i] for i in idx]
        r = {}
        for c in (treat, ctrl):
            cost = sum(s["list_cost_usd"] for t in sel for s in rows[t][c])
            p = sum(s["passed"] for t in sel for s in rows[t][c])
            r[c] = cost / p if p else None
        r["ratio"] = r[treat] / r[ctrl] if r[treat] and r[ctrl] else None
        return r
    pt = cps(range(len(tasks)))
    ci = boot_tasks(len(tasks), cps)
    out["cost_per_solved"] = {
        c: {"usd": pt[c], "passed": sum(s["passed"] for t in tasks for s in rows[t][c]),
            "sessions": sum(len(rows[t][c]) for t in tasks),
            "total_list_cost_usd": sum(s["list_cost_usd"] for t in tasks for s in rows[t][c])}
        for c in (ctrl, treat)}
    out["cost_per_solved"]["ratio"] = {"value": pt["ratio"], "ci95": ci.get("ratio")}

    # 7. token vs cost divergence per task
    lt, lc = [], []
    per_task_rows = {}
    for t in tasks:
        a = statistics.median(s["total"] for s in rows[t][treat]) / statistics.median(s["total"] for s in rows[t][ctrl])
        b = (statistics.median(s["list_cost_usd"] for s in rows[t][treat]) /
             statistics.median(s["list_cost_usd"] for s in rows[t][ctrl]))
        lt.append(math.log(a)); lc.append(math.log(b))
        per_task_rows[t] = {"tokens_ratio": a, "cost_ratio": b}
    out["token_vs_cost"] = {"pearson_r_log_ratios": pearson(lt, lc), "per_task": per_task_rows,
                            "tasks_where_tokens_fell_but_cost_rose": [t for t, v in per_task_rows.items()
                                                                       if v["tokens_ratio"] < 1 < v["cost_ratio"]],
                            "tasks_where_cost_fell_but_tokens_rose": [t for t, v in per_task_rows.items()
                                                                       if v["cost_ratio"] < 1 < v["tokens_ratio"]]}
    return out


def pearson(x, y):
    if len(x) < 3:
        return None
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x); syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def condition_totals(per_task, strata, scope):
    out = defaultdict(lambda: defaultdict(float))
    for t, cs in per_task.items():
        if (strata[t] == "post-cutoff") != (scope == "post-cutoff"):
            continue
        for c, ss in cs.items():
            o = out[c]
            for s in ss:
                o["sessions"] += 1; o["passed"] += s["passed"]
                for k in TYPES + ("total", "turns", "list_cost_usd", "cost_input", "cost_output", "cost_cache_read",
                                  "cost_cache_write"):
                    o[k] += s[k]
    res = {}
    for c, o in sorted(out.items()):
        n = o["sessions"]
        res[c] = {"sessions": int(n), "passed": int(o["passed"]),
                  "sum_tokens": {k: int(o[k]) for k in TYPES + ("total",)},
                  "token_share": {k: o[k] / o["total"] for k in TYPES},
                  "mean_per_session": {k: o[k] / n for k in TYPES + ("total", "turns", "list_cost_usd")},
                  "sum_list_cost_usd": o["list_cost_usd"],
                  "cost_share": {k: o["cost_" + k] / o["list_cost_usd"] for k in TYPES},
                  "list_cost_per_solved_usd": o["list_cost_usd"] / o["passed"] if o["passed"] else None}
    return res


def studies():
    main, pilot = BENCH / "main-2026-09-28", BENCH / "pilot-2026-09-28"
    t2 = RES / "tasks2-opus55-2026-10-22"
    abl = RES / "abl-opus55-2026-10-22"
    notes_free = {"A", "B", "E", "An", "G"}
    return [
        # key, model, specs, pairs (treat/ctrl), description
        ("opus55_main", [(main, None, False)], ["C/A", "D/B"], "Opus 5.5 main run (A-E x 24 tasks x 3)"),
        ("opus55_pilot", [(pilot, None, True)], ["C/A", "D/B"], "Opus 5.5 pilot (ant01, mcp01 x 2 reps)"),
        ("opus55_replication", [(abl, None, False)], ["C/A", "H/A", "C/H"], "Opus 5.5 placebo ablation/replication"),
        ("opus55_tasks2", [(t2, None, False)], ["C/A", "H/A", "C/H"], "Opus 5.5 new task set"),
        ("opus55_irr", [(t2, {"A": "A", "C": "C", "H": "H"}, False),
                        (RES / "irr-opus55-2026-10-22", {"R": "R", "A": "An"}, False)],
         ["C/R", "R/A", "R/An"], "Opus 5.5 E-irr (R vs tasks2 A/C/H; An = concurrent A)"),
        ("opus55_iter", [(t2, {"A": "A", "C": "C", "H": "H"}, False),
                         (RES / "iter-opus55-2026-10-22", {"C2": "C2", "A": "An", "C": "Cn"}, False)],
         ["C2/C", "C2/A"], "Opus 5.5 C2 iteration (vs tasks2 A/C)"),
        ("opus55_case", [(RES / "case-opus55-2026-10-22", None, False)], ["C/A"], "Opus 5.5 LiteLLM case (2 tasks)"),
        ("opus55_conc", [(RES / "conc-opus55-2026-10-23", None, False)], ["C/A", "H/A", "R/A", "G/A", "C/H", "C/G"],
         "Opus 5.5 concurrent five-arm ablation (A, C, H, R, G x 11 new tasks x 3; added 2026-10-23)"),
        ("sonnet55", [(RES / "gen-sonnet55-2026-10-21", None, False)], ["C/A", "H/A", "C/H"], "Sonnet 5.5"),
        ("haiku55", [(RES / "gen-haiku55-2026-10-21", None, False)], ["C/A"], "Haiku 5.5"),
        ("sonnet45_anchor", [(RES / "anchor-s45-main-2026-10-22", None, False),
                             (RES / "anchor-s45-tasks2-2026-10-22", None, False)], ["C/A"],
         "Sonnet 4.5, notes anchored to its own cutoff (15 tasks)"),
        ("opus55_pooled_main_tasks2", [(main, {"A": "A", "C": "C"}, False), (t2, {"A": "A", "C": "C"}, False)],
         ["C/A"], "pooled 25 post-cutoff tasks: main (17) + new (8)"),
        ("opus55_pooled_repl_tasks2", [(abl, None, False), (t2, None, False)], ["C/A", "H/A", "C/H"],
         "pooled 25 post-cutoff tasks: replication (17) + new (8)"),
    ], notes_free


def main():
    specs, notes_free = studies()
    out = {"generated_by": "scripts/token_breakdown.py",
           "method": __doc__.split("For each study")[1].strip() if "For each study" in __doc__ else "",
           "bootstrap": {"resamples": B, "seed": SEED, "unit": "task"},
           "token_types": {"input": "input_tokens (uncached)", "cache_read": "cache_read_input_tokens",
                           "cache_write": "cache_creation_input_tokens", "output": "output_tokens"},
           "prices_usd_per_mtok": {m: dict(zip(("input", "output", "cache_read", "cache_write_1h", "cache_write_5m"), p))
                                   for m, p in PRICES.items()},
           "studies": {}}
    for key, sp, pairs, desc in specs:
        per_task, strata = collect(sp)
        st = {"description": desc, "source_studies": sorted({d.name for d, _, _ in sp}),
              "model": sorted({s["model"] for cs in per_task.values() for ss in cs.values() for s in ss}),
              "condition_totals": {sc: condition_totals(per_task, strata, sc) for sc in ("post-cutoff", "controls")},
              "pairs": {}}
        for scope in ("post-cutoff", "controls"):
            sel = {t: cs for t, cs in per_task.items() if (strata[t] == "post-cutoff") == (scope == "post-cutoff")}
            if not sel:
                continue
            for pair in pairs:
                if scope == "controls" and pair not in ("C/A",):
                    continue
                treat, ctrl = pair.split("/")
                res = analyse_pair(sel, treat, ctrl, notes_pair=(ctrl in notes_free and treat not in notes_free))
                if res:
                    st["pairs"].setdefault(scope, {})[pair] = res
        st["condition_totals"] = {k: v for k, v in st["condition_totals"].items() if v}
        out["studies"][key] = st
        print("done", key, file=sys.stderr)
    # token-vs-cost correlation over all Opus 5.5 benchmark task-study cells (C/A, post-cutoff)
    lt, lc, cells = [], [], 0
    for key in ("opus55_main", "opus55_replication", "opus55_tasks2"):
        pt = out["studies"][key]["pairs"]["post-cutoff"]["C/A"]["token_vs_cost"]["per_task"]
        for v in pt.values():
            lt.append(math.log(v["tokens_ratio"])); lc.append(math.log(v["cost_ratio"])); cells += 1
    out["opus55_token_vs_cost_all_cells"] = {"cells": cells, "pearson_r_log_ratios": pearson(lt, lc),
                                             "studies": ["opus55_main", "opus55_replication", "opus55_tasks2"]}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "token_breakdown.json"
    path.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print("wrote", path.name)


if __name__ == "__main__":
    main()
