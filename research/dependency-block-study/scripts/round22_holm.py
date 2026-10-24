"""Round-22 Table 1 p-values: raw and Holm-adjusted exact sign-flip p of each study's pre-committed efficiency metric.

usage: python -I round22_holm.py <study dir>   ->   <study>/analysis/round22_holm_out.txt and <study>/analysis/round22_holm.json
(in the published data folder: RUNS_TABLES=runs python scripts/round22_holm.py data)

an internal review W4 and change 3. No model sessions; reads the de-identified per-run tables with the estimator and
the exact two-sided sign-flip test of round5_table1.py (per task the ratio of median run values; test on per-task log
ratios). Holm (step-down) adjustment within a family:
- main study: its pre-committed rule is a disjunction of four C/A metrics (failing test runs, turns, wall time,
  cost); family = those four. Failing test runs are counts with many zeros, so that metric is tested on per-task
  differences of mean failing runs (sign-flip, as the pass-rate tests).
- replication, new tasks, Sonnet 5.5: family = the study's three arm contrasts C/A, H/A, C/H on the pre-committed
  metric (the protocol's Holm family lists these three contrasts; it names pass rate, and the efficiency rules were
  scored on CIs, so this is the paper's detection convention applied to the efficiency metric).
- concurrent study: the pre-committed family C/G, C/R, G/H on total tokens (as conc_analysis.py).
- Haiku 5.5 and Qwen3-Coder (31 tasks): one pre-committed contrast, C/A, so Holm = raw.
The smallest attainable two-sided p with n non-zero per-task log ratios is 2 / 2^n (8 tasks: 0.0078).
"""
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import round5_table1 as r5  # noqa: E402


def holm(ps):
    """Holm step-down adjusted p-values, same order as ps."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * ps[i]))
        adj[i] = running
    return adj


def by_task(paths, treatment):
    by = {}
    for r in r5.load(paths):
        if not treatment(r):
            continue
        m = r5.metrics(r)
        m["wall"] = r.get("wall_s")
        m["fail_runs"] = (r.get("process") or {}).get("failing_pytest_runs")
        by.setdefault(r["task"], {}).setdefault(r["condition"], []).append(m)
    return by


def mean_diff_signflip(by, t, c, metric):
    d = []
    for task, cs in sorted(by.items()):
        a = [m[metric] for m in cs.get(t, []) if m[metric] is not None]
        b = [m[metric] for m in cs.get(c, []) if m[metric] is not None]
        if a and b:
            d.append(statistics.mean(a) - statistics.mean(b))
    # all-zero or symmetric differences make r5.signflip count both tails of a zero statistic; cap at 1
    return {"mean_diff": round(statistics.mean(d), 4), "signflip_p": min(1.0, r5.signflip(d)), "tasks": len(d),
            "tasks_nonzero": sum(abs(x) > 1e-12 for x in d)}


def family(by, contrasts, metric):
    res = [r5.contrast(by, *c.split("/"), metric) for c in contrasts]
    adj = holm([x["signflip_p"] for x in res])
    return {c: {"ratio": x["ratio"], "raw_p": x["signflip_p"], "holm_p": a, "tasks": x["tasks"]}
            for c, x, a in zip(contrasts, res, adj)}


def main():
    i1 = Path(sys.argv[1])
    rt = Path(os.environ.get("RUNS_TABLES", i1 / "runs_tables"))
    if not rt.is_absolute():
        rt = i1 / rt
    post = lambda r: r.get("stratum") == "post-cutoff"
    only = lambda conds: (lambda r: post(r) and r["condition"] in conds)
    out = {"generated_by": "scripts/round22_holm.py", "note": __doc__.split("\n\n")[1].replace("\n", " "),
           "studies": {}}
    S = out["studies"]

    # Main study: four-metric disjunction, C/A.
    by = by_task([rt / "main-2026-09-28"], only("AC"))
    main = {k: r5.contrast(by, "C", "A", k) for k in ("cost", "turns", "wall")}
    main["fail_runs"] = mean_diff_signflip(by, "C", "A", "fail_runs")
    names = ["cost", "turns", "wall", "fail_runs"]
    adj = holm([main[k]["signflip_p"] for k in names])
    S["main"] = {"family": "C/A cost, turns, wall time, failing test runs (pre-committed disjunction)",
                 **{k: {**main[k], "holm_p": a} for k, a in zip(names, adj)}}

    three = ["C/A", "H/A", "C/H"]
    for name, path, metrics in (("replication", "abl-opus55-2026-10-22", ("tokens", "cost")),
                                ("new_tasks", "tasks2-opus55-2026-10-22", ("tokens", "cost")),
                                ("sonnet55", "gen-sonnet55-2026-10-21", ("tokens",))):
        by = by_task([rt / path], only("ACH"))
        S[name] = {"family": "C/A, H/A, C/H on the pre-committed metric",
                   **{m: family(by, three, m) for m in metrics}}
    by = by_task([rt / "conc-opus55-2026-10-23"], only("ACHRG"))
    S["concurrent"] = {"family": "pre-committed C/G, C/R, G/H tokens",
                       "tokens": family(by, ["C/G", "C/R", "G/H"], "tokens")}
    by = by_task([rt / "gen-haiku55-2026-10-21"], only("AC"))
    S["haiku55"] = {"family": "C/A only", "tokens": family(by, ["C/A"], "tokens")}
    qwen_t = lambda r: (post(r) or r["task"] in r5.QWEN_EXTRA) and r["condition"] in "AC"
    by = by_task([rt / "openagent-qwen3c-main-2026-10-22", rt / "openagent-qwen3c-tasks2-2026-10-22"], qwen_t)
    S["qwen3c_AC"] = {"family": "C/A only (31 tasks)", "tokens": family(by, ["C/A"], "tokens")}
    out["min_two_sided_p"] = {"8 tasks": 2 / 2 ** 8, "17 tasks": 2 / 2 ** 17}

    (i1 / "analysis" / "round22_holm.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    lines = ["round22_holm.py: raw and Holm-adjusted exact sign-flip p of the pre-committed efficiency metric"]
    for s, v in S.items():
        lines.append(f"[{s}] family: {v['family']}")
        for k, x in v.items():
            if k == "family":
                continue
            if "raw_p" in next(iter(x.values())) if isinstance(next(iter(x.values())), dict) else False:
                for c, y in x.items():
                    lines.append(f"  {k} {c}: ratio {y['ratio']}, tasks {y['tasks']}, raw p {y['raw_p']:.4g}, "
                                 f"Holm p {y['holm_p']:.4g}")
            else:
                lines.append(f"  C/A {k}: " + ", ".join(f"{a} {b:.4g}" if isinstance(b, float) else f"{a} {b}"
                                                     for a, b in x.items()))
    lines.append(f"smallest attainable two-sided p: 8 tasks {2 / 2 ** 8:.4g}; 17 tasks {2 / 2 ** 17:.4g}; "
                 f"three-contrast Holm floor with 8 tasks {3 * 2 / 2 ** 8:.4g}")
    txt = "\n".join(lines) + "\n"
    (i1 / "analysis" / "round22_holm_out.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
