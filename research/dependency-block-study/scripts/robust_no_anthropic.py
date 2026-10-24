"""Robustness without the evaluated vendor's own SDK (requested in an internal review). Existing run tables only.

usage: python robust_no_anthropic.py          -> writes I1/analysis/robust_no_anthropic.json
env:   RUNS_TABLES (default I1/runs_tables), BENCH_TASKS (default ~/projects/since-cutoff-benchmark/bench/tasks),
       TASKS2 (default since_cutoff_tasks2).

Anthropic-SDK tasks are found from task.toml (`library = "anthropic"`) and checked against each task repo's
pyproject.toml (dependency `anthropic`). Task sets: all; without the anthropic tasks; without the anthropic tasks and
the pilot-exposed tasks (ant01, mcp01; ant01 is both); without the pilot tasks only (reference, as in the paper);
and the anthropic tasks alone (descriptive; 5 tasks, smallest possible two-sided sign-flip p = 0.0625).
Studies (Opus 5.5, post-cutoff stratum): main (C/A), replication (C/A, H/A, C/H), new tasks (no anthropic task; shown
for completeness), pooled main + new (C/A), pooled replication + new (C/A, H/A, C/H).
Per pair, the paper's estimators via token_breakdown.analyse_pair (so the all-task numbers reproduce section 0.12
exactly): geometric mean over tasks of per-task median ratios (total tokens, list cost, turns) with the 95% task
bootstrap (10,000, seed 20261001); cost per solved task (total list cost / passed sessions) with a task bootstrap;
mean list-cost saving per session (task-averaged session means). Exact two-sided sign-flip p over the per-task log
median ratios (round3_stats.signflip, full enumeration). Unadjusted p-values.
"""
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from token_breakdown import analyse_pair, load_runs, session  # noqa: E402
from round3_stats import signflip  # noqa: E402

RT = Path(os.environ.get("RUNS_TABLES", HERE.parent / "runs_tables"))
BENCH_TASKS = Path(os.environ.get("BENCH_TASKS", Path.home() / "projects" / "since-cutoff-benchmark" / "bench" / "tasks"))
TASKS2 = Path(os.environ.get("TASKS2", "since_cutoff_tasks2"))
OUT = HERE.parent / "analysis" / "robust_no_anthropic.json"
PILOT = {"ant01", "mcp01"}


def anthropic_tasks():
    lib, dep = {}, {}
    for root in (BENCH_TASKS, TASKS2):
        for toml in sorted(root.glob("*/task.toml")):
            t = toml.parent.name
            m = re.search(r'^library\s*=\s*"([^"]+)"', toml.read_text(encoding="utf-8"), re.M)
            lib[t] = m.group(1) if m else None
            pp = toml.parent / "repo" / "pyproject.toml"
            dep[t] = bool(pp.exists() and re.search(r'["\']anthropic[\s=<>~!\[\]"\']', pp.read_text(encoding="utf-8")))
    by_lib = sorted(t for t, l in lib.items() if l == "anthropic")
    by_dep = sorted(t for t, d in dep.items() if d)
    return by_lib, by_dep, lib


def collect(studies, pairs_conds):
    per_task = defaultdict(lambda: defaultdict(list))
    src = {}
    for st in studies:
        for r in load_runs(RT / st):
            if r["stratum"] != "post-cutoff" or r["condition"] not in pairs_conds:
                continue
            assert src.setdefault(r["task"], st) == st, f"task {r['task']} in two studies"
            per_task[r["task"]][r["condition"]].append(session(r))
    return per_task


def signflip_metric(rows, treat, ctrl, metric):
    lr = []
    for t, cs in rows.items():
        a = [s[metric] for s in cs.get(treat, []) if s[metric]]
        b = [s[metric] for s in cs.get(ctrl, []) if s[metric]]
        if a and b:
            lr.append(math.log(statistics.median(a) / statistics.median(b)))
    p, n = signflip(lr)
    return {"p": p, "tasks": n, "below_1": sum(v < 0 for v in lr)}


def summarise(per_task, treat, ctrl, exclude):
    rows = {t: cs for t, cs in per_task.items() if t not in exclude and cs.get(treat) and cs.get(ctrl)}
    res = analyse_pair(rows, treat, ctrl, notes_pair=False)
    r = res["ratios"]; cps = res["cost_per_solved"]
    ss = res["saving_shares"]["mean_cost_saving_per_session_usd"]
    out = {"tasks": res["tasks"], "task_ids": res["task_ids"],
           "sessions": res["runs"],
           "pass": {c: f"{cps[c]['passed']}/{cps[c]['sessions']}" for c in (ctrl, treat)},
           "tokens": r["total"], "list_cost": r["list_cost_usd"], "turns": r["turns"],
           "signflip_tokens": signflip_metric(rows, treat, ctrl, "total"),
           "signflip_cost": signflip_metric(rows, treat, ctrl, "list_cost_usd"),
           "cost_per_solved": {ctrl: cps[ctrl]["usd"], treat: cps[treat]["usd"], "ratio": cps["ratio"]["value"],
                               "ci95": cps["ratio"]["ci95"]},
           "mean_cost_saving_per_session_usd": {"value": ss["value"], "ci95": ss["ci95"]},
           "mean_cost_per_session_usd": {c: res["composition"][c]["mean_list_cost_usd"] for c in (ctrl, treat)}}
    return out


def fmt(x):
    return {"ratio": round(x["ratio"], 3), "ci": [round(x["lo"], 3), round(x["hi"], 3)]}


def main():
    by_lib, by_dep, lib = anthropic_tasks()
    assert by_lib == by_dep, (by_lib, by_dep)
    ANT = set(by_lib)
    sets = {"all": set(), "no_anthropic": ANT, "no_anthropic_no_pilot": ANT | PILOT, "no_pilot": PILOT}
    designs = {
        "main": (["main-2026-09-28"], ["C/A"], "Opus main study, 17 post-cutoff tasks (registered primary: cost)"),
        "replication": (["abl-opus55-2026-10-22"], ["C/A", "H/A", "C/H"],
                        "Opus replication/placebo ablation, same 17 tasks 24 days later (registered primary: tokens)"),
        "new_tasks": (["tasks2-opus55-2026-10-22"], ["C/A", "H/A", "C/H"],
                      "Opus new tasks (8; polars, streamlit, mistralai; no anthropic task)"),
        "pooled_main_new": (["main-2026-09-28", "tasks2-opus55-2026-10-22"], ["C/A"], "pooled main + new (25)"),
        "pooled_repl_new": (["abl-opus55-2026-10-22", "tasks2-opus55-2026-10-22"], ["C/A", "H/A", "C/H"],
                            "pooled replication + new (25)"),
    }
    out = {"generated_by": "scripts/robust_no_anthropic.py", "method": __doc__.split("Anthropic-SDK")[1].strip(),
           "anthropic_tasks": {"from_task_toml_library": by_lib, "from_repo_pyproject": by_dep,
                               "libraries_by_task": lib},
           "excluded_sets": {k: sorted(v) for k, v in sets.items()}, "studies": {}}
    compact = {}
    for key, (studies, pairs, desc) in designs.items():
        conds = {c for p in pairs for c in p.split("/")}
        pt = collect(studies, conds)
        st = out["studies"][key] = {"description": desc, "source_studies": studies, "pairs": {}}
        for pair in pairs:
            treat, ctrl = pair.split("/")
            for sname, ex in list(sets.items()) + [("anthropic_only", set(pt) - ANT)]:
                if sname == "anthropic_only" and not (set(pt) & ANT):
                    continue
                s = summarise(pt, treat, ctrl, ex)
                st["pairs"].setdefault(pair, {})[sname] = s
                compact[f"{key} {pair} [{sname}]"] = {
                    "tasks": s["tasks"], "pass": s["pass"], "tokens": fmt(s["tokens"]),
                    "p_tokens": float(f'{s["signflip_tokens"]["p"]:.3g}'), "cost": fmt(s["list_cost"]),
                    "p_cost": float(f'{s["signflip_cost"]["p"]:.3g}'), "turns": fmt(s["turns"]),
                    "cost_per_solved": [round(s["cost_per_solved"][ctrl], 3), round(s["cost_per_solved"][treat], 3),
                                        round(s["cost_per_solved"]["ratio"], 3),
                                        [round(x, 3) for x in s["cost_per_solved"]["ci95"]]],
                    "saving_per_session_usd": [round(s["mean_cost_saving_per_session_usd"]["value"], 4),
                                               [round(x, 4) for x in s["mean_cost_saving_per_session_usd"]["ci95"]]]}
        print("done", key, file=sys.stderr)
    out["compact"] = compact
    OUT.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    for k, v in compact.items():
        print(k, json.dumps(v))


if __name__ == "__main__":
    main()
