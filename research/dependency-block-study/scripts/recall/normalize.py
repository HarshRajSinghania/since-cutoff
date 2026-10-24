"""(scc2 = C2 as deployed, 30-day cutoff margin; scc2m0 = C2 with --cutoff-margin 0, the same pair as 0.4.1.)
Turn every tool's frozen output into one list of reports per (tool, library): out/norm/<tool>/<lib>.json.

Report = {rid, path, kind, param, text, paths}. `paths` holds every path the report covers (the change's own path,
its sync/async twins in `also`, its import paths). Tools: sc041 / scc2 (scan --json detector, uncapped), griffe
(find_breaking_changes, all kinds), aexpy (diff entries with rank >= Low), and the notes: sc041_cap5 / sc041_cap10 /
scc2_cap5 / scc2_cap10 (one-file project, dry-run block lines), sc041_frozen / scc2_frozen (union of the change
lines of the frozen benchmark blocks of the library's post-cutoff tasks).
"""
import json, re, sys
from pathlib import Path

W = Path(r"recall_eval"); OUT = W / "out"; NORM = OUT / "norm"
NOTES = Path(r"research/dependency-block-study\notes")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
LIBS = ["anthropic", "openai", "huggingface-hub", "mcp", "polars", "streamlit", "mistralai"]
TASKS = {"anthropic": ["ant01", "ant02", "ant03", "ant04", "ant05"], "openai": ["oai01", "oai02", "oai03"],
         "huggingface-hub": ["hf01", "hf02", "hf03", "hf04"], "mcp": ["mcp01", "mcp02", "mcp04", "mcp05", "mcp06"],
         "polars": ["pl01", "pl02", "pl03", "pl04"], "streamlit": ["st01", "st02"], "mistralai": ["mi01", "mi02"]}
ORIG = {"anthropic", "openai", "huggingface-hub", "mcp"}


def sc(tag, lib):
    p = OUT / f"sc{tag}" / f"{lib}.scan.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for i, c in enumerate(d["scan"][0]["changes"]):
        paths = [c["path"]] + [a.get("path", a) if isinstance(a, dict) else a for a in c.get("also", [])]
        paths += c.get("import_paths") or []
        if c.get("moved_to"):
            paths.append(c["moved_to"])
        text = " | ".join(str(x) for x in [c["kind"], c["path"], c.get("parameter"), c.get("old_signature"),
                                            c.get("new_signature"), c.get("moved_to"), c.get("hint"),
                                            c.get("deprecation")] if x)
        rows.append({"rid": f"{tag}-{lib}-{i:04d}", "path": c["path"], "kind": c["kind"], "param": c.get("parameter"),
                     "text": text[:700], "paths": sorted(set(paths))})
    return rows


def block_lines(text):
    return [l[1:].strip() if l.startswith("+") else l.strip() for l in text.splitlines()
            if re.match(r"^\+?- ", l)]


def notes(tag, lib, n):
    t = (OUT / f"sc{tag}" / f"{lib}.sync{n}.txt").read_text(encoding="utf-8")
    return [{"rid": f"{tag}cap{n}-{lib}-{i:02d}", "path": "", "kind": "note", "param": None, "text": l,
             "paths": re.findall(r"`([^`]+)`", l)} for i, l in enumerate(block_lines(t))]


def frozen(tag, lib):
    if tag == "041":
        folder = "sonnet-5-5" if lib in ORIG else "tasks2-opus-5-5"
    else:
        if lib in ORIG:
            return None
        folder = "tasks2-opus-5-5-v2"
    seen, rows = {}, []
    for t in TASKS[lib]:
        for l in block_lines((NOTES / folder / f"{t}.md").read_text(encoding="utf-8")):
            seen.setdefault(l, []).append(t)
    for i, (l, ts) in enumerate(seen.items()):
        rows.append({"rid": f"{tag}frozen-{lib}-{i:02d}", "path": "", "kind": "note", "param": None, "text": l,
                     "paths": re.findall(r"`([^`]+)`", l), "tasks": ts})
    return rows


def griffe_rows(lib):
    d = json.loads((OUT / "griffe" / f"{lib}.json").read_text(encoding="utf-8"))
    rows = []
    for i, c in enumerate(d["changes"]):
        param = None
        c["oneline"] = ANSI.sub("", c["oneline"])
        m = re.search(r"\(([^)]+)\)\s*:", c["oneline"])
        if c["kind"].startswith("PARAMETER") and m:
            param = m.group(1)
        rows.append({"rid": f"griffe-{lib}-{i:05d}", "path": c["path"], "kind": c["kind"], "param": param,
                     "text": re.sub(r"\[[0-9;]*m", "", c["oneline"])[:500], "paths": [c["path"]]})
    return rows


def aexpy_rows(lib):
    """AexPy diff entries with rank >= Low (30). The element path is the old (else new) entry's id; alias entries
    name the alias in data.name; parameter entries name the parameter in data.old/new/name."""
    p = OUT / "aexpy" / f"{lib}.diff.json"
    if not p.exists() or p.stat().st_size == 0:
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for i, e in enumerate(d["entries"].values()):
        rank = e.get("rank", -1)
        if rank is None or rank < 30:
            continue
        base = (e.get("old") or e.get("new") or {}).get("id", "")
        data = e.get("data") or {}
        kind = e.get("kind", "")
        path, param = base, None
        if "Alias" in kind and data.get("name"):
            path = f"{base}.{data['name']}"
        if "Parameter" in kind:
            param = data.get("old") or data.get("name") or data.get("new") or None
        rows.append({"rid": f"aexpy-{lib}-{i:05d}", "path": path, "kind": kind, "param": param,
                     "text": f"{kind} | {e.get('message', '')}"[:500], "paths": [path], "rank": rank})
    return rows


if __name__ == "__main__":
    summary = {}
    for lib in LIBS:
        for tool, fn in [("sc041", lambda l: sc("041", l)), ("scc2", lambda l: sc("c2", l)),
                         ("sc041_cap5", lambda l: notes("041", l, 5)), ("sc041_cap10", lambda l: notes("041", l, 10)),
                         ("scc2_cap5", lambda l: notes("c2", l, 5)), ("scc2_cap10", lambda l: notes("c2", l, 10)),
                         ("scc2m0", lambda l: sc("c2m0", l)),
                         ("scc2m0_cap5", lambda l: notes("c2m0", l, 5)), ("scc2m0_cap10", lambda l: notes("c2m0", l, 10)),
                         ("sc041_frozen", lambda l: frozen("041", l)), ("scc2_frozen", lambda l: frozen("c2", l)),
                         ("griffe", griffe_rows), ("aexpy", aexpy_rows)]:
            try:
                rows = fn(lib)
            except (FileNotFoundError, json.JSONDecodeError):
                rows = None
            if rows is None:
                summary[f"{tool}/{lib}"] = None
                continue
            (NORM / tool).mkdir(parents=True, exist_ok=True)
            json.dump(rows, open(NORM / tool / f"{lib}.json", "w", encoding="utf-8"), indent=0)
            summary[f"{tool}/{lib}"] = len(rows)
    json.dump(summary, open(NORM / "summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=0))
