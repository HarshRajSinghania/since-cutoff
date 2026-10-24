"""Exploratory mechanism analysis (not pre-registered): how much did the agent read installed package sources,
by condition, in each study?

Measure (defined in the harness before any session, bench/transcript.py):
  site_packages_reads   Read/Grep/Glob calls whose path or pattern contains .venv or site-packages
  introspection_cmds    Bash commands that call inspect.getsource/signature, help(), pydoc, __file__, dir() or name
                        site-packages / .venv
Both are taken from each valid attempt's record.json ("process"). Post-cutoff tasks only (17 tasks x 3 runs).

Statistics: the unit is the task. For each task we average the 3 runs per condition. For a contrast X-Y we report
  - the per-session means of X and Y (as in the harness report),
  - the mean over tasks of the per-task difference X-Y, with a 95% task-cluster bootstrap CI (10,000 resamples,
    seed 20261001) and an exact two-sided sign-flip test over tasks (zero differences dropped),
  - the ratio of task-averaged means X/Y with a bootstrap CI.
Everything is repeated without the pilot-exposed tasks ant01 and mcp01.

usage: python -I exploration_mechanism.py <main dir> <replication dir> <sonnet dir> <haiku dir> [--out FILE]
       (study result folders as shipped in the published data/runs/ folder or as written by the harness;
       default output ../analysis/exploration_mechanism.json)
"""
import itertools
import json
import random
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "analysis" / "exploration_mechanism.json"
STUDY_NAMES = [("main_opus55", ["A", "C"]), ("replication_opus55", ["A", "C", "H"]),
               ("sonnet55", ["A", "C", "H"]), ("haiku55", ["A", "C"])]
PILOT = {"ant01", "mcp01"}
B = 10_000
SEED = 20261001
METRICS = ["site_packages_reads", "introspection_cmds", "source_checks"]


def records(study_dir: Path):
    """Per-attempt records: the harness's runs/*/record.json if present, else runs.jsonl (same records)."""
    paths = sorted((study_dir / "runs").glob("*/record.json"))
    if paths:
        return [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    return [json.loads(line) for line in open(study_dir / "runs.jsonl", encoding="utf-8") if line.strip()]


def load(study_dir: Path):
    rows = []
    for r in records(study_dir):
        if not r.get("valid") or r.get("stratum") != "post-cutoff":
            continue
        p = r.get("process") or {}
        reads = p.get("site_packages_reads") or 0
        intro = p.get("introspection_cmds") or 0
        rows.append({"task": r["task"], "condition": r["condition"], "run_id": r["run_id"],
                     "site_packages_reads": reads, "introspection_cmds": intro, "source_checks": reads + intro})
    return rows


def per_task(rows, metric, cond, tasks):
    out = {}
    for t in tasks:
        xs = [r[metric] for r in rows if r["task"] == t and r["condition"] == cond]
        out[t] = sum(xs) / len(xs)
    return out


def signflip(diffs):
    d = [x for x in diffs if abs(x) > 1e-12]
    if not d:
        return 1.0, 0
    obs = abs(sum(d))
    n_ext = 0
    total = 0
    for signs in itertools.product((1, -1), repeat=len(d)):
        total += 1
        if abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-12:
            n_ext += 1
    return n_ext / total, len(d)


def contrast(rows, metric, x, y, tasks):
    px, py = per_task(rows, metric, x, tasks), per_task(rows, metric, y, tasks)
    diffs = [px[t] - py[t] for t in tasks]
    rng = random.Random(SEED)
    bd, br = [], []
    for _ in range(B):
        s = [rng.choice(tasks) for _ in tasks]
        mx = sum(px[t] for t in s) / len(s)
        my = sum(py[t] for t in s) / len(s)
        bd.append(mx - my)
        if my > 0:
            br.append(mx / my)
    bd.sort()
    br.sort()
    mx = sum(px.values()) / len(tasks)
    my = sum(py.values()) / len(tasks)
    p, n_nonzero = signflip(diffs)
    return {
        "mean_" + x: round(mx, 3), "mean_" + y: round(my, 3),
        "diff": round(mx - my, 3), "diff_ci": [round(bd[int(0.025 * B)], 3), round(bd[int(0.975 * B) - 1], 3)],
        "ratio": round(mx / my, 3) if my else None,
        "ratio_ci": [round(br[int(0.025 * len(br))], 3), round(br[int(0.975 * len(br)) - 1], 3)] if br else None,
        "tasks_lower": sum(1 for d in diffs if d < -1e-12), "tasks_higher": sum(1 for d in diffs if d > 1e-12),
        "signflip_p": round(p, 4), "tasks_nonzero": n_nonzero,
    }


def main():
    global OUT
    args = sys.argv[1:]
    if "--out" in args:
        i = args.index("--out"); OUT = Path(args[i + 1]); del args[i:i + 2]
    if len(args) != len(STUDY_NAMES):
        raise SystemExit(__doc__)
    STUDIES = [(name, Path(d), conds) for (name, conds), d in zip(STUDY_NAMES, args)]
    result = {"definition": __doc__.strip().splitlines()[0:9], "bootstrap": {"resamples": B, "seed": SEED},
              "studies": {}}
    for name, d, conds in STUDIES:
        rows = load(d)
        study = {"sessions": len(rows), "per_condition_session_means": {}, "contrasts": {}}
        for c in conds:
            cr = [r for r in rows if r["condition"] == c]
            study["per_condition_session_means"][c] = {
                "runs": len(cr), **{m: round(sum(r[m] for r in cr) / len(cr), 3) for m in METRICS}}
        all_tasks = sorted({r["task"] for r in rows})
        for label, tasks in (("all", all_tasks), ("without_pilot", [t for t in all_tasks if t not in PILOT])):
            study["contrasts"][label] = {}
            pairs = [("C", "A")] + ([("H", "A"), ("C", "H")] if "H" in conds else [])
            for x, y in pairs:
                study["contrasts"][label][f"{x}-{y}"] = {
                    m: contrast(rows, m, x, y, tasks) for m in METRICS}
            study["contrasts"][label]["tasks"] = len(tasks)
        result["studies"][name] = study
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for name, s in result["studies"].items():
        print(name, s["per_condition_session_means"])
        for lab in ("all", "without_pilot"):
            for k, v in s["contrasts"][lab].items():
                if k == "tasks":
                    continue
                r = v["site_packages_reads"]
                print(f"  {lab:14s} {k}: reads diff {r['diff']} {r['diff_ci']} ratio {r['ratio']} {r['ratio_ci']}"
                      f" p={r['signflip_p']} ({r['tasks_lower']} lower / {r['tasks_higher']} higher)")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
