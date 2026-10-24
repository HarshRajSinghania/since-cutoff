"""Reorder a harness plan rep-major (PROTOCOL_ADDENDUM sections 13/14): all rep-1 blocks in their shuffled order, then
rep 2, then rep 3; order indices renumbered; block contents and within-block condition order unchanged. Keeps the
original as plan.orig.jsonl and notes both sha256 in plan.meta.json.
usage: python reorder_rep_major.py <study_results_dir> <section label>
"""
import hashlib
import json
import sys
from pathlib import Path

d, label = Path(sys.argv[1]), sys.argv[2]
plan = d / "plan.jsonl"
raw = plan.read_bytes()
assert not (d / "plan.orig.jsonl").exists(), "already reordered"
(d / "plan.orig.jsonl").write_bytes(raw)
rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
rows = sorted(rows, key=lambda r: (r["rep"], r["order_index"]))   # stable: block order and within-block order kept
for i, r in enumerate(rows):
    r["order_index"] = i
text = "".join(json.dumps(r) + "\n" for r in rows)
plan.write_text(text, encoding="utf-8", newline="\n")
meta_p = d / "plan.meta.json"
meta = json.loads(meta_p.read_text(encoding="utf-8"))
meta["note"] = (f"PROTOCOL_ADDENDUM {label}: blocks reordered rep-major right after `plan` (all rep-1 blocks in their "
                "shuffled order, then rep 2, then rep 3); order indices renumbered; block contents and within-block "
                f"condition order unchanged. Original plan saved as plan.orig.jsonl (sha256 "
                f"{hashlib.sha256(raw).hexdigest()}); reordered plan.jsonl sha256 "
                f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}.")
meta_p.write_text(json.dumps(meta, indent=1), encoding="utf-8", newline="\n")
print(meta["note"])
