"""Build length-matched irrelevant-content notes (condition R, PROTOCOL_ADDENDUM section 11.1) from frozen notes.

usage: python make_irrelevant_notes.py <frozen_notes_dir> <donor_notes_dir> <tasks_dir> <out_dir>

For every task block in <frozen_notes_dir> (condition C):
  1. keep every line that is not a change line (header, meta line, intro, the task's own package/version lines),
     exactly as condition H does;
  2. append ONE donor package section (its "**package version** (old at the cutoff)" line and its change lines,
     verbatim) taken from <donor_notes_dir>: frozen notes made by the same tool version, for the same model and
     cutoff, for packages the task does not depend on. These are true changes, irrelevant to the task.
Donor choice (deterministic): among the distinct donor sections whose package is not the task's library or one
of its extra requirements and whose text matches none of the task's note_keys/doc_keys/answer_tokens, the one
that makes the R block's length (characters) closest to the C block's; ties -> alphabetical by section text.
Empty C blocks stay empty. Writes <out_dir>/<task>.md and a frozen MANIFEST.json in the harness format.
"""
import hashlib
import json
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

SECTION = re.compile(r"(\*\*[^\n]+\*\*[^\n]*\n(?:- [^\n]*\n)+)")

src, donor_dir, tasks_dir, out = map(Path, sys.argv[1:5])
out.mkdir(parents=True, exist_ok=True)
man = json.loads((src / "MANIFEST.json").read_text(encoding="utf-8"))
dman = json.loads((donor_dir / "MANIFEST.json").read_text(encoding="utf-8"))
assert man.get("frozen") and dman.get("frozen"), "source and donor notes must be frozen"
assert man["tool"] == dman["tool"], (man["tool"], dman["tool"])

donors: dict[str, str] = {}  # section text -> package name
for entry in dman["tasks"].values():
    text = (donor_dir / entry["file"]).read_text(encoding="utf-8")
    for sec in SECTION.findall(text):
        pkg = sec.split("**")[1].rsplit(" ", 1)[0]
        donors[sec] = pkg
donor_list = sorted(donors)


def canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def strip_changes(text: str) -> str:
    kept: list[str] = []
    for ln in text.splitlines():
        if ln.startswith("- "):
            continue
        if ln.strip() == "" and kept and kept[-1].strip() == "":
            continue
        kept.append(ln)
    return "\n".join(kept).strip() + "\n"


tasks, choices = {}, {}
for key, entry in sorted(man["tasks"].items()):
    text = (src / entry["file"]).read_text(encoding="utf-8")
    if not text.strip():
        new = ""
        choice = None
    else:
        raw = tomllib.loads((tasks_dir / key / "task.toml").read_text(encoding="utf-8"))
        own = {canon(raw["library"])} | {canon(re.split(r"[=<>!~ \[]", r)[0]) for r in raw.get("extra_requirements", [])}
        pats = [re.compile(p) for p in raw.get("note_keys", []) + raw.get("doc_keys", [])]
        toks = list(raw.get("answer_tokens", []))
        header = strip_changes(text)
        end = "<!-- since-cutoff:end -->"
        assert header.rstrip().endswith(end)
        body = header.rstrip()[: -len(end)].rstrip("\n") + "\n\n"
        best = None
        for sec in donor_list:
            if canon(donors[sec]) in own or any(p.search(sec) for p in pats) or any(t in sec for t in toks):
                continue
            cand = body + sec + end + "\n"
            score = (abs(len(cand) - len(text)), sec)
            if best is None or score < best[0]:
                best = (score, cand, sec)
        assert best is not None, key
        new, choice = best[1], best[2].splitlines()[0]
    data = new.encode("utf-8")
    (out / entry["file"]).write_bytes(data)
    tasks[key] = {"file": entry["file"], "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                  "tokens_est": round(len(new) / 4), "empty": not new.strip(), "note_keys": entry.get("note_keys"),
                  "note_keys_found": [], "coverage": 0.0 if entry.get("note_keys") else None, "covered": False,
                  "source_sha256": entry["sha256"], "source_bytes": entry["bytes"], "donor_section": choice}
    choices[key] = (choice, entry["bytes"], len(data))
manifest = {"schema": man["schema"],
            "tool": man["tool"] + " (irrelevant-content control, NAACL addendum section 11 condition R)",
            "model": man["model"], "source": str(src), "donor": str(donor_dir),
            "created_at": datetime.now(timezone.utc).isoformat(), "frozen": True,
            "frozen_at": datetime.now(timezone.utc).isoformat(), "tasks": tasks}
manifest["manifest_sha256"] = hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest()
(out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
for k, (c, b0, b1) in choices.items():
    print(f"{k}: C {b0} B -> R {b1} B; donor {c}")
print("irrelevant notes:", len(tasks), "tasks; manifest", manifest["manifest_sha256"])
