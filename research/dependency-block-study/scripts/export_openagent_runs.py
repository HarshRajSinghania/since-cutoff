"""Export de-identified per-run tables of an open-model study (record schema openagent-run@1).

usage: python -I export_openagent_runs.py <study results dir> <out dir>
Reads <study>/runs/*/record.json and writes, under <out dir>/<study name>/:
  runs/<run_id>/record.json  one slim record per session, in the layout openagent_analyze.py reads, so the
                             registered analysis script runs unchanged on the exported folders;
  runs.jsonl                 the same slim records, one per line;
  runs.csv                   one readable row per session.
Only the fields the analysis reads are kept (task, stratum, condition, repetition, validity, exit status, calls,
tokens, wall time, pass, first-edit staleness as a flag, stale in final diff, notes size and coverage). No prompts,
trajectories, diffs, file names, command lines, server addresses or hashes are copied.
"""
import csv
import json
import sys
from pathlib import Path

CSV_COLS = ["run_id", "attempt", "task", "stratum", "condition", "rep", "pilot", "valid", "invalid_reason", "exit",
            "passed", "visible_passed", "turns", "commands", "input_tokens", "output_tokens", "total_tokens",
            "wall_s", "first_edit", "stale_in_first_edit", "stale_in_final", "notes_tokens", "notes_covered"]


def slim(r: dict) -> dict:
    pr = r.get("process") or {}
    fe = pr.get("first_edit")
    ag = r.get("agent") or {}
    cfg = r.get("condition_config") or {}
    grade = r.get("grade") or {}
    return {
        "schema": r.get("schema"), "study_id": r.get("study_id"), "run_id": r["run_id"], "attempt": r.get("attempt"),
        "attempt_id": r.get("attempt_id"), "task": r["task"], "library": r.get("library"),
        "stratum": r.get("stratum"), "kind": r.get("kind"), "condition": r["condition"], "rep": r["rep"],
        "block_id": r.get("block_id"), "order_index": r.get("order_index"), "pilot": r.get("pilot"),
        "condition_config": {"notes_tokens": cfg.get("notes_tokens"), "notes_covered": cfg.get("notes_covered")},
        "agent": {k: ag.get(k) for k in ("scaffold", "step_limit", "textbased", "wall_limit_s", "temperature",
                                         "command_timeout_s")},
        "wall_s": r.get("wall_s"),
        "exit": {"status": (r.get("exit") or {}).get("status")},
        "process": {
            **{k: pr.get(k) for k in ("turns", "commands", "calls", "input_tokens", "output_tokens",
                                      "total_tokens", "stale_in_first_edit", "stale_in_final")},
            "first_edit": None if not fe else {"command_index": fe.get("command_index"),
                                               "stale": bool(fe.get("stale"))},
        },
        "valid": r.get("valid"), "invalid_reason": r.get("invalid_reason"),
        "grade": {k: grade.get(k) for k in ("passed", "hidden_passed", "visible_passed", "lock_modified")},
    }


def row(s: dict) -> dict:
    pr, g = s["process"], s["grade"]
    fe = pr["first_edit"]
    out = {
        "run_id": s["run_id"], "attempt": s["attempt"], "task": s["task"], "stratum": s["stratum"],
        "condition": s["condition"], "rep": s["rep"], "pilot": s["pilot"], "valid": s["valid"],
        "invalid_reason": s["invalid_reason"] or "", "exit": s["exit"]["status"], "passed": g["passed"],
        "visible_passed": g["visible_passed"], "turns": pr["turns"], "commands": pr["commands"],
        "input_tokens": pr["input_tokens"], "output_tokens": pr["output_tokens"], "total_tokens": pr["total_tokens"],
        "wall_s": s["wall_s"], "first_edit": "" if fe is None else ("stale" if fe["stale"] else "clean"),
        "stale_in_first_edit": pr["stale_in_first_edit"], "stale_in_final": pr["stale_in_final"],
        "notes_tokens": s["condition_config"]["notes_tokens"], "notes_covered": s["condition_config"]["notes_covered"],
    }
    return {k: ("" if v is None else v) for k, v in out.items()}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(src.glob("runs/*/record.json"))]
    if any(r.get("schema", "").split("/")[-1] != "openagent-run@1" for r in recs):
        raise SystemExit("not an openagent-run@1 study")
    dst = out / src.name
    dst.mkdir(parents=True, exist_ok=True)
    slims = [slim(r) for r in recs]
    for s in slims:
        d = dst / "runs" / s["run_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "record.json").write_text(json.dumps(s, indent=1) + "\n", encoding="utf-8", newline="\n")
    with open(dst / "runs.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for s in slims:
            f.write(json.dumps(s) + "\n")
    with open(dst / "runs.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for s in slims:
            w.writerow(row(s))
    print(f"{src.name}: {len(slims)} records -> {dst}")


if __name__ == "__main__":
    main()
