"""Build header-only notes (condition H) from a frozen notes directory: drop every change line ("- ..." bullets).

usage: python make_header_notes.py <frozen_notes_dir> <out_dir>
Writes <out_dir>/<task>.md and a MANIFEST.json in the harness format (frozen), so the harness verifies hashes.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
man = json.loads((src / "MANIFEST.json").read_text(encoding="utf-8"))
assert man.get("frozen"), "source notes are not frozen"
tasks = {}
for key, entry in sorted(man["tasks"].items()):
    text = (src / entry["file"]).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.startswith("- ")]
    # collapse blank lines left behind
    kept: list[str] = []
    for ln in lines:
        if ln.strip() == "" and kept and kept[-1].strip() == "":
            continue
        kept.append(ln)
    new = ("\n".join(kept).strip() + "\n") if text.strip() else ""
    data = new.encode("utf-8")
    (out / entry["file"]).write_bytes(data)
    tasks[key] = {"file": entry["file"], "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                  "tokens_est": round(len(new) / 4), "empty": not new.strip(), "note_keys": entry.get("note_keys"),
                  "note_keys_found": [], "coverage": 0.0 if entry.get("note_keys") else None, "covered": False,
                  "source_sha256": entry["sha256"]}
manifest = {"schema": man["schema"], "tool": man["tool"] + " (header-only, NAACL addendum condition H)",
            "model": man["model"], "source": str(src), "created_at": datetime.now(timezone.utc).isoformat(),
            "frozen": True, "frozen_at": datetime.now(timezone.utc).isoformat(), "tasks": tasks}
manifest["manifest_sha256"] = hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest()
(out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
print("header notes:", len(tasks), "tasks; manifest", manifest["manifest_sha256"],
      "; mean tokens", round(sum(t["tokens_est"] for t in tasks.values() if not t["empty"]) /
                             max(1, sum(1 for t in tasks.values() if not t["empty"])), 1))
