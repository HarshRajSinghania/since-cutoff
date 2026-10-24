"""Benchmark turns vs model API calls (round 21, verifier row 11).

The paper's benchmark-length t = 16.6 is the mean over the main study's 17 post-cutoff tasks of the mean CLI
`num_turns` of Notes (C) sessions (scripts/blocksize_breakeven.py, analysis/exposure2_breakeven.json). The per-context
t = 45.3 of scripts/context_cost.py counts distinct assistant message ids with a real model id, i.e. model API calls.
This script counts the benchmark sessions' API calls the same way, from each run's stream.jsonl, so the two can be
compared, and reports how num_turns relates to API calls.

usage: python -I scripts/turns_vs_calls.py   ->   prints aggregates; also written to scripts/turns_vs_calls_out.txt

Run selection is blocksize_breakeven.load(): valid, non-pilot, first attempt per run_id, from I1/runs_tables. Stream
logs: BENCH/results/main-2026-09-28/runs/<run_id>/stream.jsonl (public) and RUNS/results/<study>/runs/<run_id>/.
Counts only; no transcript content is printed.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
I1 = HERE.parent
RT = I1 / "runs_tables"
BENCH = Path(os.path.expanduser("~")) / "projects" / "since-cutoff-benchmark" / "results"
RUNS = Path("since_cutoff_runs/results")
OUT = HERE / "turns_vs_calls_out.txt"
sys.path.insert(0, str(HERE))
from recompute_cost import PRICES  # noqa: E402

P_R, P_W = PRICES["claude-opus-5-5"][2], PRICES["claude-opus-5-5"][3]
BLOCK, S_MAIN = 704, 0.08724311764705882   # analysis/exposure2_breakeven.json (main study)
K = 0.1717
STUDIES = {"main": "main-2026-09-28", "replication": "abl-opus55-2026-10-22", "new_tasks": "tasks2-opus55-2026-10-22"}


def load(study):
    recs = [json.loads(l) for l in open(RT / study / "runs.jsonl", encoding="utf-8")]
    recs = [r for r in recs if r.get("valid") and not r.get("pilot")]
    seen, out = set(), []
    for r in sorted(recs, key=lambda r: (r["run_id"], r["attempt"])):
        if r["run_id"] not in seen:
            seen.add(r["run_id"]); out.append(r)
    return out


def stream_path(study, run_id):
    for base in (BENCH, RUNS):
        p = base / study / "runs" / run_id / "stream.jsonl"
        if p.exists():
            return p
    return None


def count(path):
    ids, tool_results, num_turns = set(), 0, None
    for line in open(path, encoding="utf-8"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        if t == "assistant":
            m = d.get("message") or {}
            if m.get("id") and m.get("model") and m.get("model") != "<synthetic>":
                ids.add(m["id"])
        elif t == "user":
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
                tool_results += 1
        elif t == "result":
            num_turns = d.get("num_turns")
    return len(ids), tool_results, num_turns


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def main():
    lines = ["turns_vs_calls.py: CLI num_turns vs model API calls (distinct assistant message ids) in benchmark sessions"]
    pooled = {}
    for key, study in STUDIES.items():
        per = defaultdict(lambda: defaultdict(list))
        missing = mismatch_runs = eq_tr1 = n = 0
        for r in load(study):
            p = stream_path(study, r["run_id"])
            if p is None:
                missing += 1; continue
            calls, trs, nt_stream = count(p)
            nt = (r.get("result") or {}).get("num_turns") or 0
            n += 1
            mismatch_runs += nt_stream is not None and nt_stream != nt
            eq_tr1 += nt == trs + 1
            per[(r["stratum"] == "post-cutoff", r["task"])][r["condition"]].append((nt, calls))
        lines.append(f"\n[{key}] {study}: runs with stream {n}, missing {missing}; stream num_turns != runs.jsonl "
                     f"{mismatch_runs}; num_turns == tool-result messages + 1 in {eq_tr1}/{n}")
        for cond in ("C", "A"):
            tasks = [k for k in per if k[0] and per[k].get(cond)]
            if not tasks:
                continue
            nt = mean(mean(x[0] for x in per[k][cond]) for k in tasks)
            ca = mean(mean(x[1] for x in per[k][cond]) for k in tasks)
            lines.append(f"  post-cutoff {cond}: {len(tasks)} tasks; mean of task means: num_turns {nt:.2f}, "
                         f"API calls {ca:.2f}, ratio calls/num_turns {ca / nt:.3f}")
            if cond == "C":
                pooled[key] = (nt, ca)
    nt, ca = pooled["main"]
    c_nt = BLOCK * (nt * P_R + P_W) / 1e6
    c_ca = BLOCK * (ca * P_R + P_W) / 1e6
    lines.append("\nBlock cost at benchmark length (704 tokens, Opus 5.5 prices; s and K unchanged):")
    lines.append(f"  t = num_turns {nt:.2f}: c = ${c_nt:.5f}, f* (u = 0) = {c_nt / S_MAIN:.4f}, c/K = {c_nt / K:.4f}")
    lines.append(f"  t = API calls {ca:.2f}: c = ${c_ca:.5f}, f* (u = 0) = {c_ca / S_MAIN:.4f}, c/K = {c_ca / K:.4f}")
    lines.append("  (s also contains the benchmark block's own cost computed with num_turns; counting calls would lower "
                 "it slightly, so f* at calls is approximate)")
    txt = "\n".join(lines)
    print(txt)
    OUT.write_text(txt + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
