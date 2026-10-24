"""Unified-unit break-even with propagated uncertainty (round 22, an internal review W1, W2, Q2, Q3, change 2, item 10).

usage: python -I scripts/breakeven_unified.py   ->   scripts/breakeven_unified_out.txt and analysis/breakeven_unified.json

POST HOC AND EXPLORATORY. Offline, no model sessions, no network. Aggregates only: the transcript store is read for
counts, model-call counts, token usage and edited-file paths (used only to rebuild fsess.py's project clusters in
memory); no transcript content, path, project name or session id is printed or written.

Net saving per context (all terms in dollars per agent context, Opus 5.5 list prices):
    N = f * s + (1 - f) * u * K - c
One unit throughout: the model API call (distinct assistant message id with a real model id; turns_vs_calls.py and
context_cost.py count the same way).
  t_bench  mean model calls of the main study's C sessions on its 17 post-cutoff tasks (stream.jsonl; 11.31)
  t_ctx    mean model calls of the contexts in the base (all 1,308 contexts; or the 513 Python-editing ones)
  c        b * (t_ctx * p_r + p_w): one cache read of the b-token block per call, one 1-hour cache write per context
           (the paper's formula; p_r = $0.20, p_w = $8 per MTok, recompute_cost.PRICES)
  s        gross saving per affected use = task mean of (mean A cost - mean C cost) on the main study's post-cutoff
           tasks + the benchmark block's own cost, now computed with each C session's model calls instead of CLI
           num_turns (blocksize_breakeven.py computed it with num_turns).
           S-fixed (default): the saving is a fixed amount per affected use and does not grow with context length.
           S-prop (alternative): the saving scales with length, s_ctx = s * t_ctx / t_bench.
  K        cost of an unaffected context at the contexts' length, MEASURED from the transcripts' logged usage
           (input, output, cache read, 5-minute and 1-hour cache writes per distinct message id, field-wise max over
           the records of one message) priced at Opus 5.5 list prices for every context whatever model ran it; mean
           over the contexts in the base. Affected contexts cannot be removed (per-transcript f flags were deleted
           with fsess.py's work folder), so K is the mean over all contexts of the base (f <= 18% of them).
           Sensitivity: the benchmark K ($0.1717, 30 control A sessions) scaled by model calls, K * t_ctx / t_ctrlA.
  u        relative cost change of an unaffected context (positive = cheaper): 1 - r, r = geometric mean over the
           ten pooled main + new-task control tasks of median C cost / median A cost (the paper's estimator;
           pooled_main_tasks2.json 0.9337). Assumed to be a constant relative effect, so u * K scales with K. As in
           the paper, r includes the benchmark block's own cost, so 1 - r understates u slightly (reported).
           Sensitivity: the six controls whose block is non-empty (requested in an internal review).
  f        f_strict (edited code uses a changed API) and f_upper (edited Python file imports a changed package), per
           context, from analysis/f_sessions.json; also f_upper with unrecovered headers imputed (S7).

Bootstrap (10,000 draws, numpy default_rng(20261001), percentile 95% intervals). In each draw, independently:
  benchmark: resample the 17 post-cutoff tasks (s and t_bench together) and the 10 control tasks (u), task clusters;
  transcripts: resample fsess.py's project clusters (170 for all contexts, 133 for Python-editing ones); f, t_ctx (so
  c) and K are recomputed from the same resampled contexts.
Per-cluster f counts: fsess.py's per-transcript flags were deleted, but f_sessions.json gives the counts by project
category. The clusters are rebuilt from the store with fsess.project_key on each context's successful edits (records
stamped before the f run, as context_cost.py) and checked against f_sessions.json (n, clusters, edit_py per category).
Categories with one cluster (the tool's repository, other projects) get their exact counts; within categories with
several clusters (OSS 133, scratch 2, home 4, temp 3) a category's count is spread over its clusters in proportion to
their Python-editing contexts (fractional counts). The rebuilt cluster bootstrap of f is checked against the
published CIs. S7 imputed counts: the 56.2 imputed units (147.2 - 91) are spread over categories in proportion to
(category complete-case rate x missing-header contexts), then over clusters as above (approximate).
"""
import collections
import datetime as dt
import glob
import json
import math
import os
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(STUDY / "expansion" / "fsessions"))
from recompute_cost import PRICES, list_cost  # noqa: E402
from blocksize_breakeven import load as load_runs  # noqa: E402
from turns_vs_calls import stream_path, count as count_stream  # noqa: E402
from context_cost import x1, x2b, low, ts_of, PATH_TOOLS, EDIT_TOOLS  # noqa: E402
from fsess import project_key  # noqa: E402

OUT_TXT = HERE / "breakeven_unified_out.txt"
OUT_JSON = STUDY / "analysis" / "breakeven_unified.json"
STORE = Path(os.path.expanduser("~")) / ".claude" / "projects"
OPUS = "claude-opus-5-5"
P_R, P_W = PRICES[OPUS][2] / 1e6, PRICES[OPUS][3] / 1e6
SEED, B = 20261001, 10000
BLOCKS = {"704 (random-sample median non-empty; primary)": 704, "423 (benchmark mean)": 423,
          "1,014 (random-sample mean non-empty)": 1014, "1,024.5 (AI-stack median non-empty)": 1024.5,
          "1,320 (AI-stack mean non-empty)": 1320}
PRIMARY_BLOCK = 704
Z80 = 1.959964 + 0.841621


# ------------------------------------------------------------------------------------------- benchmark terms
def benchmark_terms():
    an = STUDY / "analysis"
    ex = json.loads((an / "exposure2_breakeven.json").read_text(encoding="utf-8"))
    b2 = json.loads((an / "breakeven2d.json").read_text(encoding="utf-8"))
    pooled = json.loads((an / "pooled_main_tasks2.json").read_text(encoding="utf-8"))
    post = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in load_runs("main-2026-09-28"):
        if r["stratum"] != "post-cutoff" or r["condition"] not in ("A", "C"):
            continue
        res = r.get("result") or {}
        p = stream_path("main-2026-09-28", r["run_id"])
        calls = count_stream(p)[0] if p else None
        notes = (r.get("condition_config") or {}).get("notes_tokens") or 0
        post[r["task"]][r["condition"]].append({
            "cost": list_cost(r["agent"]["model"], res.get("usage") or {}), "turns": res.get("num_turns") or 0,
            "calls": calls, "notes": notes})
    tasks = sorted(t for t in post if post[t]["A"] and post[t]["C"])
    mean = statistics.mean
    s_net = np.array([mean(x["cost"] for x in post[t]["A"]) - mean(x["cost"] for x in post[t]["C"]) for t in tasks])
    ob_calls = np.array([mean(x["notes"] * (x["calls"] * P_R + P_W) for x in post[t]["C"]) for t in tasks])
    ob_turns = np.array([mean(x["notes"] * (x["turns"] * P_R + P_W) for x in post[t]["C"]) for t in tasks])
    tc_calls = np.array([mean(x["calls"] for x in post[t]["C"]) for t in tasks])
    tc_turns = np.array([mean(x["turns"] for x in post[t]["C"]) for t in tasks])
    a_cost_post = [x["cost"] for t in tasks for x in post[t]["A"]]

    ctrl = collections.defaultdict(lambda: collections.defaultdict(list))
    empty = set()
    for st in ("main-2026-09-28", "tasks2-opus55-2026-10-22"):
        for r in load_runs(st):
            if r["stratum"] == "post-cutoff" or r["condition"] not in ("A", "C"):
                continue
            res = r.get("result") or {}
            p = stream_path(st, r["run_id"])
            notes = (r.get("condition_config") or {}).get("notes_tokens") or 0
            ctrl[r["task"]][r["condition"]].append({
                "cost": list_cost(r["agent"]["model"], res.get("usage") or {}),
                "calls": count_stream(p)[0] if p else None, "turns": res.get("num_turns") or 0, "notes": notes})
            if r["condition"] == "C" and not notes:
                empty.add(r["task"])
    ctasks = sorted(t for t in ctrl if ctrl[t]["A"] and ctrl[t]["C"])
    logr = np.array([math.log(statistics.median(x["cost"] for x in ctrl[t]["C"]) /
                              statistics.median(x["cost"] for x in ctrl[t]["A"])) for t in ctasks])
    nonempty = np.array([t not in empty for t in ctasks])
    a_ctrl = [x for t in ctasks for x in ctrl[t]["A"]]
    c_ctrl = [x for t in ctasks for x in ctrl[t]["C"]]
    K_bench = mean(x["cost"] for x in a_ctrl)
    t_ctrlA = mean(x["calls"] for x in a_ctrl)
    ob_ctrl = mean(x["notes"] * (x["calls"] * P_R + P_W) for x in c_ctrl)
    T = {"tasks": tasks, "s_net": s_net, "ob_calls": ob_calls, "ob_turns": ob_turns, "tc_calls": tc_calls,
         "tc_turns": tc_turns, "ctasks": ctasks, "logr": logr, "nonempty": nonempty, "K_bench": K_bench,
         "t_ctrlA": t_ctrlA, "ob_ctrl_share_of_K": ob_ctrl / K_bench,
         "a_cost_post": a_cost_post, "a_cost_ctrl": [x["cost"] for x in a_ctrl]}
    T["checks"] = {
        "S_gross_num_turns (blocksize_breakeven, paper)": (float(s_net.mean() + ob_turns.mean()),
                                                          ex["studies"]["main"]["S_gross_usd"]),
        "t_bench num_turns": (float(tc_turns.mean()), ex["studies"]["main"]["mean_C_turns"]),
        "control r cost (pooled_main_tasks2)": (float(math.exp(logr.mean())),
                                               pooled["results"]["controls"]["C/A"]["ratios"]["list_cost_usd"]["ratio"]),
        "K_bench (breakeven2d)": (K_bench, b2["K_control_A_mean_cost_usd"]),
        "control A sessions": (len(a_ctrl), b2["K_control_A_sessions"])}
    return T


# ------------------------------------------------------------------------------------------- transcripts
def scan(f, cutoff):
    rel = Path(f).relative_to(STORE).parts
    sub = "subagents" in rel
    top = rel[1] if sub else Path(f).stem
    first_ts, models, cwds, paths, edited = None, collections.Counter(), set(), set(), []
    usage = {}
    pending, py_edit = {}, False
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = ts_of(r)
            if t is not None and t >= cutoff:
                continue
            if r.get("cwd"):
                cwds.add(low(r["cwd"]))
            typ, m = r.get("type"), r.get("message")
            if typ == "assistant" and isinstance(m, dict):
                mod = m.get("model")
                if mod and not mod.startswith("<"):
                    models[mod] += 1
                    if first_ts is None and r.get("timestamp"):
                        first_ts = r["timestamp"]
                    if not r.get("isApiErrorMessage"):
                        mid = m.get("id") or r.get("requestId") or r.get("uuid")
                        u = m.get("usage") if isinstance(m.get("usage"), dict) else {}
                        cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
                        cur = {"input_tokens": u.get("input_tokens") or 0, "output_tokens": u.get("output_tokens") or 0,
                               "cache_read_input_tokens": u.get("cache_read_input_tokens") or 0,
                               "cache_creation_input_tokens": u.get("cache_creation_input_tokens") or 0,
                               "w1h": cc.get("ephemeral_1h_input_tokens"), "w5m": cc.get("ephemeral_5m_input_tokens")}
                        old = usage.get(mid)
                        if old is None:
                            usage[mid] = cur
                        else:
                            for k, v in cur.items():
                                if v is not None and (old[k] is None or v > old[k]):
                                    old[k] = v
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in PATH_TOOLS:
                        inp = c.get("input") or {}
                        p = inp.get("file_path") or inp.get("notebook_path") if isinstance(inp, dict) else None
                        if isinstance(p, str) and p:
                            paths.add(low(p))
                            if c.get("name") in EDIT_TOOLS:
                                pending[c.get("id")] = (c.get("name"), inp, p)
                continue
            if typ == "user" and isinstance(m, dict) and isinstance(m.get("content"), list):
                for c in m["content"]:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        pe = pending.pop(c.get("tool_use_id"), None)
                        if pe and not c.get("is_error"):
                            name, inp, p = pe
                            edited.append(p)
                            lp = low(p)
                            if lp.endswith(".py") and name != "NotebookEdit":
                                py_edit = True
                            elif lp.endswith(".ipynb") and name == "NotebookEdit" and \
                                    (inp.get("cell_type") or "code") == "code":
                                py_edit = True
    cost = 0.0
    for u in usage.values():
        uu = {"input_tokens": u["input_tokens"], "output_tokens": u["output_tokens"],
              "cache_read_input_tokens": u["cache_read_input_tokens"],
              "cache_creation_input_tokens": u["cache_creation_input_tokens"]}
        if u["w1h"] is not None or u["w5m"] is not None:
            uu["cache_creation"] = {"ephemeral_1h_input_tokens": u["w1h"] or 0, "ephemeral_5m_input_tokens": u["w5m"] or 0}
        cost += list_cost(OPUS, uu)
    keys = [project_key(p) for p in edited]
    nonscratch = collections.Counter(k for k, s in keys if not s)
    allk = collections.Counter(k for k, s in keys)
    cluster = (nonscratch.most_common(1)[0][0] if nonscratch else allk.most_common(1)[0][0] if allk
               else "session:" + top)
    return {"sub": sub, "top": top, "first_ts": first_ts, "model": models.most_common(1)[0][0] if models else None,
            "locs": list(cwds) + list(paths), "calls": len(usage), "cost": cost, "py_edit": py_edit,
            "cluster": cluster, "usage_logged": sum(1 for u in usage.values() if u["input_tokens"] or
                                                    u["cache_read_input_tokens"] or u["output_tokens"])}


def transcripts(fs):
    cutoff = dt.datetime.fromisoformat(fs["generated"])
    files = sorted(glob.glob(str(STORE / "**" / "*.jsonl"), recursive=True))
    ts = [scan(f, cutoff) for f in files]
    for t in ts:
        t["x"] = ("X0" if not t["model"] or not t["first_ts"] else "X1" if x1(t) else "X2b" if x2b(t) else None)
    research = {t["top"] for t in ts if t["x"] == "X2b"}
    for t in ts:
        if t["x"] is None and t["top"] in research:
            t["x"] = "X2a"
    inc = [t for t in ts if t["x"] is None]
    for t in inc:
        k = t["cluster"]
        t["cat"] = "tool_repo" if k == "projects:sc-tool" else k.split(":")[0]
        t["cat7"] = k.split(":")[0]   # fsess.py S7 category (tool repo inside 'projects')
    return inc


def allocate(inc, fs):
    """Per-cluster fractional f counts (see module docstring)."""
    bycat = fs["by_project_category"]
    cl = collections.OrderedDict()
    for t in sorted(inc, key=lambda t: t["cluster"]):
        c = cl.setdefault(t["cluster"], {"cat": t["cat"], "cat7": t["cat7"], "n": 0, "py": 0, "calls": 0.0,
                                         "cost": 0.0, "calls_py": 0.0, "cost_py": 0.0})
        c["n"] += 1
        c["calls"] += t["calls"]
        c["cost"] += t["cost"]
        if t["py_edit"]:
            c["py"] += 1
            c["calls_py"] += t["calls"]
            c["cost_py"] += t["cost"]
    check = {}
    for cat, v in bycat.items():
        mine = [c for c in cl.values() if c["cat"] == cat]
        check[cat] = {"n": (sum(c["n"] for c in mine), v["n"]), "clusters": (len(mine), v["clusters"]),
                      "edit_py": (sum(c["py"] for c in mine), v["edit_py"])}
    for flag in ("upper", "strict"):
        for cat, v in bycat.items():
            mine = [c for c in cl.values() if c["cat"] == cat]
            w = sum(c["py"] for c in mine)
            for c in mine:
                c[flag] = v[flag] * c["py"] / w if w else 0.0
    s7 = fs["S7_missing_header_imputed"]
    extra = s7["upper_imputed"]["k"] - fs["primary"]["upper"]["k"]
    wcat = {c: s7["complete_case_rate_by_category"][c] * m for c, m in s7["missing_by_category"].items()}
    tot = sum(wcat.values())
    for c in cl.values():
        c["imputed"] = c["upper"]
    for cat7, wc in wcat.items():
        mine = [c for c in cl.values() if c["cat7"] == cat7]
        w = sum(c["py"] for c in mine)
        for c in mine:
            c["imputed"] += extra * wc / tot * c["py"] / w if w else 0.0
    return cl, check, extra


def cluster_arrays(cl, base):
    cs = [c for c in cl.values() if (base == "all" or c["py"] > 0)]
    n = np.array([c["n"] if base == "all" else c["py"] for c in cs], float)
    calls = np.array([c["calls"] if base == "all" else c["calls_py"] for c in cs], float)
    cost = np.array([c["cost"] if base == "all" else c["cost_py"] for c in cs], float)
    k = {f: np.array([c[f] for c in cs], float) for f in ("strict", "upper", "imputed")}
    return n, calls, cost, k


# ------------------------------------------------------------------------------------------- helpers
def ci(x):
    x = np.sort(np.asarray(x))
    return [float(x[int(0.025 * len(x))]), float(x[int(0.975 * len(x)) - 1])]


def fm(x, d=2):
    return f"{x:,.{d}f}"


def main():
    L = []
    say = L.append
    an = STUDY / "analysis"
    fs = json.loads((an / "f_sessions.json").read_text(encoding="utf-8"))
    r9 = json.loads((an / "round9_numbers.json").read_text(encoding="utf-8"))["live_ab_sizing"]
    T = benchmark_terms()
    inc = transcripts(fs)
    cl, check, extra = allocate(inc, fs)
    rng = np.random.default_rng(SEED)

    # ---------------------------------------------------------------- point terms
    s_fixed = float(T["s_net"].mean() + T["ob_calls"].mean())
    t_bench = float(T["tc_calls"].mean())
    u_pt = 1 - math.exp(T["logr"].mean())
    u6_pt = 1 - math.exp(T["logr"][T["nonempty"]].mean())
    out = {"generated_by": "scripts/breakeven_unified.py", "post_hoc": True, "seed": SEED, "B": B,
           "model": "N = f*s + (1-f)*u*K - c per agent context; all lengths in model API calls",
           "inputs": ["runs_tables/main-2026-09-28/runs.jsonl + stream.jsonl", "runs_tables/tasks2-opus55-2026-10-22/"
                      "runs.jsonl + stream.jsonl", "analysis/f_sessions.json", "analysis/exposure2_breakeven.json",
                      "analysis/breakeven2d.json", "analysis/pooled_main_tasks2.json", "analysis/round9_numbers.json",
                      "~/.claude/projects transcripts (records before the f run; counts and usage only)"]}
    say("breakeven_unified.py (round 22): unified-unit break-even with propagated uncertainty. POST HOC, EXPLORATORY.")
    say("Aggregates only; transcript records stamped before the f run (" + fs["generated"] + ").")
    say("")
    say("0. Checks against existing outputs (this script vs source)")
    for k, (a, b) in T["checks"].items():
        say(f"   {k}: {a:.6g} vs {b:.6g} {'MATCH' if abs(a - b) <= 1e-4 * max(1, abs(b)) else 'DIFF'}")
    nall = len(inc)
    say(f"   included contexts: {nall} vs {fs['included']['transcripts']}; Python-editing "
        f"{sum(t['py_edit'] for t in inc)} vs {fs['primary']['edit_py']['k']}; mean calls all "
        f"{statistics.mean(t['calls'] for t in inc):.2f} (context_cost_out.txt 45.26), Python-editing "
        f"{statistics.mean(t['calls'] for t in inc if t['py_edit']):.2f} (81.55)")
    ok = all(a == b for v in check.values() for a, b in v.values())
    say(f"   project clusters rebuilt with fsess.project_key vs f_sessions.json by_project_category (n, clusters, "
        f"edit_py): {'ALL MATCH' if ok else 'DIFF ' + json.dumps(check)}")
    out["checks"] = {"benchmark": T["checks"], "clusters_by_category": check, "clusters_all_match": ok}

    # ---------------------------------------------------------------- transcript cost (K)
    say("")
    say("1. Terms in one unit (model calls)")
    say(f"   t_bench = {t_bench:.2f} model calls (main study, C sessions, 17 post-cutoff tasks); CLI num_turns "
        f"{T['tc_turns'].mean():.2f}")
    say(f"   s (fixed per affected use) = mean(A - C) ${T['s_net'].mean():.5f} + benchmark block's own cost at model "
        f"calls ${T['ob_calls'].mean():.5f} = ${s_fixed:.5f} (paper, num_turns: ${T['s_net'].mean() + T['ob_turns'].mean():.5f})")
    say(f"   u (pooled 10 controls) = 1 - {math.exp(T['logr'].mean()):.4f} = {u_pt:.4f}; six non-empty controls: "
        f"{u6_pt:.4f}; benchmark block's own cost on control C sessions = {T['ob_ctrl_share_of_K']:.4f} of K_bench "
        f"(1 - r understates u by about this much; not added, as in the paper)")
    say(f"   K_bench = ${T['K_bench']:.4f} per control A session ({T['t_ctrlA']:.2f} model calls; "
        f"${T['K_bench'] / T['t_ctrlA']:.5f} per call)")
    usage_ok = sum(1 for t in inc if t["usage_logged"] > 0)
    say(f"   transcript usage: logged for {usage_ok}/{nall} included contexts; priced at Opus 5.5 list prices "
        f"(recompute_cost.list_cost) whatever model ran the context")
    bases = {}
    for base, sel in (("all", inc), ("py", [t for t in inc if t["py_edit"]])):
        calls = np.array([t["calls"] for t in sel], float)
        cost = np.array([t["cost"] for t in sel], float)
        bases[base] = {"n": len(sel), "t_ctx": float(calls.mean()), "K_ctx": float(cost.mean()),
                       "K_ctx_median": float(np.median(cost)), "cost_per_call": float(cost.sum() / calls.sum()),
                       "K_scaled_bench": T["K_bench"] * float(calls.mean()) / T["t_ctrlA"],
                       "f_point": {"strict": fs["primary"]["strict"]["share"] if base == "all"
                                   else fs["primary"]["given_edit_py"]["strict"]["share"],
                                   "upper": fs["primary"]["upper"]["share"] if base == "all"
                                   else fs["primary"]["given_edit_py"]["upper"]["share"],
                                   "imputed": fs["S7_missing_header_imputed"]["upper_imputed"]["share"] if base == "all"
                                   else fs["S7_missing_header_imputed"]["upper_imputed_given_py"]["share"]}}
        bb = bases[base]
        lab = "all contexts" if base == "all" else "Python-editing contexts"
        say(f"   [{lab}] n = {bb['n']}; t_ctx = {bb['t_ctx']:.2f} calls ({bb['t_ctx'] / t_bench:.2f} x t_bench); "
            f"K_ctx measured = ${bb['K_ctx']:.4f} per context (median ${bb['K_ctx_median']:.4f}; ${bb['cost_per_call']:.5f}"
            f" per call); benchmark K scaled by calls would be ${bb['K_scaled_bench']:.4f}; c(704) = "
            f"${704 * (bb['t_ctx'] * P_R + P_W):.5f}; c/K_ctx = {704 * (bb['t_ctx'] * P_R + P_W) / bb['K_ctx']:.4f}")
    out["terms"] = {"t_bench_calls": t_bench, "t_bench_num_turns": float(T["tc_turns"].mean()),
                    "s_fixed_usd": s_fixed, "s_net_usd": float(T["s_net"].mean()),
                    "bench_block_cost_calls_usd": float(T["ob_calls"].mean()),
                    "bench_block_cost_turns_usd": float(T["ob_turns"].mean()), "u_point_pooled10": u_pt,
                    "u_point_nonempty6": u6_pt, "bench_block_share_of_K_controls": T["ob_ctrl_share_of_K"],
                    "K_bench_usd": T["K_bench"], "t_ctrlA_calls": T["t_ctrlA"], "bases": bases,
                    "usage_logged_contexts": usage_ok}

    # ---------------------------------------------------------------- f reconstruction check
    say("")
    say("2. Rebuilt per-cluster f (fractional allocation within multi-cluster categories) vs published f CIs")
    arr = {b: cluster_arrays(cl, b) for b in ("all", "py")}
    idx = {b: rng.integers(0, len(arr[b][0]), size=(B, len(arr[b][0]))) for b in ("all", "py")}
    fdraw = {}
    pub = {("all", "strict"): fs["primary"]["strict"], ("all", "upper"): fs["primary"]["upper"],
           ("all", "imputed"): fs["S7_missing_header_imputed"]["upper_imputed"],
           ("py", "strict"): fs["primary"]["given_edit_py"]["strict"],
           ("py", "upper"): fs["primary"]["given_edit_py"]["upper"],
           ("py", "imputed"): fs["S7_missing_header_imputed"]["upper_imputed_given_py"]}
    out["f_reconstruction"] = {}
    for b in ("all", "py"):
        n, calls, cost, k = arr[b]
        N = n[idx[b]].sum(1)
        fdraw[b] = {"n": N, "t_ctx": calls[idx[b]].sum(1) / N, "K_ctx": cost[idx[b]].sum(1) / N}
        for f in ("strict", "upper", "imputed"):
            fdraw[b][f] = k[f][idx[b]].sum(1) / N
            pt = float(k[f].sum() / n.sum())
            c95 = ci(fdraw[b][f])
            say(f"   {b:3s} {f:8s}: point {pt:.4f} (published {pub[(b, f)]['share']}); rebuilt CI [{c95[0]:.4f}, "
                f"{c95[1]:.4f}] vs published {pub[(b, f)]['ci95']}{' (published CI too narrow: rates fixed)' if f == 'imputed' else ''}")
            out["f_reconstruction"][f"{b}|{f}"] = {"point": pt, "ci95_rebuilt": c95, "published": pub[(b, f)]}
        say(f"   {b:3s} clusters {len(n)}; t_ctx CI {fm(ci(fdraw[b]['t_ctx'])[0])}-{fm(ci(fdraw[b]['t_ctx'])[1])}; "
            f"K_ctx CI ${ci(fdraw[b]['K_ctx'])[0]:.4f}-${ci(fdraw[b]['K_ctx'])[1]:.4f}")
        out["f_reconstruction"][f"{b}|t_ctx_ci95"] = ci(fdraw[b]["t_ctx"])
        out["f_reconstruction"][f"{b}|K_ctx_ci95"] = ci(fdraw[b]["K_ctx"])
    say(f"   S7 imputed units spread: {extra:.1f}")

    # ---------------------------------------------------------------- benchmark draws
    nt, nc = len(T["tasks"]), len(T["ctasks"])
    ti = rng.integers(0, nt, size=(B, nt))
    ci_ = rng.integers(0, nc, size=(B, nc))
    s_d = T["s_net"][ti].mean(1) + T["ob_calls"][ti].mean(1)
    tb_d = T["tc_calls"][ti].mean(1)
    u_d = 1 - np.exp(T["logr"][ci_].mean(1))
    ne_idx = np.flatnonzero(T["nonempty"])
    ci6 = rng.integers(0, len(ne_idx), size=(B, len(ne_idx)))
    u6_d = 1 - np.exp(T["logr"][ne_idx][ci6].mean(1))
    say("")
    say("3. Benchmark draws (task-cluster bootstrap)")
    say(f"   s fixed ${s_fixed:.4f} [{ci(s_d)[0]:.4f}, {ci(s_d)[1]:.4f}]; t_bench {t_bench:.2f} [{ci(tb_d)[0]:.2f}, "
        f"{ci(tb_d)[1]:.2f}]; u pooled-10 {u_pt:.4f} [{ci(u_d)[0]:.4f}, {ci(u_d)[1]:.4f}], P(u > 0) = "
        f"{(u_d > 0).mean():.3f}; u non-empty-6 {u6_pt:.4f} [{ci(u6_d)[0]:.4f}, {ci(u6_d)[1]:.4f}], P(u > 0) = "
        f"{(u6_d > 0).mean():.3f}")
    out["benchmark_draws"] = {"s_fixed": [s_fixed, ci(s_d)], "t_bench": [t_bench, ci(tb_d)],
                              "u_pooled10": [u_pt, ci(u_d), float((u_d > 0).mean())],
                              "u_nonempty6": [u6_pt, ci(u6_d), float((u6_d > 0).mean())]}

    # ---------------------------------------------------------------- net saving
    def net(b, fkey, blk, svar, ukey, kvar="measured", draws=True):
        if draws:
            fd = fdraw[b]
            f, t, K = fd[fkey], fd["t_ctx"], fd["K_ctx"]
            s, tb = s_d, tb_d
            u = {"0": 0.0, "est": u_d, "est6": u6_d}[ukey]
        else:
            bb = bases[b]
            f, t, K = bb["f_point"][fkey], bb["t_ctx"], bb["K_ctx"]
            s, tb = s_fixed, t_bench
            u = {"0": 0.0, "est": u_pt, "est6": u6_pt}[ukey]
        if kvar == "scaled":
            K = T["K_bench"] * t / T["t_ctrlA"]
        c = blk * (t * P_R + P_W)
        sc = s if svar == "fixed" else s * t / tb
        return f * sc + (1 - f) * u * K - c

    say("")
    say("4. Net saving N per 1,000 contexts (dollars): point [95% CI], P(N > 0). K measured from transcripts.")
    rows = {}
    FLAB = {"strict": "f_strict", "upper": "f_upper", "imputed": "f_upper imputed (S7)"}
    ULAB = {"0": "u = 0", "est": "u est. (10 controls)", "est6": "u est. (6 non-empty controls)"}
    for svar in ("fixed", "prop"):
        say(f"   --- s {'fixed per affected use (default)' if svar == 'fixed' else 'proportional to length (alternative)'}")
        for blab, blk in BLOCKS.items():
            primary = blk == PRIMARY_BLOCK
            if not primary and svar == "prop":
                continue
            say(f"   block {blab}")
            for b in ("all", "py"):
                for fkey in ("strict", "upper", "imputed"):
                    for ukey in (("0", "est", "est6") if primary else ("0", "est")):
                        pt = 1000 * net(b, fkey, blk, svar, ukey, draws=False)
                        d = 1000 * net(b, fkey, blk, svar, ukey)
                        lo, hi = ci(d)
                        p = float((d > 0).mean())
                        key = f"{svar}|{blk}|{b}|{fkey}|{ukey}"
                        rows[key] = {"N_per_1000_usd": pt, "ci95": [lo, hi], "P_N_gt_0": p}
                        say(f"     {('all' if b == 'all' else 'py '):3s} {FLAB[fkey]:22s} {ULAB[ukey]:30s} "
                            f"{pt:9.2f} [{lo:8.2f}, {hi:8.2f}]  P = {p:.3f}")
    say("   --- sensitivity: K = benchmark K scaled by model calls (not measured), s fixed, 704 tokens")
    for b in ("all", "py"):
        for fkey in ("strict", "upper"):
            pt = 1000 * net(b, fkey, 704, "fixed", "est", "scaled", draws=False)
            d = 1000 * net(b, fkey, 704, "fixed", "est", "scaled")
            rows[f"fixed|704|{b}|{fkey}|est|K_scaled"] = {"N_per_1000_usd": pt, "ci95": ci(d),
                                                          "P_N_gt_0": float((d > 0).mean())}
            say(f"     {b:3s} {FLAB[fkey]:22s} u est.: {pt:9.2f} [{ci(d)[0]:8.2f}, {ci(d)[1]:8.2f}]  "
                f"P = {(d > 0).mean():.3f}")
    out["net_saving"] = rows

    # ---------------------------------------------------------------- f* and u*
    say("")
    say("5. Break-even f* at u = 0 (= c / s) in the unified unit, point [95% CI]; and u needed at the measured f")
    fst = {}
    for blab, blk in BLOCKS.items():
        for b in ("all", "py"):
            bb = bases[b]
            c_pt = blk * (bb["t_ctx"] * P_R + P_W)
            c_d = blk * (fdraw[b]["t_ctx"] * P_R + P_W)
            for svar in ("fixed", "prop"):
                s_pt = s_fixed if svar == "fixed" else s_fixed * bb["t_ctx"] / t_bench
                s_dd = s_d if svar == "fixed" else s_d * fdraw[b]["t_ctx"] / tb_d
                pt = c_pt / s_pt
                d = np.where(s_dd > 0, c_d / np.maximum(s_dd, 1e-12), np.inf)
                lo, hi = ci(d)
                fst[f"{blk}|{b}|{svar}"] = {"f_star": pt, "ci95": [lo, hi], "P_f_star_gt_1_or_never": float((d > 1).mean())}
                if blk == PRIMARY_BLOCK or svar == "fixed":
                    say(f"   block {blk:>6}, {b:3s}, s {svar:5s}: f* = {pt:.4f} [{lo:.4f}, {hi:.4f}]; c = ${c_pt:.5f}, "
                        f"s = ${s_pt:.4f}")
    for b in ("all", "py"):
        bb = bases[b]
        for fkey in ("strict", "upper"):
            f, t, K = bb["f_point"][fkey], bb["t_ctx"], bb["K_ctx"]
            c = 704 * (t * P_R + P_W)
            ustar = (c - f * s_fixed) / ((1 - f) * K)
            fd = fdraw[b]
            ud = (704 * (fd["t_ctx"] * P_R + P_W) - fd[fkey] * s_d) / ((1 - fd[fkey]) * fd["K_ctx"])
            fst[f"u_needed|704|{b}|{fkey}"] = {"u_needed": ustar, "ci95": ci(ud),
                                               "P_u_est_gt_u_needed": float((u_d > ud).mean())}
            say(f"   u needed (704, s fixed, K measured) {b:3s} {FLAB[fkey]}: {ustar:.4f} [{ci(ud)[0]:.4f}, "
                f"{ci(ud)[1]:.4f}]; P(u > u needed) = {(u_d > ud).mean():.3f}")
    out["f_star_u0"] = fst

    # ---------------------------------------------------------------- Lesson 2 power
    say("")
    say("6. Lesson 2 live A/B sizing (requested in an internal review). n per arm = 2 (z.975 + z.80)^2 V / delta^2")
    # exact session-level SDs of log None cost on post-cutoff tasks (round9_numbers.json stores them rounded)
    lg = {}
    for st in ("main-2026-09-28", "abl-opus55-2026-10-22", "tasks2-opus55-2026-10-22", "conc-opus55-2026-10-23"):
        lg[st] = [math.log(list_cost(r["agent"]["model"], (r.get("result") or {}).get("usage") or {}))
                  for r in load_runs(st) if r["stratum"] == "post-cutoff" and r["condition"] == "A"]
    sd_m = statistics.stdev(lg["main-2026-09-28"])
    sd_a = statistics.stdev([x for v in lg.values() for x in v])
    say(f"   SD of log None cost, post-cutoff: main {sd_m:.4f} ({len(lg['main-2026-09-28'])} sessions; round9 "
        f"{r9['sd_log_cost_none_sessions_main']}, {r9['none_sessions_main']}), four Opus studies {sd_a:.4f} "
        f"({sum(len(v) for v in lg.values())}; round9 {r9['sd_log_cost_none_sessions_4_opus_studies']}, "
        f"{r9['none_sessions_4_opus_studies']})")
    mu_a, mu_u = statistics.mean(T["a_cost_post"]), T["K_bench"]   # exact (round9 stores 0.4193)
    s_paper = 0.08724311764705882
    c_paper = 704 * (16.647058823529413 * P_R + P_W)
    gain = 0.2 * s_paper - c_paper

    def n_log(d, sd):
        return 2 * Z80 ** 2 * sd ** 2 / (-math.log(1 - d)) ** 2
    L2 = {}
    d1 = gain / mu_a
    L2["paper"] = {"d": d1, "n_main_sd": n_log(d1, sd_m), "n_all_sd": n_log(d1, sd_a)}
    mu_all = 0.2 * mu_a + 0.8 * mu_u
    d2 = gain / mu_all
    L2["reviewer_denominator"] = {"mean_all_session_cost": mu_all, "d": d2, "n_main_sd": n_log(d2, sd_m),
                                  "n_all_sd": n_log(d2, sd_a)}
    # raw-cost test on the mixed population (the estimand is the mean cost per session)
    xa, xu = np.array(T["a_cost_post"]), np.array(T["a_cost_ctrl"])
    va, vu = xa.var(ddof=1), xu.var(ddof=1)
    ma, mu = xa.mean(), xu.mean()
    vmix = 0.2 * va + 0.8 * vu + 0.2 * 0.8 * (ma - mu) ** 2
    n_raw = 2 * Z80 ** 2 * vmix / gain ** 2
    L2["raw_cost_mixture"] = {"affected_A_sessions": len(xa), "affected_mean": float(ma), "affected_sd": float(va ** .5),
                              "unaffected_A_sessions": len(xu), "unaffected_mean": float(mu),
                              "unaffected_sd": float(vu ** .5), "mixture_sd": float(vmix ** .5),
                              "mixture_cv": float(vmix ** .5 / (0.2 * ma + 0.8 * mu)), "delta_usd": gain,
                              "n_per_arm": n_raw}
    # unified unit: c at benchmark model calls, s at model calls
    c_calls = 704 * (t_bench * P_R + P_W)
    gain_u = 0.2 * s_fixed - c_calls
    L2["raw_cost_mixture_model_calls"] = {"delta_usd": gain_u, "d": gain_u / (0.2 * ma + 0.8 * mu),
                                          "n_per_arm": 2 * Z80 ** 2 * vmix / gain_u ** 2}
    # log-scale test with the effect computed per group (affected cheaper by (s - c), unaffected dearer by c, u = 0)
    dlog = 0.2 * math.log(1 - (s_paper - c_paper) / mu_a) + 0.8 * math.log(1 + c_paper / mu_u)
    L2["log_scale_mixture_note"] = {"mean_log_effect": dlog,
                                    "n_per_arm_at_main_sd": 2 * Z80 ** 2 * sd_m ** 2 / dlog ** 2}
    say(f"   paper: d = (0.2 x {s_paper:.4f} - {c_paper:.5f}) / {mu_a:.4f} = {d1:.4f}; n = {L2['paper']['n_main_sd']:.0f}"
        f" (SD {sd_m:.3f}) to {L2['paper']['n_all_sd']:.0f} (SD {sd_a:.3f})  [round9_numbers.json: 6,042 / 7,843]")
    say(f"   reviewer's denominator: all-session mean 0.2 x {mu_a:.4f} + 0.8 x {mu_u:.4f} = ${mu_all:.4f}; d = {d2:.4f}; "
        f"n = {L2['reviewer_denominator']['n_main_sd']:.0f} to {L2['reviewer_denominator']['n_all_sd']:.0f}")
    say(f"   raw-cost test of the mean on the 20/80 mixture (affected = {len(xa)} main post-cutoff A sessions, mean "
        f"${ma:.4f}, SD ${va ** .5:.4f}; unaffected = {len(xu)} control A sessions, mean ${mu:.4f}, SD ${vu ** .5:.4f}):"
        f" mixture SD ${vmix ** .5:.4f} (CV {L2['raw_cost_mixture']['mixture_cv']:.3f}); delta ${gain:.5f}; "
        f"n = {n_raw:.0f} per arm")
    say(f"   same at model calls (c = ${c_calls:.5f}, s = ${s_fixed:.4f}): delta ${gain_u:.5f}, d = "
        f"{L2['raw_cost_mixture_model_calls']['d']:.4f}, n = {L2['raw_cost_mixture_model_calls']['n_per_arm']:.0f}")
    say(f"   note: a test on log cost targets the geometric mean, whose effect here is {dlog:+.4f} (unaffected "
        f"sessions +{c_paper / mu_u:.3f}, affected {-(s_paper - c_paper) / mu_a:.3f}); n = "
        f"{L2['log_scale_mixture_note']['n_per_arm_at_main_sd']:.0f} at SD {sd_m:.3f}; the money estimand is the "
        f"arithmetic mean, so the raw-cost test is the relevant one")
    out["lesson2"] = L2

    # ---------------------------------------------------------------- imputation
    s7 = fs["S7_missing_header_imputed"]
    say("")
    say("7. Imputed f_upper (f_sessions.json S7; fsess.py cmd_analyze, deviation D3)")
    say(f"   all contexts {s7['upper_imputed']['share']} {s7['upper_imputed']['ci95']} (k = {s7['upper_imputed']['k']} "
        f"of {s7['upper_imputed']['n']}); Python-editing {s7['upper_imputed_given_py']['share']} "
        f"{s7['upper_imputed_given_py']['ci95']}; complete-case rates {s7['complete_case_rate_by_category']}; "
        f"missing-header contexts {s7['missing_by_category']}; note: {s7['note']}")
    out["imputation"] = s7

    say("")
    say("Assumptions (all stated): one model call = one cache read of the block; one 1-hour cache write per context "
        "(a lower bound for long contexts); s from the main study (17 tasks, 704-token block assumed to save as the "
        "benchmark block did); u a constant relative effect on unaffected contexts, measured on 10 control tasks; K "
        "the mean Opus-5.5-list cost of all contexts in the base; f from one developer's transcripts, per context; "
        "benchmark and transcript draws independent.")
    txt = "\n".join(L) + "\n"
    OUT_TXT.write_text(txt, encoding="utf-8")
    OUT_JSON.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(txt, end="")


if __name__ == "__main__":
    main()
