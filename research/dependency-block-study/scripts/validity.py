"""One-line validity summary of a study (or --count-valid: number of planned runs with a valid record)."""
import collections
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
recs = [json.loads(l) for l in open(d / "runs.jsonl", encoding="utf-8")] if (d / "runs.jsonl").exists() else []
valid_runs = {r["run_id"] for r in recs if r.get("valid")}
if "--count-valid" in sys.argv:
    print(len(valid_runs)); sys.exit(0)
inv = collections.Counter(r.get("invalid_reason") for r in recs if not r.get("valid"))
v = [r for r in recs if r.get("valid")]
sub = collections.Counter((r.get("result") or {}).get("subtype") for r in v)
timeouts = sum(1 for r in v if (r.get("exit") or {}).get("timed_out"))
net = sum(1 for r in v if ((r.get("process") or {}).get("network_like_cmds") or 0) > 0)
passed = collections.Counter(r["condition"] for r in v if (r.get("grade") or {}).get("passed"))
by = collections.Counter(r["condition"] for r in v)
print(f"records={len(recs)} valid={len(v)} invalid={dict(inv)} subtypes={dict(sub)} timeouts={timeouts} "
      f"network_like_runs={net} passed={ {c: f'{passed[c]}/{by[c]}' for c in sorted(by)} }")
