"""Export de-identified per-run tables of a study, so that the analysis scripts can be re-run without the transcripts.

usage: python -I export_runs.py <study results dir> <out dir>
Writes <out dir>/<study name>/runs.jsonl (every attempt, only the fields the analysis scripts read: task, condition,
repetition, validity, model, token usage by type, turns, wall time, grade, and the process counts) and runs.csv (one
row per attempt: the columns stale_tests.py reads plus a readable summary). No prompts, transcripts, file paths,
command lines or hashes are copied.
recompute_cost.py, pooled_old_new.py, stale_tests.py and exploration_mechanism.py accept the exported folders.
"""
import csv
import json
import sys
from pathlib import Path

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
PROCESS_KEYS = ("pytest_runs", "failing_pytest_runs", "edits_after_first_failure", "stale_in_first_edit",
                "stale_in_final", "site_packages_reads", "introspection_cmds", "context7_calls", "doc_hit",
                "network_like_cmds")
CSV_COLS = ["run_id", "attempt", "task", "stratum", "condition", "rep", "pilot", "valid", "invalid_reason", "model",
            "passed", "turns", "wall_s", "input_tokens", "output_tokens", "cache_read_input_tokens",
            "cache_creation_input_tokens", "total_tokens", "cli_cost_usd", "notes_tokens", "notes_covered",
            *PROCESS_KEYS[:-1], "started_at"]


def slim(r: dict) -> dict:
    res = r.get("result") or {}
    u = res.get("usage") or {}
    cc = u.get("cache_creation") or {}
    cfg = r.get("condition_config") or {}
    grade = r.get("grade") or {}
    proc = r.get("process") or {}
    return {
        "study_id": r.get("study_id"), "run_id": r["run_id"], "attempt": r["attempt"],
        "attempt_id": r.get("attempt_id"), "task": r["task"], "stratum": r.get("stratum"), "kind": r.get("kind"),
        "condition": r["condition"], "rep": r.get("rep"), "order_index": r.get("order_index"),
        "pilot": r.get("pilot"), "valid": r.get("valid"), "invalid_reason": r.get("invalid_reason"),
        "started_at": r.get("started_at"), "wall_s": r.get("wall_s"),
        "agent": {k: (r.get("agent") or {}).get(k) for k in ("model", "claude_code_version", "effort")},
        "condition_config": {"notes_tokens": cfg.get("notes_tokens"), "notes_covered": cfg.get("notes_covered")},
        "result": {
            "subtype": res.get("subtype"), "num_turns": res.get("num_turns"),
            "total_cost_usd": res.get("total_cost_usd"),
            "usage": {**{k: u.get(k, 0) for k in USAGE_KEYS},
                      "cache_creation": {k: cc.get(k) for k in ("ephemeral_1h_input_tokens",
                                                                "ephemeral_5m_input_tokens")}},
        },
        "grade": {k: grade.get(k) for k in ("passed", "hidden_passed", "lock_modified", "venv_modified")},
        "process": {k: proc.get(k) for k in PROCESS_KEYS},
    }


def row(s: dict) -> dict:
    u = s["result"]["usage"]
    out = {
        "run_id": s["run_id"], "attempt": s["attempt"], "task": s["task"], "stratum": s["stratum"],
        "condition": s["condition"], "rep": s["rep"], "pilot": s["pilot"], "valid": s["valid"],
        "invalid_reason": s["invalid_reason"] or "", "model": s["agent"]["model"], "passed": s["grade"]["passed"],
        "turns": s["result"]["num_turns"], "wall_s": s["wall_s"], **{k: u.get(k, 0) for k in USAGE_KEYS},
        "total_tokens": sum(u.get(k, 0) or 0 for k in USAGE_KEYS), "cli_cost_usd": s["result"]["total_cost_usd"],
        "notes_tokens": s["condition_config"]["notes_tokens"], "notes_covered": s["condition_config"]["notes_covered"],
        **{k: s["process"].get(k) for k in PROCESS_KEYS[:-1]}, "started_at": s["started_at"],
    }
    return {k: ("" if v is None else v) for k, v in out.items()}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    recs = [json.loads(line) for line in open(src / "runs.jsonl", encoding="utf-8") if line.strip()]
    dst = out / src.name
    dst.mkdir(parents=True, exist_ok=True)
    slims = [slim(r) for r in recs]
    with open(dst / "runs.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for s in slims:
            f.write(json.dumps(s, sort_keys=False) + "\n")
    with open(dst / "runs.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for s in slims:
            w.writerow(row(s))
    print("wrote", dst, len(slims), "attempts")


if __name__ == "__main__":
    main()
