"""Context7 sessions that received documentation, main study (Appendix D, Context7 paragraph).

usage: python context7_received.py [<main study results dir>] [--out analysis/context7_received.json]

Reads the public main-study transcripts (runs/<run_id>/stream.jsonl and record.json; default: the benchmark repository's
results/main-2026-09-28, or RUNS_RESULTS/main-2026-09-28 if RUNS_RESULTS is set). For every valid, non-pilot session of
the Context7 arms B, D and E it collects the results of all Context7 tool calls (any tool whose name contains
"context7": resolve-library-id, query-docs or get-library-docs) and counts:

  calling   the session made at least one Context7 call;
  received  at least one Context7 call returned a result that is not an error and not the quota message
            ("Monthly quota exceeded ..."), i.e. some documentation or library listing reached the agent
            (the "transcript count" of the paper: B 14/23, D 8/13, E 42/72; post-cutoff E 34);
  doc_hit   the harness's per-run flag in runs.jsonl (bench/transcript.py): documentation matching every answer-key
            pattern of the task (stricter; the per-run tables give B 7, D 3, E 32, post-cutoff E 27).

Writes the counts per arm (all tasks and post-cutoff only) and the run IDs behind each count, so the counts can be
checked against the per-run tables without the transcripts. Standard library only.
"""
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = (Path(os.environ["RUNS_RESULTS"]) / "main-2026-09-28" if "RUNS_RESULTS" in os.environ
           else Path.home() / "projects" / "since-cutoff-benchmark" / "results" / "main-2026-09-28")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return str(content)


def session(run_dir: Path):
    """Return (calling, received) for one session transcript."""
    uses, results = {}, []
    for line in open(run_dir / "stream.jsonl", encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message") if isinstance(e, dict) else None
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and "context7" in b.get("name", "").lower():
                uses[b["id"]] = b["name"]
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                results.append((bool(b.get("is_error")), text_of(b.get("content"))))
    received = any(not err and "quota" not in txt.lower() for err, txt in results)
    return bool(uses), received


def main():
    args = sys.argv[1:]
    out_path = HERE.parent / "analysis" / "context7_received.json"
    if "--out" in args:
        i = args.index("--out"); out_path = Path(args[i + 1]); del args[i:i + 2]
    root = Path(args[0]) if args else DEFAULT
    counts = defaultdict(Counter)
    ids = defaultdict(lambda: defaultdict(list))
    for rec_path in sorted(root.glob("runs/*/record.json")):
        rec = json.load(open(rec_path, encoding="utf-8"))
        if rec.get("condition") not in ("B", "D", "E") or not rec.get("valid") or rec.get("pilot"):
            continue
        calling, received = session(rec_path.parent)
        doc_hit = bool((rec.get("process") or {}).get("doc_hit"))
        post = rec.get("stratum") == "post-cutoff"
        for key, flag in (("calling", calling), ("received", received), ("doc_hit", doc_hit)):
            if flag:
                counts[rec["condition"]][key] += 1
                ids[rec["condition"]][key].append(rec["run_id"])
                if post:
                    counts[rec["condition"]][key + "_post_cutoff"] += 1
    out = {"generated_by": "scripts/context7_received.py", "study": root.name,
           "definitions": {"calling": "at least one Context7 tool call",
                           "received": "at least one Context7 call returned a non-error result other than the quota "
                                       "message (transcript count)",
                           "doc_hit": "harness per-run flag: documentation matching every answer-key pattern"},
           "counts": {c: dict(counts[c]) for c in sorted(counts)},
           "run_ids": {c: {k: sorted(v) for k, v in ids[c].items()} for c in sorted(ids)}}
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["counts"], indent=1))


if __name__ == "__main__":
    main()
